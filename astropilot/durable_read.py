"""Enumerate durable JSON documents without glob's silent I/O suppression."""
import os
from pathlib import Path


def json_document_paths(directory: Path) -> list[Path]:
    # Callers decide whether absence is legitimate and hold their store lock.
    # Do not turn an unreadable directory into an authoritative empty history.
    with os.scandir(directory) as entries:
        return sorted(Path(directory) / entry.name for entry in entries
                      if os.path.normcase(entry.name).endswith(os.path.normcase('.json')))
