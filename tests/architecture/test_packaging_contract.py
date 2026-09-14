from pathlib import Path
import importlib.util
import sys
import tomllib
from unittest.mock import ANY

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _pyproject():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_installed_package_exposes_astropilot_command():
    project = _pyproject()

    scripts = project["project"]["scripts"]

    assert scripts["astropilot"] == "astro_score:main"
    assert scripts["astropilot-app"] == "astropilot.launcher:main"


def test_project_declares_canonical_beta_version():
    assert _pyproject()["project"]["version"] == "1.0.0b2"

    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    astropilot_package = lock.split('name = "astropilot"', 1)[1].split(
        "[[package]]", 1
    )[0]
    assert 'version = "1.0.0b2"' in astropilot_package
    assert 'version = "0.0.0"' not in astropilot_package


def test_installed_runtime_declares_uvicorn_for_api_and_ui_serving():
    dependencies = _pyproject()["project"]["dependencies"]

    assert "uvicorn>=0.52,<1.0" in dependencies


def test_packaging_dependencies_are_isolated_from_runtime_dependencies():
    project = _pyproject()["project"]

    assert project["dependencies"] == [
        "astral>=3.2,<4.0",
        "astropy>=7.2,<8.0",
        "fastapi>=0.116,<1.0",
        "requests>=2.32,<3.0",
        "timezonefinder>=8,<9",
        "uvicorn>=0.52,<1.0",
    ]
    packaging_dependencies = project["optional-dependencies"]["packaging"]
    assert any(
        dependency.lower().startswith("pyinstaller>=6.")
        and "<7" in dependency
        for dependency in packaging_dependencies
    )
    assert any(
        dependency.lower().startswith("tzdata")
        for dependency in packaging_dependencies
    )


def test_wheel_excludes_internal_decision_tests():
    package_finder = _pyproject()["tool"]["setuptools"]["packages"]["find"]

    assert "decision.tests*" in package_finder["exclude"]


def test_wheel_includes_only_immutable_product_assets():
    package_data = _pyproject()["tool"]["setuptools"]["package-data"]

    assert package_data == {
        "astropilot": ["knowledge/objects/*.json", "web/*"],
    }
    declared_patterns = package_data["astropilot"]
    assert "data/user_profile.json" not in declared_patterns
    assert "user_filters.json" not in declared_patterns


def test_obsolete_image_quality_demo_is_not_shipped_as_a_module():
    assert not (ROOT / "decision" / "test_decision_context_image_quality.py").exists()


def test_launcher_is_directly_executable_without_changing_entry_points():
    launcher = (ROOT / "astropilot" / "launcher.py").read_text(encoding="utf-8")
    scripts = _pyproject()["project"]["scripts"]

    assert 'if __name__ == "__main__":' in launcher
    assert scripts == {
        "astropilot": "astro_score:main",
        "astropilot-app": "astropilot.launcher:main",
    }


def test_spec_defines_arm64_windowed_onedir_application():
    spec = (ROOT / "AstroPilot.spec").read_text(encoding="utf-8")

    assert 'astropilot" / "launcher.py"' in spec
    assert 'name="AstroPilot"' in spec
    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec
    assert "console=False" in spec
    assert 'target_arch="arm64"' in spec
    assert 'name="AstroPilot.app"' in spec
    assert 'bundle_identifier="fr.astropilot.desktop"' in spec
    assert 'CFBundleShortVersionString": MARKETING_VERSION' in spec
    assert 'CFBundleVersion": BUNDLE_BUILD_NUMBER' in spec
    assert 'MARKETING_VERSION = f"{major}.{minor}.{patch}"' in spec
    assert "BUNDLE_BUILD_NUMBER = beta" in spec


def test_spec_collects_exact_runtime_assets_without_broad_hidden_imports():
    spec = (ROOT / "AstroPilot.spec").read_text(encoding="utf-8")

    for asset in ("index.html", "app.js", "styles.css"):
        assert asset in spec
    assert '"astropilot/web"' in spec
    assert '"*.json"' in spec
    assert '"astropilot/knowledge/objects"' in spec
    assert 'collect_data_files("timezonefinder_data")' in spec
    assert 'collect_data_files("astropy_iers_data")' in spec
    assert 'collect_data_files("tzdata")' in spec
    assert 'copy_metadata("astropilot")' in spec
    assert "hiddenimports=[]" in spec
    assert "collect_submodules" not in spec
    assert "tests/data" not in spec


