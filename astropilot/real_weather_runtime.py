"""Portable components for an explicit, managed real-weather kit."""
import json
import os
from pathlib import Path
import re
import socket

CONFIG = "ASTROPILOT_REAL_WEATHER_COMPONENT"


def main(role, raw_fd):
    if role not in {"application", "assistant", "relay"} or not raw_fd.isdecimal():
        raise ValueError("real_weather_component_invalid")
    from astropilot.launcher_context import LaunchSession
    from astropilot.real_weather_context import activate
    from astropilot.demo_mode import context as demo_context
    if demo_context()["enabled"]:
        raise ValueError("real_weather_demo_conflict")
    session = LaunchSession.from_environment()
    if (session is None or session.location_status() != "available"
            or os.environ.get("NIGHTMERIT_COPY_KIND") != "fictitious"
            or Path(session.data_directory) != Path(session.kit_directory) / "DONNEES-FICTIVES/profil"):
        raise ValueError("real_weather_launch_identity_invalid")
    raw = os.environ.get(CONFIG, "")
    if len(raw) > 8192:
        raise ValueError("real_weather_component_invalid")
    value = json.loads(raw)
    expected = {"role", "application_port", "relay_port"} | ({"token"} if role != "assistant" else set())
    if not isinstance(value, dict) or set(value) != expected or value["role"] != role:
        raise ValueError("real_weather_component_invalid")
    for key in ("application_port", "relay_port"):
        if type(value[key]) is not int or not 20000 <= value[key] <= 65535:
            raise ValueError("real_weather_component_invalid")
    if value["application_port"] == value["relay_port"]:
        raise ValueError("real_weather_component_invalid")
    if role != "assistant" and (not isinstance(value["token"], str) or re.fullmatch("[0-9a-f]{64}", value["token"]) is None):
        raise ValueError("real_weather_component_invalid")
    listener = socket.socket(fileno=int(raw_fd))
    port = value["relay_port"] if role == "relay" else value["application_port"]
    # SO_ACCEPTCONN is not a readable socket option on the qualified Mac.
    # The supervisor owns listen(); validate its inherited endpoint and type.
    if (listener.getsockname() != ("127.0.0.1", port)
            or listener.family != socket.AF_INET
            or listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM):
        listener.close()
        raise ValueError("real_weather_reserved_listener_invalid")
    try:
        if role == "relay":
            from astropilot.weather_relay import RelayState, relay_server
            import logging
            from logging.handlers import RotatingFileHandler
            logger = logging.getLogger("nightmerit.real_weather.relay")
            logger.propagate = False
            logger.setLevel(logging.INFO)
            class PrivateJournal(RotatingFileHandler):
                def _open(self):
                    fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
                    os.fchmod(fd, 0o600)
                    return os.fdopen(fd, "a", encoding="utf-8")
            handler = PrivateJournal(Path(session.kit_directory) / "runtime/weather-relay.jsonl",
                maxBytes=256 * 1024, backupCount=2)
            logger.addHandler(handler)
            def audit(**fields):
                logger.info(json.dumps(fields, allow_nan=False))
            server = relay_server(listener, RelayState(value["token"], session.session_id, audit=audit))
            try:
                server.serve_forever(poll_interval=.1)
            finally:
                server.server_close()
                logger.removeHandler(handler)
                handler.close()
        else:
            activate(session, relay_port=value.get("relay_port") if role == "application" else None,
                     relay_token=value.get("token") if role == "application" else None)
            if role == "assistant":
                from astropilot.profile_transfer_app import main as transfer_main
                def request_application():
                    event = Path(session.kit_directory) / "runtime/open-application.json"
                    fd = os.open(event, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                    with os.fdopen(fd, "w") as stream:
                        json.dump({"session_id": session.session_id}, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                transfer_main(port=port, open_browser=False, isolated_candidate=True,
                              reserved_socket=listener, application_runner=request_application)
            else:
                import uvicorn
                from astropilot.app import create_app
                uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                    access_log=False, log_config=None)).run(sockets=[listener])
    finally:
        listener.close()
    return 0
