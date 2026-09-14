import threading
from pathlib import Path
from urllib.error import URLError

import pytest

from astropilot import launcher
from astropilot.app import app


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.value += duration


@pytest.fixture(autouse=True)
def isolated_user_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path / "user-data"))
    monkeypatch.setattr(launcher, "_home_directory", lambda: tmp_path)
    probe_port = launcher._probe_port

    def isolated_probe(**kwargs):
        return probe_port(**kwargs) if kwargs else launcher.PortState.FREE

    monkeypatch.setattr(launcher, "_probe_port", isolated_probe)


def launcher_log():
    return launcher._get_log_path().read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def test_launcher_has_stable_loopback_origin():
    assert launcher.HOST == "127.0.0.1"
    assert launcher.HOST != "0.0.0.0"
    assert launcher.PORT == 8000
    assert launcher.BROWSER_URL == "http://127.0.0.1:8000/"
    assert (
        launcher.IDENTITY_URL
        == "http://127.0.0.1:8000/v1/runtime-identity"
    )
    assert callable(launcher.main)


def test_log_path_uses_macos_user_logs_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "_home_directory", lambda: tmp_path)

    assert launcher._get_log_path() == (
        tmp_path / "Library" / "Logs" / "AstroPilot" / "AstroPilot.log"
    )


def test_logger_creates_rotating_file_once(tmp_path):
    log_path = tmp_path / "nested" / "AstroPilot.log"

    first, first_path = launcher._configure_launcher_logger(log_path=log_path)
    second, second_path = launcher._configure_launcher_logger(log_path=log_path)
    first.info("persistent-test-entry")
    for handler in first.handlers:
        handler.flush()

    managed = [
        handler
        for handler in first.handlers
        if getattr(handler, "_astropilot_launcher_handler", False)
    ]
    assert first is second
    assert first_path == second_path == log_path
    assert len(managed) == 1
    assert log_path.is_file()
    assert "persistent-test-entry" in log_path.read_text(encoding="utf-8")


def test_existing_instance_logs_runtime_metadata_and_browser_result(monkeypatch):
    monkeypatch.setattr(launcher, "canonical_version", lambda: "1.0.0b2")
    monkeypatch.setattr(launcher, "build_identifier", lambda: "8541acc")
    monkeypatch.setattr(launcher.platform, "machine", lambda: "test-architecture")

    launcher.run(
        port_probe=lambda: launcher.PortState.EXISTING,
        browser_open=lambda url: True,
    )

    log = launcher_log()
    assert "launcher_start" in log
    assert "version=1.0.0b2" in log
    assert "build=8541acc" in log
    assert "python=" in log
    assert "architecture=test-architecture" in log
    assert "host=127.0.0.1" in log
    assert "port=8000" in log
    assert "preflight=existing_astropilot" in log
    assert "existing_instance_detected" in log
    assert "browser_open_succeeded" in log


def test_browser_failure_is_diagnostic_without_marking_healthy_server_failed(
    monkeypatch,
    capsys,
):
    def browser_failure(url):
        raise RuntimeError("browser unavailable")

    result = launcher.run(
        port_probe=lambda: launcher.PortState.EXISTING,
        browser_open=browser_failure,
    )

    assert result is None
    assert "browser_open_failed" in launcher_log()
    assert str(launcher._get_log_path()) in capsys.readouterr().err


@pytest.mark.parametrize(
    "body",
    [
        b'{"application":"astropilot"}',
        b'{"application":"astropilot","version":"1.0.0b2",'
        b'"build":"8541acc","architecture":"arm64"}',
        b'{"application":"astropilot","version":"9.9.9"}',
        b'{"application":"astropilot","build":"fffffff"}',
        b'{"application":"astropilot","architecture":"x86_64"}',
    ],
)
def test_identity_probe_is_bounded_and_accepts_compatible_identity(body):
    calls = []

    def urlopen(url, *, timeout):
        calls.append((url, timeout))
        return FakeResponse(200, body)

    assert launcher._probe_port(urlopen=urlopen) is launcher.PortState.EXISTING
    assert calls == [(launcher.IDENTITY_URL, launcher.PROBE_TIMEOUT_SECONDS)]


