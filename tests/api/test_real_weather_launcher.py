"""Fictitious copies only: port collisions must fail before profile writes."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest
from astropilot import real_weather_launcher as launcher
from astropilot.real_weather_runtime import CONFIG

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Mac-only launcher filesystem contract")


def kit(tmp_path):
    root = tmp_path.resolve() / "Fictitious kit"
    root.mkdir()
    settings = dict(schema="nightmerit.real-weather-kit.v1", kind="fictitious", weather="real",
                    application_port=25001, relay_port=25002, source_commit="a" * 40)
    (root / "KIT.json").write_text(json.dumps(settings))
    name = "candidate/AstroPilot.app/Contents/MacOS/AstroPilot"
    exe = root / name
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"offline fixture, not a binary")
    (root / "MANIFESTE-APPLICATION.json").write_text(json.dumps({name: hashlib.sha256(exe.read_bytes()).hexdigest()}))
    (root / "MANIFESTE-LIENS.json").write_text("{}")
    return root


@pytest.mark.parametrize("key,value", [("application_port", 8000), ("relay_port", True),
    ("relay_port", 25001), ("weather", "simulated"), ("kind", "personal"), ("source_commit", "short")])
def test_invalid_settings_fail_before_profile_creation(tmp_path, key, value):
    root = kit(tmp_path)
    settings = json.loads((root / "KIT.json").read_text())
    settings[key] = value
    (root / "KIT.json").write_text(json.dumps(settings))
    with pytest.raises(launcher.LaunchError): launcher.RealWeatherKit(root)
    assert not (root / "DONNEES-FICTIVES").exists()


def test_busy_port_does_not_probe_stop_or_write_profile(tmp_path, monkeypatch):
    root = kit(tmp_path)
    with socket.socket() as foreign:
        foreign.bind(("127.0.0.1", 0))
        foreign.listen()
        settings = json.loads((root / "KIT.json").read_text())
        settings["application_port"] = foreign.getsockname()[1]
        if settings["application_port"] < 20000: pytest.skip("OS selected port outside kit range")
        (root / "KIT.json").write_text(json.dumps(settings))
        instance = launcher.RealWeatherKit(root)
        monkeypatch.setattr(launcher.sys, "platform", "darwin")
        monkeypatch.setattr(launcher.os, "kill", lambda *_: pytest.fail("foreign process signalled"))
        with pytest.raises(OSError): instance.run("start-only")
        foreign.settimeout(.05)
        with pytest.raises(TimeoutError): foreign.accept()
        assert not instance.profile.exists() and not instance.children


def test_runtime_environment_is_private_and_assistant_has_no_relay_token(tmp_path, monkeypatch):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    monkeypatch.setenv("HTTPS_PROXY", "http://secret")
    monkeypatch.setenv("ASTROPILOT_DEMO", "1")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/foreign")
    with instance.locked():
        env = instance.environment(instance.session(), "assistant", "b" * 64)
        assert "token" not in json.loads(env[CONFIG])
        assert all(key not in env for key in ("HTTPS_PROXY", "ASTROPILOT_DEMO", "REQUESTS_CA_BUNDLE"))
        assert Path(env["HOME"]).is_relative_to(instance.runtime)
        assert env["ASTROPILOT_DATA_DIR"] == str(instance.profile)
        assert instance.runtime.stat().st_mode & 0o777 == 0o700
        with pytest.raises(BlockingIOError):
            with instance.locked(): pytest.fail("double launcher acquired lock")


def test_manifest_tampering_is_refused(tmp_path):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    instance.exe.write_bytes(b"altered")
    with pytest.raises(launcher.LaunchError, match="modified"): instance.validate_contents()


def test_stop_checks_all_process_identities_before_signalling(tmp_path, monkeypatch):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    with instance.locked():
        launcher._private_json(instance.runtime / "processes.json", dict(root_identity=instance.identity,
            children=[dict(pid=101, role="relay", process_identity="expected --real-weather-component relay"),
                      dict(pid=102, role="application", process_identity="different")]))
    monkeypatch.setattr(launcher, "_process", lambda pid: "expected --real-weather-component relay" if pid == 101 else "foreign")
    monkeypatch.setattr(launcher.os, "kill", lambda *_: pytest.fail("signal sent before all identities checked"))
    with pytest.raises(launcher.LaunchError, match="identity_changed"): instance.stop()


def owned_record(instance, session):
    return dict(root_identity=instance.identity, session_id=session["session_id"],
                supervisor=dict(pid=os.getpid()), children=[])


def fictitious_profile(root, monkeypatch):
    from fastapi.testclient import TestClient
    from astropilot.app import create_app
    from test_configuration_api import configuration_payload
    profile = root / "DONNEES-FICTIVES/profil"
    with monkeypatch.context() as env:
        env.setenv("ASTROPILOT_DATA_DIR", str(profile))
        result = TestClient(create_app()).put("/v1/configuration", json=configuration_payload(
            projects={"Rosette": {"hours": 0, "target_hours": 3}}))
        assert result.status_code == 200, result.text
    return (profile / "user_profile.json").read_bytes()


def test_moved_copy_cleanup_preserves_replacement_copy_and_profiles(tmp_path, monkeypatch):
    original = kit(tmp_path)
    a = launcher.RealWeatherKit(original)
    profile_a = fictitious_profile(original, monkeypatch)
    with a.locked():
        session_a = a.session()
        launcher._private_json(a.runtime / "processes.json", owned_record(a, session_a))
        moved = tmp_path / "Moved fictitious copy"
        original.rename(moved)
        replacement = kit(tmp_path)
        b = launcher.RealWeatherKit(replacement)
        profile_b = fictitious_profile(replacement, monkeypatch)
        with b.locked():
            session_b = b.session()
            launcher._private_json(b.runtime / "processes.json", owned_record(b, session_b))
            record_b = (b.runtime / "processes.json").read_bytes()
            assert a.cleanup_process_record(session_a) is True
            assert (b.runtime / "processes.json").read_bytes() == record_b
            assert not (moved / "runtime/processes.json").exists()
            assert (moved / "DONNEES-FICTIVES/profil/user_profile.json").read_bytes() == profile_a
            assert (replacement / "DONNEES-FICTIVES/profil/user_profile.json").read_bytes() == profile_b


@pytest.mark.parametrize("kind", ["other_session", "other_root", "other_supervisor", "invalid_json", "symlink"])
def test_cleanup_leaves_unowned_or_unreadable_record_untouched(tmp_path, kind):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    with instance.locked():
        session = instance.session()
        record = owned_record(instance, session)
        path = instance.runtime / "processes.json"
        if kind == "other_session": record["session_id"] = "foreign-session"
        if kind == "other_root": record["root_identity"] = [0, 0]
        if kind == "other_supervisor": record["supervisor"]["pid"] += 1
        if kind == "invalid_json": path.write_text("{incomplete")
        elif kind == "symlink":
            target = tmp_path / "foreign-record.json"
            target.write_text(json.dumps(record))
            path.symlink_to(target)
        else: launcher._private_json(path, record)
        before = path.read_bytes()
        assert instance.cleanup_process_record(session) is False
        assert path.read_bytes() == before
        assert path.is_symlink() == (kind == "symlink")


@pytest.mark.skipif(sys.platform != "darwin", reason="Mac OS network enforcement")
def test_os_policy_denies_other_loopback_port():
    # Only our two freshly reserved sockets, never existing instances or upstream.
    with socket.socket() as allowed, socket.socket() as denied:
        for listener in (allowed, denied):
            listener.bind(("127.0.0.1", 0)); listener.listen()
        port = allowed.getsockname()[1]
        policy = '(version 1)(allow default)(deny network-outbound)(allow network-outbound (remote ip "localhost:%d"))' % port
        script = """import socket,sys
