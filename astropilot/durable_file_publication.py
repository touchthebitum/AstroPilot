from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from re import Pattern


def fsync_directory(directory: Path) -> None:
    """Make a previously published directory entry durable where supported."""
    if os.name == "nt":
        # Windows does not expose a portable directory handle accepted by
        # os.fsync. The hard-link remains atomic, but directory fsync is not
        # available through Python's cross-platform filesystem API.
        return

    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        primary_error = sys.exception()
        try:
            os.close(descriptor)
        except OSError:
            if primary_error is None:
                raise


def remove_temporary_file_durably(
    temporary_path: Path,
    directory: Path,
    *,
    primary_error: BaseException | None,
    synchronize_directory: Callable[[Path], None] = fsync_directory,
) -> None:
    """Remove a publication temporary and durably record that removal."""
    try:
        temporary_path.unlink(missing_ok=True)
    except OSError:
        if primary_error is None:
            raise
        return

    try:
        synchronize_directory(directory)
    except OSError:
        if primary_error is None:
            raise


def cleanup_temporary_files_durably(
    directory: Path,
    *,
    name_pattern: Pattern[str],
    primary_error: BaseException | None,
    synchronize_directory: Callable[[Path], None] = fsync_directory,
) -> None:
    """Remove only store-owned publication temporaries under a writer lock."""
    removed = False
    cleanup_error: OSError | None = None
    try:
        for candidate in directory.iterdir():
            if name_pattern.fullmatch(candidate.name) is None:
                continue
            try:
                candidate.unlink()
                removed = True
            except OSError as error:
                cleanup_error = error
                break
    except OSError as error:
        cleanup_error = error

    if removed:
        try:
            synchronize_directory(directory)
        except OSError as error:
            if cleanup_error is None:
                cleanup_error = error

    if primary_error is None and cleanup_error is not None:
        raise cleanup_error
