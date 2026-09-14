# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import re
import tomllib

from PyInstaller.utils.hooks import collect_data_files, copy_metadata


ROOT = Path(SPECPATH).resolve()
with (ROOT / "pyproject.toml").open("rb") as handle:
    PROJECT_VERSION = tomllib.load(handle)["project"]["version"]
version_match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)b(\d+)", PROJECT_VERSION)
if version_match is None:
    raise RuntimeError("Expected a PEP 440 beta project version.")
major, minor, patch, beta = version_match.groups()
MARKETING_VERSION = f"{major}.{minor}.{patch}"
BUNDLE_BUILD_NUMBER = beta

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
CODESIGN_IDENTITY = os.environ.get("ASTROPILOT_CODESIGN_IDENTITY") or None

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
    runtime_hooks=[str(build_identity_hook)],
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
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=None,
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
    version=MARKETING_VERSION,
    info_plist={
        "CFBundleShortVersionString": MARKETING_VERSION,
        "CFBundleVersion": BUNDLE_BUILD_NUMBER,
    },
)
