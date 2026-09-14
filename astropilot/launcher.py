"""Runtime launcher for the local AstroPilot web application."""

from __future__ import annotations

import threading
import time
import webbrowser
from collections.abc import Callable
from typing import Any

import uvicorn

from astropilot.app import app


HOST = "127.0.0.1"
PORT = 8000
BROWSER_URL = "http://127.0.0.1:8000/"
READINESS_TIMEOUT_SECONDS = 15.0
READINESS_POLL_INTERVAL_SECONDS = 0.05


class LauncherStartupError(RuntimeError):
    """Raised when the owned server does not complete startup."""


def _wait_until_started(
    server: Any,
    stop_event: threading.Event,
    *,
    timeout: float = READINESS_TIMEOUT_SECONDS,
    poll_interval: float = READINESS_POLL_INTERVAL_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    deadline = monotonic() + timeout

    while not stop_event.is_set() and not server.should_exit:
        if server.started:
            return True

        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        sleep(min(poll_interval, remaining))

    return bool(server.started)


def run(
    *,
    config_factory: Callable[..., Any] = uvicorn.Config,
    server_factory: Callable[[Any], Any] = uvicorn.Server,
    browser_open: Callable[[str], Any] = webbrowser.open,
    readiness_timeout: float = READINESS_TIMEOUT_SECONDS,
    poll_interval: float = READINESS_POLL_INTERVAL_SECONDS,
):
    """Run the existing AstroPilot application until its server exits."""

    config = config_factory(app, host=HOST, port=PORT)
    server = server_factory(config)
    stop_event = threading.Event()
    ready_event = threading.Event()
    timed_out_event = threading.Event()
    browser_errors: list[BaseException] = []

    def open_browser_after_startup() -> None:
        try:
            if _wait_until_started(
                server,
                stop_event,
                timeout=readiness_timeout,
                poll_interval=poll_interval,
            ):
                ready_event.set()
                browser_open(BROWSER_URL)
            elif not stop_event.is_set():
                timed_out_event.set()
                server.should_exit = True
        except BaseException as exc:
            browser_errors.append(exc)
            server.should_exit = True

    browser_thread = threading.Thread(
        target=open_browser_after_startup,
        name="astropilot-browser-opener",
        daemon=True,
    )
    browser_thread.start()

    interrupted = False
    try:
        server.run()
    except KeyboardInterrupt:
        interrupted = True
    finally:
        server.should_exit = True
        stop_event.set()
        browser_thread.join(timeout=max(0.1, poll_interval * 2))

    if browser_errors:
        raise LauncherStartupError("browser_open_failed") from browser_errors[0]
    if not interrupted and (timed_out_event.is_set() or not ready_event.is_set()):
        raise LauncherStartupError("server_startup_failed")

    return server


def main() -> None:
    run()

