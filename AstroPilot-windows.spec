# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import re

from PyInstaller.utils.hooks import collect_data_files, copy_metadata


ROOT = Path(SPECPATH).resolve()
BUILD_COMMIT = os.environ.get("ASTROPILOT_BUILD_COMMIT", "")
if re.fullmatch(r"[0-9a-f]{7}", BUILD_COMMIT) is None:
    raise RuntimeError("ASTROPILOT_BUILD_COMMIT must be 7 hexadecimal characters.")
generated_dir = ROOT / "build" / "generated"
generated_dir.mkdir(parents=True, exist_ok=True)
build_identity_hook = generated_dir / "astropilot_build_identity.py"
build_identity_hook.write_text(
    "import os\n"
    f"os.environ['ASTROPILOT_BUILD_COMMIT'] = {BUILD_COMMIT!r}\n",
    encoding="utf-8",
)

datas = [
    (str(ROOT / "astropilot" / "web" / "index.html"), "astropilot/web"),
    (str(ROOT / "astropilot" / "web" / "app.js"), "astropilot/web"),
    (str(ROOT / "astropilot" / "web" / "styles.css"), "astropilot/web"),
    (
        str(ROOT / "astropilot" / "knowledge" / "objects" / "*.json"),
        "astropilot/knowledge/objects",
    ),
]
datas += collect_data_files("timezonefinder_data")
datas += collect_data_files("astropy_iers_data")
datas += collect_data_files("tzdata")
datas += copy_metadata("astropilot")

analysis = Analysis(
    [str(ROOT / "astropilot" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[str(ROOT / "packaging" / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[str(build_identity_hook)],
    excludes=["astropy.visualization.wcsaxes"],
    noarchive=False,
    optimize=0,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AstroPilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="AstroPilot",
)
