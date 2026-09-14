"""Build AstroPilot after creating the isolated packaging environment with:

UV_PROJECT_ENVIRONMENT=.venv-packaging uv sync --locked --extra packaging
"""

from __future__ import annotations

from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]


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


def build(
    *,
    root: Path = ROOT,
    runner: Callable[..., object] = subprocess.run,
) -> Path:
    validate_target()
    root = Path(root).resolve()
    clean_outputs(root)
    command: Sequence[str] = (
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "AstroPilot.spec",
    )
    runner(list(command), cwd=root, check=True)

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
