import argparse,datetime,json,os,pathlib,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--original',required=True);p.add_argument('--diagnostic',required=True);p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args()
root=pathlib.Path(a.out).resolve();root.mkdir(parents=True,exist_ok=False);result={'source_sha':'3a39f4de1f620ccfcae2f2cd01f7719551ba1d38','diagnostic_twin_only':True,'trials':[]};env=os.environ.copy()
for key in ['HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP']:
 d=root/key;d.mkdir();env[key]=str(d)
env['SSL_CERT_FILE']='/nonexistent/validation-ca.pem';env['SSL_CERT_DIR']='/nonexistent/validation-certs'
for round_no in range(2):
 for kind in (['original','diagnostic','python'] if round_no==0 else ['python','diagnostic','original']):
  trial=root/f'{round_no+1}-{kind}';trial.mkdir();output=trial/'weather.json';log_dir=trial/'events';env['WEATHER_DIAGNOSTIC_LOG_DIR']=str(log_dir)
  if kind=='python':command=[sys.executable,str(pathlib.Path(__file__).with_name('weather_probe.py')),'--source',a.source,'--out',str(output)]
  else:command=[a.original if kind=='original' else a.diagnostic,'--guardian-http-worker','40.4','-3.7','15',str(output)]
  started=time.monotonic();r=subprocess.run(command,capture_output=True,env=env,cwd=trial,timeout=35);(trial/'stdout.txt').write_bytes(r.stdout);(trial/'stderr.txt').write_bytes(r.stderr)
  row={'round':round_no+1,'kind':kind,'exit':r.returncode,'elapsed_seconds':time.monotonic()-started,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  if kind=='diagnostic':row['events']=[json.loads(l) for f in log_dir.glob('*.jsonl') for l in f.read_text().splitlines()]
  if kind=='python':row['probe']=json.loads(output.read_text())
  result['trials'].append(row);(root/'twin.json').write_text(json.dumps(result,indent=2));print(json.dumps(row),flush=True);time.sleep(8)
