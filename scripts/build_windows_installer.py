"""Compile a per-user installer from an existing Windows onedir build."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tomllib
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]


def validate_target() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("The Windows installer build requires Windows.")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("The Windows installer build requires an x86_64 host.")


def read_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", version):
        raise RuntimeError("project.version must be nonempty and safe for an installer filename.")
    return version


def find_iscc(explicit: str | Path | None = None) -> Path:
    configured = explicit if explicit is not None else os.environ.get("ISCC_PATH")
    if configured is not None:
        candidate = Path(configured).expanduser()
        if candidate.name.lower() != "iscc.exe" or not candidate.is_file():
            raise RuntimeError(f"ISCC.exe not found at configured path: {candidate}")
        return candidate.resolve()

    on_path = shutil.which("ISCC.exe")
    if on_path:
        return Path(on_path).resolve()

    standard_roots = []
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(variable)
        if base:
            standard_roots.append(Path(base))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        standard_roots.append(Path(local) / "Programs")
    for directory in ("Inno Setup 7", "Inno Setup 6"):
        for base in standard_roots:
            candidate = base / directory / "ISCC.exe"
            if candidate.is_file():
                return candidate.resolve()
    raise RuntimeError(
        "ISCC.exe not found. Install Inno Setup 7 (or 6.3+) manually, then use "
        "--iscc or ISCC_PATH to supply its executable path."
    )


def build(
    *,
    root: Path = ROOT,
    iscc: str | Path | None = None,
    runner: Callable[..., object] = subprocess.run,
) -> Path:
    validate_target()
    root = Path(root).resolve()
    source = root / "dist" / "AstroPilot"
    if not source.is_dir() or not any(source.iterdir()):
        raise RuntimeError("Existing nonempty onedir build required: dist/AstroPilot")
    if not (source / "AstroPilot.exe").is_file():
        raise RuntimeError("Existing executable required: dist/AstroPilot/AstroPilot.exe")
    version = read_version(root)
    compiler = find_iscc(iscc)
    script = root / "packaging" / "windows" / "AstroPilot.iss"
    if not script.is_file():
        raise RuntimeError(f"Installer script not found: {script}")
    output_dir = root / "dist" / "installer"
    output = output_dir / f"AstroPilot-{version}-windows-x86_64-setup.exe"
    runner(
        [
            str(compiler),
            f"/DAppVersion={version}",
            f"/DSourceDir={source}",
            f"/DInstallerOutputDir={output_dir}",
            str(script),
        ],
        cwd=root,
        check=True,
    )
    if not output.is_file():
        raise RuntimeError(f"Expected installer was not created: {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", type=Path, help="Explicit path to ISCC.exe (overrides ISCC_PATH)")
    args = parser.parse_args()
    try:
        print(build(iscc=args.iscc))
    except (RuntimeError, OSError, KeyError, tomllib.TOMLDecodeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Installer build failed: {error}\n")


if __name__ == "__main__":
    main()
