"""PR380 native binary diagnostics; only isolated synthetic weather, never sessions."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from kit_safety import guard_placement, reject_links, safe_extract
from windows_job import IsolatedProcess
from weather_fixture import WeatherFixture, prepare_certificates

BASE=Path(__file__).resolve().parent
PROVENANCE=json.loads((BASE/'Kit-provenance.json').read_text(encoding='utf-8'))
OWNER=None
local=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def snapshot(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs+files:
            item = Path(directory)/name
            if item.is_symlink() or (hasattr(item,'is_junction') and item.is_junction()):
                raise RuntimeError('Lien ou jonction dans la configuration : arrêt sans copie.')
        for name in files:
            item = Path(directory)/name
            with item.open('rb') as file:
                result[str(item.relative_to(root))] = hashlib.file_digest(file,'sha256').hexdigest()
    return result

def api(path, body=None):
    if OWNER is None or OWNER.poll() is not None or OWNER.listener_pid() is None:
        raise RuntimeError('Serveur de test absent ou non contenu : aucun appel API.')
    request = urllib.request.Request('http://127.0.0.1:8000'+path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    started = time.time()
    try:
        with local.open(request,timeout=300) as response:
            status, content = response.status, response.read()
            response_headers = response.headers
    except urllib.error.HTTPError as error:
        status, content = error.code, error.read()
        response_headers = error.headers
    return {'http':status,'seconds':time.time()-started,'body':json.loads(content),
            'diagnostic_id':response_headers.get('X-Weather-Diagnostic-ID')}



def diagnostic_events(path):
    events=[]
    for file in sorted(path.parent.glob('AstroPilot.log*')):
        if not file.is_file(): continue
        for line in file.read_text(encoding='utf-8',errors='replace').splitlines():
            if 'weather_diagnostic ' in line:
                events.append(json.loads(line.split('weather_diagnostic ',1)[1]))
    return events


def check_phase(reply, events, *, failure, category=None, status=None):
    identifier=reply.get('diagnostic_id')
    if not isinstance(identifier,str) or len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):
        return False,'diagnostic_header_missing'
    records=[r for r in events if r.get('diagnostic_id')==identifier]
    expected={'weather_fetch_failed','tonight_weather_refused'} if failure else {'weather_fetch_succeeded','tonight_weather_available'}
    if {r.get('event') for r in records}!=expected or len(records)!=2:
        return False,'diagnostic_correlation_mismatch'
    keys={'schema_version','event','diagnostic_id','occurred_at_utc','provider','category','duration_ms','http_status'}
    for record in records:
        if set(record)!=keys or type(record['schema_version']) is not int or record['schema_version']!=1 or record['provider']!='open_meteo':
            return False,'diagnostic_schema_mismatch'
        try:
            stamp=datetime.datetime.fromisoformat(record['occurred_at_utc'])
            if stamp.utcoffset()!=datetime.timedelta(0) or type(record['duration_ms']) not in (float,int) or not math.isfinite(record['duration_ms']) or record['duration_ms']<0:
                return False,'diagnostic_time_invalid'
        except (ValueError,TypeError): return False,'diagnostic_time_invalid'
    fetch=next(r for r in records if r['event'].startswith('weather_fetch_'))
    boundary=next(r for r in records if r['event'].startswith('tonight_weather_'))
    if failure:
        valid=(reply['http']==503 and reply['body'].get('detail',{}).get('code')=='weather_unavailable'
            and fetch['category']==category and fetch['http_status']==status
            and boundary['category']=='weather_unavailable' and boundary['http_status']==503)
    else:
        valid=(reply['http']==200 and fetch['category']=='validated' and fetch['http_status']==200
            and boundary['category']=='available')
    return valid,'matched' if valid else 'phase_result_mismatch'


def main():
    global OWNER
    if sys.platform!='win32': raise SystemExit('Ce kit est réservé au PC Windows.')
    guard_placement(BASE)
    print('PR #380 : erreurs météo SIMULÉES puis reprise, aucune session exécutée.',flush=True)
    print('Les prévisions de reprise sont synthétiques ; elles ne doivent pas servir à observer.',flush=True)
    config=BASE/'Configuration-Mac-reference.zip'
    if hashlib.sha256(config.read_bytes()).hexdigest()!=PROVENANCE['mac_reference_zip_sha256']:
        raise SystemExit('Référence Mac incorrecte : arrêt sans test.')
    source=BASE/'profil-Mac-reference';reject_links(source)
    if not source.exists(): safe_extract(config,source)
    expected=json.loads((BASE/'Manifest-configuration-Mac.json').read_text(encoding='utf-8'))
    before=snapshot(source)
    if {k.replace('\\','/'):v for k,v in before.items()}!=expected:
        raise SystemExit('Référence Mac modifiée : utilisez un nouveau dossier du kit.')
    if IsolatedProcess.listening_pids(): raise SystemExit('Port 8000 occupé : fermez AstroPilot.')
    archive=BASE/'AstroPilot-PR380-331093b-portable.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=PROVENANCE['portable_zip_sha256']:
        raise SystemExit('Binaire incorrect : arrêt.')
    out=BASE/('resultats-meteo-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir()
    report={'build':'331093b','source_sha':PROVENANCE['source_sha'],
        'portable_zip_sha256':PROVENANCE['portable_zip_sha256'],'simulated_weather':True,
        'reference_files':len(before),'cases':[]}
    child=None;fixture=None;log=None
    try:
        required=6*sum((source/name).stat().st_size for name in before)+500*1024*1024
        if shutil.disk_usage(out).free<required: raise RuntimeError('Espace disque insuffisant pour les copies isolées.')
        reference=out/'reference-copy';shutil.copytree(source,reference)
        if snapshot(reference)!=before or snapshot(source)!=before: raise RuntimeError('Référence changée pendant la copie.')
        extracted=out/'extracted';safe_extract(archive,extracted)
        exe=extracted/'AstroPilot'/'AstroPilot.exe'
        if hashlib.sha256(exe.read_bytes()).hexdigest()!=PROVENANCE['binary_sha256']:
            raise RuntimeError('Empreinte exécutable incorrecte.')
        report['binary_sha256']=PROVENANCE['binary_sha256']
        tzdata=extracted/'AstroPilot'/'_internal'/'tzdata'/'zoneinfo'
        if not (tzdata/'Europe'/'Zurich').is_file(): raise RuntimeError('Données de fuseau du binaire absentes.')
        certificates=out/'certificats-test'
        generated=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(BASE/'Create-test-certificates.ps1'),'-OutputDirectory',str(certificates)],
            capture_output=True,text=True,timeout=60)
        if generated.returncode: raise RuntimeError('Génération des certificats de test échouée.')
        prepare_certificates(certificates)
        scenarios=[('connection_error','connection_error',None),('tls_error','tls_error',None),
            ('http_429','http_error',429),('http_503','http_error',503),('read_timeout','read_timeout',None)]
        for mode,category,status in scenarios:
            case={'scenario':mode,'expected_category':category,'expected_http_status':status,'simulated':True}
            report['cases'].append(case)
            root=out/mode;root.mkdir();data=root/'data';shutil.copytree(reference,data)
            profile_hash=hashlib.sha256((data/'user_profile.json').read_bytes()).hexdigest()
            legacy_before=(data/'user_filters.json').exists()
            clear={'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','SSL_CERT_FILE','SSL_CERT_DIR'}
            env={k:v for k,v in os.environ.items() if not k.upper().startswith(('ASTROPILOT_','NIGHTMERIT_')) and k.upper() not in clear}
            for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME'):
                p=root/key;p.mkdir();env[key]=str(p)
            fixture=WeatherFixture(certificates,tzdata,mode)
            proxy='http://127.0.0.1:'+str(fixture.port)
            env.update(ASTROPILOT_DATA_DIR=str(data),HTTP_PROXY=proxy,HTTPS_PROXY=proxy,
                NO_PROXY='127.0.0.1,localhost',REQUESTS_CA_BUNDLE=str(certificates/'trust.pem'))
            noop=root/'noop.py';noop.write_text('pass\n',encoding='utf-8')
            env['BROWSER']='"'+sys.executable+'" "'+str(noop)+'" %s'
            if IsolatedProcess.listening_pids(): raise RuntimeError('Port occupé : aucun serveur existant ne sera utilisé.')
            log=(root/'binary.log').open('w',encoding='utf-8')
            child=IsolatedProcess([str(exe)],cwd=root,env=env);OWNER=child
            case['launcher_pid']=child.pid
            try:
                deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    if child.poll() is not None: raise RuntimeError('Binaire arrêté au démarrage.')
                    try: identity=api('/v1/runtime-identity')
                    except (OSError,RuntimeError): time.sleep(.5);continue
                    if identity['http']!=200 or identity['body'].get('build')!='331093b':
                        raise RuntimeError('Identité binaire incorrecte.')
                    case['runtime_identity']=identity['body'];case['server_pid']=child.listener_pid();break
                else: raise RuntimeError('Serveur non prêt.')
                request={'availability':{'mode':'duration','duration':'PT2H'}}
                failed=api('/v1/tonight',request)
                (root/'echec-simule.json').write_text(json.dumps(failed,indent=2),encoding='utf-8')
                event_path=data/'Logs'/'AstroPilot.log'
                events=diagnostic_events(event_path)
                case['failure_valid'],case['failure_reason']=check_phase(failed,events,failure=True,category=category,status=status)
                case['failure_http']=failed['http'];case['failure_diagnostic_id']=failed['diagnostic_id']
                fixture.recover()
                recovered=api('/v1/tonight',request)
                (root/'reprise-synthetique.json').write_text(json.dumps(recovered,indent=2),encoding='utf-8')
                events=diagnostic_events(event_path)
                case['recovery_valid'],case['recovery_reason']=check_phase(recovered,events,failure=False)
                case['recovery_http']=recovered['http'];case['recovery_diagnostic_id']=recovered['diagnostic_id']
                case['distinct_ids']=failed['diagnostic_id']!=recovered['diagnostic_id']
                case['fixture_calls']=list(fixture.records);case['fixture_errors']=list(fixture.errors)
                case['single_call_per_phase']=[x['mode'] for x in fixture.records]==[mode,'success']
                case['profile_copy_unchanged']=hashlib.sha256((data/'user_profile.json').read_bytes()).hexdigest()==profile_hash
                case['legacy_inventory_created']=not legacy_before and (data/'user_filters.json').exists()
                valid=all(case[k] for k in ('failure_valid','recovery_valid','distinct_ids','single_call_per_phase','profile_copy_unchanged')) and not case['fixture_errors'] and not case['legacy_inventory_created']
                case['result']='PASS' if valid else 'FAIL'
                print(mode,':',case['result'],'échec HTTP',failed['http'],'reprise HTTP',recovered['http'],flush=True)
            finally:
                if child is not None: child.close()
                case['binary_stopped']=child is None or child.stopped;OWNER=None
                deadline=time.monotonic()+5
                while IsolatedProcess.listening_pids() and time.monotonic()<deadline: time.sleep(.1)
                case['port_released']=not IsolatedProcess.listening_pids()
                case['fixture_stopped']=fixture.close();fixture=None
                log.write('Job stopped; descendants reaped; fixture stopped; port released.\n');log.close();log=None;child=None
                if not case['port_released']: raise RuntimeError('Port 8000 non libéré : essais suivants annulés.')
    except (Exception,KeyboardInterrupt) as error:
        report['error_type']=type(error).__name__;report['error']=str(error) or type(error).__name__
        print('Test interrompu :',report['error'],flush=True)
    finally:
        if child is not None:
            try: child.close()
            except Exception: report['cleanup_error']=True
        OWNER=None
        if fixture is not None: fixture.close()
        if log is not None: log.close()
        report['reference_unchanged']=snapshot(source)==before
        report['overall_result']='PASS' if not report.get('error') and not report.get('cleanup_error') and report['reference_unchanged'] and len(report['cases'])==5 and all(c.get('result')=='PASS' and c.get('binary_stopped') and c.get('port_released') and c.get('fixture_stopped') for c in report['cases']) else 'FAIL'
        (out/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        result_zip=out.with_suffix('.zip')
        with zipfile.ZipFile(result_zip,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(out/'comparison.json','comparison.json')
            for case in report['cases']:
                root=out/case['scenario']
                for name in ('echec-simule.json','reprise-synthetique.json','binary.log'):
                    p=root/name
                    if p.is_file(): z.write(p,case['scenario']+'/'+name)
                for p in (root/'data'/'Logs').glob('AstroPilot.log*'):
                    if p.is_file(): z.write(p,case['scenario']+'/Logs/'+p.name)
        print('Résultat :',report['overall_result'],'; archive à transmettre :',result_zip,flush=True)
        print('Prévisions SIMULÉES : ce test ne valide aucune nuit réelle ni acquisition.',flush=True)
    return 0 if report['overall_result']=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
