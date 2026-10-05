"""Explicit, disjoint Field Lab roots; never falls back to user storage."""
import os
from pathlib import Path

from astropilot.user_profile import get_user_data_dir, _default_user_data_dir

MARKER = ".field_lab_namespace"


def _canonical(path):
    path = Path(path).expanduser()
    if ".." in path.parts or not path.is_absolute():
        raise ValueError("field_lab_absolute_path_required_no_traversal")
    return path.resolve()


def _overlaps(left, right):
    return left == right or left in right.parents or right in left.parents


def field_lab_root():
    configured = os.environ.get("FIELD_LAB_DATA_DIR")
    if not configured:
        raise ValueError("field_lab_root_required")
    lab = _canonical(configured)
    for user in (get_user_data_dir(), _default_user_data_dir()):
        if _overlaps(lab, Path(user).expanduser().resolve()):
            raise ValueError("field_lab_user_root_overlap")
    return lab


def require_user_directory(directory):
    """Reject lab storage even through an alias or after configuration removal."""
    path = Path(directory).expanduser().resolve()
    configured = os.environ.get("FIELD_LAB_DATA_DIR")
    if configured and _overlaps(path, _canonical(configured)):
        raise ValueError("field_lab_user_directory_overlap")
    if any((parent / MARKER).exists() or (parent / MARKER).is_symlink()
           for parent in (path, *path.parents)):
        raise ValueError("field_lab_user_directory_excluded")
