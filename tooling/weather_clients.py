import argparse,concurrent.futures,json,os,pathlib,platform,ssl,subprocess,sys,time
from urllib.parse import urlencode
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args()
source=pathlib.Path(a.source).resolve();out=pathlib.Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
curl=pathlib.Path(os.environ['SystemRoot'])/'System32/curl.exe'
version=subprocess.check_output([str(curl),'--version'],text=True)
assert 'Schannel' in version,version
params=urlencode({'latitude':40.4,'longitude':-3.7,'current':','.join(('rain','showers','wind_speed_10m','wind_gusts_10m','relative_humidity_2m','temperature_2m','dew_point_2m')),'timezone':'UTC','timeformat':'unixtime','temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm','forecast_days':1})
url='https://api.open-meteo.com/v1/forecast?'+params
report={'platform':platform.platform(),'python':sys.version,'openssl':ssl.OPENSSL_VERSION,'curl_version':version,'url':url,'samples':[]}
env=dict(os.environ)
for key in ('GH_TOKEN','GITHUB_TOKEN'):env.pop(key,None)
def probe(client,ip,round,start):
 time.sleep(max(0,start-time.time()));actual=time.time();base=out/f'{round}-{ip}-{client}'
 if client=='python':
  file=base.with_suffix('.json');cmd=[sys.executable,str(pathlib.Path(__file__).with_name('weather_probe.py').resolve()),'--source',str(source),'--out',str(file),'--connect-ip',ip]
  r=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=30)
  if r.returncode:raise RuntimeError(r.stderr)
  d=json.loads(file.read_text())
 else:
  body=base.with_suffix('.body');headers=base.with_suffix('.headers');trace=base.with_suffix('.trace')
  cmd=[str(curl),'--disable','--noproxy','*','--resolve',f'api.open-meteo.com:443:{ip}','--http1.1','--user-agent','','--max-time','15','--connect-timeout','15','--silent','--show-error','--verbose','--output',str(body),'--dump-header',str(headers),'--write-out','%{json}',url]
  r=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=30);trace.write_text(r.stderr)
  d=json.loads(r.stdout) if r.stdout.strip() else {};valid=False
  if body.exists():
   try:valid=isinstance(json.loads(body.read_text()).get('current'),dict)
   except (ValueError,UnicodeError):pass
  d={'success':r.returncode==0 and d.get('http_code')==200 and valid,'exit_code':r.returncode,'metrics':d,'error_message':r.stderr[-1500:] if r.returncode else None,'tls_verified_by_default':True,'hostname':'api.open-meteo.com','elapsed_seconds':d.get('time_total')}
 d.update(client=client,ip=ip,round=round,scheduled_epoch=start,actual_start_epoch=actual);return d
ips=['188.40.99.226','94.130.142.35','167.114.211.86']
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for round in range(1,7):
  for ip in ips[(round-1)%3:]+ips[:(round-1)%3]:
   start=time.time()+1
   futures=[pool.submit(probe,c,ip,round,start) for c in ['python','schannel']]
   pair=[f.result() for f in futures];report['samples'].extend(pair);(out/'comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(pair),flush=True);time.sleep(8)