def test_connection_refusal_means_port_is_free():
    def refused(url, *, timeout):
        raise URLError(ConnectionRefusedError("connection refused"))

    assert launcher._probe_port(urlopen=refused) is launcher.PortState.FREE


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (404, b'{"application":"astropilot"}'),
        (200, b"not-json"),
        (200, b'"astropilot"'),
        (200, b'[]'),
        (200, b'{}'),
        (200, b'{"application":"another"}'),
    ],
)
def test_foreign_http_responses_fail_closed(status, body):
    state = launcher._probe_port(
        urlopen=lambda url, timeout: FakeResponse(status, body)
    )

    assert state is launcher.PortState.FOREIGN


def test_identity_probe_timeout_fails_closed():
    def timeout(url, *, timeout):
        raise TimeoutError("timed out")

    assert launcher._probe_port(urlopen=timeout) is launcher.PortState.FOREIGN


def test_identity_probe_response_failure_fails_closed():
    class BrokenResponse(FakeResponse):
        def read(self):
            raise RuntimeError("connection ended during identity response")

    state = launcher._probe_port(
        urlopen=lambda url, timeout: BrokenResponse(200, b"")
    )

    assert state is launcher.PortState.FOREIGN


def test_existing_instance_reopens_browser_without_server_or_data_mutation(
    monkeypatch,
):
    browser_calls = []
    monkeypatch.setattr(
        launcher,
        "get_user_data_dir",
        lambda: pytest.fail("existing instance must not initialize user data"),
    )

    result = launcher.run(
        port_probe=lambda: launcher.PortState.EXISTING,
        config_factory=lambda *args, **kwargs: pytest.fail(
            "existing instance must not configure Uvicorn"
        ),
        server_factory=lambda config: pytest.fail(
            "existing instance must not create a server"
        ),
        browser_open=browser_calls.append,
    )

    assert result is None
    assert browser_calls == ["http://127.0.0.1:8000/"]


def test_foreign_port_raises_without_browser_server_or_data_mutation(monkeypatch):
    browser_calls = []
    monkeypatch.setattr(
        launcher,
        "get_user_data_dir",
        lambda: pytest.fail("foreign port must not initialize user data"),
    )

    with pytest.raises(
        launcher.LauncherPortConflictError,
        match="port_8000_identity_unverified",
    ) as caught:
        launcher.run(
            port_probe=lambda: launcher.PortState.FOREIGN,
            config_factory=lambda *args, **kwargs: pytest.fail(
                "foreign port must not configure Uvicorn"
            ),
            server_factory=lambda config: pytest.fail(
                "foreign port must not create a server"
            ),
            browser_open=browser_calls.append,
        )

    assert browser_calls == []
    assert str(launcher._get_log_path()) in str(caught.value)
    assert "preflight=foreign_or_indeterminate" in launcher_log()
    assert "foreign_port_conflict" in launcher_log()


def test_launcher_initializes_canonical_data_root_before_uvicorn(monkeypatch):
    events = []

    class DataRoot:
        def mkdir(self, *, parents, exist_ok):
            events.append(("mkdir", parents, exist_ok))

    class FakeServer:
        def __init__(self, config):
            self.started = False
            self.should_exit = False

        def run(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(
        launcher,
        "_probe_port",
        lambda: events.append("probe") or launcher.PortState.FREE,
    )
    monkeypatch.setattr(launcher, "get_user_data_dir", lambda: DataRoot())

    launcher.run(
        config_factory=lambda application, **options: events.append("config"),
        server_factory=FakeServer,
    )

    assert events == ["probe", ("mkdir", True, True), "config"]


def test_launcher_honors_data_root_override_from_arbitrary_cwd(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "configured" / "nested"
    current_dir = tmp_path / "elsewhere"
    current_dir.mkdir()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_root))
    monkeypatch.chdir(current_dir)

    resolved = launcher._initialize_user_data_root()

    assert resolved == data_root
    assert data_root.is_dir()


def test_launcher_does_not_reset_existing_data_root(tmp_path, monkeypatch):
    data_root = tmp_path / "existing"
    data_root.mkdir()
    sentinel = data_root / "user_profile.json"
    sentinel.write_text("existing-profile", encoding="utf-8")
    monkeypatch.setattr(launcher, "get_user_data_dir", lambda: data_root)

    assert launcher._initialize_user_data_root() == data_root
    assert sentinel.read_text(encoding="utf-8") == "existing-profile"


