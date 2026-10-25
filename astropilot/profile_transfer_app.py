"""Separate offline data assistant. Not mounted in the observing application."""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit
import webbrowser

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from astropilot.profile_backup import (BackupError, MAX_ARCHIVE, create_backup,
                                      inspect_backup, restore_empty, profile_state)
from astropilot.user_profile import get_user_data_dir

MESSAGES = {
    "backup_no_user_data": "Cette copie ne contient aucun profil enregistré à sauvegarder. Pour reprendre vos essais, ouvrez l’assistant dans une nouvelle copie vierge, avant de lancer l’application.",
    "backup_destination_not_empty": "Cette copie contient déjà des données. Elles restent intactes. Ouvrez une nouvelle copie vierge pour reprendre une sauvegarde.",
    "backup_invalid": "Cette sauvegarde est incomplète ou endommagée. Aucune donnée n’a été reprise.",
    "backup_incompatible": "Cette sauvegarde ne peut pas être validée par cette version. Conservez l’ancienne copie ; aucune donnée n’a été reprise.",
    "backup_unsupported_file": "Ce dossier contient des fichiers non pris en charge. Aucune sauvegarde partielle n’a été créée.",
    "backup_changed": "Les données ont changé pendant la lecture. Fermez les autres outils NightMerit, puis réessayez.",
    "backup_unsafe_path": "Le dossier contient un lien ou un fichier non pris en charge. Aucune donnée n’a été modifiée.",
    "backup_too_large": "La sauvegarde dépasse les limites de cette bêta. Vos données sont conservées dans l’ancienne copie.",
}


def create_transfer_app(directory=None, *, origin="http://127.0.0.1:8000",
                        exporter=create_backup, inspector=inspect_backup, restorer=restore_empty):
    root = Path(directory) if directory is not None else get_user_data_dir()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    token = secrets.token_urlsafe(32)
    pending = None
    operations = asyncio.Lock()

    @app.middleware("http")
    async def local_requests(request, call_next):
        if request.headers.get("host") != urlsplit(origin).netloc:
            return Response(status_code=403)
        if request.method != "GET" and (request.headers.get("X-NightMerit-Transfer") != token
                or request.headers.get("origin", origin) != origin):
            return Response(status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self' 'nonce-" + token + "'; style-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        return response

    @app.exception_handler(BackupError)
    async def backup_error(_request, error):
        code = str(error)
        return JSONResponse({"message": MESSAGES.get(code, MESSAGES["backup_invalid"])}, status_code=409)

    @app.exception_handler(OSError)
    async def io_error(_request, _error):
        return JSONResponse({"message": "La lecture ou l’enregistrement n’a pas abouti. Conservez l’ancienne copie et vérifiez les données avant de réessayer."}, status_code=503)

    @app.get("/")
    def page():
        source = (Path(__file__).with_name("web") / "profile-transfer.html").read_text(encoding="utf-8")
        return HTMLResponse(source.replace("__TRANSFER_TOKEN__", token))

    @app.get("/v1/runtime-identity")
    def identity():
        from astropilot.app import runtime_identity_payload
        return runtime_identity_payload()

    @app.get("/transfer/status")
    def status():
        # No profile initialization, cursor key creation or fallback to another copy.
        state = profile_state(root)
        return {"state": state, "has_data": state in {"profile", "unrecognized"},
                "can_export": state == "profile", "can_restore": state == "empty",
                "platform": "windows" if os.name == "nt" else "other"}

    @app.post("/transfer/export")
    async def export():
        async with operations:
            raw, _summary = await asyncio.to_thread(exporter, root)
        name = "NightMerit-sauvegarde-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".zip"
        return Response(raw, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="' + name + '"'})

    @app.post("/transfer/preview")
    async def preview(request: Request):
        nonlocal pending
        async with operations:
            pending = None
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_ARCHIVE:
                    raise BackupError("backup_too_large")
            files, summary = await asyncio.to_thread(inspector, bytes(raw))
            nonce = secrets.token_urlsafe(32)
            pending = (nonce, time.monotonic(), files)
            return {"summary": summary, "confirmation": nonce}

    @app.post("/transfer/restore")
    async def restore(request: Request):
        nonlocal pending
        async with operations:
            # Confirmation is small and separate from the archive upload.
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 4096:
                    raise BackupError("backup_invalid")
            try:
                import json
                choice = json.loads(raw)
            except (ValueError, UnicodeError):
                raise BackupError("backup_invalid") from None
            if (not isinstance(choice, dict) or choice.get("confirm") is not True or pending is None
                    or choice.get("confirmation") != pending[0] or time.monotonic() - pending[1] > 600):
                raise BackupError("backup_invalid")
            files = pending[2]
            pending = None
            summary = await asyncio.to_thread(restorer, root, files)
            return {"restored": True, "summary": summary}

    return app


def reserve_listener(port=8000):
    """Reserve loopback without taking over a live listener.

    On POSIX, allow a stopped assistant's TIME_WAIT connections so the next
    copy can open immediately. Do not enable Windows address sharing: the
    private Windows flow closes Sandbox between copies instead.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name != "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        return listener
    except BaseException:
        listener.close()
        raise


def main():
    import uvicorn
    from astropilot.file_lock import exclusive_file_lock
    # Reserve before opening a browser. Never hand off to or stop another copy.
    listener = reserve_listener()
    try:
        app = create_transfer_app()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000,
                                              log_config=None, access_log=False))
        finished = threading.Event()
        def open_when_ready():
            while not finished.wait(.1):
                if server.started:
                    webbrowser.open("http://127.0.0.1:8000/")
                    return
        worker = threading.Thread(target=open_when_ready, daemon=True)
        worker.start()
        try:
            with exclusive_file_lock(get_user_data_dir().parent / ".nightmerit-profile-transfer.lock"):
                server.run(sockets=[listener])
        finally:
            finished.set()
            worker.join(timeout=2)
    finally:
        listener.close()