def _build_module():
    path = ROOT / "scripts" / "build_macos.py"
    spec = importlib.util.spec_from_file_location("astropilot_build_macos", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_rejects_unsupported_platform_and_architecture(monkeypatch):
    build = _build_module()

    monkeypatch.setattr(build.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="macOS"):
        build.validate_target()

    monkeypatch.setattr(build.sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: "x86_64")
    with pytest.raises(RuntimeError, match="arm64"):
        build.validate_target()


def test_build_script_documents_isolated_locked_packaging_environment():
    script = (ROOT / "scripts" / "build_macos.py").read_text(encoding="utf-8")

    assert (
        "UV_PROJECT_ENVIRONMENT=.venv-packaging "
        "uv sync --locked --extra packaging"
    ) in script


def test_build_script_cleans_only_repository_local_outputs(tmp_path):
    build = _build_module()
    outside = tmp_path.parent / "outside-build-sentinel"
    outside.mkdir(exist_ok=True)
    for name in ("build", "dist"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "artifact").write_text("generated", encoding="utf-8")

    build.clean_outputs(tmp_path)

    assert not (tmp_path / "build").exists()
    assert not (tmp_path / "dist").exists()
    assert outside.is_dir()


def test_build_script_invokes_current_python_and_verifies_bundle(
    tmp_path,
    monkeypatch,
):
    build = _build_module()
    calls = []
    monkeypatch.setattr(build.sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")

    def runner(command, *, cwd, check, **options):
        calls.append((command, cwd, check, options))
        if command[:2] == ["git", "rev-parse"]:
            return type("Result", (), {"stdout": "8541acc\n"})()
        (tmp_path / "dist" / "AstroPilot.app").mkdir(parents=True)

    output = build.build(root=tmp_path, runner=runner)

    assert calls == [
        (
            ["git", "rev-parse", "--short=7", "HEAD"],
            tmp_path,
            True,
            {"capture_output": True, "text": True},
        ),
        (
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "AstroPilot.spec",
            ],
            tmp_path,
            True,
            {"env": ANY},
        )
    ]
    assert calls[1][3]["env"]["ASTROPILOT_BUILD_COMMIT"] == "8541acc"
    assert output == tmp_path / "dist" / "AstroPilot.app"


def test_build_script_fails_when_bundle_is_missing(tmp_path, monkeypatch):
    build = _build_module()
    monkeypatch.setattr(build.sys, "platform", "darwin")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")

    def runner(command, **kwargs):
        if command[:2] == ["git", "rev-parse"]:
            return type("Result", (), {"stdout": "8541acc\n"})()

    with pytest.raises(RuntimeError, match="dist/AstroPilot.app"):
        build.build(root=tmp_path, runner=runner)


@pytest.mark.parametrize("value", ["", "8541ac", "not-git", "8541acc8"])
def test_build_script_rejects_invalid_short_git_commit(tmp_path, value):
    build = _build_module()

    with pytest.raises(RuntimeError, match="7 hexadecimal"):
        build.resolve_build_commit(
            tmp_path,
            runner=lambda *args, **kwargs: type(
                "Result", (), {"stdout": value}
            )(),
        )


def test_tester_label_and_future_artifact_name_are_deterministic():
    build = _build_module()

    assert build.tester_version_label("1.0.0b2") == "1.0.0-beta.2"
    assert build.artifact_name("1.0.0b2", "arm64") == (
        "AstroPilot-1.0.0-beta.2-macos-arm64.zip"
    )


def test_runtime_identity_has_no_git_subprocess_dependency():
    runtime_sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("astropilot/app.py", "astropilot/launcher.py")
    )

    assert "git rev-parse" not in runtime_sources
    assert "subprocess" not in runtime_sources


def test_build_identity_is_injected_by_generated_ignored_runtime_hook():
    spec = (ROOT / "AstroPilot.spec").read_text(encoding="utf-8")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "ASTROPILOT_BUILD_COMMIT" in spec
    assert "runtime_hooks=[" in spec
    assert "build/" in ignored


def test_fastapi_version_derives_from_canonical_project_version():
    from astropilot.app import canonical_version, create_app

    assert canonical_version() == "1.0.0b2"
    assert create_app().version == canonical_version()


def test_generated_packaging_outputs_are_ignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "build/" in ignored
    assert "dist/" in ignored
    assert ".venv-packaging/" in ignored
    assert "AstroPilot.spec" not in ignored
    assert "scripts/build_macos.py" not in ignored


def test_build_definition_has_no_local_paths_or_release_operations():
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("AstroPilot.spec", "scripts/build_macos.py")
    )

    assert "/Users/" not in sources
    assert ".venv/" not in sources
    assert "Anaconda" not in sources
    assert "Miniconda" not in sources
    assert "codesign" not in sources
    assert "notar" not in sources.lower()
    assert "dmg" not in sources.lower()
    assert "zipfile" not in sources.lower()
    assert "shutil.make_archive" not in sources
    assert "ditto" not in sources.lower()
