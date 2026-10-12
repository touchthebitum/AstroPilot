"""Immutable, disposable metadata generations; scientific files remain authoritative.

Only the fixed-width name table is mapped (at most 64 MiB at the 2M ceiling).
Metadata streams sequentially. Readers check the real inventory before yielding;
new files use the legacy no-follow path, including interrupted publications.
"""
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import hashlib
import heapq
import json
import mmap
import os
import re
import stat
import time
import uuid

MAX_COUNT = 2_000_000
MAX_BYTES = 2 * 1024**3
MAX_ROW = 16_384
CHUNK = 8192
COMMIT = re.compile(r'([0-9]{20})-([0-9a-f]{32})\.commit\.json')


def _open(fd, name):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    if not stat.S_ISREG(os.fstat(handle).st_mode):
        os.close(handle)
        raise ValueError('field_lab_index_regular_file_required')
    return handle


def _hash(handle):
    os.lseek(handle, 0, os.SEEK_SET)
    value = hashlib.sha256()
    while block := os.read(handle, 1024*1024):
        value.update(block)
    os.lseek(handle, 0, os.SEEK_SET)
    return value.hexdigest()


def latest(fd):
    chosen = None
    with os.scandir(fd) as entries:
        for count, entry in enumerate(entries, 1):
            if count > 50_000:
                raise ValueError('field_lab_index_generation_limit_exceeded')
            if entry.name.startswith('.') and entry.name.endswith('.tmp'):
                continue
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                raise ValueError('field_lab_index_regular_file_required')
            if COMMIT.fullmatch(entry.name):
                chosen = max(chosen or entry.name, entry.name)
    return chosen


class Names:
    def __init__(self, mapped, count):
        self.mapped, self.count = mapped, count

    def __len__(self):
        return self.count

    def __getitem__(self, position):
        return self.mapped[position*32:(position+1)*32]

    def contains(self, name):
        key = bytes.fromhex(name[:64])
        position = bisect_left(self, key)
        return position < self.count and self[position] == key


