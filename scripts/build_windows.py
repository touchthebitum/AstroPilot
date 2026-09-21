"""Synchronize the Windows packaging environment and build AstroPilot."""

from __future__ import annotations

from pathlib import Path
import os
import platform
import re
import shutil
import subprocess
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_RELEASE_TARGET_ARCHITECTURE = "x86_64"
WINDOWS_X86_64_HOST_ALIASES = frozenset({"amd64", "x86_64"})
SHORT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{7}")


def validate_target() -> str:
    if platform.system() != "Windows":
        raise RuntimeError("AstroPilot Windows packaging requires Windows.")
    if platform.machine().lower() not in WINDOWS_X86_64_HOST_ALIASES:
        raise RuntimeError(
            "AstroPilot Windows packaging requires an x86_64 host."
        )
    return WINDOWS_RELEASE_TARGET_ARCHITECTURE


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


def build_environment(build_commit: str) -> dict[str, str]:
    if not SHORT_COMMIT_PATTERN.fullmatch(build_commit):
        raise RuntimeError("Git commit must be exactly 7 hexadecimal characters.")
    environment = os.environ.copy()
    environment["ASTROPILOT_BUILD_COMMIT"] = build_commit
    return environment


def build(
    *,
    root: Path = ROOT,
    runner: Callable[..., object] = subprocess.run,
) -> Path:
    validate_target()
    root = Path(root).resolve()
    build_commit = resolve_build_commit(root, runner=runner)
    status = runner(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root, check=True, capture_output=True, text=True,
    )
    if str(getattr(status, "stdout", "")).strip():
        raise RuntimeError("Release build requires a clean committed checkout.")
    runner(["uv", "sync", "--locked", "--extra", "packaging"], cwd=root, check=True)
    clean_outputs(root)
    environment = build_environment(build_commit)
    command: Sequence[str] = (
        "uv", "run", "--locked", "--extra", "packaging", "python", "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "AstroPilot-windows.spec",
    )
    runner(list(command), cwd=root, check=True, env=environment)

    output = root / "dist" / "AstroPilot"
    if not output.is_dir():
        raise RuntimeError("Expected onedir output was not created: dist/AstroPilot")
    return output


def main() -> None:
    build()


if __name__ == "__main__":
    main()
