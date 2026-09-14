"""Build, notarize, and package the closed-beta macOS application."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib
from typing import Callable, NamedTuple

from build_macos import artifact_name, build


ROOT = Path(__file__).resolve().parents[1]
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MACOS_RELEASE_TARGET_ARCHITECTURE = "arm64"


class ReleaseResult(NamedTuple):
    artifact: Path
    sidecar: Path
    sha256: str
    submission_id: str


def _project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _run(
    runner: Callable[..., object],
    command: list[str],
    *,
    root: Path,
    capture_output: bool = False,
) -> object:
    options: dict[str, object] = {"cwd": root, "check": True}
    if capture_output:
        options.update(capture_output=True, text=True)
    return runner(command, **options)


def release(
    *,
    root: Path = ROOT,
    codesign_identity: str,
    notary_profile: str,
    target_architecture: str = MACOS_RELEASE_TARGET_ARCHITECTURE,
    build_function: Callable[..., Path] = build,
    runner: Callable[..., object] = subprocess.run,
) -> ReleaseResult:
    root = Path(root).resolve()
    if not codesign_identity.strip():
        raise RuntimeError("A Developer ID Application identity is required.")
    if not notary_profile.strip():
        raise RuntimeError("A notarytool keychain profile is required.")
    if target_architecture != MACOS_RELEASE_TARGET_ARCHITECTURE:
        raise RuntimeError("The macOS release target must be arm64.")

    application = build_function(
        root=root,
        codesign_identity=codesign_identity,
    )
    _run(
        runner,
        [
            "codesign",
            "--verify",
            "--deep",
            "--strict",
            "--verbose=4",
            str(application),
        ],
        root=root,
    )
    _run(
        runner,
        ["codesign", "-dv", "--verbose=4", str(application)],
        root=root,
    )

    notarization_dir = root / "build" / "notarization"
    notarization_dir.mkdir(parents=True, exist_ok=True)
    upload = notarization_dir / "AstroPilot-notarization-upload.zip"
    upload.unlink(missing_ok=True)
    _run(
        runner,
        ["ditto", "-c", "-k", "--keepParent", str(application), str(upload)],
        root=root,
    )

    submission = _run(
        runner,
        [
            "xcrun",
            "notarytool",
            "submit",
            str(upload),
            "--keychain-profile",
            notary_profile,
            "--wait",
            "--output-format",
            "json",
        ],
        root=root,
        capture_output=True,
    )
    response = json.loads(str(getattr(submission, "stdout", "")))
    if not isinstance(response, dict) or response.get("status") != "Accepted":
        raise RuntimeError("Apple notarization was not accepted.")
    submission_id = response.get("id")
    if not isinstance(submission_id, str) or not submission_id:
        raise RuntimeError("Apple notarization returned no submission identifier.")
    upload.unlink(missing_ok=True)

    _run(
        runner,
        ["xcrun", "stapler", "staple", str(application)],
        root=root,
    )
    _run(
        runner,
        ["xcrun", "stapler", "validate", str(application)],
        root=root,
    )
    _run(
        runner,
        [
            "spctl",
            "--assess",
            "--type",
            "execute",
            "--verbose=4",
            str(application),
        ],
        root=root,
    )

    artifact = root / "dist" / artifact_name(
        _project_version(root),
        target_architecture,
    )
    artifact.unlink(missing_ok=True)
    _run(
        runner,
        [
            "ditto",
            "-c",
            "-k",
            "--keepParent",
            str(application),
            str(artifact),
        ],
        root=root,
    )
    checksum = _run(
        runner,
        ["shasum", "-a", "256", str(artifact)],
        root=root,
        capture_output=True,
    )
    digest = str(getattr(checksum, "stdout", "")).split(maxsplit=1)[0]
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise RuntimeError("Could not determine the release artifact SHA-256.")
    sidecar = artifact.with_suffix(artifact.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
    return ReleaseResult(artifact, sidecar, digest, submission_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--codesign-identity",
        default=os.environ.get("ASTROPILOT_CODESIGN_IDENTITY"),
        required=os.environ.get("ASTROPILOT_CODESIGN_IDENTITY") is None,
    )
    parser.add_argument("--notary-profile", required=True)
    arguments = parser.parse_args()
    result = release(
        codesign_identity=arguments.codesign_identity,
        notary_profile=arguments.notary_profile,
    )
    print(result.artifact)
    print(result.sha256)


if __name__ == "__main__":
    main()
