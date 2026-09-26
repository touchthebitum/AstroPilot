from pathlib import Path
import ast
import importlib.util
import json
import subprocess
import tomllib
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[2]
ISS = ROOT / "packaging" / "windows" / "AstroPilot.iss"
SCRIPT = ROOT / "scripts" / "build_windows_installer.py"
APP_ID = "A3B620CB-8E79-4B91-8DAB-4CF1BEE63985"


def test_release_procedure_requires_rebuild_and_identity_verification():
    documentation = (ROOT / "docs" / "WINDOWS_INSTALLER.md").read_text(encoding="utf-8")
    assert "python scripts/build_windows.py" in documentation
    assert "python scripts/build_windows_installer.py" in documentation
    assert "Run both steps for every release candidate" in documentation
    assert "only when a new application build is needed" not in documentation
    assert "--runtime-identity" in documentation


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
    "localappdata", "{localappdata}", "[uninstalldelete]",
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
    assert len(runners) == 4
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


@pytest.mark.parametrize("identity", (
    None,
    {"application": "astropilot", "version": "1.0.0b5", "build": "f5479d9", "architecture": "x86_64"},
    {"application": "astropilot", "version": "1.0.0b6", "build": "abcdef0", "architecture": "x86_64"},
    {"application": "astropilot", "version": "1.0.0b6", "architecture": "x86_64"},
))
def test_unverified_executable_never_reaches_compiler(builder, tmp_path, identity):
    root = tmp_path
    source = root / "dist" / "AstroPilot"
    source.mkdir(parents=True)
    executable = source / "AstroPilot.exe"
    executable.write_bytes(b"stub")
    (root / "pyproject.toml").write_text('[project]\nversion = "1.0.0b6"\n')
    compiler = root / "ISCC.exe"
    compiler.write_bytes(b"stub")
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[:2] == ["git", "rev-parse"]:
            return type("Result", (), {"stdout": "f5479d9\n"})()
        if command[:2] == ["git", "status"]:
            return type("Result", (), {"stdout": ""})()
        if command == [str(executable), "--runtime-identity"]:
            return type("Result", (), {"stdout": "not json" if identity is None else json.dumps(identity)})()
        pytest.fail("compiler ran before identity validation")

    with pytest.raises(RuntimeError, match="identity"):
        builder.build(root=root, iscc=compiler, runner=runner)
    assert not (root / "dist" / "installer").exists()
    assert calls[-1] == [str(executable), "--runtime-identity"]


def test_version_comes_unchanged_from_project_metadata(builder):
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert builder.read_version(ROOT) == version
    assert version not in SCRIPT.read_text(encoding="utf-8")
    assert builder.ROOT == ROOT