def test_readiness_wait_is_bounded_and_requires_owned_server_started():
    server = type("Server", (), {"started": False, "should_exit": False})()
    clock = FakeClock()

    ready = launcher._wait_until_started(
        server,
        threading.Event(),
        timeout=0.3,
        poll_interval=0.1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert ready is False
    assert sum(clock.sleeps) == pytest.approx(0.3)


def test_readiness_wait_stops_after_owned_server_becomes_ready():
    server = type("Server", (), {"started": False, "should_exit": False})()
    clock = FakeClock()

    def become_ready(duration):
        clock.sleep(duration)
        server.started = True

    ready = launcher._wait_until_started(
        server,
        threading.Event(),
        timeout=1.0,
        poll_interval=0.1,
        monotonic=clock.monotonic,
        sleep=become_ready,
    )

    assert ready is True
    assert clock.sleeps == [0.1]


def test_launcher_reuses_existing_app_and_opens_browser_once_after_readiness():
    configured = {}
    browser_calls = []
    browser_opened = threading.Event()

    def config_factory(application, **options):
        configured.update(application=application, **options)
        return object()

    class FakeServer:
        def __init__(self, config):
            self.config = config
            self.started = False
            self.should_exit = False

        def run(self):
            self.started = True
            assert browser_opened.wait(timeout=1.0)

    def open_browser(url):
        browser_calls.append(url)
        browser_opened.set()

    server = launcher.run(
        config_factory=config_factory,
        server_factory=FakeServer,
        browser_open=open_browser,
        readiness_timeout=1.0,
        poll_interval=0.001,
    )

    assert configured == {
        "application": app,
        "host": "127.0.0.1",
        "port": 8000,
    }
    assert browser_calls == ["http://127.0.0.1:8000/"]
    assert server.should_exit is True
    log = launcher_log()
    assert "preflight=free" in log
    assert "owned_server_starting" in log
    assert "owned_server_ready" in log
    assert "browser_open_attempt" in log
    assert "graceful_shutdown_requested" in log


def test_startup_that_never_becomes_ready_does_not_open_browser():
    browser_calls = []

    class FakeServer:
        def __init__(self, config):
            self.started = False
            self.should_exit = False

        def run(self):
            threading.Event().wait(0.03)

    with pytest.raises(launcher.LauncherStartupError):
        launcher.run(
            config_factory=lambda application, **options: object(),
            server_factory=FakeServer,
            browser_open=browser_calls.append,
            readiness_timeout=0.01,
            poll_interval=0.001,
        )

    assert browser_calls == []
    assert "startup_timeout" in launcher_log()


def test_startup_failure_propagates_and_requests_shutdown():
    failure = RuntimeError("bind failed")
    created = []

    class FakeServer:
        def __init__(self, config):
            self.started = False
            self.should_exit = False
            created.append(self)

        def run(self):
            raise failure

    with pytest.raises(
        launcher.LauncherStartupError,
        match="launcher_startup_failed",
    ) as caught:
        launcher.run(
            config_factory=lambda application, **options: object(),
            server_factory=FakeServer,
            readiness_timeout=0.01,
            poll_interval=0.001,
        )

    assert created[0].should_exit is True
    assert str(launcher._get_log_path()) in str(caught.value)
    assert "launcher_exception" in launcher_log()


def test_keyboard_interrupt_requests_clean_owned_server_shutdown():
    created = []

    class FakeServer:
        def __init__(self, config):
            self.started = False
            self.should_exit = False
            created.append(self)

        def run(self):
            raise KeyboardInterrupt

    result = launcher.run(
        config_factory=lambda application, **options: object(),
        server_factory=FakeServer,
        readiness_timeout=0.01,
        poll_interval=0.001,
    )

    assert result is created[0]
    assert created[0].should_exit is True
    assert "keyboard_interrupt" in launcher_log()
    assert "graceful_shutdown_requested" in launcher_log()


def test_launcher_log_does_not_include_domain_payloads():
    sensitive_value = "PRIVATE-PROFILE-SITE-ACCEPTANCE-MISSION"

    launcher.run(
        port_probe=lambda: launcher.PortState.EXISTING,
        browser_open=lambda url: True,
    )

    assert sensitive_value not in launcher_log()


def test_readme_documents_launcher_runtime_and_support_log():
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(
        encoding="utf-8"
    )

    assert "astropilot-app" in readme
    assert "http://127.0.0.1:8000/" in readme
    assert "~/Library/Logs/AstroPilot" in readme
    assert "existing AstroPilot" in readme
    assert "port 8000" in readme
