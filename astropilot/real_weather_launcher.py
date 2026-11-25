"""Explicit Mac fictitious-profile launcher; no port discovery or takeover."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

from astropilot.real_weather_runtime import CONFIG

NAP = .1


class LaunchError(ValueError):
    pass


def _read(path, limit=4 * 1024 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise LaunchError("real_weather_file_invalid")
    from astropilot.weather_relay import decode
    return decode(path.read_bytes())


def _private_json(path, value):
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix=".launch-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _process(pid):
    if type(pid) is not int or pid <= 1:
        raise LaunchError("real_weather_process_invalid")
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart=", "-o", "command="],
                            text=True, capture_output=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TZ": "UTC"})
    return result.stdout.strip() if result.returncode == 0 else None


def reserve(port):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        return listener
    except BaseException:
        listener.close()
        raise


class RealWeatherKit:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink() or self.root != self.root.resolve():
            raise LaunchError("real_weather_root_invalid")
        self.profile = self.root / "DONNEES-FICTIVES/profil"
        self.runtime = self.root / "runtime"
        self.exe = self.root / "candidate/AstroPilot.app/Contents/MacOS/AstroPilot"
        self.identity = [self.root.stat().st_dev, self.root.stat().st_ino]
        settings = _read(self.root / "KIT.json", 4096)
        if (not isinstance(settings, dict) or set(settings) != {"schema", "kind", "weather", "application_port", "relay_port", "source_commit"}
                or settings["schema"] != "nightmerit.real-weather-kit.v1"
                or settings["kind"] != "fictitious" or settings["weather"] != "real"
                or not isinstance(settings["source_commit"], str)
                or re.fullmatch("[0-9a-f]{40}", settings["source_commit"]) is None):
            raise LaunchError("real_weather_settings_invalid")
        for name in ("application_port", "relay_port"):
            if type(settings[name]) is not int or not 20000 <= settings[name] <= 65535:
                raise LaunchError("real_weather_settings_invalid")
        if settings["application_port"] == settings["relay_port"]:
            raise LaunchError("real_weather_settings_invalid")
        self.settings = settings
        for p in (self.runtime, self.root / "DONNEES-FICTIVES", self.profile, self.profile / "user_profile.json"):
            if p.is_symlink():
                raise LaunchError("real_weather_path_redirected")
        self.children = []
        self.stopping = False
        self._runtime_fd = None
        self.opener = build_opener(ProxyHandler({}))

    def validate_contents(self):
        manifest = _read(self.root / "MANIFESTE-APPLICATION.json")
        if not isinstance(manifest, dict) or not manifest:
            raise LaunchError("real_weather_manifest_invalid")
        for name, digest in manifest.items():
            if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
                    or not name.startswith("candidate/") or not isinstance(digest, str)):
                raise LaunchError("real_weather_manifest_invalid")
            path = self.root / name
            if (not path.resolve().is_relative_to(self.root) or path.is_symlink()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
                raise LaunchError("real_weather_application_modified")
        if str(self.exe.relative_to(self.root)) not in manifest or self.exe.is_symlink():
            raise LaunchError("real_weather_executable_invalid")
        links = _read(self.root / "MANIFESTE-LIENS.json")
        if not isinstance(links, dict):
            raise LaunchError("real_weather_links_invalid")
        for name, target in links.items():
            path = self.root / name
            if (Path(name).is_absolute() or ".." in Path(name).parts or not name.startswith("candidate/")
                    or not path.is_symlink() or os.readlink(path) != target
                    or not path.resolve().is_relative_to(self.root)):
                raise LaunchError("real_weather_links_invalid")

    @contextmanager
    def locked(self):
        import fcntl
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(self.root, directory_flags)
        try:
            info = os.fstat(root_fd)
            if [info.st_dev, info.st_ino] != self.identity:
                raise LaunchError("real_weather_root_invalid")
            try:
                os.mkdir("runtime", mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            runtime_fd = os.open("runtime", directory_flags, dir_fd=root_fd)
        finally:
            os.close(root_fd)
        try:
            info = os.fstat(runtime_fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise LaunchError("real_weather_runtime_permissions_invalid")
            fd = os.open("launcher.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=runtime_fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                previous = self._runtime_fd
                self._runtime_fd = runtime_fd
                try:
                    yield
                finally:
                    self._runtime_fd = previous
            finally:
                os.close(fd)
        finally:
            os.close(runtime_fd)

    def owned_process_record(self, session):
        """Read only our session record through the locked directory descriptor."""
        if self._runtime_fd is None:
            return None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open("processes.json", flags, dir_fd=self._runtime_fd)
            with os.fdopen(fd, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode) or opened.st_size > 16384:
                    return None
                from astropilot.weather_relay import decode
                record = decode(stream.read(16385))
            if (not isinstance(record, dict) or record.get("root_identity") != self.identity
                    or record.get("session_id") != session["session_id"]
                    or not isinstance(record.get("supervisor"), dict)
                    or record["supervisor"].get("pid") != os.getpid()):
                return None
            return record, opened
        except (OSError, ValueError):
            return None

    def process_record_unchanged(self, opened):
        current = os.stat("processes.json", dir_fd=self._runtime_fd, follow_symlinks=False)
        return (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino)

    def retire_exited_relays(self, session):
        # Only Popen objects created by this supervisor can confirm termination.
        exited = {child.pid for role, child in self.children
                  if role == "relay" and child.poll() is not None}
        if not exited:
            return False
        owned = self.owned_process_record(session)
        if owned is None:
            return False
        record, opened = owned
        children = record.get("children")
        if not isinstance(children, list) or any(not isinstance(item, dict) for item in children):
            return False
        remaining = [item for item in children
                     if not (item.get("role") == "relay" and item.get("pid") in exited)]
        if remaining == children:
            return False
        # Never resolve the old kit path after a move: both the temporary file
        # and its atomic replacement belong to the directory we still lock.
        temporary = ".launch-" + secrets.token_hex(16)
        created = False
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                         0o600, dir_fd=self._runtime_fd)
            created = True
            with os.fdopen(fd, "w") as stream:
                json.dump({**record, "children": remaining}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            if not self.process_record_unchanged(opened):
                return False
            os.replace(temporary, "processes.json", src_dir_fd=self._runtime_fd, dst_dir_fd=self._runtime_fd)
            return True
        finally:
            if created:
                try:
                    os.unlink(temporary, dir_fd=self._runtime_fd)
                except FileNotFoundError:
                    pass

    def cleanup_process_record(self, session):
        """Remove only our record in the directory held by our launcher lock.

        A moved copy must not resolve its old path into a replacement copy.
        Unreadable, redirected or foreign-session records are left untouched.
        """
        owned = self.owned_process_record(session)
        if owned is None:
            return False
        _, opened = owned
        try:
            if not self.process_record_unchanged(opened):
                return False
            os.unlink("processes.json", dir_fd=self._runtime_fd)
            return True
        except (OSError, ValueError):
            return False

    def session(self):
        return {"session_id": secrets.token_hex(32), "kit_directory": str(self.root),
                "data_directory": str(self.profile), "kit_device": self.identity[0], "kit_inode": self.identity[1]}

    def environment(self, session, role, token):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("ASTROPILOT_", "NIGHTMERIT_", "FIELD_LAB_", "PYTHON", "XDG_", "PYTEST_", "NM_"))
               and k not in {"HOME", "TMPDIR", "BASH_ENV", "ENV", "NETRC", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"}
               and "proxy" not in k.lower()}
        for key in ("HOME", "TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "FIELD_LAB_DATA_DIR"):
            directory = self.runtime / key
            if directory.is_symlink():
                raise LaunchError("real_weather_path_redirected")
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.stat().st_uid != os.getuid() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
                raise LaunchError("real_weather_runtime_permissions_invalid")
            env[key] = str(directory)
        env.update(ASTROPILOT_DATA_DIR=str(self.profile), ASTROPILOT_LAUNCH_SESSION=json.dumps(session),
                   NIGHTMERIT_COPY_KIND="fictitious", BROWSER="/usr/bin/true")
        value = {"role": role, "application_port": self.settings["application_port"], "relay_port": self.settings["relay_port"]}
        if role != "assistant":
            value["token"] = token
        env[CONFIG] = json.dumps(value)
        if not getattr(sys, "frozen", False):
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            # Development execution only; shipped binaries use their build hook.
            env["ASTROPILOT_BUILD_COMMIT"] = self.settings["source_commit"][:7]
        return env

    def spawn(self, role, listener, session, token):
        command = [str(self.exe)] if getattr(sys, "frozen", False) else [sys.executable, "-m", "astropilot.portable_entry"]
        if role != "relay":
            policy = "(version 1)(allow default)(deny network-outbound)"
            if role == "application":
                policy += '(allow network-outbound (remote ip "localhost:%d"))' % self.settings["relay_port"]
            command = ["/usr/bin/sandbox-exec", "-p", policy, *command]
        command += ["--real-weather-component", role, str(listener.fileno())]
        child = subprocess.Popen(command, cwd=self.root, env=self.environment(session, role, token),
            pass_fds=(listener.fileno(),), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        listener.close()
        self.children.append((role, child))
        return child, {"role": role, "pid": child.pid}

    def ready(self, child, role, session, token):
        port = self.settings["relay_port" if role == "relay" else "application_port"]
        route = "/health" if role == "relay" else "/v1/launcher-context"
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if child.poll() is not None or self.stopping:
                raise LaunchError("real_weather_startup_failed")
            request = Request("http://127.0.0.1:%d%s" % (port, route))
            if role == "relay":
                request.add_header("Authorization", "Bearer " + token)
            try:
                with self.opener.open(request, timeout=.5) as reply:
                    raw = reply.read(16385)
                    if len(raw) > 16384:
                        raise LaunchError("real_weather_identity_invalid")
                    data = json.loads(raw)
                    if role == "relay":
                        if reply.headers.get("X-NightMerit-Relay-Session") != session["session_id"] or data != {"ready": True}:
                            raise LaunchError("real_weather_identity_invalid")
                    elif data.get("session_id") != session["session_id"] or data.get("service") != role or data.get("location_status") != "available":
                        raise LaunchError("real_weather_identity_invalid")
                if role != "relay":
                    with self.opener.open("http://127.0.0.1:%d/v1/runtime-identity" % port, timeout=1) as reply:
                        identity = json.loads(reply.read(16384))
                    if identity["build"] != self.settings["source_commit"][:7] or identity["architecture"] != "arm64":
                        raise LaunchError("real_weather_build_invalid")
                if role == "application":
                    with self.opener.open("http://127.0.0.1:%d/v1/demo-context" % port, timeout=1) as reply:
                        mode = json.loads(reply.read(16384))
                    if mode["enabled"] is not False or mode["weather"] != "real":
                        raise LaunchError("real_weather_mode_invalid")
                # sandbox-exec replaces itself; capture identity only after the
                # component is ready, never its transient wrapper command.
                actual = _process(child.pid)
                if actual is None or "--real-weather-component " + role not in actual:
                    raise LaunchError("real_weather_child_identity_unavailable")
                return actual
            except (OSError, json.JSONDecodeError):
                time.sleep(NAP)
        raise LaunchError("real_weather_startup_timeout")

    def terminate_children(self):
        for _, child in reversed(self.children):
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

    def stop(self):
        record_path = self.runtime / "processes.json"
        if not record_path.exists():
            return
        record = _read(record_path, 16384)
        if record.get("root_identity") != self.identity:
            raise LaunchError("real_weather_process_identity_changed")
        # Validate every live identity before signalling any of them. Never HTTP-probe a foreign socket.
        live = []
        for item in record["children"]:
            actual = _process(item["pid"])
            if actual is None:
                continue
            if actual != item["process_identity"] or "--real-weather-component " + item["role"] not in actual:
                raise LaunchError("real_weather_process_identity_changed")
            live.append(item)
        for item in live:
            if _process(item["pid"]) != item["process_identity"]:
                raise LaunchError("real_weather_process_identity_changed")
        supervisor = record.get("supervisor")
        if (not isinstance(supervisor, dict)
                or _process(supervisor.get("pid")) != supervisor.get("process_identity")
                or not supervisor.get("process_identity")):
            raise LaunchError("real_weather_process_identity_changed")
        # The verified supervisor owns and waits its children. Do not signal
        # children directly and mistake an intentional stop for a crash.
        os.kill(supervisor["pid"], signal.SIGTERM)

    def run(self, action):
        if action not in {"start", "start-only", "data", "data-only", "stop"} or sys.platform != "darwin":
            raise LaunchError("real_weather_action_invalid")
        if action == "stop":
            # The active supervisor holds launcher.lock, so stopping uses identities only.
            return self.stop()
        with self.locked():
            self.validate_contents()
            listeners = []
            try:
                # Reserve both ports before any profile creation, including assistant mode.
                listeners = [reserve(self.settings["application_port"])]
                listeners.append(reserve(self.settings["relay_port"]))
                assistant = action in {"data", "data-only"}
                if not self.profile.exists():
                    if assistant:
                        self.profile.mkdir(parents=True, mode=0o700)
                    else:
                        from astropilot.profile_backup import create_backup, restore_empty
                        # Reuse the checked backup contract rather than copying links/keys.
                        archive, _ = create_backup(self.root / "EXEMPLE-FICTIF")
                        from astropilot.profile_backup import inspect_backup
                        files, _ = inspect_backup(archive)
                        restore_empty(self.profile, files)
                event = self.runtime / "open-application.json"
                if event.exists():
                    if event.is_symlink():
                        raise LaunchError("real_weather_event_invalid")
                    event.unlink()
                session, token = self.session(), secrets.token_hex(32)
                def closing(*_):
                    self.stopping = True
                old_signals = {sig: signal.signal(sig, closing) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
                try:
                    while True:
                        records = []
                        if not assistant:
                            relay, record = self.spawn("relay", listeners[1], session, token)
                            records.append(record)
                            record["process_identity"] = self.ready(relay, "relay", session, token)
                        child, record = self.spawn("assistant" if assistant else "application", listeners[0], session, token)
                        records.append(record)
                        record["process_identity"] = self.ready(child, "assistant" if assistant else "application", session, token)
                        _private_json(self.runtime / "processes.json", {"root_identity": self.identity, "children": records,
                            "supervisor": {"pid": os.getpid(), "process_identity": _process(os.getpid())},
                            "session_id": session["session_id"], "application_port": self.settings["application_port"]})
                        if action in {"start", "data"}:
                            subprocess.run(["/usr/bin/open", "http://127.0.0.1:%d/" % self.settings["application_port"]], check=True)
                        while child.poll() is None and not self.stopping:
                            # Reap only relay processes spawned by this supervisor.
                            # A dead relay must not remain a zombie whose changed
                            # ps identity would prevent the normal stop action.
                            # Keep the application open; never restart the relay.
                            self.retire_exited_relays(session)
                            time.sleep(NAP)
                        if self.stopping:
                            break
                        if assistant and child.returncode == 0 and event.exists() and _read(event, 4096) == {"session_id": session["session_id"]}:
                            event.unlink()
                            listeners[0] = reserve(self.settings["application_port"])
                            assistant = False
                            continue
                        if child.returncode != 0:
                            raise LaunchError("real_weather_application_exited")
                        break
                finally:
                    self.terminate_children()
                    self.cleanup_process_record(session)
                    for sig, handler in old_signals.items():
                        signal.signal(sig, handler)
            finally:
                for listener in listeners:
                    listener.close()


def main(root, action):
    try:
        RealWeatherKit(root).run(action)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print("NightMerit : ouverture impossible ou identité non confirmée. Aucune autre copie arrêtée.", file=sys.stderr)
        return 1
