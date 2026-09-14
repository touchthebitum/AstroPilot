import threading

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


def test_launcher_has_stable_loopback_origin():
    assert launcher.HOST == "127.0.0.1"
    assert launcher.HOST != "0.0.0.0"
    assert launcher.PORT == 8000
    assert launcher.BROWSER_URL == "http://127.0.0.1:8000/"
    assert callable(launcher.main)


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