s=socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=1);s.close()
try: socket.create_connection(('127.0.0.1',int(sys.argv[2])),timeout=1)
except OSError: pass
else: raise AssertionError('Unpermitted port accessible')
"""
        subprocess.run(["/usr/bin/sandbox-exec", "-p", policy, sys.executable, "-c", script,
                        str(port), str(denied.getsockname()[1])], check=True, timeout=10)


@pytest.mark.parametrize("relay_exit", [0, 124])
def test_supervisor_reaps_exited_relay_while_application_remains_open(
        tmp_path, monkeypatch, relay_exit):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    instance.profile.mkdir(parents=True)
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    monkeypatch.setattr(instance, "validate_contents", lambda: None)
    monkeypatch.setattr(instance, "ready", lambda child, role, *_: "owned " + role)
    monkeypatch.setattr(launcher, "_process", lambda pid: "owned supervisor")
    spawned = {}
    real_sleep = launcher.time.sleep
    real_reserve = launcher.reserve
    monkeypatch.setattr(launcher, "reserve", lambda _: real_reserve(0))

    def spawn(role, listener, *_):
        assert role not in spawned, "Exited relay must never be restarted"
        code = "import sys; sys.exit(%d)" % relay_exit if role == "relay" else "import time; time.sleep(60)"
        child = subprocess.Popen([sys.executable, "-c", code])
        spawned[role] = child
        instance.children.append((role, child))
        listener.close()
        return child, dict(role=role, pid=child.pid)

    ticks = 0
    def tick(_):
        nonlocal ticks
        ticks += 1
        assert ticks < 200, "Exited relay was never reaped while application stayed open"
        real_sleep(.01)
        # Inspect returncode without polling here: only the supervisor may reap.
        if spawned["relay"].returncode is not None:
            assert spawned["relay"].returncode == relay_exit
            assert spawned["application"].poll() is None
            tracked = json.loads((instance.runtime / "processes.json").read_text())
            assert [item["role"] for item in tracked["children"]] == ["application"]
            instance.stopping = True

    monkeypatch.setattr(instance, "spawn", spawn)
    from types import SimpleNamespace
    monkeypatch.setattr(launcher, "time", SimpleNamespace(sleep=tick, monotonic=launcher.time.monotonic))
    instance.run("start-only")
    assert set(spawned) == {"relay", "application"}
    assert all(child.poll() is not None for child in spawned.values())
    assert not (instance.runtime / "processes.json").exists()


def tracked_children():
    return [dict(pid=101, role="relay", process_identity="old --real-weather-component relay"),
            dict(pid=102, role="application", process_identity="ours --real-weather-component application")]


def fake_relay(instance, returncode=124):
    from types import SimpleNamespace
    instance.children = [("relay", SimpleNamespace(pid=101, poll=lambda: returncode))]


@pytest.mark.parametrize("relay_exit", [0, 124])
def test_retired_relay_pid_reuse_stops_only_our_supervisor(tmp_path, monkeypatch, relay_exit):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    with instance.locked():
        session = instance.session()
        record = owned_record(instance, session)
        record.update(children=tracked_children(), supervisor=dict(pid=os.getpid(), process_identity="our supervisor"))
        launcher._private_json(instance.runtime / "processes.json", record)
        fake_relay(instance, relay_exit)
        assert instance.retire_exited_relays(session) is True
        after = json.loads((instance.runtime / "processes.json").read_text())
        assert after == {**record, "children": [record["children"][1]]}
        assert (instance.runtime / "processes.json").stat().st_mode & 0o777 == 0o600
        assert instance.retire_exited_relays(session) is False
        calls = []
        def identity(pid):
            assert pid != 101, "Retired PID, now foreign, must never be probed"
            return "our supervisor" if pid == os.getpid() else record["children"][1]["process_identity"]
        monkeypatch.setattr(launcher, "_process", identity)
        monkeypatch.setattr(launcher.os, "kill", lambda pid, sig: calls.append((pid, sig)))
        instance.stop()
        assert calls == [(os.getpid(), launcher.signal.SIGTERM)]
        assert not list(instance.runtime.glob(".launch-*"))


def test_live_relay_is_never_retired(tmp_path):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    with instance.locked():
        session = instance.session()
        record = {**owned_record(instance, session), "children": tracked_children()}
        launcher._private_json(instance.runtime / "processes.json", record)
        before = (instance.runtime / "processes.json").read_bytes()
        fake_relay(instance, None)
        assert instance.retire_exited_relays(session) is False
        assert (instance.runtime / "processes.json").read_bytes() == before


@pytest.mark.parametrize("kind", ["other_session", "other_root", "other_supervisor", "invalid_json", "symlink"])
def test_retirement_preserves_unowned_records(tmp_path, kind):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    with instance.locked():
        session = instance.session()
        record = {**owned_record(instance, session), "children": tracked_children()}
        path = instance.runtime / "processes.json"
        if kind == "other_session": record["session_id"] = "foreign-session"
        if kind == "other_root": record["root_identity"] = [0, 0]
        if kind == "other_supervisor": record["supervisor"]["pid"] += 1
        if kind == "invalid_json": path.write_text("{incomplete")
        elif kind == "symlink":
            target = tmp_path / "foreign.json"
            target.write_text(json.dumps(record))
            path.symlink_to(target)
        else: launcher._private_json(path, record)
        before = path.read_bytes()
        fake_relay(instance)
        assert instance.retire_exited_relays(session) is False
        assert path.read_bytes() == before
        assert path.is_symlink() == (kind == "symlink")
        assert not list(instance.runtime.glob(".launch-*"))


def test_moved_copy_retirement_preserves_replacement_and_both_profiles(tmp_path, monkeypatch):
    original = kit(tmp_path)
    a = launcher.RealWeatherKit(original)
    profile_a = fictitious_profile(original, monkeypatch)
    with a.locked():
        session_a = a.session()
        record_a = {**owned_record(a, session_a), "children": tracked_children()}
        launcher._private_json(a.runtime / "processes.json", record_a)
        moved = tmp_path / "Moved fictitious copy"
        original.rename(moved)
        replacement = kit(tmp_path)
        b = launcher.RealWeatherKit(replacement)
        profile_b = fictitious_profile(replacement, monkeypatch)
        with b.locked():
            session_b = b.session()
            launcher._private_json(b.runtime / "processes.json", owned_record(b, session_b))
            before_b = (b.runtime / "processes.json").read_bytes()
            fake_relay(a)
            assert a.retire_exited_relays(session_a) is True
            assert json.loads((moved / "runtime/processes.json").read_text()) == {
                **record_a, "children": [record_a["children"][1]]}
            assert (b.runtime / "processes.json").read_bytes() == before_b
            assert (moved / "DONNEES-FICTIVES/profil/user_profile.json").read_bytes() == profile_a
            assert (replacement / "DONNEES-FICTIVES/profil/user_profile.json").read_bytes() == profile_b
            assert not list((moved / "runtime").glob(".launch-*"))


def test_retirement_does_not_overwrite_record_replaced_during_write(tmp_path, monkeypatch):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    with instance.locked():
        session = instance.session()
        path = instance.runtime / "processes.json"
        launcher._private_json(path, {**owned_record(instance, session), "children": tracked_children()})
        fake_relay(instance)
        replacement = {"foreign": "replacement must be preserved"}
        unchanged = instance.process_record_unchanged
        def replace_before_check(opened):
            launcher._private_json(path, replacement)
            return unchanged(opened)
        monkeypatch.setattr(instance, "process_record_unchanged", replace_before_check)
        assert instance.retire_exited_relays(session) is False
        assert json.loads(path.read_text()) == replacement
        assert not list(instance.runtime.glob(".launch-*"))


def test_retirement_preserves_unowned_temporary_file(tmp_path, monkeypatch):
    instance = launcher.RealWeatherKit(kit(tmp_path))
    with instance.locked():
        session = instance.session()
        path = instance.runtime / "processes.json"
        launcher._private_json(path, {**owned_record(instance, session), "children": tracked_children()})
        before = path.read_bytes()
        fake_relay(instance)
        monkeypatch.setattr(launcher.secrets, "token_hex", lambda _: "collision")
        foreign = instance.runtime / ".launch-collision"
        foreign.write_bytes(b"must remain untouched")
        with pytest.raises(FileExistsError): instance.retire_exited_relays(session)
        assert foreign.read_bytes() == b"must remain untouched"
        assert path.read_bytes() == before
