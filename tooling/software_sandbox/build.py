"""Derive a diagnostic launcher variant from the exact already-qualified Windows kit."""
from pathlib import Path,PurePosixPath
import base64,json,hashlib,os,subprocess,zipfile
BASE='d4a4d10345b888c7b69a759f111c6fcd7216ab58867e1bfb1b7020968d45ce1f'
SHA='7e98e45b2f46f57dcf959f3bf8d2b1373375cf48'
ops=Path(__file__).resolve().parents[2];root=Path(os.environ['RUNNER_TEMP']);incoming=root/'input-kit';archive=next(incoming.glob('*.zip'));assert hashlib.sha256(archive.read_bytes()).hexdigest()==BASE
out=root/'software-kit';out.mkdir();name='NightMerit-Installation-7e98e45-Windows-Logiciel';target=out/(name+'.zip');prefix=archive.stem+'/';newprefix=name+'/'
launch=(ops/'tooling/installation7e/launch-sandbox.ps1').read_text(encoding='utf-8');encoded=base64.b64encode(launch.encode('utf-16le')).decode();launcher=('@echo off\r\nset "NIGHTMERIT_INSTALL_KIT=%~dp0"\r\npowershell.exe -NoProfile -EncodedCommand '+encoded+'\r\nif errorlevel 1 pause\r\n').encode('ascii')
assert len(max(launcher.splitlines(),key=len))<8190
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 old_manifest=json.loads(z.read(prefix+'manifest.json'));assert old_manifest['source_sha']==SHA
 old_launch=z.read(prefix+'Audit/launch-sandbox.ps1').decode('utf-8-sig').replace('\r\n','\n')
 assert launch.replace(' <vGPU>Disable</vGPU>\n','')==old_launch,'Only the vGPU tag may change the launcher source'
 config=json.loads(z.read(prefix+'kit.json'));assert config['source_sha']==SHA
 config.update(diagnostic_variant='software_rendering',launcher_operations_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ops,text=True).strip(),base_kit_sha256=BASE,vgpu='Disable',physical_user_test_pending=True)
 text=z.read(prefix+'LIRE-MOI.txt').decode('utf-8-sig')
 intro='VARIANTE DIAGNOSTIQUE — RENDU GRAPHIQUE LOGICIEL\n\nDécompresser ce ZIP dans un NOUVEAU dossier sur le Bureau Windows.\nFermer toute fenêtre Windows Sandbox déjà ouverte, puis lancer\nLANCER-TEST-WINDOWS.cmd. Le guide et les crédits sont déjà fournis.\nNe créer aucune session ni aucun crédit.\n\nSeul le partage GPU de CETTE instance Sandbox est désactivé ; Windows utilise\nson rendu logiciel. L isolation Sandbox et les réglages du PC restent inchangés.\nCe test n est pas une correction confirmée du plantage 0x3B.\n\nSi Sandbox se ferme, NE PAS relancer le test : retourner les fichiers du dossier\nRESULTATS (journal demarrage-sandbox et sous-dossier diagnostic-en-cours).\nLe diagnostic partiel n est jamais une preuve de réussite.\n\n'
 guide=z.read(prefix+'Guide.html').decode('utf-8-sig').replace('<main>','<main><p><b>ESSAI DIAGNOSTIQUE — RENDU LOGICIEL.</b> Isolation Sandbox conservée. La cause du plantage reste à confirmer. Les étapes sont enregistrées dans RESULTATS.</p>',1)
 provenance={'schema_version':1,'product_source_sha':SHA,'base_kit_sha256':BASE,'base_operations_sha':config['operations_sha'],'launcher_operations_sha':config['launcher_operations_sha'],'runtime_configuration_change':{'vGPU':'Disable'},'product_binaries_changed':False,'seeded_profile_changed':False,'chrome_sandbox_disabled':False,'physical_user_test_pending':True,'base_qualification':'https://github.com/touchthebitum/AstroPilot/actions/runs/39035081606','base_kit_job':'kits (windows-2022)'}
 changes={'Audit/launch-sandbox.ps1':launch.encode('utf-8'),'LANCER-TEST-WINDOWS.cmd':launcher,'LIRE-MOI.txt':(intro+text).encode('utf-8'),'Guide.html':guide.encode('utf-8'),'kit.json':json.dumps(config,indent=2).encode(),'software-rendering-provenance.json':json.dumps(provenance,indent=2).encode()}
 rows={};unchanged=0
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as output:
  for rel,entry in old_manifest['files'].items():
   assert 'sha256' in entry
   raw=z.read(prefix+rel);assert hashlib.sha256(raw).hexdigest()==entry['sha256'],rel
   payload=changes.get(rel,raw)
   if rel not in changes:unchanged+=1
   rows[rel]={'sha256':hashlib.sha256(payload).hexdigest()};output.writestr(newprefix+rel,payload)
  for rel,payload in changes.items():
   if rel not in rows:rows[rel]={'sha256':hashlib.sha256(payload).hexdigest()};output.writestr(newprefix+rel,payload)
  output.writestr(newprefix+'manifest.json',json.dumps({'source_sha':SHA,'files':rows},indent=2))
with zipfile.ZipFile(target) as z:
 assert z.testzip() is None
 restored=root/'software-roundtrip';restored.mkdir()
 for n in z.namelist():assert not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts
 z.extractall(restored)
 for rel,entry in rows.items():assert hashlib.sha256(z.read(newprefix+rel)).hexdigest()==entry['sha256']
subprocess.run([str(restored/name/'TestController/TestController.exe'),'--verify-only'],cwd=restored/name,check=True,timeout=180)
proof=json.loads((root/'software-launch-proof.json').read_text(encoding='utf-8-sig'));assert proof['result']=='PASS' and proof['sandbox_started'] is False
result={'result':'PASS_VARIANT_INTEGRITY_AND_LAUNCHER','source_sha':SHA,'base_kit_sha256':BASE,'kit':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'files':len(rows),'unchanged_base_files':unchanged,'changed_base_files':sorted(set(changes)&set(old_manifest['files'])),'added_files':sorted(set(changes)-set(old_manifest['files'])),'launcher_operations_sha':config['launcher_operations_sha'],'product_binaries_unchanged':True,'seeded_profile_unchanged':True,'durable_diagnostics_unchanged':True,'launcher_test':proof,'physical_user_test_pending':True}
(out/'variant-validation.json').write_text(json.dumps(result,indent=2));(out/(target.name+'.sha256')).write_text(result['sha256']+'  '+target.name+'\n');print(json.dumps(result),flush=True)
