from pathlib import Path
import importlib.util
from unittest.mock import ANY

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "AstroPilot-windows.spec"
BUILD_SCRIPT_PATH = ROOT / "scripts" / "build_windows.py"
ASTROPY_HOOK_PATH = ROOT / "packaging" / "pyinstaller_hooks" / "hook-astropy.py"


def _build_module():
    spec = importlib.util.spec_from_file_location(
        "astropilot_build_windows",
        BUILD_SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_spec_exists_and_defines_console_onedir_executable():
    source = SPEC_PATH.read_text(encoding="utf-8")

    assert 'astropilot" / "launcher.py"' in source
    assert 'name="AstroPilot"' in source
    assert "exclude_binaries=True" in source
    assert "COLLECT(" in source
    assert "console=True" in source
    assert "BUNDLE(" not in source
    assert "onefile" not in source.lower()


def test_windows_spec_excludes_macos_bundle_and_signing_behavior():
    source = SPEC_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "Developer ID",
        "codesign_identity",
        "entitlements_file",
        "info_plist",
        "CFBundle",
        "bundle_identifier",
        "AstroPilot.app",
    ):
        assert forbidden not in source


def test_windows_spec_collects_exact_runtime_assets_without_broad_imports():
    source = SPEC_PATH.read_text(encoding="utf-8")

    for asset in ("index.html", "app.js", "styles.css"):
        assert asset in source
    assert '"astropilot/web"' in source
    assert '"astropilot/knowledge/objects"' in source
    assert 'collect_data_files("timezonefinder_data")' in source
    assert 'collect_data_files("astropy_iers_data")' in source
    assert 'collect_data_files("tzdata")' in source
    assert 'copy_metadata("astropilot")' in source
    assert "hiddenimports=[]" in source
    assert "collect_submodules" not in source


def test_windows_spec_uses_local_astropy_hook_without_optional_wcsaxes():
    spec = SPEC_PATH.read_text(encoding="utf-8")
    hook = ASTROPY_HOOK_PATH.read_text(encoding="utf-8")

    assert 'hookspath=[str(ROOT / "packaging" / "pyinstaller_hooks")]' in spec
    assert 'collect_submodules(' in hook
    assert 'name == "astropy.visualization.wcsaxes"' in hook
    assert 'name.startswith("astropy.visualization.wcsaxes.")' in hook
    assert 'excludes=["astropy.visualization.wcsaxes"]' in spec


def test_windows_spec_injects_build_identity_without_runtime_git():
    source = SPEC_PATH.read_text(encoding="utf-8")

    assert 'os.environ.get("ASTROPILOT_BUILD_COMMIT", "")' in source
    assert "runtime_hooks=[str(build_identity_hook)]" in source
    assert "git" not in source.lower()


def test_build_script_rejects_non_windows_host(monkeypatch):
    build = _build_module()
    monkeypatch.setattr(build.platform, "system", lambda: "Darwin")

    with pytest.raises(RuntimeError, match="Windows"):
        build.validate_target()


@pytest.mark.parametrize("host_architecture", ("AMD64", "x86_64"))
def test_build_script_accepts_supported_windows_host_aliases(
    monkeypatch,
    host_architecture,
):
    build = _build_module()
    monkeypatch.setattr(build.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build.platform, "machine", lambda: host_architecture)

    assert build.validate_target() == "x86_64"


def test_build_script_rejects_unsupported_windows_architecture(monkeypatch):
    build = _build_module()
    monkeypatch.setattr(build.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build.platform, "machine", lambda: "ARM64")

    with pytest.raises(RuntimeError, match="x86_64"):
        build.validate_target()


def test_canonical_target_is_explicit_and_independent_of_host_alias(monkeypatch):
    build = _build_module()
    monkeypatch.setattr(build.platform, "system", lambda: "Windows")

    assert build.WINDOWS_RELEASE_TARGET_ARCHITECTURE == "x86_64"
    for host_alias in ("AMD64", "x86_64"):
        monkeypatch.setattr(build.platform, "machine", lambda: host_alias)
        assert build.validate_target() == build.WINDOWS_RELEASE_TARGET_ARCHITECTURE


def test_build_script_root_is_derived_from_script_location():
    build = _build_module()

    assert build.ROOT == BUILD_SCRIPT_PATH.resolve().parents[1]
    assert "Path.cwd" not in BUILD_SCRIPT_PATH.read_text(encoding="utf-8")


def test_build_invokes_pyinstaller_from_repo_and_returns_deterministic_directory(
    tmp_path,
    monkeypatch,
):
    build = _build_module()
    calls = []
    monkeypatch.setattr(build.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build.platform, "machine", lambda: "AMD64")

    def runner(command, *, cwd, check, **options):
        calls.append((command, cwd, check, options))
        if command[:2] == ["git", "rev-parse"]:
            return type("Result", (), {"stdout": "f5479d9\n"})()
        if command[:2] == ["git", "status"]:
            return type("Result", (), {"stdout": ""})()
        (tmp_path / "dist" / "AstroPilot").mkdir(parents=True)

    output = build.build(root=tmp_path, runner=runner)

    assert calls == [
        (
            ["git", "rev-parse", "--short=7", "HEAD"],
            tmp_path,
            True,
            {"capture_output": True, "text": True},
        ),
        (
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            tmp_path, True, {"capture_output": True, "text": True},
        ),
        (
            ["uv", "sync", "--locked", "--extra", "packaging"],
            tmp_path, True, {},
        ),
        (
            [
                "uv", "run", "--locked", "--extra", "packaging", "python", "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "AstroPilot-windows.spec",
            ],
            tmp_path,
            True,
            {"env": ANY},
        ),
    ]
    assert calls[3][3]["env"]["ASTROPILOT_BUILD_COMMIT"] == "f5479d9"
    assert output == tmp_path / "dist" / "AstroPilot"


def test_build_fails_if_deterministic_output_directory_is_missing(
    tmp_path,
    monkeypatch,
):
    build = _build_module()
    monkeypatch.setattr(build.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build.platform, "machine", lambda: "x86_64")

    def runner(command, **options):
        del options
        if command[:2] == ["git", "rev-parse"]:
            return type("Result", (), {"stdout": "f5479d9\n"})()
        if command[:2] == ["git", "status"]:
            return type("Result", (), {"stdout": ""})()

    with pytest.raises(RuntimeError, match=r"dist[/\\]AstroPilot"):
        build.build(root=tmp_path, runner=runner)


def test_build_script_has_no_zip_signing_or_installer_behavior():
    source = BUILD_SCRIPT_PATH.read_text(encoding="utf-8").lower()

    for forbidden in (
        ".zip",
        "zipfile",
        "make_archive",
        "compress-archive",
        "signtool",
        "osslsigncode",
        "codesign",
        "notarytool",
        "inno setup",
        "wix",
        "nsis",
        "msi",
    ):
        assert forbidden not in source
