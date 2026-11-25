"""Offline component bootstrap and bounded private journal."""
import json
import os
import socket
from types import SimpleNamespace

import pytest
from astropilot import real_weather_runtime as runtime
from astropilot import weather_relay as relay
from astropilot import real_weather_context as context


@pytest.mark.skipif(os.name == "nt", reason="Mac/POSIX private journal permissions")
def test_reserved_endpoint_and_private_rotating_journal(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    (root / "runtime").mkdir(mode=0o700)
    session = dict(session_id="b" * 64, kit_directory=str(root),
        data_directory=str(root / "DONNEES-FICTIVES/profil"),
        kit_device=root.stat().st_dev, kit_inode=root.stat().st_ino)
    monkeypatch.setenv("ASTROPILOT_LAUNCH_SESSION", json.dumps(session))
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", session["data_directory"])
    monkeypatch.setenv("NIGHTMERIT_COPY_KIND", "fictitious")
    monkeypatch.setattr(context, "_runtime", None)
    import astropilot.demo_mode as demo
    monkeypatch.setattr(demo, "_active", False)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0)); listener.listen()
    port = listener.getsockname()[1]
    if port < 20000:
        listener.close(); pytest.skip("OS selected port outside kit range")
    monkeypatch.setenv(runtime.CONFIG, json.dumps(dict(role="relay", application_port=25001 if port != 25001 else 25002,
                                                     relay_port=port, token="a" * 64)))
    def server(sock, state):
        assert sock.getsockname() == ("127.0.0.1", port)
        def serve_forever(**_):
            for i in range(12000):
                state.audit(category="relay_timeout", operations=i, duration_ms=30000)
        return SimpleNamespace(serve_forever=serve_forever, server_close=lambda: None)
    monkeypatch.setattr(relay, "relay_server", server)
    monkeypatch.setattr(relay, "fetch_upstream", lambda *_: pytest.fail("unexpected upstream operation"))
    assert runtime.main("relay", str(listener.detach())) == 0
    files = list((root / "runtime").iterdir())
    assert len(files) == 3
    assert all(p.stat().st_size <= 256 * 1024 and p.stat().st_mode & 0o777 == 0o600 for p in files)
    for path in files:
        for line in path.read_text().splitlines():
            assert set(json.loads(line)) == {"category", "operations", "duration_ms"}
    assert not (root / "DONNEES-FICTIVES").exists()


def test_bootstrap_refuses_demo_conflict_before_opening_socket(monkeypatch):
    import astropilot.demo_mode as demo
    monkeypatch.setattr(demo, "_active", True)
    with pytest.raises(ValueError, match="demo_conflict"):
        runtime.main("application", "123456")
