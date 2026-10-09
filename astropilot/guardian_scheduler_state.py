"""Dedicated durable Guardian scheduling watermarks; no business decisions."""
import errno
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import get_ident


class GuardianSchedulerStateError(RuntimeError):
    """State cannot safely authorize evaluation."""


class GuardianSchedulerStateLocked(RuntimeError):
    """Another owner holds the nonblocking cycle lock."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def _time(value):
    if not isinstance(value, str):
        raise ValueError('invalid_time')
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('utc_required')
    parsed = parsed.astimezone(timezone.utc)
    if parsed.isoformat() != value:
        raise ValueError('canonical_time_required')
    return parsed


class GuardianSchedulerStateStore:
    """One explicit local data directory and cadence per Guardian owner."""
    def __init__(self, data_dir):
        self.directory = Path(data_dir).expanduser().resolve() / 'guardian_scheduler'
        self.path = self.directory / 'state.json'
        self.lock_path = self.directory / '.lock'
        self._lock_owner = None

    @contextmanager
    def locked(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open('a+b') as handle:
                if os.name == 'nt':
                    import msvcrt
                    # Byte-range locks may extend beyond EOF; no file mutation is needed.
                    handle.seek(0)
                    acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    release = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))
                else:
                    import fcntl
                    acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                try:
                    acquire()
                except OSError as error:
                    if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise GuardianSchedulerStateLocked('state_locked') from error
                    raise
                try:
                    self._lock_owner = get_ident()
                    yield self
                finally:
                    self._lock_owner = None
                    release()
        except (OSError, UnicodeError) as error:
            raise GuardianSchedulerStateError('state_unavailable') from error

    def _load(self, cadence):
        identity = {'anchor': cadence.anchor.isoformat(),
                    'interval_seconds': cadence.interval // timedelta(seconds=1)}
        try:
            try:
                text = self.path.read_text(encoding='utf-8')
            except FileNotFoundError:
                return {'schema_version': 1, 'cadence': identity,
                        'last_reserved_slot': None, 'last_completed_slot': None}
            doc = json.loads(text, object_pairs_hook=_object)
            if not isinstance(doc, dict) or set(doc) != {
                    'schema_version', 'cadence', 'last_reserved_slot', 'last_completed_slot'}:
                raise ValueError('invalid_document')
            if type(doc['schema_version']) is not int or doc['schema_version'] != 1:
                raise ValueError('unsupported_schema')
            if (doc['cadence'] != identity or not isinstance(doc['cadence'], dict)
                    or type(doc['cadence'].get('interval_seconds')) is not int):
                raise ValueError('cadence_mismatch')
            reserved, completed = (None if doc[key] is None else _time(doc[key])
                                   for key in ('last_reserved_slot', 'last_completed_slot'))
            if completed is not None and (reserved is None or completed > reserved):
                raise ValueError('invalid_watermark')
            for slot in (reserved, completed):
                if slot is not None and cadence.slot(slot) != slot:
                    raise ValueError('off_cadence_slot')
            return doc
        except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as error:
            raise GuardianSchedulerStateError('state_invalid') from error

    def _write(self, doc):
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                    prefix='.state.', suffix='.tmp', delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(doc, temporary, sort_keys=True, separators=(',', ':'), allow_nan=False)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            if os.name != 'nt':
                descriptor = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except (OSError, UnicodeError, ValueError) as error:
            raise GuardianSchedulerStateError('state_write_failed') from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def claim(self, slot, cadence):
        """Caller must hold locked() through claim, cycle and completion."""
        if self._lock_owner != get_ident():
            raise GuardianSchedulerStateError('lock_required')
        if cadence.slot(slot) != slot:
            raise GuardianSchedulerStateError('invalid_slot')
        doc = self._load(cadence)
        previous = doc['last_reserved_slot']
        if previous is not None and slot <= _time(previous):
            return False
        doc['last_reserved_slot'] = slot.isoformat()
        self._write(doc)
        return True

    def complete(self, slot, cadence):
        """Complete only the currently reserved slot, under the same lock."""
        if self._lock_owner != get_ident():
            raise GuardianSchedulerStateError('lock_required')
        if cadence.slot(slot) != slot:
            raise GuardianSchedulerStateError('invalid_slot')
        doc = self._load(cadence)
        if doc['last_reserved_slot'] != slot.isoformat():
            raise GuardianSchedulerStateError('reservation_mismatch')
        doc['last_completed_slot'] = slot.isoformat()
        self._write(doc)
