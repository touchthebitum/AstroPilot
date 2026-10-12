import argparse,json,pathlib,subprocess,sys,time,socket,platform,os
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args()
source=pathlib.Path(a.source).resolve();out=pathlib.Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
ips=['188.40.99.226','94.130.142.35'];report={'platform':platform.platform(),'python':sys.version,'hostname':'api.open-meteo.com','normal_dns':sorted({r[4][0] for r in socket.getaddrinfo('api.open-meteo.com',443)}),'samples':[],'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
env=dict(os.environ);env.pop('GH_TOKEN',None);env.pop('GITHUB_TOKEN',None)
for round in range(6):
 for ip in ips if round%2==0 else list(reversed(ips)):
  file=out/f'round-{round+1}-{ip}.json'
  run=subprocess.run([sys.executable,str(pathlib.Path(__file__).resolve().with_name('weather_probe.py')),'--source',str(source),'--out',str(file),'--connect-ip',ip],cwd=out,env=env,capture_output=True,text=True,timeout=35)
  if run.returncode or not file.exists():raise RuntimeError(run.stderr[:500])
  sample=json.loads(file.read_text());sample.update(round=round+1,ip=ip);report['samples'].append(sample)
  (out/'comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(sample),flush=True);time.sleep(8)
report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());(out/'comparison.json').write_text(json.dumps(report,indent=2))
