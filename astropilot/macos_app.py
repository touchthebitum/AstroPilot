"""Minimal Cocoa event loop for the packaged macOS application."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


def _create_application_delegate(
    ns_object: type,
    reopen: Callable[[], Any],
    terminate: Callable[[], Any],
    application_delegate_protocol: Any | None = None,
    terminate_now: int = 1,
):
    class AstroPilotApplicationDelegate(ns_object):
        if application_delegate_protocol is not None:
            __pyobjc_protocols__ = [application_delegate_protocol]

        def applicationShouldHandleReopen_hasVisibleWindows_(
            self,
            application,
            has_visible_windows,
        ):
            reopen()
            return True

        def applicationShouldTerminate_(self, application):
            terminate()
            return terminate_now

    return AstroPilotApplicationDelegate.alloc().init()


def run_macos_application(
    launch: Callable[[], Any],
    reopen: Callable[[], Any],
    shutdown: Callable[[], Any],
    *,
    application: Any | None = None,
    ns_object: type | None = None,
) -> None:
    """Run one launcher worker while Cocoa handles app reopen events."""

    if application is None or ns_object is None:
        import AppKit
        import objc
        from Foundation import NSObject

        application = AppKit.NSApplication.sharedApplication()
        ns_object = NSObject
        application_delegate_protocol = objc.protocolNamed(
            "NSApplicationDelegate"
        )
        terminate_now = AppKit.NSTerminateNow
    else:
        application_delegate_protocol = None
        terminate_now = 1

    errors: list[BaseException] = []
    launcher_finished = threading.Event()

    def shutdown_and_wait() -> None:
        shutdown()
        launcher_thread.join()

    delegate = _create_application_delegate(
        ns_object,
        reopen,
        shutdown_and_wait,
        application_delegate_protocol,
        terminate_now,
    )
    application.setDelegate_(delegate)

    def launch_and_stop_event_loop() -> None:
        try:
            launch()
        except BaseException as exc:
            errors.append(exc)
        finally:
            launcher_finished.set()
            application.performSelectorOnMainThread_withObject_waitUntilDone_(
                "stop:",
                None,
                False,
            )

    launcher_thread = threading.Thread(
        target=launch_and_stop_event_loop,
        name="astropilot-launcher",
        daemon=False,
    )
    launcher_thread.start()
    application.run()
    shutdown_and_wait()
    if errors:
        raise errors[0]
