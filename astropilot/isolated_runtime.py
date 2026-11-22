"""Explicit candidate-only local ports; never discover, reuse or stop a listener."""
from pathlib import Path
import os

MODES = {'--isolated-test-server', '--isolated-demo-server', '--isolated-data-transfer', '--isolated-demo-transfer'}


def isolated_port(raw: str) -> int:
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 5:
        raise ValueError('Le port isolé doit être un entier entre 20000 et 65535.')
    port = int(raw)
    if not 20000 <= port <= 65535:
        raise ValueError('Le port isolé doit être un entier entre 20000 et 65535.')
    return port


def main(mode: str, raw_port: str) -> None:
    if mode not in MODES:
        raise ValueError('Mode isolé inconnu.')
    port = isolated_port(raw_port)
    raw = os.environ.get('ASTROPILOT_DATA_DIR', '')
    if not raw or not Path(raw).is_absolute():
        raise ValueError('Un dossier de profil isolé absolu est obligatoire.')
    if mode in {'--isolated-data-transfer', '--isolated-demo-transfer'}:
        from astropilot.profile_transfer_app import main as transfer_main
        transfer_main(port=port, open_browser=False,
                      demo=mode == '--isolated-demo-transfer', isolated_candidate=True)
        return
    if mode == '--isolated-demo-server':
        from astropilot.demo_mode import main as demo_main
        demo_main(port=port, open_browser=False, isolated_candidate=True)
        return
    # Reserve before creating data or importing the application. A conflict is
    # an error, never a handoff to an existing instance.
    from astropilot.profile_transfer_app import reserve_listener
    listener = reserve_listener(port=port)
    try:
        Path(raw).mkdir(parents=True, exist_ok=True)
        import uvicorn
        from astropilot.app import app
        uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port)).run(sockets=[listener])
    finally:
        listener.close()
