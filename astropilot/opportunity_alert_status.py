"""Best-effort host observations; read-only UI access, never decision authority."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from astropilot.field_lab_paths import require_user_directory

FILENAME = 'opportunity_alert_status.json'
MAX_BYTES = 16384
_FIELDS = {'schema_version', 'enabled', 'channel', 'interval_seconds', 'updated_at',
           'stopped', 'last_success_at', 'notification', 'error'}
_DELIVERY = {'DELIVERED': {'accepted_by_os'},
             'FAILED': {'invalid_payload', 'delivery_timeout', 'process_failed', 'notifier_failed'},
             'SKIPPED': {'disabled', 'unsupported_platform'}}
_ERRORS = {None, 'cycle_failed', 'scheduler_failed', 'delivery_failed', 'host_failed'}


def _time(value):
    if not isinstance(value, str):
        raise ValueError('invalid_status_time')
    at = datetime.fromisoformat(value)
    if at.utcoffset() != timedelta(0):
        raise ValueError('invalid_status_time')
    return at


def _unique(pairs):
    doc = {}
    for key, value in pairs:
        if key in doc:
            raise ValueError('duplicate_status_key')
        doc[key] = value
    return doc


def _validate(doc):
    if (type(doc) is not dict or set(doc) != _FIELDS
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1
            or type(doc['enabled']) is not bool or type(doc['stopped']) is not bool
            or doc['channel'] not in ('disabled', 'macos', 'windows')
            or type(doc['interval_seconds']) is not int or doc['interval_seconds'] <= 0
            or doc['error'] not in _ERRORS):
        raise ValueError('invalid_status')
    updated = _time(doc['updated_at'])
    if doc['last_success_at'] is not None and _time(doc['last_success_at']) > updated:
        raise ValueError('invalid_status_order')
    notification = doc['notification']
    if notification is not None:
        if (type(notification) is not dict or set(notification) != {'at', 'status', 'reason'}
                or notification['status'] not in _DELIVERY
                or notification['reason'] not in _DELIVERY[notification['status']]
                or _time(notification['at']) > updated):
            raise ValueError('invalid_status_notification')
    return doc


def _load(directory):
    directory = Path(directory).expanduser().resolve()
    require_user_directory(directory)
    path = directory / FILENAME
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        raise ValueError('invalid_status_file')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
            raise ValueError('status_file_changed')
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('status_file_limit')
    return _validate(json.loads(raw, object_pairs_hook=_unique))


def read_status(directory, *, now=None):
    """Read one atomic observation, never create storage or probe live processes."""
    try:
        doc = _load(directory)
        now = datetime.now(timezone.utc) if now is None else now
        if now.utcoffset() is None:
            raise ValueError('aware_status_clock_required')
        age = (now - _time(doc['updated_at'])).total_seconds()
        if age < 0:
            raise ValueError('future_status')
        state = ('stale' if age > max(120, 2 * doc['interval_seconds']) else
                 'stopped' if doc['stopped'] else 'recent_activity')
        return dict(doc, state=state)
    except FileNotFoundError:
        return {'state': 'unknown'}
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {'state': 'unavailable'}


class StatusObserver:
    def __init__(self, directory, *, clock=None):
        self.directory = Path(directory)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.doc = None

    def start(self, *, enabled, channel, interval_seconds):
        try:
            previous = _load(self.directory)
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            previous = {}
        self.doc = dict(schema_version=1, enabled=enabled, channel=channel,
                        interval_seconds=interval_seconds, updated_at=self.clock().isoformat(),
                        stopped=False, last_success_at=previous.get('last_success_at'),
                        notification=previous.get('notification'), error=previous.get('error'))
        self._save()

    def record(self, event):
        if self.doc is None:
            return
        at = self.clock().isoformat()
        self.doc['updated_at'] = at
        if event['event'] == 'cycle':
            if event['status'] == 'ERROR':
                self.doc['error'] = 'scheduler_failed'
            elif event['cycle_status'] == 'ERROR':
                self.doc['error'] = 'cycle_failed'
            elif event['status'] == 'COMPLETED' and event['cycle_status'] in ('NO_ALERT', 'ALERT_EMITTED'):
                self.doc['last_success_at'] = at
                if self.doc['error'] != 'delivery_failed':
                    self.doc['error'] = None
        elif event['event'] == 'notification':
            self.doc['notification'] = dict(at=at, status=event['status'], reason=event['reason'])
            if event['status'] == 'FAILED':
                self.doc['error'] = 'delivery_failed'
            elif self.doc['error'] == 'delivery_failed':
                self.doc['error'] = None
        elif event['event'] == 'shutdown':
            self.doc['stopped'] = True
        elif event['event'] == 'error':
            self.doc['error'] = 'host_failed'
        else:
            return
        self._save()

    def _save(self):
        try:
            self._publish()
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            print('opportunity_alert_status_unavailable', file=sys.stderr, flush=True)

    def _publish(self):
        _validate(self.doc)
        directory = self.directory.expanduser().resolve()
        require_user_directory(directory)
        path = directory / FILENAME
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('invalid_status_destination')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                    prefix='.opportunity_alert_status.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(self.doc, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