@pytest.mark.parametrize("route", ("explicit", "environment", "path", "standard", "local"))
@pytest.mark.parametrize("version", ("7", "6"))
def test_compiler_discovery(builder, monkeypatch, tmp_path, route, version):
    for name in ("ISCC_PATH", "ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(builder.shutil, "which", lambda name: None)
    compiler = tmp_path / f"Inno Setup {version}" / "ISCC.exe"
    if route == "local":
        compiler = tmp_path / "Programs" / f"Inno Setup {version}" / "ISCC.exe"
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


@pytest.mark.parametrize("version7_location", ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"))
def test_standard_locations_prefer_version7_over_version6(
    builder, monkeypatch, tmp_path, version7_location,
):
    monkeypatch.delenv("ISCC_PATH", raising=False)
    monkeypatch.setattr(builder.shutil, "which", lambda name: None)
    version7_compiler = None
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = tmp_path / variable
        monkeypatch.setenv(variable, str(base))
        if variable == "LOCALAPPDATA":
            base = base / "Programs"
        version6 = base / "Inno Setup 6" / "ISCC.exe"
        version6.parent.mkdir(parents=True)
        version6.write_bytes(b"stub 6")
        if variable == version7_location:
            version7_compiler = base / "Inno Setup 7" / "ISCC.exe"
            version7_compiler.parent.mkdir(parents=True)
            version7_compiler.write_bytes(b"stub 7")
    assert builder.find_iscc() == version7_compiler.resolve()


@pytest.mark.parametrize("route", ("explicit", "environment", "path"))
def test_configured_and_path_priority_over_standard_locations(
    builder, monkeypatch, tmp_path, route,
):
    for name in ("ISCC_PATH", "ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    compilers = {}
    for name in ("explicit", "environment", "path", "Inno Setup 7"):
        compiler = tmp_path / name / "ISCC.exe"
        compiler.parent.mkdir()
        compiler.write_bytes(b"stub")
        compilers[name] = compiler
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setattr(builder.shutil, "which", lambda name: str(compilers["path"]))
    if route in ("explicit", "environment"):
        monkeypatch.setenv("ISCC_PATH", str(compilers["environment"]))
    explicit = compilers["explicit"] if route == "explicit" else None
    assert builder.find_iscc(explicit) == compilers[route].resolve()


@pytest.mark.parametrize("route", ("explicit", "environment"))
def test_invalid_configured_path_does_not_fall_back(builder, monkeypatch, tmp_path, route):
    available = tmp_path / "ISCC.exe"
    available.write_bytes(b"available compiler")
    monkeypatch.setattr(builder.shutil, "which", lambda name: str(available))
    invalid = tmp_path / "missing" / "ISCC.exe"
    monkeypatch.setenv("ISCC_PATH", str(available if route == "explicit" else invalid))
    with pytest.raises(RuntimeError, match="ISCC.exe not found at configured path"):
        builder.find_iscc(invalid if route == "explicit" else None)


def test_missing_compiler_fails_without_installing(builder, monkeypatch, tmp_path):
    for name in ("ISCC_PATH", "ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(builder.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="manually"):
        builder.find_iscc()
    with pytest.raises(RuntimeError, match="configured path"):
        builder.find_iscc(tmp_path / "ISCC.exe")


@pytest.mark.parametrize("result", ("created", "missing", "failure"))
@pytest.mark.parametrize("version", ("2.3.4b5", "1.0.0b7"))
def test_compiler_invocation_and_output_preserve_existing_files(builder, tmp_path, result, version):
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
    if version == "1.0.0b7":
        assert builder.read_version(ROOT) == version
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    script = root / "packaging" / "windows" / "AstroPilot.iss"
    script.parent.mkdir(parents=True)
    script.write_text(ISS.read_text(encoding="utf-8"), encoding="utf-8")
    compiler = tmp_path / "ISCC.exe"
    compiler.write_bytes(b"stub")
    output_dir = root / "dist" / "installer"
    output = output_dir / f"AstroPilot-{version}-windows-x86_64-setup.exe"
    calls = []

    def runner(command, *, cwd, check, **options):
        calls.append((command, cwd, check))
        if command[:2] == ["git", "rev-parse"]:
            return type("Result", (), {"stdout": "f5479d9\n"})()
        if command[:2] == ["git", "status"]:
            return type("Result", (), {"stdout": ""})()
        if command == [str(executable), "--runtime-identity"]:
            return type("Result", (), {"stdout": json.dumps({
                "application": "astropilot", "version": version,
                "build": "f5479d9", "architecture": "x86_64",
            })})()
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
    assert calls[-1:] == [([
        str(compiler.resolve()), f"/DAppVersion={version}",
        f"/DSourceDir={source}", f"/DInstallerOutputDir={output_dir}", str(script),
    ], root, True)]
    assert executable.read_bytes() == b"existing program"
    assert internal.read_bytes() == b"runtime"
    assert data.read_bytes() == b"existing profile"
    assert build_file.read_bytes() == b"keep"


def metadata_cleanup_rule():
    """Read the actual Inno rule; simulations must not supply their own pattern."""
    import re

    source = ISS.read_text(encoding="utf-8")
    assert "[InstallDelete]" in source
    entries = source.split("[InstallDelete]", 1)[1].split("[", 1)[0]
    entries = [line.strip() for line in entries.splitlines()
               if line.strip() and not line.lstrip().startswith(";")]
    assert len(entries) == 1
    match = re.fullmatch(r'Type: filesandordirs; Name: "([^\"]+)"', entries[0])
    assert match is not None
    return match.group(1)


def test_upgrade_cleanup_is_only_astropilot_metadata_in_program_internal():
    assert metadata_cleanup_rule() == r"{app}\_internal\astropilot-*.dist-info"
    source = ISS.read_text(encoding="utf-8").lower()
    assert "[uninstalldelete]" not in source
    assert "localappdata" not in source
    assert "[code]" not in source


@pytest.mark.parametrize("payload_metadata", ["directory", "archive"])
def test_upgrade_removes_beta2_metadata_and_runtime_reports_beta4(
    tmp_path, monkeypatch, payload_metadata,
):
    import importlib.metadata
    import shutil
    import sys
    import zipfile
    import astropilot.app as app_module

    local = tmp_path / "LocalAppData"
    app = local / "Programs" / "AstroPilot"
    internal = app / "_internal"
    old = internal / "astropilot-1.0.0b2.dist-info"
    old.mkdir(parents=True)
    (old / "METADATA").write_text("Name: astropilot\nVersion: 1.0.0b2\n")
    (old / "nested").mkdir()
    (old / "nested" / "obsolete.txt").write_text("obsolete metadata")
    keep = [
        internal / "requests-2.0.dist-info" / "METADATA",
        internal / "astropilot_helper-1.0.dist-info" / "METADATA",
        internal / "runtime.dll",
        app / "user-note.txt",
        app / "astropilot-1.0.0b2.dist-info" / "METADATA",
        local / "AstroPilot" / "user_profile.json",
        local / "AstroPilot" / "projects.json",
        local / "AstroPilot" / "AstroPilot.log",
        local / "AstroPilot" / "astropilot-1.0.0b2.dist-info" / "METADATA",
    ]
    for path in keep:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preserved")

    # A ZIP models embedded metadata when no dist-info directory is in the payload.
    # Both layouts use real importlib.metadata discovery, not a stub version lookup.
    payload = tmp_path / "payload" / "_internal"
    payload.mkdir(parents=True)
    metadata = "Name: astropilot\nVersion: 1.0.0b4\n"
    if payload_metadata == "directory":
        current = payload / "astropilot-1.0.0b4.dist-info"
        current.mkdir()
        (current / "METADATA").write_text(metadata)
    else:
        with zipfile.ZipFile(payload / "metadata.zip", "w") as archive:
            archive.writestr("astropilot-1.0.0b4.dist-info/METADATA", metadata)
        assert not list(payload.glob("astropilot-*.dist-info"))

    monkeypatch.setattr(sys, "path", [str(internal), str(payload), str(payload / "metadata.zip")])
    # Reproduce the installed/frozen fallback: no source pyproject.toml present.
    monkeypatch.setattr(app_module, "__file__", str(internal / "astropilot" / "app.py"))
    assert importlib.metadata.version("astropilot") == "1.0.0b2"
    assert app_module.canonical_version() == "1.0.0b2"
    pattern = metadata_cleanup_rule().removeprefix("{app}\\").replace("\\", "/")

    # Contractual InstallDelete-before-Files simulation, repeated for reinstall.
    for _ in range(2):
        for path in app.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        shutil.copytree(payload, internal, dirs_exist_ok=True)
        monkeypatch.setattr(sys, "path", [str(internal), str(internal / "metadata.zip")])
        assert not old.exists()
        assert app_module.canonical_version() == "1.0.0b4"
        assert app_module.runtime_identity_payload()["version"] == "1.0.0b4"
        assert all(path.read_bytes() == b"preserved" for path in keep)
