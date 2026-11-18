"""Build a private demonstration on Windows, in a fresh directory only.

Run from a clean committed checkout with Python 3.13 x64 and uv installed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import uuid


def resolve_source_commit(source):
    """Fail before creating a build directory if provenance cannot be verified."""
    source = Path(source).resolve()
    def git(*args):
        return subprocess.run(['git', *args], cwd=source, check=True,
                              capture_output=True, text=True).stdout.strip()
    try:
        if Path(git('rev-parse', '--show-toplevel')).resolve() != source:
            raise ValueError('unexpected_source_root')
        commit = git('rev-parse', 'HEAD')
        if not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise ValueError('invalid_commit')
        if git('status', '--porcelain', '--untracked-files=all'):
            raise ValueError('uncommitted_source')
        return commit
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        raise SystemExit('La compilation exige une source Git enregistrée et sans modifications. '
                         'Enregistrez les changements ou utilisez une copie propre du dépôt.') from error


def main():
    if platform.system() != 'Windows' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise SystemExit('Compilation réservée à Windows x64 ; aucun exécutable Windows ne peut être produit ici.')
    if sys.version_info[:2] != (3, 13):
        raise SystemExit('Utilisez Python 3.13 x64 pour cette préparation privée.')
    source=Path(__file__).resolve().parents[1]
    source_commit = resolve_source_commit(source)
    task=Path.home()/'NM-Builds'
    task.mkdir(exist_ok=True)
    work=task/('demo-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    work.mkdir()
    tree=work/'source'
    shutil.copytree(source,tree,ignore=shutil.ignore_patterns('.git','.venv','build','dist','__pycache__','*.pyc'))
    env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_','PYTHONPATH','PYTHONHOME'))}
    env.update(ASTROPILOT_BUILD_COMMIT=source_commit[:7],UV_PROJECT_ENVIRONMENT=str(work/'venv'),UV_NO_ENV_FILE='1',PYINSTALLER_CONFIG_DIR=str(work/'pyinstaller-cache'))
    source_hashes={str(p.relative_to(tree)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tree.rglob('*') if p.is_file()}
    source_sha=hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode()).hexdigest()
    if resolve_source_commit(source) != source_commit:
        raise SystemExit('La source a changé pendant sa copie. Aucune compilation lancée.')
    log=work/'compilation.log'
    with log.open('wb') as stream:
        for command in ([sys.executable,'-m','uv','sync','--locked','--extra','packaging','--python',sys.executable],
                        [sys.executable,'-m','uv','run','--locked','--extra','packaging','python','-m','PyInstaller','--noconfirm','AstroPilot-windows.spec']):
            result=subprocess.run(command,cwd=tree,env=env,stdout=stream,stderr=subprocess.STDOUT)
            if result.returncode:raise SystemExit(f'Compilation arrêtée. Consultez {log}')
    kit=work/'NM-DEMO'
    kit.mkdir();shutil.copytree(tree/'dist/AstroPilot',kit/'candidate/AstroPilot')
    command='@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\nset "ASTROPILOT_DATA_DIR=%~dp0DONNEES-DEMO\\profil"\r\n"%~dp0candidate\\AstroPilot\\AstroPilot.exe" --demo-18831\r\nif errorlevel 1 pause\r\n'
    (kit/'DEMARRER-DEMO.cmd').write_bytes(command.encode('ascii'))
    transfer=command.replace('--demo-18831', '--demo-data-transfer-18831')
    (kit/'GERER-MES-DONNEES.cmd').write_bytes(transfer.encode('ascii'))
    (kit/'LIRE-MOI.txt').write_text('Démonstration privée Windows x64 — exécutable nouvellement compilé, à vérifier sur Windows avant transmission.\nDouble-cliquez sur DEMARRER-DEMO.cmd. Gardez sa fenêtre ouverte ; Ctrl+C pour arrêter. Profil fictif séparé dans DONNEES-DEMO. Météo simulée, pas de prévisions réelles. Port local 18831 uniquement.\nSite de test : Berne, latitude 46.95, longitude 7.45, Bortle 5 ; Samyang 135 + ASI183MM ; filtre Baader Ha Highspeed 6.5 nm.\nPour recommencer, extrayez une nouvelle copie du ZIP dans un nouveau dossier ; ne supprimez pas les anciennes données.\nAucun Python requis sur le PC du testeur après compilation. Si Windows affiche une alerte, relevez son texte ; ne désactivez pas les protections.\n',encoding='utf-8')
    (kit/'provenance.json').write_text(json.dumps({'source_commit':source_commit,'source_tree_sha256':source_sha,'platform':'Windows x64','native_validation':'required','demo_weather':'simulated'},indent=2))
    if (kit/'DONNEES-DEMO').exists():
        raise SystemExit('Le kit de distribution doit rester vierge.')
    (kit/'ESSAI-A-LIRE.txt').write_text("""NIGHTMERIT — ESSAI PRIVE WINDOWS x64
1. Extraire tout le ZIP dans un dossier court, par exemple C:/Users/votre-nom/NM-Test. Ne pas lancer depuis le ZIP.
2. Double-cliquer DEMARRER-DEMO.cmd, puis garder la fenetre de commande ouverte. Aucun Python a installer pour cet essai.
3. Verifier le bandeau ESSAI FICTIF — METEO SIMULEE. Il ne s'agit pas de previsions reelles.
4. Site fictif : TEST FRERE — Berne ; latitude 46.95 ; longitude 7.45 ; Bortle 5.
5. Materiel fictif : Samyang 135 + ASI183MM ; filtre Baader Ha Highspeed 6.5 nm.
6. Choisir Aidez-moi a choisir une cible, Toute la nuit, puis une cible autre que Sh2-129/Ou4. Objectif 3 heures, sans images deja acquises.
7. Creer le plan, demarrer puis terminer une seance fictive. Ajouter une seule fois 8 poses de 300 secondes : 40 minutes, 2 h 20 restantes.
8. Actualiser puis arreter par Ctrl+C et relancer depuis le meme dossier. Verifier plan, seance terminee et Deja ajoute : 0 h 40.
Sauvegarde : arreter la demo avec Ctrl+C, lancer GERER-MES-DONNEES.cmd, telecharger le ZIP et verifier sa presence dans Telechargements.
Restauration : extraire une NOUVELLE copie dans un autre dossier court ; ouvrir GERER-MES-DONNEES.cmd AVANT DEMARRER-DEMO.cmd ; choisir la sauvegarde et confirmer apres verification du resume. Les anciens dossiers restent conserves.
Pour signaler un probleme : noter l'action, le message et joindre une capture. En cas d'alerte Windows, ne pas desactiver les protections.
Aucun equipement photo pilote. Aucune publication ni synchronisation. Donnees fictives locales dans DONNEES-DEMO.
""", encoding='utf-8')
    manifest={str(p.relative_to(kit)):hashlib.sha256(p.read_bytes()).hexdigest() for p in kit.rglob('*') if p.is_file()}
    (kit/'manifest.json').write_text(json.dumps(manifest,indent=2))
    archive=shutil.make_archive(str(work/'NM-DEMO'),'zip',work,kit.name)
    print('Compilation terminée, validation Windows encore requise :',archive)


if __name__=='__main__':main()
