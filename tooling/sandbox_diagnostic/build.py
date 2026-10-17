from pathlib import Path
import base64,hashlib,json,shutil,zipfile
root=Path(__file__).parent;dest=Path('diagnostic-output');dest.mkdir(exist_ok=False);kit=dest/'NightMerit-Diagnostic-Sandbox-Windows-v2';kit.mkdir()
launcher='@echo off\r\nchcp 65001 >nul\r\nset "NIGHTMERIT_DIAG_ROOT=%~dp0"\r\npowershell.exe -NoProfile -Command "& ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $env:NIGHTMERIT_DIAG_ROOT \'Audit\\collect.ps1\'))))"\r\npause\r\n'
assert len(max(launcher.splitlines(),key=len))<8190,'CMD command exceeds Windows limit'
(kit/'COLLECTER-DIAGNOSTIC.cmd').write_bytes(launcher.encode('ascii'))
(kit/'Audit').mkdir();shutil.copy2(root/'collect.ps1',kit/'Audit/collect.ps1')
(kit/'LIRE-MOI.txt').write_text('NightMerit — diagnostic du plantage Windows Sandbox\n\nSur votre Windows habituel, pas dans Sandbox :\n1. Décompresser entièrement ce ZIP dans un nouveau dossier.\n2. Clic droit sur COLLECTER-DIAGNOSTIC.cmd puis Exécuter en tant qu administrateur.\n3. Attendre « Diagnostic exporte ».\n4. Retourner le fichier diagnostic-sandbox-*.zip du dossier RESULTATS.\n\nNe relance ni Sandbox, ni NightMerit, ni les installeurs.\nNe change aucun réglage, aucune fonctionnalité ni politique système.\nLa demande administrateur est déclenchée seulement par votre clic droit. Les journaux inaccessibles sont signalés.\nNe lit ni profil NightMerit, ni stash, ni cache navigateur, ni journal Security.\nExporte des événements système pertinents des dernières 24 heures et des\nmétadonnées Windows, mémoire et virtualisation. Les événements peuvent contenir\ndes chemins ou identifiants locaux ; aucune transmission automatique.\nCe ZIP ne valide pas le test d’installation et ne prouve pas seul la cause.\n\nAucun merge, tag, release, signature personnelle ou soumission Apple.\n',encoding='utf-8')
manifest={p.relative_to(kit).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in kit.rglob('*') if p.is_file()};(kit/'manifest.json').write_text(json.dumps(manifest,indent=2))
archive=dest/(kit.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in kit.rglob('*'):
  if p.is_file():z.write(p,p.relative_to(dest))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for n,h in manifest.items():assert hashlib.sha256(z.read(kit.name+'/'+n)).hexdigest()==h
(dest/(archive.name+'.sha256')).write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print(archive)

# Native smoke of the actual human launcher in an isolated copy, not the shipping kit.
import os,subprocess
if os.name=='nt':
 smoke=dest/'smoke-copy';shutil.copytree(kit,smoke)
 subprocess.run(['cmd.exe','/d','/c',str((smoke/'COLLECTER-DIAGNOSTIC.cmd').resolve())],input='\n',text=True,check=True,timeout=180)
 exports=list((smoke/'RESULTATS').glob('*.zip'));assert len(exports)==1
 with zipfile.ZipFile(exports[0]) as z:
  assert z.testzip() is None
  row=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/diagnostic.json'))).decode('utf-8-sig'))
  assert row['schema_version']==2
  assert any(n.endswith('/log-inventory.json') for n in z.namelist())
  assert row['verdict']=='NOT_A_QUALIFICATION' and row['sandbox_launched'] is False
 (dest/'launcher-smoke.json').write_text(json.dumps({'result':'PASS','actual_cmd_launcher':True,'zip_roundtrip':True,'sandbox_launched':False,'settings_changed':False}))
