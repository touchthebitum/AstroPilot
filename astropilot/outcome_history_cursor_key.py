"""Local signing key, initialized only while composing the application.

Raw 32-byte file; POSIX mode 0600. Windows relies on the user directory ACL.
This file is outside domain documents, fingerprints and logical history backups.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import sys
import tempfile

from astropilot.durable_file_publication import fsync_directory, remove_temporary_file_durably
from astropilot.file_lock import exclusive_file_lock
from astropilot.user_profile import get_user_data_dir


class OutcomeHistoryCursorKeyError(RuntimeError):
    """Startup cannot load or durably initialize the local signing key."""


def _load(path: Path) -> bytes:
    key = path.read_bytes()
    if len(key) != 32:
        raise OutcomeHistoryCursorKeyError('invalid_outcome_history_cursor_key')
    if os.name != 'nt' and path.stat().st_mode & 0o777 != 0o600:
        raise OutcomeHistoryCursorKeyError('invalid_outcome_history_cursor_key_permissions')
    return key


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
