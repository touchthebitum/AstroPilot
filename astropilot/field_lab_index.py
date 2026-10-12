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
import struct
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


class Records:
    def __init__(self, mapped, width):
        self.mapped, self.width = mapped, width
    def __len__(self):
        return len(self.mapped)//self.width
    def __getitem__(self, position):
        return self.mapped[position*self.width:(position+1)*self.width]


class Generation:
    def __init__(self, names, stream, row_fd, offsets=None, relations=None):
        self.names, self.stream, self.row_fd = names, stream, row_fd
        self.offsets, self.relations = offsets, relations
    def __iter__(self):
        return iter((self.names, self.stream))
    def __getitem__(self, position):
        return (self.names, self.stream)[position]
    def related(self, run_id, store):
        key = hashlib.sha256(run_id.encode()).digest()
        position = bisect_left(self.relations, key+b'\0'*4)
        while position < len(self.relations):
            relation = self.relations[position]
            if relation[:32] != key:
                break
            row = struct.unpack('>I', relation[32:])[0]
            offset, length = struct.unpack('>QI', self.offsets[row])
            value = json.loads(os.pread(self.row_fd, length, offset))
            if (store._name(value['idempotency_key']) != self.names[row].hex()+'.json'
                    or value.get('forecast_run_id') != run_id
                    or value['artifact_type'] not in ('reference_comparison', 'reference_comparison_state')):
                raise ValueError('field_lab_index_invalid_relation')
            yield value


@contextmanager
def generation(store, root, max_names):
    if type(max_names) is not int or max_names < 1:
        raise ValueError('invalid_field_lab_name_limit')
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
        version = manifest.get('schema_version')
        if (type(version) is not int or version not in (1, 2) or type(count) is not int
                or not 0 <= count <= MAX_COUNT):
            raise ValueError('field_lab_index_invalid_manifest')
        if count > max_names:
            raise ValueError('field_lab_name_limit_exceeded')
        with ExitStack() as stack:
            handles = []
            sizes = [('.names', count*32), ('.rows', manifest.get('rows_bytes'))]
            if version == 2:
                related_count = manifest.get('related_count')
                if type(related_count) is not int or not 0 <= related_count <= count:
                    raise ValueError('field_lab_index_invalid_manifest')
                sizes.extend([('.offsets', count*12), ('.relations', related_count*36)])
            for suffix, size in sizes:
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
            offsets = relations = None
            if version == 2:
                offsets = Records(stack.enter_context(mmap.mmap(handles[2], 0, access=mmap.ACCESS_READ)) if count else b'', 12)
                relations = Records(stack.enter_context(mmap.mmap(handles[3], 0, access=mmap.ACCESS_READ)) if related_count else b'', 36)
                end = 0
                for i in range(count):
                    offset, length = struct.unpack('>QI', offsets[i])
                    if offset != end or not 0 < length <= MAX_ROW:
                        raise ValueError('field_lab_index_invalid_offsets')
                    end += length
                if end != manifest['rows_bytes']:
                    raise ValueError('field_lab_index_invalid_offsets')
                previous = None
                for i in range(related_count):
                    value = relations[i]
                    if ((previous is not None and value <= previous)
                            or struct.unpack('>I', value[32:])[0] >= count):
                        raise ValueError('field_lab_index_invalid_relations')
                    previous = value
            yield Generation(names, rows, handles[1], offsets, relations)
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
                        for value in rows(names, stream, store):
                            if (value['artifact_type'] in ('reference_comparison', 'reference_comparison_state')
                                    and 'forecast_run_id' not in value):
                                upgraded = envelope(store._name(value['idempotency_key']))
                                old_fields = dict(upgraded)
                                old_fields.pop('forecast_run_id', None)
                                if old_fields != value:
                                    raise ValueError('field_lab_metadata_mismatch')
                                value = upgraded
                            yield value
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
                    for key, relation, value in sorted(chunk):
                        stream.write(key.encode()+b' '+relation+b' '+value)
                runs.append(name)
                chunk.clear()

            for value in inputs():
                document = (_json(value)+'\n').encode()
                if len(document) > MAX_ROW:
                    raise ValueError('field_lab_index_row_too_large')
                relation = (hashlib.sha256(value['forecast_run_id'].encode()).hexdigest().encode()
                            if value['artifact_type'] in ('reference_comparison', 'reference_comparison_state') else b'-')
                chunk.append((store._name(value['idempotency_key'])[:64], relation, document))
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
            offsets_tmp, offsets_out = temporary()
            relations_tmp, relations_out = temporary()
            with names_out, rows_out, offsets_out, relations_out, ExitStack() as stack:
                streams = [stack.enter_context(os.fdopen(_open(fd, name), 'rb')) for name in runs]
                previous_key = None
                length, merged, related_count = 0, 0, 0
                relation_runs, relation_chunk = [], []
                def flush_relations():
                    name, stream = temporary()
                    with stream:
                        stream.write(b''.join(sorted(relation_chunk)))
                    relation_runs.append(name)
                    relation_chunk.clear()
                for line in heapq.merge(*streams):
                    key, relation, document = line.split(b' ', 2)
                    if previous_key is not None and key <= previous_key:
                        raise ValueError('field_lab_index_duplicate_identity')
                    previous_key = key
                    names_out.write(bytes.fromhex(key.decode()))
                    offsets_out.write(struct.pack('>QI', length, len(document)))
                    rows_out.write(document)
                    if relation != b'-':
                        relation_chunk.append(bytes.fromhex(relation.decode())+struct.pack('>I', merged))
                        related_count += 1
                        if len(relation_chunk) == CHUNK:
                            flush_relations()
                    length += len(document)
                    merged += 1
                    if length > MAX_BYTES:
                        raise ValueError('field_lab_index_too_large')
                if merged != count:
                    raise ValueError('field_lab_index_inventory_changed')
                if relation_chunk:
                    flush_relations()
                relation_streams = [stack.enter_context(os.fdopen(_open(fd, name), 'rb')) for name in relation_runs]
                for record in heapq.merge(*(iter(lambda stream=stream:stream.read(36), b'') for stream in relation_streams)):
                    relations_out.write(record)
                for stream in (names_out, rows_out, offsets_out, relations_out):
                    stream.flush()
                    os.fsync(stream.fileno())
                manifest = dict(schema_version=2, count=count, rows_bytes=length, related_count=related_count,
                                names_sha256=_hash(names_out.fileno()), rows_sha256=_hash(rows_out.fileno()),
                                offsets_sha256=_hash(offsets_out.fileno()), relations_sha256=_hash(relations_out.fileno()))
            for temporary_name, suffix in ((names_tmp, '.names'), (rows_tmp, '.rows'),
                                           (offsets_tmp, '.offsets'), (relations_tmp, '.relations')):
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
