"""Validate extracted portable and an installer deployed only to disposable runner temp."""
import hashlib,json,os,pathlib,subprocess,sys,zipfile
root=pathlib.Path.cwd();temp=pathlib.Path(os.environ['RUNNER_TEMP']);sha=os.environ['APPROVED_SHA'];output=root/'dist/beta8-artifacts';tool=pathlib.Path(__file__).with_name('validate_binary.py')
portable=output/'AstroPilot-1.0.0b8-windows-x86_64-portable.zip';extract=temp/'beta8-portable-extraction';extract.mkdir(exist_ok=False)
with zipfile.ZipFile(portable) as archive:
 assert archive.testzip() is None
 for name in archive.namelist():
  dest=(extract/name).resolve();dest.relative_to(extract.resolve())
 archive.extractall(extract)
subprocess.run([sys.executable,str(tool),'--binary',str(extract/'AstroPilot/AstroPilot.exe'),'--work',str(temp/'beta8-native-portable-validation'),'--source',str(root),'--expected-sha',sha],check=True)
setup=output/'AstroPilot-1.0.0b8-windows-x86_64-setup.exe';installed=temp/'beta8-installer-synthetic-destination';installlog=temp/'beta8-installer.log'
r=subprocess.run([str(setup),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS','/TASKS=',f'/DIR={installed}',f'/LOG={installlog}'],timeout=180)
assert r.returncode==0,r.returncode
# Every installed payload byte must match the portable artifact; ignore the generated uninstaller.
for file in (extract/'AstroPilot').rglob('*'):
 if file.is_file():assert hashlib.sha256(file.read_bytes()).digest()==hashlib.sha256((installed/file.relative_to(extract/'AstroPilot')).read_bytes()).digest()
isolation=temp/'beta8-installed-identity-isolation';isolation.mkdir();env=os.environ.copy()
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR'):
 p=isolation/key;p.mkdir();env[key]=str(p)
r=subprocess.run([str(installed/'AstroPilot.exe'),'--runtime-identity'],env=env,cwd=isolation,capture_output=True,text=True,timeout=60);assert r.returncode==0
identity=json.loads(r.stdout);assert identity['build']==sha[:7] and identity['version']=='1.0.0b8' and identity['architecture']=='x86_64'
report={'source_sha':sha,'portable_extraction_validated':True,'installer_exit':0,'installed_payload_matches_portable':True,'installed_runtime_identity':identity,'installer_destination':'disposable GitHub runner temp only','no_startup_job_or_notification':True,'windows_desktop_ui_manually_observed':False}
(output/'installer-and-portable-validation.json').write_text(json.dumps(report,indent=2))
(output/'native-portable-validation.json').write_bytes((temp/'beta8-native-portable-validation/validation.json').read_bytes())
print(json.dumps(report))
