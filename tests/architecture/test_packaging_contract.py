from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def _pyproject():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_installed_package_exposes_astropilot_command():
    project = _pyproject()

    assert project["project"]["scripts"] == {
        "astropilot": "astro_score:main",
    }


def test_wheel_excludes_internal_decision_tests():
    package_finder = _pyproject()["tool"]["setuptools"]["packages"]["find"]

    assert "decision.tests*" in package_finder["exclude"]


def test_obsolete_image_quality_demo_is_not_shipped_as_a_module():
    assert not (ROOT / "decision" / "test_decision_context_image_quality.py").exists()
