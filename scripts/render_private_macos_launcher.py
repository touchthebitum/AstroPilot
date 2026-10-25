"""Render auditable private Mac launcher sources into a new build directory."""
from pathlib import Path
import re


def render(source_sha: str, output: Path, *, data_mode="isolated"):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Full lowercase source SHA required")
    if data_mode not in {"stable", "isolated"}:
        raise ValueError("Unknown private data mode")
    output.mkdir(parents=True, exist_ok=False)
    text = (Path(__file__).with_name("private_beta_macos") / "launcher.py").read_text()
    (output / "launcher.py").write_text(text.replace("__SOURCE_SHA__", source_sha).replace("__DATA_MODE__", data_mode))
    for name, arguments in [("DEMARRER-BETA.command", ""), ("ARRETER-BETA.command", " --stop"),
                            ("GERER-MES-DONNEES.command", " --data-transfer")]:
        path = output / name
        path.write_text('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\n./BetaLauncher/BetaLauncher' + arguments + '\n')
        path.chmod(0o755)
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-mode", choices=["stable", "isolated"], default="isolated")
    args = parser.parse_args()
    render(args.source_sha, args.output, data_mode=args.data_mode)
