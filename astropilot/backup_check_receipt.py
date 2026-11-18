"""Local reminder of an actually inspected archive; never a portable profile file."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from datetime import datetime

from astropilot.durable_file_publication import fsync_directory
from astropilot.profile_backup import BackupError, _safe_root, profile_state, snapshot

NAME_PREFIX = '.nightmerit-last-backup-check-'
SCHEMA = 'nightmerit.last_backup_check.v1'
MAX_RECEIPT = 2 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode('utf-8')


def fingerprint(files):
    records = {name: {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
               for name, raw in files.items()}
    return hashlib.sha256(canonical(records)).hexdigest()


def receipt_path(root):
    # The parent is already local, explicit and free of redirection. Never mkdir here.
    root = _safe_root(root)
    name_key = hashlib.sha256(root.name.encode('utf-8')).hexdigest()
    return root.parent / (NAME_PREFIX + name_key + '.json')


def safe_entry(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_size > MAX_RECEIPT):
        raise ValueError('receipt_unavailable')
    return info


def _load(root):
    path = receipt_path(root)
    try:
        info = safe_entry(path)
    except FileNotFoundError:
        return None
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (info.st_dev, info.st_ino, info.st_size):
            raise ValueError('receipt_changed')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_RECEIPT + 1)
        if len(raw) > MAX_RECEIPT:
            raise ValueError('receipt_too_large')
    finally:
        os.close(fd)
    record = json.loads(raw)
    if not isinstance(record, dict) or set(record) != {'schema', 'payload', 'sha256'} or record['schema'] != SCHEMA:
        raise ValueError('receipt_invalid')
    payload = record['payload']
    if not isinstance(payload, dict) or set(payload) != {'filename','summary','checked_at_utc','archive_sha256','data_fingerprint'}:
        raise ValueError('receipt_invalid')
    if hashlib.sha256(canonical(payload)).hexdigest() != record['sha256']:
        raise ValueError('receipt_invalid')
    for key in ('archive_sha256', 'data_fingerprint'):
        if not isinstance(payload[key], str) or not re.fullmatch('[0-9a-f]{64}', payload[key]):
            raise ValueError('receipt_invalid')
    name = payload['filename']
    if not isinstance(name, str) or not name or len(name) > 255 or any(ord(c) < 32 for c in name) or '/' in name or '\\' in name:
        raise ValueError('receipt_invalid')
    if not isinstance(payload['summary'], dict) or not isinstance(payload['summary'].get('project_details'), list):
        raise ValueError('receipt_invalid')
    if not isinstance(payload['checked_at_utc'], str) or datetime.fromisoformat(payload['checked_at_utc']).tzinfo is None:
        raise ValueError('receipt_invalid')
    return payload


def read_status(root):
    try:
        payload = _load(root)
    except (OSError, ValueError, TypeError, RecursionError, BackupError):
        return {'state': 'unavailable', 'record': None}
    if payload is None:
        return {'state': 'none', 'record': None}
    try:
        if profile_state(root) != 'profile':
            return {'state': 'unverifiable', 'record': payload}
        current = fingerprint(snapshot(root))
    except (OSError, ValueError, TypeError, RecursionError, BackupError):
        return {'state': 'unverifiable', 'record': payload}
    return {'state': 'current' if current == payload['data_fingerprint'] else 'outdated', 'record': payload}


def remember(root, files, checked, archive_sha256):
    """Publish only a successfully inspected ZIP. Source documents stay untouched."""
    if profile_state(root) != 'profile':
        return False
    path = receipt_path(root)
    try:
        safe_entry(path)
    except FileNotFoundError:
        pass
    payload = {key: checked[key] for key in ('filename','summary','checked_at_utc')}
    payload.update(archive_sha256=archive_sha256, data_fingerprint=fingerprint(files))
    raw = canonical({'schema': SCHEMA, 'payload': payload, 'sha256': hashlib.sha256(canonical(payload)).hexdigest()})
    if len(raw) > MAX_RECEIPT:
        raise ValueError('receipt_too_large')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.last-backup-check-', delete=False) as stream:
            temporary = Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return True
