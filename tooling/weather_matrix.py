"""Paired probes of an existing binary artifact and exact sources; synthetic Madrid only."""
import argparse,datetime,hashlib,importlib.util,json,os,pathlib,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--binary',required=True);p.add_argument('--out',required=True);a=p.parse_args()
source=pathlib.Path(a.source).resolve();binary=pathlib.Path(a.binary).resolve();root=pathlib.Path(a.out).resolve();root.mkdir(exist_ok=False,parents=True);env=os.environ.copy()
for key,sub in {'HOME':'home','USERPROFILE':'home','APPDATA':'appdata','LOCALAPPDATA':'localappdata','ASTROPILOT_DATA_DIR':'data','TEMP':'tmp','TMP':'tmp','TMPDIR':'tmp'}.items():
 d=root/sub;d.mkdir(exist_ok=True);env[key]=str(d)
for key in ['ASTROPILOT_BUILD_COMMIT','ASTROPILOT_CODESIGN_IDENTITY','GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN']:env.pop(key,None)
env['SSL_CERT_FILE']='/nonexistent/validation-ca.pem';env['SSL_CERT_DIR']='/nonexistent/validation-certs'
result={'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'ca_sha256':hashlib.sha256((binary.parent/'_internal/certifi/cacert.pem').read_bytes()).hexdigest(),'trials':[],'proxy_variables_present':[k for k in ['HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','SSL_CERT_FILE','SSL_CERT_DIR'] if env.get(k)],'coordinates':'synthetic Madrid 40.4,-3.7','interval_between_probes_seconds':8};processes=[]
probe=pathlib.Path(__file__).with_name('weather_probe.py');report=root/'matrix.json'
variants=['python_instrumented','binary_file','binary_stdout','binary_host']
for round_no in range(3):
 order=variants[round_no:]+variants[:round_no]
 for kind in order:
  name=f'round-{round_no+1}-{kind}';trial_dir=root/name;trial_dir.mkdir();outfile=trial_dir/'result.json';trial={'round':round_no+1,'kind':kind,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  if kind=='python_instrumented':command=[sys.executable,str(probe),'--source',str(source),'--out',str(outfile)]
  elif kind=='binary_host':
   cfg=trial_dir/'host.json';cfg.write_text(json.dumps({'schema_version':1,'enabled':True,'provider':'open_meteo_current_v1','interval_seconds':60,'anchor':datetime.datetime.now(datetime.timezone.utc).isoformat(),'weather_site':{'latitude':40.4,'longitude':-3.7,'timeout_seconds':15},'notification':{'enabled':False}}));command=[str(binary),'--guardian','--config',str(cfg),'--data-dir',str(trial_dir/'state'),'--once']
  else:command=[str(binary),'--guardian-http-worker','40.4','-3.7','15']+([str(outfile)] if kind=='binary_file' else [])
  started=time.monotonic();child=subprocess.Popen(command,env=env,cwd=trial_dir,stdout=subprocess.PIPE,stderr=subprocess.PIPE);processes.append(child)
  try:stdout,stderr=child.communicate(timeout=35)
  except subprocess.TimeoutExpired:
   child.kill();stdout,stderr=child.communicate();trial['parent_deadline_exceeded']=True
  trial.update(exit=child.returncode,elapsed_seconds=round(time.monotonic()-started,4));(trial_dir/'stdout.txt').write_bytes(stdout);(trial_dir/'stderr.txt').write_bytes(stderr)
  if kind=='python_instrumented':
   trial['diagnostic']=json.loads(outfile.read_text()) if outfile.exists() else {'error':'probe_did_not_report'};trial['success']=trial['diagnostic'].get('success',False)
  elif kind=='binary_host':
   events=[]
   for line in stdout.decode('utf-8',errors='replace').splitlines():
    try:events.append(json.loads(line))
    except ValueError:pass
   trial['events']=events;trial['success']=child.returncode==0
  else:
   trial['success']=False
   if child.returncode==0:
    try:
     payload=json.loads(outfile.read_text() if kind=='binary_file' else stdout);trial['success']=isinstance(payload.get('current'),dict) and isinstance(payload.get('current_units'),dict)
    except (ValueError,OSError):trial['parse_error']=True
  result['trials'].append(trial);result['children_reaped']=all(c.poll() is not None for c in processes);report.write_text(json.dumps(result,indent=2));print(json.dumps(trial),flush=True);time.sleep(8)
assert result['children_reaped']
print('MATRIX COMPLETE',flush=True)
