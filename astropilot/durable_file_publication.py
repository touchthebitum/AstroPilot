from __future__ import annotations

import os
import sys
from pathlib import Path


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
