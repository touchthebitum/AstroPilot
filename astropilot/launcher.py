"""Runtime launcher for the local AstroPilot web application."""

from __future__ import annotations

import errno
import json
import logging
from logging.handlers import RotatingFileHandler
import platform
from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from enum import Enum
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

import uvicorn

from astropilot.app import (
    app,
    build_identifier,
    canonical_version,
    runtime_architecture,
)
from astropilot.user_profile import get_user_data_dir


HOST = "127.0.0.1"
PORT = 8000
BROWSER_URL = "http://127.0.0.1:8000/"
IDENTITY_URL = "http://127.0.0.1:8000/v1/runtime-identity"
PROBE_TIMEOUT_SECONDS = 0.5
READINESS_TIMEOUT_SECONDS = 15.0
READINESS_POLL_INTERVAL_SECONDS = 0.05
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 2
LOGGER_NAME = "astropilot.launcher"
# The first Windows beta deliberately keeps a console for diagnostics and
# KeyboardInterrupt-driven owned-server shutdown.
WINDOWS_BETA_CONSOLE_ENABLED = True

_home_directory = Path.home


class LauncherStartupError(RuntimeError):
    """Raised when the owned server does not complete startup."""


class LauncherPortConflictError(LauncherStartupError):
    """Raised when port 8000 is occupied without verified AstroPilot identity."""


class PortState(Enum):
    FREE = "free"
    EXISTING = "existing_astropilot"
    FOREIGN = "foreign_or_indeterminate"


def _get_log_path() -> Path:
    if sys.platform == "win32":
        return get_user_data_dir() / "Logs" / "AstroPilot.log"
    return (
        _home_directory()
        / "Library"
        / "Logs"
        / "AstroPilot"
        / "AstroPilot.log"
    )


def _configure_launcher_logger(
    *,
    log_path: Path | None = None,
) -> tuple[logging.Logger, Path]:
    resolved_path = _get_log_path() if log_path is None else Path(log_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    matching_handler = None
    for handler in tuple(logger.handlers):
        if not getattr(handler, "_astropilot_launcher_handler", False):
            continue
        if Path(handler.baseFilename) == resolved_path.resolve():
            matching_handler = handler
            continue
        logger.removeHandler(handler)
        handler.close()

    if matching_handler is None:
        handler = RotatingFileHandler(
            resolved_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler._astropilot_launcher_handler = True
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s"
        ))
        logger.addHandler(handler)

    return logger, resolved_path


def _diagnostic_message(code: str, log_path: Path) -> str:
    return f"{code}. See the AstroPilot support log: {log_path}"


def _open_browser(
    browser_open: Callable[[str], Any],
    logger: logging.Logger,
    log_path: Path,
) -> bool:
    logger.info("browser_open_attempt url=%s", BROWSER_URL)
    try:
        opened = browser_open(BROWSER_URL)
    except Exception as exc:
        logger.error("browser_open_failed type=%s", type(exc).__name__)
        print(
            _diagnostic_message(
                f"AstroPilot is running at {BROWSER_URL}, but the browser "
                "could not be opened",
                log_path,
            ),
            file=sys.stderr,
        )
        return False
    if opened is False:
        logger.error("browser_open_failed result=false")
        print(
            _diagnostic_message(
                f"AstroPilot is running at {BROWSER_URL}, but the browser "
                "did not open",
                log_path,
            ),
            file=sys.stderr,
        )
        return False
    logger.info("browser_open_succeeded")
    return True


def _is_connection_refused(error: BaseException) -> bool:
    reason = getattr(error, "reason", error)
    return isinstance(reason, ConnectionRefusedError) or (
        isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED
    )


def _direct_urlopen(url: str, *, timeout: float):
    """Open a loopback URL without consulting user or system proxies."""

    return build_opener(ProxyHandler({})).open(url, timeout=timeout)


def _can_bind_loopback(
    socket_factory: Callable[..., Any] = socket.socket,
) -> bool:
    """Confirm that the configured loopback port can be reserved locally."""

    candidate = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
    try:
        candidate.bind((HOST, PORT))
    except OSError:
        return False
    finally:
        candidate.close()
    return True


