import threading

import pytest

from astropilot import macos_app


class FakeNSObject:
    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        return self


class FakeApplication:
    def __init__(self):
        self.delegate = None
        self.reopen_results = []
        self.stopped = threading.Event()

    def setDelegate_(self, delegate):
        self.delegate = delegate

    def run(self):
        self.reopen_results.append(
            self.delegate.applicationShouldHandleReopen_hasVisibleWindows_(
                self,
                False,
            )
        )
        assert self.stopped.wait(timeout=1.0)

    def performSelectorOnMainThread_withObject_waitUntilDone_(
        self,
        selector,
        argument,
        wait,
    ):
        assert (selector, argument, wait) == ("stop:", None, False)
        self.stopped.set()


def test_reopen_callback_runs_without_relaunching_application():
    application = FakeApplication()
    events = []

    macos_app.run_macos_application(
        lambda: events.append("launch"),
        lambda: events.append("reopen"),
        lambda: events.append("shutdown"),
        application=application,
        ns_object=FakeNSObject,
    )

    assert sorted(events) == ["launch", "reopen", "shutdown"]
    assert application.reopen_results == [True]


def test_launcher_failure_crosses_the_cocoa_event_loop():
    application = FakeApplication()
    failure = RuntimeError("launch failed")

    def fail():
        raise failure

    with pytest.raises(RuntimeError, match="launch failed") as caught:
        macos_app.run_macos_application(
            fail,
            lambda: None,
            lambda: None,
            application=application,
            ns_object=FakeNSObject,
        )

    assert caught.value is failure


def test_quit_requests_shutdown_and_waits_for_launcher_worker():
    application = FakeApplication()
    launch_started = threading.Event()
    shutdown_requested = threading.Event()
    launch_finished = threading.Event()

    def launch():
        launch_started.set()
        assert shutdown_requested.wait(timeout=1.0)
        launch_finished.set()

    termination_results = []

    def run_until_quit():
        assert launch_started.wait(timeout=1.0)
        termination_results.append(application.delegate.applicationShouldTerminate_(
            application
        ))
        assert launch_finished.is_set()

    application.run = run_until_quit

    macos_app.run_macos_application(
        launch,
        lambda: None,
        shutdown_requested.set,
        application=application,
        ns_object=FakeNSObject,
    )

    assert shutdown_requested.is_set()
    assert launch_finished.is_set()
    assert termination_results == [1]
    assert not any(
        thread.name == "astropilot-launcher" and thread.is_alive()
        for thread in threading.enumerate()
    )
