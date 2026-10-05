"""Minimal immutable Field Lab artifacts, offline only.

Descriptor-relative operations pin each directory and refuse symlink redirection.
They do not prevent same-owner processes from relocating an opened directory;
see docs/field-lab-reference-stations.md for the local-process threat model.
Unsupported platforms fail before touching storage (same POSIX policy as History).
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import stat
import uuid
import threading
try:
    import fcntl
except ImportError:
    fcntl = None

_WRITERS = threading.local()
_PROCESS_LOCK = threading.RLock()
from astropilot.field_lab_capacity import capacity_policy


@contextmanager
def _process_writer():
    if not _PROCESS_LOCK.acquire(blocking=False):
        raise RuntimeError('field_lab_writer_busy')
    try:
        yield
    finally:
        _PROCESS_LOCK.release()

from astropilot.field_lab_paths import field_lab_root, MARKER
from decision.storage_namespace import FIELD_LAB_PROVENANCE

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_OPERATIONS = (os.open, os.mkdir, os.link, os.unlink, os.stat)
_SCANDIR = os.scandir
_MAX_BYTES = 16 * 1024 * 1024
_MARKER_DOCUMENT = '{"namespace":"field_lab_reference_station","schema_version":1}'


def _capabilities():
    supports = getattr(os, "supports_dir_fd", None)
    supports_fd = getattr(os, "supports_fd", None)
    if (type(supports_fd) not in (set, frozenset) or _SCANDIR not in supports_fd
            or os.name != "posix" or type(supports) not in (set, frozenset)
            or not all(operation in supports for operation in _OPERATIONS)
            or not all(hasattr(os, flag) for flag in
                       ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))):
        raise RuntimeError("field_lab_secure_storage_unavailable")


def _unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("field_lab_duplicate_json_field")
        value[key] = item
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class FieldLabArtifact:
    artifact_type: str
    created_at_utc: str
    source_id: str
    idempotency_key: str
    payload_json: str
    schema_version: int = 1
    provenance: str = FIELD_LAB_PROVENANCE
    namespace: str = FIELD_LAB_PROVENANCE
    calibration_eligible: bool = False

    def __post_init__(self):
        if (type(self.schema_version) is not int or self.schema_version != 1
                or self.provenance != FIELD_LAB_PROVENANCE
                or self.namespace != FIELD_LAB_PROVENANCE
                or self.calibration_eligible is not False):
            raise ValueError("invalid_field_lab_domain")
        for value in (self.artifact_type, self.source_id, self.idempotency_key):
            if not isinstance(value, str) or _ID.fullmatch(value) is None:
                raise ValueError("invalid_field_lab_identity")
        stamp = datetime.fromisoformat(self.created_at_utc)
        if stamp.tzinfo is None or stamp.utcoffset() != timezone.utc.utcoffset(stamp):
            raise ValueError("field_lab_utc_required")
        payload = json.loads(self.payload_json, object_pairs_hook=_unique_fields)
        if not isinstance(payload, dict):
            raise ValueError("field_lab_payload_object_required")
        object.__setattr__(self, "payload_json", _json(payload))

    @classmethod
    def create(cls, *, artifact_type, source_id, idempotency_key, payload,
               created_at_utc):
        return cls(artifact_type, created_at_utc, source_id, idempotency_key, _json(payload))

    @property
    def digest(self):
        return hashlib.sha256(self.payload_json.encode()).hexdigest()

    def document(self):
        return _json(dict(artifact_type=self.artifact_type, schema_version=self.schema_version,
                         provenance=self.provenance, namespace=self.namespace,
                         calibration_eligible=False, created_at_utc=self.created_at_utc,
                         source_id=self.source_id, idempotency_key=self.idempotency_key,
                         payload=json.loads(self.payload_json, object_pairs_hook=_unique_fields), digest=self.digest))

    @classmethod
    def decode(cls, document):
        value = json.loads(document, object_pairs_hook=_unique_fields)
        fields = {"artifact_type", "schema_version", "provenance", "namespace",
                  "calibration_eligible", "created_at_utc", "source_id",
                  "idempotency_key", "payload", "digest"}
        if type(value) is not dict or set(value) != fields:
            raise ValueError("invalid_field_lab_document")
        digest = value.pop("digest")
        value["payload_json"] = _json(value.pop("payload"))
        artifact = cls(**value)
        if artifact.digest != digest:
            raise ValueError("field_lab_digest_mismatch")
        return artifact


class FileFieldLabStore:
    def __init__(self):
        _capabilities()
        self._root = field_lab_root()

    @contextmanager
    def _directory(self, *, create=False, root_only=False):
        _capabilities()
        if field_lab_root() != self._root:
            raise ValueError("field_lab_configuration_changed")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self._root.anchor, flags)
        try:
            for part in self._root.parts[1:]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            if create:
                try:
                    marker = self._read(fd, MARKER)
                except FileNotFoundError:
                    with os.scandir(fd) as entries:
                        if next(entries, None) is not None:
                            raise ValueError("field_lab_unmarked_root_not_empty")
                else:
                    if marker != _MARKER_DOCUMENT:
                        raise ValueError("field_lab_marker_mismatch")
                self._publish(fd, MARKER, _MARKER_DOCUMENT)
                try:
                    os.mkdir("artifacts", mode=0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            else:
                try:
                    marker = self._read(fd, MARKER)
                except FileNotFoundError as error:
                    raise ValueError("field_lab_marker_missing") from error
                if marker != _MARKER_DOCUMENT:
                    raise ValueError("field_lab_marker_mismatch")
            if root_only:
                yield fd
                return
            child = os.open("artifacts", flags, dir_fd=fd)
            os.close(fd)
            fd = child
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def _name(key):
        if not isinstance(key, str) or _ID.fullmatch(key) is None:
            raise ValueError("invalid_field_lab_identity")
        return hashlib.sha256(key.encode()).hexdigest() + ".json"

    @staticmethod
    def _read(fd, name):
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(handle, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("field_lab_regular_file_required")
            document = stream.read(_MAX_BYTES + 1)
        if len(document) > _MAX_BYTES:
            raise ValueError("field_lab_document_too_large")
        return document.decode("utf-8")

    @staticmethod
    def _publish(fd, name, document, *, rollback=False):
        temporary = "." + uuid.uuid4().hex + ".tmp"
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
        linked = False
        cleaned = False
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(document)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd,
                        follow_symlinks=False)
            except FileExistsError:
                if FileFieldLabStore._read(fd, name) != document:
                    raise ValueError("field_lab_immutable_conflict")
                os.fsync(fd)
                return False
            linked = True
            if rollback:
                os.unlink(temporary, dir_fd=fd)
                cleaned = True
            os.fsync(fd)
            return True
        except BaseException:
            if rollback and linked:
                os.unlink(name, dir_fd=fd)
                try:
                    os.fsync(fd)
                except OSError:
                    # Preserve the original publication failure; never claim recovery.
                    pass
            raise
        finally:
            if not cleaned:
                os.unlink(temporary, dir_fd=fd)
            # Candidate cleanup is not part of commit publication.
            if not rollback:
                os.fsync(fd)

    @contextmanager
    def writer_lock(self, *, create=False, max_names=100000):
        """One reentrant process/thread and POSIX cross-process writer boundary."""
        if fcntl is None or os.name != 'posix':
            raise RuntimeError('field_lab_secure_lock_unavailable')
        with _process_writer():
            state = getattr(_WRITERS, 'state', None)
            identity = (os.getpid(), str(self._root))
            if state is not None and state['identity'] == identity:
                yield state
                return
            if state is not None and state['identity'][0] == os.getpid():
                raise ValueError('field_lab_nested_writer_root_changed')
            with self._directory(create=create, root_only=True) as fd:
                handle = os.open('.writer.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=fd)
                try:
                    if not stat.S_ISREG(os.fstat(handle).st_mode):
                        raise ValueError('field_lab_lock_regular_file_required')
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as error:
                        raise RuntimeError('field_lab_writer_busy') from error
                    state = dict(identity=identity, count=sum(1 for _ in self.iter_metadata(max_names=max_names)),
                                 stop_at=capacity_policy(max_names)['stop_at'])
                    _WRITERS.state = state
                    try:
                        yield state
                    finally:
                        _WRITERS.state = None
                finally:
                    os.close(handle)

    @staticmethod
    def _metadata(artifact):
        payload = json.loads(artifact.payload_json)
        measurement_digest = None
        if artifact.artifact_type == 'reference_acquisition':
            from astropilot.reference_station_lab import ReferenceObservation
            measurement_digest = ReferenceObservation(**payload).measurement_digest
        times = [artifact.created_at_utc]
        if artifact.artifact_type == 'reference_forecast':
            times = [p['at'] for p in json.loads(payload['snapshot_json'])['points']] or times
        elif artifact.artifact_type in ('reference_comparison', 'reference_comparison_state'):
            times = [payload['forecast_point_at_utc']]
        elif artifact.artifact_type in ('reference_acquisition', 'reference_observation'):
            times = [payload['observed_at_utc']]
        times = [datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(timezone.utc).isoformat(timespec='microseconds') for t in times]
        return dict(point_count=len(times), artifact_type=artifact.artifact_type, source_id=artifact.source_id,
                    idempotency_key=artifact.idempotency_key, created_at_utc=artifact.created_at_utc,
                    time_min=min(times), time_max=max(times), variable=payload.get('variable'),
                    digest=artifact.digest, measurement_digest=measurement_digest,
                    prospective=payload.get('prospective'))

    def _save_metadata(self, artifact):
        with self._directory(root_only=True) as root:
            try:
                os.mkdir('metadata', mode=0o700, dir_fd=root)
                os.fsync(root)
            except FileExistsError:
                pass
            fd = os.open('metadata', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                name = self._name(artifact.idempotency_key)
                document = _json(self._metadata(artifact))
                try:
                    previous = self._read(fd, name)
                except FileNotFoundError:
                    previous = None
                if previous is not None and previous != document:
                    # Sidecars are disposable derived metadata, never scientific facts.
                    os.unlink(name, dir_fd=fd)
                self._publish(fd, name, document)
            finally:
                os.close(fd)

    def iter_metadata(self, *, max_names=100000):
        """Stream lightweight sidecars; legacy files fall back to validated envelopes.

        Missing sidecars after interruption never hide authoritative facts. Readers
        never migrate storage; a writer publishes sidecars for new artifacts.
        """
        try:
            with self._directory(root_only=True) as root:
                try:
                    meta = os.open('metadata', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
                except FileNotFoundError:
                    meta = None
                try:
                    with self._directory() as fd:
                        # Constant-memory preflight preserves fail-closed limits.
                        for _ in self._names(fd, max_names):
                            pass
                        for name in self._names(fd, max_names):
                            try:
                                value = json.loads(self._read(meta, name)) if meta is not None else None
                            except FileNotFoundError:
                                value = None
                            if value is None:
                                artifact = FieldLabArtifact.decode(self._read(fd, name))
                                value = self._metadata(artifact)
                            if self._name(value['idempotency_key']) != name:
                                raise ValueError('field_lab_identity_mismatch')
                            yield value
                finally:
                    if meta is not None:
                        os.close(meta)
        except FileNotFoundError:
            if self._root.exists():
                raise

    @staticmethod
    def _names(fd, max_names):
        if type(max_names) is not int or max_names < 1:
            raise ValueError('invalid_field_lab_name_limit')
        count = 0
        with os.scandir(fd) as entries:
            for entry in entries:
                name = entry.name
                if name.startswith('.') and name.endswith('.tmp'):
                    continue
                if re.fullmatch(r'[0-9a-f]{64}\.json', name) is None:
                    raise ValueError('field_lab_unexpected_artifact_file')
                if entry.is_symlink():
                    raise OSError('field_lab_regular_file_required')
                if not stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
                    raise ValueError('field_lab_regular_file_required')
                count += 1
                if count > max_names:
                    raise ValueError('field_lab_name_limit_exceeded')
                yield name

    def save(self, artifact):
        with self.writer_lock(create=True, max_names=2_000_000):
            return self._save(artifact)

    def _save(self, artifact):
        if type(artifact) is not FieldLabArtifact:
            raise ValueError("field_lab_artifact_required")
        document = artifact.document()
        # Revalidate the envelope at the writer boundary.
        FieldLabArtifact.decode(document)
        if len(document.encode()) > _MAX_BYTES:
            raise ValueError("field_lab_document_too_large")
        with self._directory(create=True) as fd:
            state = _WRITERS.state
            existing = self.load(idempotency_key=artifact.idempotency_key)
            if existing is None and state['count'] + 1 >= state['stop_at']:
                raise ValueError('field_lab_capacity_stop_scientific_facts_preserved')
            if artifact.artifact_type == 'reference_seal_commit':
                saved = self._publish(fd, self._name(artifact.idempotency_key), document, rollback=True)
            else:
                saved = self._publish(fd, self._name(artifact.idempotency_key), document)
            if saved:
                state['count'] += 1
        self._save_metadata(artifact)
        return saved

    def confirm_durable(self, artifact):
        """Revalidate and fsync the existing inode and pinned parent this attempt."""
        if type(artifact) is not FieldLabArtifact:
            raise ValueError("field_lab_artifact_required")
        with self._directory() as fd:
            handle = os.open(self._name(artifact.idempotency_key),
                             os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(handle, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("field_lab_regular_file_required")
                document = stream.read(_MAX_BYTES + 1)
                if len(document) > _MAX_BYTES:
                    raise ValueError("field_lab_document_too_large")
                existing = FieldLabArtifact.decode(document.decode("utf-8"))
                if existing.document() != artifact.document():
                    raise ValueError("field_lab_immutable_conflict")
                os.fsync(stream.fileno())
                os.fsync(fd)

    def load(self, *, idempotency_key):
        name = self._name(idempotency_key)
        try:
            with self._directory() as fd:
                artifact = FieldLabArtifact.decode(self._read(fd, name))
                if artifact.idempotency_key != idempotency_key:
                    raise ValueError("field_lab_identity_mismatch")
                return artifact
        except FileNotFoundError:
            return None

    def iter_artifacts(self, *, max_names=100000, artifact_type=None, station_id=None,
                       start=None, end=None, variable=None):
        """Filter metadata before decoding payloads; enumeration memory is constant."""
        start = datetime.fromisoformat(start.replace('Z', '+00:00')).isoformat(timespec='microseconds') if start else None
        end = datetime.fromisoformat(end.replace('Z', '+00:00')).isoformat(timespec='microseconds') if end else None
        for meta in self.iter_metadata(max_names=max_names):
            if artifact_type is not None and meta['artifact_type'] not in (
                    (artifact_type,) if isinstance(artifact_type, str) else artifact_type):
                continue
            if station_id is not None and meta['source_id'] != station_id:
                continue
            if variable is not None and meta['variable'] != variable:
                continue
            if start is not None and meta['time_max'] < start:
                continue
            if end is not None and meta['time_min'] > end:
                continue
            artifact = self.load(idempotency_key=meta['idempotency_key'])
            if artifact is None or artifact.digest != meta['digest'] or self._metadata(artifact) != meta:
                raise ValueError('field_lab_metadata_mismatch')
            yield artifact
