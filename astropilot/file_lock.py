from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import BinaryIO, Protocol

if os.name == "nt":
    import msvcrt as _msvcrt
else:
    import fcntl as _fcntl


class _WindowsLockBackend(Protocol):
    LK_LOCK: int
    LK_UNLCK: int

    def locking(self, descriptor: int, mode: int, byte_count: int) -> None: ...


_registry_guard = Lock()
_path_locks: dict[str, Lock] = {}


def _normalized_lock_path(path: Path) -> tuple[Path, str]:
    absolute = Path(path).expanduser().resolve(strict=False)
    return absolute, os.path.normcase(str(absolute))


def _thread_lock(registry_key: str) -> Lock:
    with _registry_guard:
        return _path_locks.setdefault(registry_key, Lock())


def _acquire_windows_lock(
    handle: BinaryIO,
    backend: _WindowsLockBackend,
) -> None:
    handle.seek(0)
    backend.locking(handle.fileno(), backend.LK_LOCK, 1)


def _release_windows_lock(
    handle: BinaryIO,
    backend: _WindowsLockBackend,
) -> None:
    handle.seek(0)
    backend.locking(handle.fileno(), backend.LK_UNLCK, 1)


def _acquire_os_lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        _acquire_windows_lock(handle, _msvcrt)
    else:
        _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)


def _release_os_lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        _release_windows_lock(handle, _msvcrt)
    else:
        _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)


@contextmanager
def exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    path, registry_key = _normalized_lock_path(lock_path)
    process_lock = _thread_lock(registry_key)

    with process_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            _acquire_os_lock(handle)
            try:
                yield
            finally:
                _release_os_lock(handle)
