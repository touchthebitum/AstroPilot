# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata


ROOT = Path(SPECPATH).resolve()

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
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="AstroPilot",
)
application = BUNDLE(
    collection,
    name="AstroPilot.app",
    icon=None,
    bundle_identifier="fr.astropilot.desktop",
    version="0.0.0",
)
