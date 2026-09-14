"""Build AstroPilot after creating the isolated packaging environment with:

UV_PROJECT_ENVIRONMENT=.venv-packaging uv sync --locked --extra packaging
"""

from __future__ import annotations

from pathlib import Path
import os
import platform
import re
import shutil
import subprocess
import sys
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
SHORT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{7}")
BETA_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)b(\d+)")


def validate_target() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("AstroPilot packaging requires macOS.")
    if platform.machine() != "arm64":
        raise RuntimeError("AstroPilot packaging requires an arm64 host.")


def clean_outputs(root: Path = ROOT) -> None:
    root = Path(root).resolve()
    for name in ("build", "dist"):
        output = (root / name).resolve()
        if output.parent != root:
            raise RuntimeError("Refusing to clean outside the repository root.")
        if output.exists():
            shutil.rmtree(output)


def resolve_build_commit(
    root: Path = ROOT,
    *,
    runner: Callable[..., object] = subprocess.run,
) -> str:
    result = runner(
        ["git", "rev-parse", "--short=7", "HEAD"],
        cwd=Path(root).resolve(),
        check=True,
        capture_output=True,
        text=True,
    )
    commit = str(getattr(result, "stdout", "")).strip()
    if not SHORT_COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeError("Git commit must be exactly 7 hexadecimal characters.")
    return commit


def tester_version_label(version: str) -> str:
    match = BETA_VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError("Expected a PEP 440 beta version.")
    major, minor, patch, beta = match.groups()
    return f"{major}.{minor}.{patch}-beta.{beta}"


def artifact_name(version: str, architecture: str) -> str:
    return f"AstroPilot-{tester_version_label(version)}-macos-{architecture}.zip"


def build(
    *,
    root: Path = ROOT,
    runner: Callable[..., object] = subprocess.run,
) -> Path:
    validate_target()
    root = Path(root).resolve()
    clean_outputs(root)
    build_commit = resolve_build_commit(root, runner=runner)
    build_environment = os.environ.copy()
    build_environment["ASTROPILOT_BUILD_COMMIT"] = build_commit
    command: Sequence[str] = (
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "AstroPilot.spec",
    )
    runner(list(command), cwd=root, check=True, env=build_environment)

    application = root / "dist" / "AstroPilot.app"
    if not application.is_dir():
        raise RuntimeError(
            "Expected bundle was not created: dist/AstroPilot.app"
        )
    return application


def main() -> None:
    build()


if __name__ == "__main__":
    main()
