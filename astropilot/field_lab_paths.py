"""Explicit, disjoint Field Lab roots; never falls back to user storage."""
import os
import stat
from pathlib import Path

from astropilot.user_profile import get_user_data_dir, _default_user_data_dir

MARKER = ".field_lab_namespace"


def _canonical(path):
    path = Path(path).expanduser()
    if ".." in path.parts or not path.is_absolute():
        raise ValueError("field_lab_absolute_path_required_no_traversal")
    return path.resolve()


def _directory_identity(path):
    """Injectable filesystem identity; errors other than absence fail closed."""
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("field_lab_directory_required")
    return info.st_dev, info.st_ino


def _ancestry(path):
    missing = []
    current = path
    while True:
        try:
            identity = _directory_identity(current)
            break
        except FileNotFoundError:
            if current == current.parent:
                raise ValueError("field_lab_filesystem_identity_unavailable")
            missing.insert(0, current.name)
            current = current.parent
    chain = [(identity, tuple(missing))]
    while current != current.parent:
        missing.insert(0, current.name)
        current = current.parent
        chain.append((_directory_identity(current), tuple(missing)))
    return chain


def _overlaps(left, right):
    left_chain, right_chain = _ancestry(left), _ancestry(right)
    # An existing endpoint is compared to actual ancestor identities, never
    # lexical spelling. Distinct existing endpoints may differ only in case.
    for endpoint, other in ((left_chain, right_chain), (right_chain, left_chain)):
        identity, suffix = endpoint[0]
        if not suffix and any(identity == ancestor for ancestor, _ in other):
            return True
    if not left_chain[0][1] and not right_chain[0][1]:
        return False
    # Start at the deepest shared real ancestor. Unknown suffix semantics are
    # conservative: case-fold aliases are refused even on sensitive volumes.
    for identity, left_suffix in left_chain:
        for other, right_suffix in right_chain:
            if identity == other:
                if identity not in (left_chain[0][0], right_chain[0][0]):
                    # Both existing prefixes diverged into distinct real
                    # directories; no future suffix can make them ancestors.
                    return False
                a = tuple(part.casefold() for part in left_suffix)
                b = tuple(part.casefold() for part in right_suffix)
                return a == b[:len(a)] or b == a[:len(b)]
    raise ValueError("field_lab_filesystem_identity_unavailable")


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
