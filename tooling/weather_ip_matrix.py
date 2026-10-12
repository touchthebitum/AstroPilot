import argparse,json,pathlib,subprocess,sys,time,socket,platform,os
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--start-epoch',type=float,required=True);a=p.parse_args()
source=pathlib.Path(a.source).resolve();out=pathlib.Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
ips=['188.40.99.226','94.130.142.35','167.114.211.86'];report={'platform':platform.platform(),'python':sys.version,'hostname':'api.open-meteo.com','normal_dns':sorted({r[4][0] for r in socket.getaddrinfo('api.open-meteo.com',443)}),'samples':[],'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
env=dict(os.environ);env.pop('GH_TOKEN',None);env.pop('GITHUB_TOKEN',None)
slot=0
if time.time()>a.start_epoch:raise RuntimeError('Missed synchronized start')
report['scheduled_start_epoch']=a.start_epoch
for round in range(6):
 for ip in ips[round%3:]+ips[:round%3]:
  scheduled=a.start_epoch+slot*20;slot+=1
  time.sleep(max(0,scheduled-time.time()));actual=time.time()
  file=out/f'round-{round+1}-{ip}.json'
  run=subprocess.run([sys.executable,str(pathlib.Path(__file__).resolve().with_name('weather_probe.py')),'--source',str(source),'--out',str(file),'--connect-ip',ip],cwd=out,env=env,capture_output=True,text=True,timeout=35)
  if run.returncode or not file.exists():raise RuntimeError(run.stderr[:500])
  sample=json.loads(file.read_text());sample.update(round=round+1,ip=ip,scheduled_epoch=scheduled,actual_start_epoch=actual,start_delay_seconds=actual-scheduled);report['samples'].append(sample)
  (out/'comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(sample),flush=True)
report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());(out/'comparison.json').write_text(json.dumps(report,indent=2))
