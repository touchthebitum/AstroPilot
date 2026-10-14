"""Launch only an isolated diagnostic worker; export evidence without the profile."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile

from kit_safety import guard_placement, safe_extract, reject_links
from windows_job import IsolatedProcess
from test_choix_helpers import snapshot

BASE = Path(__file__).resolve().parent
EXPORT = ('diagnostic.json', 'forecast-snapshot.json', 'forecast-raw.json',
          'forecast-hourly.csv', 'slice-scores.csv', 'cases.json', 'weather-attempts.json',
          'Resume.txt', 'worker.log')


def main():
    if sys.platform != 'win32':
        raise SystemExit('Ce kit est réservé à Windows.')
    guard_placement(BASE)
    # Every executable dependency and source file is verified before the child imports it.
    manifest = json.loads((BASE / 'Manifest-diagnostic.json').read_text(encoding='utf-8'))
    for name, digest in manifest.items():
        path = BASE / name
        reject_links(path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SystemExit('Fichier diagnostic absent ou modifié : ' + name)
    for folder in ('source', 'runtime-libs'):
        actual = {p.relative_to(BASE).as_posix() for p in (BASE / folder).rglob('*') if p.is_file()}
        if actual != {n for n in manifest if n.startswith(folder + '/')}:
            raise SystemExit('Inventaire diagnostic modifié : ' + folder)
    prov = json.loads((BASE / 'Kit-provenance.json').read_text(encoding='utf-8'))
    archive = BASE / 'Configuration-Mac-reference.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != prov['mac_reference_zip_sha256']:
        raise SystemExit('Référence Mac incorrecte.')
    reference = BASE / 'profil-Mac-reference'
    reject_links(reference)
    if not reference.exists():
        safe_extract(archive, reference)
    before = snapshot(reference)
    expected = json.loads((BASE / 'Manifest-configuration-Mac.json').read_text(encoding='utf-8'))
    if {n.replace('\\', '/'): h for n, h in before.items()} != expected:
        raise SystemExit('Référence Mac modifiée : utilisez un nouveau dossier extrait du kit.')
    while True:
        first = input('Première nuit AAAA-MM-JJ (Entrée = demain) : ').strip()
        first = first or (dt.date.today() + dt.timedelta(days=1)).isoformat()
        try:
            if len(first) != 10:
                raise ValueError()
            dt.date.fromisoformat(first)
            break
        except ValueError:
            print('Exemple : 2026-10-15, pas 12026. Recommencez.')
    if shutil.disk_usage(BASE).free < 2 * 1024**3:
        raise SystemExit('Prévoir au moins 2 Go libres pour le diagnostic.')
    out = BASE / ('resultats-diagnostic-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir()
    work = out / 'isolated-worker'
    work.mkdir()
    shutil.copytree(reference, work / 'data')
    if snapshot(work / 'data') != before or snapshot(reference) != before:
        raise SystemExit('Copie non conforme : aucun calcul lancé.')
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(('ASTROPILOT_', 'NIGHTMERIT_', 'PYTHON'))}
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'TMPDIR',
                'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'MPLCONFIGDIR'):
        path = work / key
        path.mkdir()
        env[key] = str(path)
    env.update(ASTROPILOT_DATA_DIR=str(work / 'data'), PYTHONDONTWRITEBYTECODE='1')
    report = {'source_sha': prov['source_sha'], 'first_night': first,
              'no_confirmation_sent': True, 'isolated_data_directory': str(work / 'data')}
    child = None
    try:
        print('Acquisition météo puis recherche sur les nuits couvertes ; cela peut prendre plusieurs minutes.', flush=True)
        child = IsolatedProcess([str(BASE / 'python-portable-3.13.5/python.exe'),
                                 '-B', str(BASE / 'diagnostic_worker.py'), first], work, env)
        deadline = time.monotonic() + 1500
        while child.poll() is None:
            if time.monotonic() >= deadline:
                raise RuntimeError('Délai de diagnostic dépassé ; processus arrêtés.')
            time.sleep(.5)
        report['worker_exit'] = child.poll()
        if report['worker_exit'] != 0:
            raise RuntimeError('Le diagnostic a échoué : consulter worker.log.')
    except (Exception, KeyboardInterrupt) as exc:
        report['error'] = str(exc) or type(exc).__name__
    finally:
        if child is not None:
            try:
                child.close()
                report['processes_stopped'] = child.stopped
            except Exception as exc:
                report['cleanup_error'] = str(exc)
        report['reference_files_unchanged'] = snapshot(reference) == before
        report['source_files'] = len(before)
        (out / 'isolation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        with zipfile.ZipFile(out.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(out / 'isolation.json', 'isolation.json')
            for name in EXPORT:
                path = work / name
                if path.is_file():
                    bundle.write(path, name)
        if (work / 'Resume.txt').exists():
            print((work / 'Resume.txt').read_text(encoding='utf-8'), flush=True)
        elif (work / 'diagnostic.json').exists():
            print((work / 'diagnostic.json').read_text(encoding='utf-8'), flush=True)
        print('ZIP à joindre :', out.with_suffix('.zip'), flush=True)
        print('Pour confirmer une fenêtre proposée, lancer ensuite Lancer-test-choix.cmd avec les heures indiquées.', flush=True)
        if report.get('error') or report.get('cleanup_error') or not report['reference_files_unchanged']:
            raise SystemExit('Diagnostic interrompu : ' + str(report))


if __name__ == '__main__':
    main()
