"""Reference hashing shared by the read-only diagnostic coordinator."""
import hashlib
import os
from pathlib import Path


def snapshot(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise RuntimeError('Lien ou jonction dans la référence : arrêt sans copie.')
        for name in files:
            path = Path(directory) / name
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result
