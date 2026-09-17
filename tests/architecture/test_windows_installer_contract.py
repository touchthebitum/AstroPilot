from pathlib import Path
import ast
import importlib.util
import subprocess
import tomllib
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[2]
ISS = ROOT / "packaging" / "windows" / "AstroPilot.iss"
SCRIPT = ROOT / "scripts" / "build_windows_installer.py"
APP_ID = "A3B620CB-8E79-4B91-8DAB-4CF1BEE63985"


def test_script_exists_and_requires_compiler_defines():
    source = ISS.read_text(encoding="utf-8")
    for define in ("AppVersion", "SourceDir", "InstallerOutputDir"):
        assert f"#ifndef {define}" in source
        assert "#error " in source


@pytest.mark.parametrize("directive", (
    "AppName=AstroPilot",
    "AppVersion={#AppVersion}",
    "DefaultDirName={userpf}\\AstroPilot",
    "DisableDirPage=yes",
    "PrivilegesRequired=lowest",
    "CloseApplications=yes",
    "RestartApplications=yes",
    "UsePreviousAppDir=yes",
    "OutputDir={#InstallerOutputDir}",
    "OutputBaseFilename=AstroPilot-{#AppVersion}-windows-x86_64-setup",
))
def test_setup_contract(directive):
    assert directive in ISS.read_text(encoding="utf-8").splitlines()


def test_app_id_is_fixed_valid_product_guid():
    assert str(uuid.UUID(APP_ID)).upper() == APP_ID
    assert f"AppId={{{{{APP_ID}}}" in ISS.read_text(encoding="utf-8").splitlines()


def test_shortcuts_are_user_only_with_optional_desktop_task():
    source = ISS.read_text(encoding="utf-8")
    task = next(line for line in source.splitlines() if line.startswith('Name: "desktopicon"'))
    assert "Flags: unchecked" in task
    icons = source.split("[Icons]", 1)[1].strip().splitlines()
    assert len(icons) == 2
    assert 'Name: "{userprograms}\\AstroPilot"' in icons[0]
    assert "Tasks:" not in icons[0]
    assert 'Name: "{userdesktop}\\AstroPilot"' in icons[1]
    assert "Tasks: desktopicon" in icons[1]
    assert all('Filename: "{app}\\AstroPilot.exe"' in line for line in icons)


def test_entire_onedir_tree_is_copied_only_to_program_directory():
    source = ISS.read_text(encoding="utf-8")
    files = source.split("[Files]", 1)[1].split("[Icons]", 1)[0].strip().splitlines()
    assert len(files) == 1
    assert 'Source: "{#SourceDir}\\*"; DestDir: "{app}"' in files[0]
    assert "recursesubdirs" in files[0]
    assert "createallsubdirs" in files[0]
    assert "ignoreversion" in files[0]


@pytest.mark.parametrize("forbidden", (
    "localappdata", "{localappdata}", "[uninstalldelete]", "[installdelete]",
    "[dirs]", "[registry]", "[code]", "[run]", "{commonprograms}",
    "{commondesktop}", "privilegesrequiredoverridesallowed", "privilegesrequired=admin",
    "closeapplications=force", "signtool", "signeduninstaller", ".msi", "onefile",
))
def test_installer_has_no_data_management_elevation_or_out_of_scope_behavior(forbidden):
    assert forbidden not in ISS.read_text(encoding="utf-8").lower()


def test_builder_has_no_rebuild_cleanup_download_or_signing():
    source = SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in (
        "pyinstaller", "build_windows.py", "rmtree", ".unlink(", "os.remove",
        "urlopen", "urlretrieve", "requests", "http://", "https://", "pip install",
        "signtool", "signing", ".msi", "onefile",
    ):
        assert forbidden not in source
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    runners = [node for node in calls if isinstance(node.func, ast.Name) and node.func.id == "runner"]
    assert len(runners) == 1
    assert not any(isinstance(node.func, ast.Attribute) and node.func.attr in {
        "system", "popen", "run", "Popen", "remove", "rmdir", "unlink", "rmtree"
    } for node in calls if not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "platform"))


