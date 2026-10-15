"""Verify public predecessor assets and official candidate bytes before execution."""
from pathlib import Path,PurePosixPath
import hashlib
import json
import os
import zipfile

root=Path(os.environ['RUNNER_TEMP'])/'upgrade-inputs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for folder,expected in [('current',os.environ['APPROVED_SHA']),('modern','0dcde494c8450176f445cc29b28d004eddb60734')]:
 d=root/folder;metadata=json.loads((d/'provenance.json').read_text(encoding='utf-8-sig'))
 assert metadata['source_sha']==expected
 for name,record in metadata['artifacts'].items():assert sha(d/name)==record['sha256']
 archive=next(d.glob('*portable.zip'));target=d/'unpacked';target.mkdir()
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for name in z.namelist():
   p=PurePosixPath(name);assert not p.is_absolute() and '..' not in p.parts
  z.extractall(target)
 payload=target/'AstroPilot'
 actual={p.relative_to(payload).as_posix():sha(p) for p in payload.rglob('*') if p.is_file()}
 expected_files={row['path']:row['sha256'] for row in metadata['portable_inventory']}
 assert actual==expected_files
for p in (root/'legacy').glob('*.exe'):
 assert sha(p)==Path(str(p)+'.sha256').read_text().split()[0]
print('Published predecessor and official candidates verified')
