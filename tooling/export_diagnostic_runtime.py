"""Export the exact production sources and locked Windows libraries, without user data."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

source = Path.cwd()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == 'a29513447355b05cbcceda85a10d6dc1f90da3fb'
library = source / '.venv-diagnostic/Lib/site-packages'
assert library.is_dir()
tracked = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
files = []
for name in tracked:
    if (name in ('astro_score.py', 'data/locations.json', 'data/equipment_catalog.json') or name.startswith(('astropilot/', 'decision/'))) and not name.startswith('decision/tests/'):
        path = source / name
        assert path.is_file() and not path.is_symlink()
        assert path.name not in ('user_profile.json', 'user_filters.json', '.env')
        files.append((path, 'source/' + name))
for path in library.rglob('*'):
    if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.pth', '.pyc') or path.name.startswith('__editable__') or path.name == 'direct_url.json':
        continue
    assert not path.is_symlink()
    files.append((path, 'runtime-libs/' + path.relative_to(library).as_posix()))
manifest = {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in files}
out = source / 'dist-diagnostic'
out.mkdir(exist_ok=False)
with zipfile.ZipFile(out / 'diagnostic-runtime.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
    for path, name in files:
        bundle.write(path, name)
    bundle.writestr('Manifest-runtime.json', json.dumps(manifest, indent=2))
(out / 'Runtime-provenance.json').write_text(json.dumps({
    'source_sha': 'a29513447355b05cbcceda85a10d6dc1f90da3fb',
    'uv_lock_sha256': hashlib.sha256((source / 'uv.lock').read_bytes()).hexdigest(),
    'runtime_zip_sha256': hashlib.sha256((out / 'diagnostic-runtime.zip').read_bytes()).hexdigest(),
    'files': len(files), 'profile': 'no user profile included', 'libraries': 'uv sync --locked on Windows, Python 3.13.5',
}, indent=2))
print('Exported', len(files), 'source and dependency files')
