import datetime, hashlib, json, os, pathlib, shutil, socket, subprocess, sys, time, urllib.request, urllib.error, uuid, zipfile

BASE = pathlib.Path(__file__).resolve().parent
from windows_job import IsolatedProcess
from kit_safety import guard_placement, safe_extract, reject_links
PROVENANCE = json.loads((BASE/'Kit-provenance.json').read_text(encoding='utf-8'))
EXPECTED = PROVENANCE['portable_zip_sha256']
BUILD = 'a6f5bd8'
OWNER = None
local = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def snapshot(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs+files:
            item = pathlib.Path(directory)/name
            if item.is_symlink() or (hasattr(item,'is_junction') and item.is_junction()):
                raise RuntimeError('Lien ou jonction dans la configuration : arrêt sans copie.')
        for name in files:
            item = pathlib.Path(directory)/name
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
    except urllib.error.HTTPError as error:
        status, content = error.code, error.read()
    return {'http':status,'seconds':time.time()-started,'body':json.loads(content)}

def subject_for(decision, intent):
    if intent in decision.get('viable_acquisition_intent_ids',[]) and (decision.get('acquisition_intent_choice_available') is True or decision.get('target_decision_status')=='recommended'):
        return decision,'primary_recommendation'
    for alternative in decision.get('alternatives',[]):
        if alternative.get('target_decision_status')=='viable' and intent in alternative.get('viable_acquisition_intent_ids',[]):
            return alternative,'alternative'
    return None,None

def main():
    global OWNER
    if sys.platform!='win32':
        raise SystemExit('Ce kit est réservé au PC Windows.')
    guard_placement(pathlib.Path(__file__).absolute().parent)
    print('Test Halpha/OIII : copie locale, aucune exécution de mission.',flush=True)
    print('Source : référence Mac fournie dans le kit. La configuration réelle du PC ne sera pas utilisée.',flush=True)
    config_archive = BASE/'Configuration-Mac-reference.zip'
    if not config_archive.is_file() or hashlib.sha256(config_archive.read_bytes()).hexdigest() != PROVENANCE['mac_reference_zip_sha256']:
        raise SystemExit('Archive de configuration Mac absente ou incorrecte.')
    source = BASE/'profil-Mac-reference'
    reject_links(source)
    expected_profile = json.loads((BASE/'Manifest-configuration-Mac.json').read_text(encoding='utf-8'))
    if not source.exists():
        safe_extract(config_archive, source)
    actual_profile = {key.replace('\\','/'):value for key,value in snapshot(source).items()}
    if actual_profile != expected_profile:
        raise SystemExit('La référence Mac du kit a changé. Utilisez un nouveau dossier extrait du kit.')
    day = input('Date locale à tester AAAA-MM-JJ (Entrée = '+datetime.date.today().isoformat()+') : ').strip() or datetime.date.today().isoformat()
    start = input('Début local HH:MM (Entrée = 20:30) : ').strip() or '20:30'
    end = input('Fin locale HH:MM (Entrée = 23:00) : ').strip() or '23:00'
    start_dt = datetime.datetime.fromisoformat(day+'T'+start)
    end_dt = datetime.datetime.fromisoformat(day+'T'+end)
    if end_dt <= start_dt:
        end_dt += datetime.timedelta(days=1)
    if end_dt-start_dt > datetime.timedelta(hours=24):
        raise SystemExit('Le créneau doit durer au plus 24 heures.')
    if IsolatedProcess.listening_pids():
        raise SystemExit('Le port 8000 est occupé. Fermez AstroPilot avant le test.')
    archive = BASE/'AstroPilot-PR376-a6f5bd8-portable.zip'
    if not archive.is_file():
        raise SystemExit('Archive du binaire corrigé absente. Extrayez tout le nouveau kit.')
    with archive.open('rb') as file:
        if hashlib.file_digest(file,'sha256').hexdigest()!=EXPECTED:
            raise SystemExit('SHA256 du binaire incorrect : arrêt.')
    out = BASE/('resultats-choix-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    if out.resolve().is_relative_to(source):
        raise SystemExit('Le kit doit se trouver hors du dossier de données réel.')
    out.mkdir()
    report = {'build':BUILD,'source_sha':'a6f5bd8e454d3de28dd9cc5f23408efabca6e0a1','portable_zip_sha256':EXPECTED,'source_directory':str(source),'availability':{'mode':'fixed_window','start_local':start_dt.isoformat(timespec='minutes'),'end_local':end_dt.isoformat(timespec='minutes')},'cases':[]}
    before = None
    child = None
    log = None
    try:
        print('Vérification et copie de la configuration ; cela peut prendre quelques minutes...',flush=True)
        before = snapshot(source)
        required = 3*sum((source/name).stat().st_size for name in before)+400*1024*1024
        if shutil.disk_usage(out).free<required:
            raise RuntimeError('Espace disque insuffisant pour les trois copies isolées et le binaire.')
        reference = out/'reference-copy'
        shutil.copytree(source,reference)
        if snapshot(reference)!=before or snapshot(source)!=before:
            raise RuntimeError('La configuration a changé pendant la copie. Fermez AstroPilot et relancez.')
        report['source_files'] = len(before)
        extracted = out/'extracted'
        safe_extract(archive, extracted)
        exe = extracted/'AstroPilot/AstroPilot.exe'
        report['binary_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
        if report['binary_sha256'] != PROVENANCE['binary_sha256']:
            raise RuntimeError('Empreinte de l’exécutable incorrecte.')
        for intent in ['sh2-129_ha','ou4_oiii']:
            case = {'intent':intent}
            report['cases'].append(case)
            root = out/intent
            root.mkdir()
            data = root/'data'
            shutil.copytree(reference,data)
            env = {key:value for key,value in os.environ.items()
                   if not key.upper().startswith(('ASTROPILOT_', 'NIGHTMERIT_'))}
            for key in ['HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME']:
                directory = root/key
                directory.mkdir()
                env[key] = str(directory)
            env['ASTROPILOT_DATA_DIR'] = str(data)
            env['ASTROPILOT_SESSION_TIMING'] = '1'
            noop = root/'noop.py'
            noop.write_text('pass\n',encoding='utf-8')
            env['BROWSER'] = '"'+sys.executable+'" "'+str(noop)+'" %s'
            if IsolatedProcess.listening_pids():
                raise RuntimeError('Le port 8000 est occupé ; aucun serveur existant ne sera utilisé.')
            log = (root/'binary.log').open('w',encoding='utf-8')
            child = IsolatedProcess([str(exe)], cwd=root, env=env)
            OWNER = child
            case['launcher_pid'] = child.pid
            log.write('Launcher contained in Windows Job; PID='+str(child.pid)+'\n'); log.flush()
            try:
                deadline = time.time()+120
                while time.time()<deadline:
                    if child.poll() is not None:
                        raise RuntimeError('Binaire arrêté au démarrage.')
                    try:
                        identity = api('/v1/runtime-identity')
                    except (OSError, RuntimeError) as error:
                        if isinstance(error, RuntimeError) and 'autre processus' in str(error):
                            raise
                        time.sleep(.5)
                        continue
                    if identity['http']!=200 or identity['body'].get('build')!=BUILD or identity['body'].get('version') != '1.0.0b8':
                        raise RuntimeError('Identité du serveur incorrecte.')
                    case['runtime_identity'] = identity['body']
                    case['server_pid'] = child.listener_pid()
                    break
                else:
                    raise RuntimeError('Binaire non prêt après 120 secondes.')
                tonight = api('/v1/tonight',{'availability':report['availability']})
                (root/'tonight.json').write_text(json.dumps(tonight,indent=2),encoding='utf-8')
                case['preparation_http'] = tonight['http']
                case['preparation_seconds'] = tonight['seconds']
                decision = tonight['body']
                case['night_date'] = decision.get('night_date')
                expected_night = (start_dt.date()-datetime.timedelta(days=1) if start_dt.hour<12 else start_dt.date()).isoformat()
                case['requested_night'] = expected_night
                case['intent_assessments'] = decision.get('acquisition_intent_assessments',[])
                if tonight['http']==200 and case['night_date'] is None:
                    case.update(result='NOT_VALIDATED',reason='requested_night_not_available',detail=decision)
                    print(intent,': aucune nuit disponible ; aucune confirmation.',flush=True)
                    continue
                if tonight['http']==200 and case['night_date']!=expected_night:
                    case.update(result='FAIL',reason='requested_night_mismatch' if case['night_date'] is not None else 'requested_night_missing')
                    print('Nuit renvoyée différente du créneau :',case['night_date'],expected_night,flush=True)
                    continue
                subject,selection_source = subject_for(decision,intent) if tonight['http']==200 else (None,None)
                if subject is None:
                    case.update(result='NOT_VALIDATED',reason='requested_intent_not_offered',creation_refusal=decision.get('creation_refusal'),detail=decision.get('detail'))
                    print(intent,': choix non proposé ; refus enregistré sans contournement.',flush=True)
                    continue
                selection = {'acceptance_request_id':'isolated-'+uuid.uuid4().hex,'decision_id':decision['decision_id'],'source':selection_source,'selected_catalog_key':subject['catalog_key'],'acquisition_intent_id':intent,'selected_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
                accepted = api('/v1/decision-selections',selection)
                (root/'selection.json').write_text(json.dumps({'request':selection,'response':accepted},indent=2),encoding='utf-8')
                body = accepted['body']
                mission = body.get('mission') or {}
                expected_filter = {'sh2-129_ha':'Ha', 'ou4_oiii':'OIII'}[intent]
                valid = (accepted['http']==200 and body.get('status')=='accepted'
                         and body.get('selected_acquisition_intent_id')==intent
                         and mission.get('acquisition_intent_id')==intent
                         and isinstance(mission.get('selected_filter'), dict)
                         and mission['selected_filter'].get('filter_type')==expected_filter
                         and case['night_date']==expected_night)
                case.update(result='PASS' if valid else 'FAIL',confirmation_http=accepted['http'],confirmation_seconds=accepted['seconds'],returned_intent=mission.get('acquisition_intent_id'),selected_filter=mission.get('selected_filter'),window_start=mission.get('window_start'),window_end=mission.get('window_end'))
                print(intent,case['result'],'préparation',round(tonight['seconds'],2),'s ; confirmation',round(accepted['seconds'],2),'s',flush=True)
            finally:
                if child is not None:
                    child.close()
                case['binary_stopped'] = child is None or child.stopped
                OWNER = None
                try:
                    deadline = time.monotonic()+5
                    remaining = IsolatedProcess.listening_pids()
                    while remaining and time.monotonic() < deadline:
                        time.sleep(.1)
                        remaining = IsolatedProcess.listening_pids()
                    if remaining:
                        raise OSError('Un serveur écoute encore sur le port 8000 : '+str(sorted(remaining)))
                    case['port_released'] = True
                except OSError:
                    case['port_released'] = False
                    raise RuntimeError('Le port 8000 n’est pas libéré ; test suivant annulé.')
                if log is not None:
                    log.write('Job stopped; descendants reaped; port 8000 released.\n')
                    log.close()
                    log = None
                child = None
    except (Exception, KeyboardInterrupt) as error:
        report['error'] = str(error) or type(error).__name__
        print('Test interrompu :',error,flush=True)
    finally:
        if child is not None:
            try:
                child.close()
            except Exception as error:
                report['cleanup_error'] = str(error)
        OWNER = None
        if log is not None:
            log.close()
        if before is not None:
            try:
                report['original_files_unchanged'] = snapshot(source)==before
            except (Exception, KeyboardInterrupt) as error:
                report['preservation_error'] = str(error)
        if report.get('error') or report.get('cleanup_error') or not report.get('original_files_unchanged'):
            report['overall_result'] = 'ERROR'
        elif any(c.get('result')=='FAIL' for c in report['cases']):
            report['overall_result'] = 'FAIL'
        elif len(report['cases'])==2 and all(c.get('result')=='PASS'
                and c.get('binary_stopped') and c.get('port_released') for c in report['cases']):
            report['overall_result'] = 'PASS'
        else:
            report['overall_result'] = 'NOT_VALIDATED'
        (out/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        result_zip = out.with_suffix('.zip')
        with zipfile.ZipFile(result_zip,'w',zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(out/'comparison.json','comparison.json')
            for intent in ['sh2-129_ha','ou4_oiii']:
                for name in ['binary.log','tonight.json','selection.json']:
                    entry = out/intent/name
                    if entry.is_file():
                        bundle.write(entry,intent+'/'+name)
            for intent in ['sh2-129_ha','ou4_oiii']:
                for location in ['LOCALAPPDATA','APPDATA']:
                    for entry in sorted((out/intent/location).rglob('*.log')):
                        if entry.is_file():
                            bundle.write(entry,entry.relative_to(out).as_posix())
        print('Résultat global :',report['overall_result'],flush=True)
        print('ZIP à joindre dans le chat :',result_zip,flush=True)
        print('Référence Mac du kit inchangée :',report.get('original_files_unchanged','non vérifié'),flush=True)
        print('La configuration Windows réelle n’a pas été utilisée.',flush=True)

if __name__=='__main__':
    main()
