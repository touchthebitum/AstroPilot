"""Local signing key, initialized only while composing the application.

Raw 32-byte file; POSIX mode 0600. Windows relies on the user directory ACL.
This file is outside domain documents, fingerprints and logical history backups.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile

from astropilot.durable_file_publication import fsync_directory, remove_temporary_file_durably
from astropilot.file_lock import exclusive_file_lock
from astropilot.user_profile import get_user_data_dir


class OutcomeHistoryCursorKeyError(RuntimeError):
    """Startup cannot load or durably initialize the local signing key."""


def _load(path: Path) -> bytes:
    # Reject special files before opening, including on platforms without
    # O_NOFOLLOW/O_NONBLOCK. Only a missing initial path permits initialization.
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode):
        raise OutcomeHistoryCursorKeyError('invalid_outcome_history_cursor_key_type')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OutcomeHistoryCursorKeyError('outcome_history_cursor_key_unavailable') from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OutcomeHistoryCursorKeyError('invalid_outcome_history_cursor_key_type')
        # Check both the fd and the path after opening: the portable fallback
        # must reject a symlink swapped in after lstat, even to the same inode.
        current = path.lstat()
        if (not stat.S_ISREG(current.st_mode)
                or not os.path.samestat(expected, opened)
                or not os.path.samestat(current, opened)):
            raise OutcomeHistoryCursorKeyError('invalid_outcome_history_cursor_key_changed')
        if os.name != 'nt' and stat.S_IMODE(opened.st_mode) != 0o600:
            raise OutcomeHistoryCursorKeyError('invalid_outcome_history_cursor_key_permissions')
        key = bytearray()
        while len(key) < 33:
            chunk = os.read(descriptor, 33 - len(key))
            if not chunk:
                break
            key.extend(chunk)
        if len(key) != 32:
            raise OutcomeHistoryCursorKeyError('invalid_outcome_history_cursor_key')
        return bytes(key)
    except OSError as exc:
        raise OutcomeHistoryCursorKeyError('outcome_history_cursor_key_unavailable') from exc
    finally:
        os.close(descriptor)


def load_or_create_cursor_key(data_dir: Path | None = None) -> bytes:
    """Load a stable key or atomically publish one at first composition.

    Callers retain the returned bytes. Requests never reload or regenerate it.
    Concurrent processes coordinate through the existing application lock primitive.
    """
    directory = Path(data_dir) if data_dir is not None else get_user_data_dir()
    path = directory / '.outcome_history_cursor.key'
    temporary = None
    try:
        with exclusive_file_lock(directory / '.outcome_history_cursor.key.lock'):
            try:
                return _load(path)
            except FileNotFoundError:
                pass
            descriptor, name = tempfile.mkstemp(prefix='.outcome_history_cursor.key-', dir=directory)
            temporary = Path(name)
            with os.fdopen(descriptor, 'wb') as handle:
                if os.name != 'nt':
                    os.fchmod(handle.fileno(), 0o600)
                handle.write(secrets.token_bytes(32))
                handle.flush()
                os.fsync(handle.fileno())
            # Create-only publication; never replace an existing key.
            os.link(temporary, path)
            fsync_directory(directory)
            return _load(path)
    except OSError as exc:
        raise OutcomeHistoryCursorKeyError('outcome_history_cursor_key_unavailable') from exc
    finally:
        if temporary is not None:
            remove_temporary_file_durably(temporary, directory, primary_error=sys.exception())
