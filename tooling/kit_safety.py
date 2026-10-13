"""Local extraction and placement checks for the portable test kit."""
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile


def reject_links(path):
    for item in (Path(path).absolute(), *Path(path).absolute().parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise RuntimeError('Placez le kit dans un dossier sans lien ni jonction.')


def guard_placement(base):
    reject_links(base)
    base = Path(base).resolve()
    candidates = []
    if os.environ.get('ASTROPILOT_DATA_DIR'):
        candidates.append(Path(os.environ['ASTROPILOT_DATA_DIR']))
    for key in ('LOCALAPPDATA', 'APPDATA'):
        if os.environ.get(key):
            candidates.append(Path(os.environ[key])/'AstroPilot')
    for root in candidates:
        if base.is_relative_to(root.expanduser().resolve()):
            raise RuntimeError('Extrayez le kit hors du dossier de données AstroPilot réel.')


def safe_extract(archive, destination):
    reject_links(destination)
    destination = Path(destination)
    if destination.exists():
        raise RuntimeError('Le dossier d’extraction doit être nouveau.')
    destination.mkdir()
    seen = set()
    with zipfile.ZipFile(archive) as bundle:
        if sum(member.file_size for member in bundle.infolist()) > 2 * 1024**3:
            raise RuntimeError('Archive au-delà du plafond de 2 Go.')
        for member in bundle.infolist():
            name = member.filename
            path = PurePosixPath(name)
            mode = member.external_attr >> 16
            if ('\\' in name or ':' in name or path.is_absolute() or '..' in path.parts
                    or any(part.endswith((' ', '.')) for part in path.parts)
                    or stat.S_ISLNK(mode)):
                raise RuntimeError('Chemin ZIP invalide ou lien.')
            key = name.rstrip('/').casefold()
            if key in seen:
                raise RuntimeError('Chemin ZIP dupliqué.')
            seen.add(key)
            if not (destination/name).resolve().is_relative_to(destination.resolve()):
                raise RuntimeError('Chemin ZIP sortant.')
        if bundle.testzip() is not None:
            raise RuntimeError('Archive corrompue.')
        bundle.extractall(destination)
