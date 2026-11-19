"""Read-only identity of a managed local session, independent of bundle files.

Metadata is never used as a storage destination. The launcher also checks the
kit's filesystem identity and process start time before signalling a process.
"""
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import re
import stat

ENVIRONMENT_KEY = 'ASTROPILOT_LAUNCH_SESSION'
DIAGNOSTIC_ROUTES = frozenset({'/v1/launcher-context', '/v1/runtime-identity', '/v1/data-context'})
MOVED_MESSAGE = ('Cette copie a été déplacée ou son dossier est inaccessible. '
                 'Fermez-la avec ARRETER-MES-PROJETS.command depuis son dossier actuel, '
                 'puis rouvrez-la. Aucune donnée ne sera recréée à l’ancien emplacement.')


@dataclass(frozen=True)
class LaunchSession:
    session_id: str
    kit_directory: str
    data_directory: str
    kit_device: int
    kit_inode: int

    @classmethod
    def from_environment(cls):
        raw = os.environ.get(ENVIRONMENT_KEY)
        if raw is None:
            return None
        try:
            if len(raw) > 16384:
                raise ValueError()
            value = json.loads(raw)
            if set(value) != {'session_id', 'kit_directory', 'data_directory', 'kit_device', 'kit_inode'}:
                raise ValueError()
            if not isinstance(value['session_id'], str) or not re.fullmatch('[0-9a-f]{64}', value['session_id']):
                raise ValueError()
            for key in ('kit_directory', 'data_directory'):
                path = value[key]
                if (not isinstance(path, str) or len(path) > 4096 or not Path(path).is_absolute()
                    or '..' in Path(path).parts or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in path)):
                    raise ValueError()
            # No metadata may select a different storage directory.
            if value['data_directory'] != os.environ.get('ASTROPILOT_DATA_DIR'):
                raise ValueError()
            if Path(value['data_directory']).parent.parent != Path(value['kit_directory']):
                raise ValueError()
            if any(type(value[key]) is not int or value[key] < 0 for key in ('kit_device', 'kit_inode')):
                raise ValueError()
            return cls(**value)
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise ValueError('Identité du lanceur invalide ; fermer puis relancer cette copie.') from exc

    def location_status(self):
        try:
            info = os.stat(self.kit_directory, follow_symlinks=False)
            if (stat.S_ISDIR(info.st_mode)
                and (info.st_dev, info.st_ino) == (self.kit_device, self.kit_inode)):
                return 'available'
        except OSError:
            pass
        return 'moved_or_unavailable'

    def storage_scope(self):
        relative = Path(self.data_directory).relative_to(self.kit_directory).as_posix()
        return hashlib.sha256(f'{self.kit_device}:{self.kit_inode}:{relative}'.encode()).hexdigest()

    def payload(self, service):
        return {'status': 'managed', 'session_id': self.session_id, 'service': service,
                'location_status': self.location_status(), 'storage_scope': self.storage_scope()}


def blocked_response(request):
    from fastapi.responses import HTMLResponse, JSONResponse
    if request.url.path == '/':
        return HTMLResponse('<!doctype html><html lang="fr"><meta charset="utf-8">'
            '<title>NightMerit — copie déplacée</title><main><h1>Cette copie doit être rouverte</h1><p>'
            + MOVED_MESSAGE + '</p></main></html>', status_code=409, headers={'Cache-Control': 'no-store'})
    return JSONResponse({'detail': {'code': 'kit_moved_or_unavailable', 'message': MOVED_MESSAGE},
                         'message': MOVED_MESSAGE}, status_code=409, headers={'Cache-Control': 'no-store'})