def _probe_port(
    *,
    urlopen: Callable[..., Any] = _direct_urlopen,
    can_bind: Callable[[], bool] = _can_bind_loopback,
) -> PortState:
    try:
        with urlopen(IDENTITY_URL, timeout=PROBE_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return PortState.FOREIGN
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError:
        return PortState.FOREIGN
    except URLError as exc:
        return (
            PortState.FREE
            if _is_connection_refused(exc) or can_bind()
            else PortState.FOREIGN
        )
    except OSError as exc:
        return (
            PortState.FREE
            if _is_connection_refused(exc) or can_bind()
            else PortState.FOREIGN
        )
    except (AttributeError, TypeError, UnicodeError, ValueError):
        return PortState.FOREIGN
    except Exception:
        return PortState.FOREIGN

    return (
        PortState.EXISTING
        if isinstance(payload, dict)
        and payload.get("application") == "astropilot"
        else PortState.FOREIGN
    )


def _initialize_user_data_root():
    data_root = get_user_data_dir()
    data_root.mkdir(parents=True, exist_ok=True)
    return data_root


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
    port_probe: Callable[[], PortState] | None = None,
):
    """Run the existing AstroPilot application until its server exits."""

    logger, log_path = _configure_launcher_logger()
    logger.info(
        "launcher_start version=%s build=%s python=%s architecture=%s host=%s port=%s",
        canonical_version(),
        build_identifier(),
        platform.python_version(),
        runtime_architecture(),
        HOST,
        PORT,
    )
    try:
        port_state = _probe_port() if port_probe is None else port_probe()
    except Exception as exc:
        logger.exception("launcher_exception phase=preflight type=%s", type(exc).__name__)
        raise LauncherStartupError(
            _diagnostic_message("runtime_identity_preflight_failed", log_path)
        ) from exc
    state_value = port_state.value if isinstance(port_state, PortState) else "invalid"
    logger.info("preflight=%s", state_value)
    if port_state is PortState.EXISTING:
        logger.info("existing_instance_detected")
        _open_browser(browser_open, logger, log_path)
        logger.info("launcher_exit existing_instance_handoff")
        return None
    if port_state is not PortState.FREE:
        logger.error("foreign_port_conflict host=%s port=%s", HOST, PORT)
        raise LauncherPortConflictError(_diagnostic_message(
            "port_8000_identity_unverified",
            log_path,
        ))

    try:
        data_root = _initialize_user_data_root()
        logger.info("user_data_root_ready path=%s", data_root)
        config = config_factory(app, host=HOST, port=PORT)
        server = server_factory(config)
    except Exception as exc:
        logger.exception("launcher_exception phase=setup type=%s", type(exc).__name__)
        raise LauncherStartupError(
            _diagnostic_message("launcher_setup_failed", log_path)
        ) from exc
    stop_event = threading.Event()
    ready_event = threading.Event()
    timed_out_event = threading.Event()

    def open_browser_after_startup() -> None:
        try:
            if _wait_until_started(
                server,
                stop_event,
                timeout=readiness_timeout,
                poll_interval=poll_interval,
            ):
                ready_event.set()
                logger.info("owned_server_ready")
                _open_browser(browser_open, logger, log_path)
            elif not stop_event.is_set():
                timed_out_event.set()
                logger.error("startup_timeout seconds=%s", readiness_timeout)
                server.should_exit = True
        except Exception as exc:
            logger.exception(
                "launcher_exception phase=readiness type=%s",
                type(exc).__name__,
            )
            server.should_exit = True

    browser_thread = threading.Thread(
        target=open_browser_after_startup,
        name="astropilot-browser-opener",
        daemon=True,
    )
    browser_thread.start()

    interrupted = False
    run_error: BaseException | None = None
    logger.info("owned_server_starting")
    try:
        server.run()
    except KeyboardInterrupt:
        interrupted = True
        logger.info("keyboard_interrupt")
    except (Exception, SystemExit) as exc:
        run_error = exc
        logger.exception(
            "launcher_exception phase=uvicorn type=%s",
            type(exc).__name__,
        )
    finally:
        server.should_exit = True
        stop_event.set()
        browser_thread.join(timeout=max(0.1, poll_interval * 2))
        logger.info("graceful_shutdown_requested")

    if run_error is not None:
        raise LauncherStartupError(
            _diagnostic_message("launcher_startup_failed", log_path)
        ) from run_error
    if not interrupted and (timed_out_event.is_set() or not ready_event.is_set()):
        raise LauncherStartupError(
            _diagnostic_message("server_startup_failed", log_path)
        )

    logger.info("launcher_exit")
    return server


def main() -> None:
    run()


if __name__ == "__main__":
    main()
