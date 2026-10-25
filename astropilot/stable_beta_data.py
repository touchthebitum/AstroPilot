"""Prepare a version-independent private-beta store before any application writer.

Called by an owning private launcher while it holds the shared session lease.
Existing kit/production profiles are never searched, imported or merged here.
"""
import hashlib
import json
import os
import re
import secrets

from astropilot.profile_backup import BackupError, _safe_root, create_backup, profile_state, _json
from astropilot.durable_file_publication import fsync_directory

SCHEMA = 'nightmerit.stable_private_beta.v1'
MARKER = 'stockage-beta.json'
RESERVED = {MARKER, 'profil', 'SAUVEGARDES-AUTO', '.publication', '.nightmerit-session.lock',
            '.nightmerit-profile-transfer.lock'}


def _publish(path, raw, *, replace=False):
    staging = _safe_root(path.parent / '.publication')
    staging.mkdir(mode=0o700, exist_ok=True)
    temporary = staging / ('.' + path.name + '.' + secrets.token_hex(12))
    try:
        with temporary.open('xb') as stream:
            os.chmod(temporary, 0o600)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        elif os.name == 'nt':
            # Windows rename is atomic and refuses an existing destination. Do
            # not require hard-link support from the mapped Sandbox directory.
            os.rename(temporary, path)
        else:
            # POSIX rename would overwrite: publish with exclusive creation.
            os.link(temporary, path)
            temporary.unlink()
        fsync_directory(path.parent)
        fsync_directory(staging)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(directory, build, *, backup_factory=create_backup):
    if not re.fullmatch(r'[0-9a-f]{40}', build):
        raise BackupError('stable_invalid_build')
    profile = _safe_root(directory)
    root = _safe_root(profile.parent)
    if profile.name != 'profil':
        raise BackupError('stable_invalid_directory')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = _safe_root(root)
    if any(p.name not in RESERVED for p in root.iterdir()):
        raise BackupError('stable_unrecognized_directory')
    marker = root / MARKER
    for path in root.iterdir():
        # The parent owns this FileShare.None lease on Windows. Do not open or
        # stat it in the preparation child; the launcher checks it before locking.
        if path.name == '.nightmerit-session.lock':
            continue
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise BackupError('backup_unsafe_path')
        if path.name in {'profil', 'SAUVEGARDES-AUTO', '.publication'} and not path.is_dir():
            raise BackupError('stable_invalid_directory')
    state = profile_state(profile)
    if state == 'unrecognized':
        raise BackupError('stable_unrecognized_profile')
    previous = None
    if marker.exists():
        if not marker.is_file() or marker.stat().st_size > 4096:
            raise BackupError('stable_invalid_marker')
        try:
            previous = _json(marker.read_bytes())
        except (ValueError, UnicodeError) as exc:
            raise BackupError('stable_invalid_marker') from exc
        if (not isinstance(previous, dict) or previous.get('schema') != SCHEMA
                or not re.fullmatch(r'[0-9a-f]{40}', str(previous.get('last_build', '')))):
            raise BackupError('stable_incompatible_storage')
    elif state != 'empty':
        raise BackupError('stable_explicit_adoption_required')
    backup = None
    if previous and previous['last_build'] != build and state == 'profile':
        raw, summary = backup_factory(profile)
        folder = _safe_root(root / 'SAUVEGARDES-AUTO')
        folder.mkdir(mode=0o700, exist_ok=True)
        backup = folder / ('avant-mise-a-jour-' + previous['last_build'][:7]
                           + '-' + secrets.token_hex(8) + '.zip')
        _publish(backup, raw)
        # The original profile is never rewritten by this preparation.
        if hashlib.sha256(backup.read_bytes()).digest() != hashlib.sha256(raw).digest():
            raise BackupError('stable_backup_verification_failed')
    if previous is None or previous['last_build'] != build:
        _publish(marker, (json.dumps({'schema': SCHEMA, 'last_build': build})+'\n').encode(),
                 replace=previous is not None)
    return {'mode': 'stable_private_beta', 'profile_state': state,
            'backup_created': backup is not None}


def main(build):
    from astropilot.user_profile import get_user_data_dir
    try:
        result = prepare(get_user_data_dir(), build)
    except (BackupError, OSError) as exc:
        raise SystemExit('Vos données sont conservées. La préparation des données bêta '
                         'a été arrêtée avant le démarrage : ' + str(exc)) from exc
    print(json.dumps(result))
