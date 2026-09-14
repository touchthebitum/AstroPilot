import threading
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
    probe_port = launcher._probe_port

    def isolated_probe(**kwargs):
        return probe_port(**kwargs) if kwargs else launcher.PortState.FREE

    monkeypatch.setattr(launcher, "_probe_port", isolated_probe)


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


def test_identity_probe_is_bounded_and_accepts_only_exact_identity():
    calls = []

    def urlopen(url, *, timeout):
        calls.append((url, timeout))
        return FakeResponse(200, b'{"application":"astropilot"}')

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
        (200, b'{"application":"another"}'),
        (200, b'{"application":"astropilot","extra":true}'),
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
    ):
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

    with pytest.raises(RuntimeError, match="bind failed"):
        launcher.run(
            config_factory=lambda application, **options: object(),
            server_factory=FakeServer,
            readiness_timeout=0.01,
            poll_interval=0.001,
        )

    assert created[0].should_exit is True


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
