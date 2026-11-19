"""Standalone, stdlib-only Mac kit launcher. Copied as manage.py into each kit."""
from contextlib import contextmanager
import fcntl
import json
import hashlib
import os
from pathlib import Path
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request


class LaunchError(RuntimeError):
    pass


class KitManager:
    def __init__(self, root, port=18831, copy_kind=None):
        self.root = Path(root).resolve()
        if type(port) is not int or port not in {18831, 18841, 18871}:
            raise LaunchError('Le port de cette copie n’est pas pris en charge.')
        if copy_kind is not None and (not isinstance(copy_kind, str) or copy_kind not in {'personal', 'fictitious'}):
            raise LaunchError('Le type de cette copie est invalide. Conservez le kit et vérifiez son fichier KIT.json.')
        self.copy_kind = copy_kind
        self.port = port
        self.profile = self.root / 'DONNEES-PERSONNELLES/profil'
        self.exe = self.root / 'candidate/AstroPilot.app/Contents/MacOS/AstroPilot'
        self.runtime = self.root / 'runtime'
        self.base = f'http://127.0.0.1:{port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def listener(self):
        result = subprocess.run(['/usr/sbin/lsof', '-t', f'-iTCP:{self.port}', '-sTCP:LISTEN'],
                                capture_output=True, text=True)
        values = set(result.stdout.split())
        if result.returncode not in (0, 1) or len(values) > 1 or any(not p.isdecimal() for p in values):
            raise LaunchError('Impossible d’identifier la session locale. Aucune application n’a été arrêtée.')
        return int(next(iter(values))) if values else None

    def read(self, endpoint):
        with self.opener.open(self.base + endpoint, timeout=3) as reply:
            raw = reply.read(16385)
        if len(raw) > 16384:
            raise LaunchError('Réponse d’identification trop longue.')
        return json.loads(raw)

    @staticmethod
    def start_time(pid):
        result = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'lstart='], capture_output=True,
                                text=True, env={**os.environ, 'LC_ALL': 'C', 'TZ': 'UTC'})
        value = result.stdout.strip()
        if result.returncode or not value:
            raise LaunchError('La session ne peut plus être identifiée. Aucune application n’a été arrêtée.')
        return value

    def root_identity(self):
        info = self.root.stat()
        return [info.st_dev, info.st_ino]

    def load_record(self):
        path = self.runtime / 'process.json'
        if path.is_symlink() or path.stat().st_size > 16384:
            raise LaunchError('L’identité conservée de cette copie est invalide.')
        return json.loads(path.read_text())

    def owner(self):
        pid = self.listener()
        if pid is None:
            return None
        try:
            record = self.load_record()
            if (record['root_identity'] != self.root_identity() or type(record['pid']) is not int
                or record['pid'] != pid or self.start_time(pid) != record['process_start']):
                raise ValueError()
            identity = self.read('/v1/launcher-context')
            if (identity.get('status') != 'managed' or identity.get('session_id') != record['session_id']
                or identity.get('service') not in {'application', 'assistant'}):
                raise ValueError()
            return {'pid': pid, 'record': record, 'identity': identity,
                    'moved': record['kit_directory'] != str(self.root)
                             or identity.get('location_status') != 'available'}
        except (OSError, ValueError, KeyError, TypeError, LaunchError):
            raise LaunchError('Une autre copie utilise ce port, ou l’identité de la session ne peut pas être confirmée. '
                              'Fermez-la depuis son propre dossier ou son Terminal. Aucune application n’a été arrêtée.') from None

    def pending_session(self):
        """An assistant can release its socket briefly while opening the application."""
        try:
            record = self.load_record()
            if (record['root_identity'] != self.root_identity() or type(record['pid']) is not int
                or self.start_time(record['pid']) != record['process_start']):
                return False
            command = subprocess.run(['/bin/ps', '-p', str(record['pid']), '-o', 'command='],
                                     capture_output=True, text=True)
            return (command.returncode == 0
                    and command.stdout.strip().startswith(record['executable'] + ' --private-')
                    and any(flag in command.stdout for flag in
                            (f'--private-data-transfer-{self.port}', f'--private-test-server-{self.port}')))
        except (OSError, ValueError, KeyError, TypeError, LaunchError):
            return False

    def settled_owner(self):
        deadline = time.monotonic() + 15
        while True:
            owned = self.owner()
            if owned is not None or not self.pending_session():
                return owned
            if time.monotonic() >= deadline:
                raise LaunchError('Cette copie est encore en cours d’ouverture ou de changement de mode. '
                                  'Attendez avant de réessayer ; aucune seconde application n’a été lancée.')
            time.sleep(.1)

    def validate_paths(self):
        # Refuse links that could redirect profile or runtime writes into another copy.
        for path in (self.runtime, self.runtime / 'process.json', self.root / 'DONNEES-PERSONNELLES', self.profile,
                     self.profile / 'user_profile.json'):
            if path.is_symlink():
                raise LaunchError('Un lien redirige les données ou le lanceur. Utilisez une copie indépendante du kit.')
        if self.exe.is_symlink() or not self.exe.is_file() or not self.exe.resolve().is_relative_to(self.root):
            raise LaunchError('L’application manque dans ce dossier. Extrayez entièrement le ZIP dans un nouveau dossier.')

    @contextmanager
    def locked(self):
        if self.runtime.is_symlink():
            raise LaunchError('Le dossier technique redirige vers une autre copie. Aucune intervention.')
        self.runtime.mkdir(mode=0o700, exist_ok=True)
        descriptor = os.open(self.runtime / '.launcher.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LaunchError('Un lancement ou un arrêt est déjà en cours. Attendez avant de réessayer.')
                    time.sleep(.1)
            yield
        finally:
            os.close(descriptor)

    def save_record(self, value):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.runtime, prefix='.process-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(value, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.runtime / 'process.json')
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def environment(self, session):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('ASTROPILOT_', 'NIGHTMERIT_', 'FIELD_LAB_', 'PYTHON', 'PYTEST_', 'XDG_', 'NM_TEST_'))
               and k not in ('HOME', 'TMPDIR', 'BASH_ENV', 'ENV') and 'proxy' not in k.lower()}
        for name in ('home', 'temp', 'cache', 'config', 'state', 'field-lab'):
            (self.runtime / name).mkdir(mode=0o700, exist_ok=True)
        env.update(HOME=str(self.runtime / 'home'), TMPDIR=str(self.runtime / 'temp'),
                   XDG_CACHE_HOME=str(self.runtime / 'cache'), XDG_CONFIG_HOME=str(self.runtime / 'config'),
                   XDG_STATE_HOME=str(self.runtime / 'state'), ASTROPILOT_DATA_DIR=str(self.profile),
                   FIELD_LAB_DATA_DIR=str(self.runtime / 'field-lab'), BROWSER='/usr/bin/true',
                   ASTROPILOT_LAUNCH_SESSION=json.dumps(session))
        if self.copy_kind is not None:
            env['NIGHTMERIT_COPY_KIND'] = self.copy_kind
        return env

    def remember_profile(self, owned):
        if (self.profile / 'user_profile.json').is_file() and not owned['record'].get('known_profile'):
            record = dict(owned['record'], known_profile=True)
            try:
                self.save_record(record)
            except OSError:
                # Failure to update launch metadata must not prevent a verified stop.
                pass

    def check_missing_profile(self):
        if (self.profile / 'user_profile.json').is_file():
            return
        try:
            record = self.load_record()
            known = (record.get('root_identity') == self.root_identity()
                     and record.get('known_profile') is True)
        except (OSError, ValueError, TypeError, AttributeError, LaunchError):
            known = False
        if known:
            raise LaunchError('Le profil précédemment utilisé n’est plus à son emplacement. '
                              'Conservez cette copie et retrouvez son dossier de données ou votre sauvegarde. '
                              'Aucun profil vide ne sera recréé automatiquement.')
        runtime_only = {'.outcome_history_cursor.key', '.outcome_history_cursor.key.lock',
                        '.user_profile.lock', '.DS_Store', 'Logs', 'guardian', 'guardian_scheduler'}
        if self.profile.exists() and any(p.is_symlink() or p.name not in runtime_only
                                         for p in self.profile.iterdir()):
            raise LaunchError('Des fichiers sont présents mais le profil ne peut pas être identifié. '
                              'Conservez-les et utilisez GERER-MES-DONNEES.command ; ne recréez pas vos projets ici.')

    def stop(self):
        owned = self.settled_owner()
        if owned is None:
            return 'Cette copie est déjà arrêtée.'
        # Recheck both the live socket and the process start time immediately before signalling.
        if (self.listener() != owned['pid']
            or self.start_time(owned['pid']) != owned['record']['process_start']):
            raise LaunchError('La session a changé ; aucun arrêt n’a été demandé.')
        self.remember_profile(owned)
        os.kill(owned['pid'], signal.SIGTERM)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            pid = self.listener()
            if pid is None:
                return 'Cette copie est arrêtée. Vos données sont conservées.'
            if pid != owned['pid']:
                raise LaunchError('Cette copie est fermée, mais un autre programme utilise maintenant le port. Aucune intervention sur ce programme.')
            time.sleep(.1)
        raise LaunchError('L’arrêt est encore en cours. Attendez ; aucune fermeture forcée n’a été effectuée.')

    def start(self, service):
        owned = self.settled_owner()
        if owned:
            if owned['moved']:
                raise LaunchError('Cette copie a été déplacée pendant son utilisation. '
                                  'Lancez ARRETER-MES-PROJETS.command dans ce dossier, puis rouvrez cette copie. Vos données restent conservées.')
            if owned['identity']['service'] != service:
                raise LaunchError('Cette copie est déjà ouverte dans un autre mode. Fermez-la avec '
                                  'ARRETER-MES-PROJETS.command avant d’ouvrir l’application ou l’assistant de sauvegarde.')
            self.remember_profile(owned)
            return
        if any(part in {'.Trash', '.Trashes'} for part in self.root.parts):
            raise LaunchError('Ce kit est dans la Corbeille. Replacez-le dans Documents avant de l’ouvrir. Aucune donnée n’a été modifiée.')
        self.validate_paths()
        if service == 'application':
            self.check_missing_profile()
        root_device, root_inode = self.root_identity()
        session = {'session_id': secrets.token_hex(32), 'kit_directory': str(self.root),
                   'data_directory': str(self.profile), 'kit_device': root_device, 'kit_inode': root_inode}
        env = self.environment(session)
        flag = f'--private-{"data-transfer" if service == "assistant" else "test-server"}-{self.port}'
        with (self.runtime / 'server.log').open('ab') as log:
            proc = subprocess.Popen([str(self.exe), flag], cwd=self.root, env=env,
                                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            record = {**session, 'root_identity': [root_device, root_inode], 'pid': proc.pid,
                      'process_start': self.start_time(proc.pid), 'executable': str(self.exe),
                      'known_profile': (self.profile / 'user_profile.json').is_file()}
            self.save_record(record)
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise LaunchError('Le démarrage n’a pas abouti. Consultez runtime/server.log ; vos anciennes données sont conservées.')
                try:
                    live = self.owner()
                    if live and live['pid'] == proc.pid and live['identity']['service'] == service:
                        return
                except LaunchError:
                    pass
                time.sleep(.2)
            raise LaunchError('Le démarrage prend trop de temps. Réessayez après avoir vérifié runtime/server.log.')
        except BaseException:
            # This is our own newly spawned process, never a discovered foreign listener.
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            raise

    def browser(self):
        chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        owned = self.owner()
        if not owned or owned['moved']:
            raise LaunchError('La session a changé ; rouvrez cette copie avant de continuer.')
        if not chrome.is_file():
            return 'Le serveur est prêt. Ouvrez cette adresse dans votre navigateur : ' + self.base + '/'
        session = {k: owned['record'][k] for k in ('session_id', 'kit_directory', 'data_directory', 'kit_device', 'kit_inode')}
        try:
            with (self.runtime / 'browser.log').open('ab') as log:
                subprocess.Popen([str(chrome), '--user-data-dir=' + str(self.runtime / 'browser-profiles' / hashlib.sha256(
                                      f"{session['kit_device']}:{session['kit_inode']}:{self.profile.relative_to(self.root).as_posix()}".encode()).hexdigest()),
                                  '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
                                  '--disable-sync', '--new-window', self.base + '/'],
                                 env=self.environment(session),
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            return 'Cette copie est prête : ' + self.base + '/'
        except OSError:
            return 'Le serveur est prêt, mais le navigateur n’a pas pu être ouvert. Adresse : ' + self.base + '/'

    def run(self, action):
        if action not in {'open', 'start-only', 'data', 'data-only', 'stop'}:
            raise LaunchError('Commande inconnue.')
        with self.locked():
            if action == 'stop':
                return self.stop()
            self.start('assistant' if action in {'data', 'data-only'} else 'application')
            return self.browser() if action in {'open', 'data'} else 'Cette copie est prête : ' + self.base + '/'


def main(root=None, argv=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    args = sys.argv[1:] if argv is None else argv
    try:
        port = 18831
        copy_kind = None
        settings = root / 'KIT.json'
        if settings.exists():
            if settings.is_symlink() or settings.stat().st_size > 4096:
                raise LaunchError('Le réglage du lanceur est invalide.')
            value = json.loads(settings.read_text())
            if not isinstance(value, dict):
                raise LaunchError('Le réglage du lanceur est invalide.')
            port = value.get('port', port)
            copy_kind = value.get('copy_kind')
        if len(args) != 1:
            raise LaunchError('Choisissez l’ouverture, la sauvegarde ou l’arrêt depuis les lanceurs du kit.')
        print(KitManager(root, port, copy_kind=copy_kind).run(args[0]))
        return 0
    except (LaunchError, OSError, ValueError) as exc:
        message = str(exc) if isinstance(exc, LaunchError) else (
            'Le lanceur ne peut pas accéder à ses fichiers. Vérifiez que le ZIP est entièrement extrait '
            'dans un dossier accessible ; vos données existantes restent conservées.')
        print('NightMerit : ' + message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