@contextmanager
def generation(store, root, max_names):
    try:
        fd = os.open('metadata-index', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    except FileNotFoundError:
        yield None
        return
    try:
        commit = latest(fd)
        if commit is None:
            yield None
            return
        manifest = json.loads(store._read(fd, commit))
        prefix = commit.removesuffix('.commit.json')
        count = manifest.get('count')
        if (manifest.get('schema_version') != 1 or type(count) is not int
                or not 0 <= count <= MAX_COUNT):
            raise ValueError('field_lab_index_invalid_manifest')
        if count > max_names:
            raise ValueError('field_lab_name_limit_exceeded')
        with ExitStack() as stack:
            handles = []
            for suffix, size in (('.names', count*32), ('.rows', manifest.get('rows_bytes'))):
                handle = _open(fd, prefix+suffix)
                stack.callback(os.close, handle)
                if (type(size) is not int or not 0 <= size <= MAX_BYTES
                        or os.fstat(handle).st_size != size
                        or _hash(handle) != manifest.get(suffix[1:]+'_sha256')):
                    raise ValueError('field_lab_index_integrity_mismatch')
                handles.append(handle)
            mapped = stack.enter_context(mmap.mmap(handles[0], 0, access=mmap.ACCESS_READ)) if count else b''
            names = Names(mapped, count)
            previous = None
            for i in range(count):
                key = names[i]
                if previous is not None and key <= previous:
                    raise ValueError('field_lab_index_invalid_names')
                previous = key
            rows = stack.enter_context(os.fdopen(os.dup(handles[1]), 'rb'))
            yield names, rows
    finally:
        os.close(fd)


def rows(names, stream, store):
    for i in range(len(names)):
        document = stream.readline(MAX_ROW+1)
        if len(document) > MAX_ROW or not document.endswith(b'\n'):
            raise ValueError('field_lab_index_invalid_row')
        value = json.loads(document)
        if store._name(value['idempotency_key']) != names[i].hex()+'.json':
            raise ValueError('field_lab_identity_mismatch')
        yield value
    if stream.read(1):
        raise ValueError('field_lab_index_invalid_row_count')


def build(store, *, max_names, force=False, workers=1, progress=None):
    """Explicit maintenance; immutable generations and old sidecars are retained.

    A failed build publishes no commit. A force rebuild validates all envelopes;
    ordinary refreshes reuse the verified base and validate new envelopes only.
    """
    from astropilot.field_lab_store import FieldLabArtifact, _json
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError('field_lab_index_workers_1_to_8')
    with store.maintenance_lock() as root, store._directory() as artifacts:
        count = sum(1 for _ in store._names(artifacts, max_names))
        if count > MAX_COUNT:
            raise ValueError('field_lab_name_limit_exceeded')
        try:
            os.mkdir('metadata-index', mode=0o700, dir_fd=root)
            os.fsync(root)
        except FileExistsError:
            pass
        fd = os.open('metadata-index', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        scratch = []
        try:
            previous = latest(fd)
            number = max(time.time_ns(), int(previous[:20])+1 if previous else 0)
            prefix = f'{number:020d}-{uuid.uuid4().hex}'

            def temporary():
                name = '.'+uuid.uuid4().hex+'.tmp'
                handle = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                scratch.append(name)
                return name, os.fdopen(handle, 'w+b')

            def envelope(name):
                artifact = FieldLabArtifact.decode(store._read(artifacts, name))
                if store._name(artifact.idempotency_key) != name:
                    raise ValueError('field_lab_identity_mismatch')
                return store._metadata(artifact)

            def inputs():
                with generation(store, root, max_names) if not force else _absent() as cached:
                    if cached is not None:
                        names, stream = cached
                        matched = sum(names.contains(n) for n in store._names(artifacts, max_names))
                        if matched != len(names):
                            raise ValueError('field_lab_index_missing_authoritative_fact')
                        yield from rows(names, stream, store)
                    else:
                        names = None
                    pending = []
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        for name in store._names(artifacts, max_names):
                            if names is not None and names.contains(name):
                                continue
                            pending.append(name)
                            if len(pending) == 64:
                                yield from pool.map(envelope, pending)
                                pending.clear()
                        yield from pool.map(envelope, pending)

            runs, chunk, total = [], [], 0
            def flush():
                name, stream = temporary()
                with stream:
                    for key, value in sorted(chunk):
                        stream.write(key.encode()+b' '+value)
                runs.append(name)
                chunk.clear()

            for value in inputs():
                document = (_json(value)+'\n').encode()
                if len(document) > MAX_ROW:
                    raise ValueError('field_lab_index_row_too_large')
                chunk.append((store._name(value['idempotency_key'])[:64], document))
                total += 1
                if total > count:
                    raise ValueError('field_lab_index_inventory_changed')
                if len(chunk) == CHUNK:
                    flush()
                    if progress:
                        progress(total, count)
            if chunk:
                flush()
            if total != count:
                raise ValueError('field_lab_index_inventory_changed')
            names_tmp, names_out = temporary()
            rows_tmp, rows_out = temporary()
            with names_out, rows_out, ExitStack() as stack:
                streams = [stack.enter_context(os.fdopen(_open(fd, name), 'rb')) for name in runs]
                previous_key = None
                length, merged = 0, 0
                for line in heapq.merge(*streams):
                    key, document = line[:64], line[65:]
                    if previous_key is not None and key <= previous_key:
                        raise ValueError('field_lab_index_duplicate_identity')
                    previous_key = key
                    names_out.write(bytes.fromhex(key.decode()))
                    rows_out.write(document)
                    length += len(document)
                    merged += 1
                    if length > MAX_BYTES:
                        raise ValueError('field_lab_index_too_large')
                if merged != count:
                    raise ValueError('field_lab_index_inventory_changed')
                for stream in (names_out, rows_out):
                    stream.flush()
                    os.fsync(stream.fileno())
                manifest = dict(schema_version=1, count=count, rows_bytes=length,
                                names_sha256=_hash(names_out.fileno()), rows_sha256=_hash(rows_out.fileno()))
            for temporary_name, suffix in ((names_tmp, '.names'), (rows_tmp, '.rows')):
                os.link(temporary_name, prefix+suffix, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            os.fsync(fd)
            store._publish(fd, prefix+'.commit.json', _json(manifest))
            return dict(indexed_count=count, generation=prefix, rows_bytes=length)
        finally:
            try:
                for name in scratch:
                    os.unlink(name, dir_fd=fd)  # Only scratch created by this attempt.
            finally:
                os.close(fd)


@contextmanager
def _absent():
    yield None
