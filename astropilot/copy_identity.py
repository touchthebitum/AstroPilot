"""Copy provenance is launcher metadata, never inferred from weather or profile data."""
import json
import os
from pathlib import Path

COPY_KIND_ENV = 'NIGHTMERIT_COPY_KIND'
COPY_LABELS = {'personal': 'Personnel', 'fictitious': 'Essai fictif'}


def capture_copy_identity(session, *, demonstration=False):
    kind = os.environ.get(COPY_KIND_ENV) if session else None
    # Explicit runtime mode, not inferred from forecast content or restored files.
    if session is None and demonstration is True:
        return {'kind': 'demonstration', 'label': 'Essai fictif — météo simulée',
                'name': 'Démonstration locale — données fictives uniquement'}
    identified = kind in COPY_LABELS
    return {'kind': kind if identified else 'unidentified',
            'label': COPY_LABELS[kind] if identified else 'Copie non identifiée',
            'name': Path(session.kit_directory).name if session else None}


def identity_script(identity):
    # External JavaScript plus textContent avoids interpreting folder names as HTML.
    prefix = 'globalThis.NightMeritCopyIdentity=' + json.dumps(identity, ensure_ascii=True) + ';\n'
    return prefix + (Path(__file__).with_name('web') / 'copy-identity.js').read_text(encoding='utf-8')