@pytest.fixture
def builder(monkeypatch):
    spec = importlib.util.spec_from_file_location("windows_installer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(module.platform, "machine", lambda: "AMD64")
    return module


@pytest.mark.parametrize("system,machine,accepted", (
    ("Windows", "AMD64", True), ("Windows", "x86_64", True),
    ("Linux", "x86_64", False), ("Darwin", "x86_64", False),
    ("Windows", "ARM64", False), ("Windows", "x86", False),
))
def test_host_guard(builder, monkeypatch, system, machine, accepted):
    monkeypatch.setattr(builder.platform, "system", lambda: system)
    monkeypatch.setattr(builder.platform, "machine", lambda: machine)
    if accepted:
        builder.validate_target()
    else:
        with pytest.raises(RuntimeError, match="Windows|x86_64"):
            builder.build(runner=lambda *args, **kwargs: pytest.fail("runner must not be called"))


@pytest.mark.parametrize("state", ("missing", "empty", "no_executable"))
def test_existing_onedir_and_executable_required(builder, tmp_path, state):
    source = tmp_path / "dist" / "AstroPilot"
    if state != "missing":
        source.mkdir(parents=True)
    if state == "no_executable":
        (source / "support.dll").write_bytes(b"support")
    with pytest.raises(RuntimeError, match="dist/AstroPilot"):
        builder.build(root=tmp_path, runner=lambda *args, **kwargs: pytest.fail("runner must not be called"))


def test_version_comes_unchanged_from_project_metadata(builder):
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert builder.read_version(ROOT) == version
    assert version not in SCRIPT.read_text(encoding="utf-8")
    assert builder.ROOT == ROOT


@pytest.mark.parametrize("route", ("explicit", "environment", "path", "standard", "local"))
def test_compiler_discovery(builder, monkeypatch, tmp_path, route):
    for name in ("ISCC_PATH", "ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(builder.shutil, "which", lambda name: None)
    compiler = tmp_path / "Inno Setup 6" / "ISCC.exe"
    if route == "local":
        compiler = tmp_path / "Programs" / "Inno Setup 6" / "ISCC.exe"
    compiler.parent.mkdir(parents=True)
    compiler.write_bytes(b"stub")
    explicit = None
    if route == "explicit":
        explicit = compiler
        monkeypatch.setenv("ISCC_PATH", str(tmp_path / "wrong.exe"))
    elif route == "environment":
        monkeypatch.setenv("ISCC_PATH", str(compiler))
    elif route == "path":
        monkeypatch.setattr(builder.shutil, "which", lambda name: str(compiler) if name == "ISCC.exe" else None)
    elif route == "standard":
        monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    else:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert builder.find_iscc(explicit) == compiler.resolve()


def test_missing_compiler_fails_without_installing(builder, monkeypatch, tmp_path):
    for name in ("ISCC_PATH", "ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(builder.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="manually"):
        builder.find_iscc()
    with pytest.raises(RuntimeError, match="configured path"):
        builder.find_iscc(tmp_path / "ISCC.exe")


@pytest.mark.parametrize("result", ("created", "missing", "failure"))
def test_compiler_invocation_and_output_preserve_existing_files(builder, tmp_path, result):
    root = tmp_path / "Chemin avec espaces et accents é"
    source = root / "dist" / "AstroPilot"
    source.mkdir(parents=True)
    executable = source / "AstroPilot.exe"
    executable.write_bytes(b"existing program")
    internal = source / "_internal" / "runtime.dll"
    internal.parent.mkdir()
    internal.write_bytes(b"runtime")
    data = root / "data" / "user_profile.json"
    data.parent.mkdir()
    data.write_bytes(b"existing profile")
    build_file = root / "build" / "keep.txt"
    build_file.parent.mkdir()
    build_file.write_bytes(b"keep")
    (root / "pyproject.toml").write_text('[project]\nversion = "2.3.4b5"\n', encoding="utf-8")
    script = root / "packaging" / "windows" / "AstroPilot.iss"
    script.parent.mkdir(parents=True)
    script.write_text(ISS.read_text(encoding="utf-8"), encoding="utf-8")
    compiler = tmp_path / "ISCC.exe"
    compiler.write_bytes(b"stub")
    output_dir = root / "dist" / "installer"
    output = output_dir / "AstroPilot-2.3.4b5-windows-x86_64-setup.exe"
    calls = []

    def runner(command, *, cwd, check):
        calls.append((command, cwd, check))
        if result == "failure":
            raise subprocess.CalledProcessError(2, command)
        if result == "created":
            output_dir.mkdir()
            output.write_bytes(b"setup")

    if result == "created":
        assert builder.build(root=root, iscc=compiler, runner=runner) == output
    else:
        error = subprocess.CalledProcessError if result == "failure" else RuntimeError
        with pytest.raises(error):
            builder.build(root=root, iscc=compiler, runner=runner)
    assert calls == [([
        str(compiler.resolve()), "/DAppVersion=2.3.4b5",
        f"/DSourceDir={source}", f"/DInstallerOutputDir={output_dir}", str(script),
    ], root, True)]
    assert executable.read_bytes() == b"existing program"
    assert internal.read_bytes() == b"runtime"
    assert data.read_bytes() == b"existing profile"
    assert build_file.read_bytes() == b"keep"
