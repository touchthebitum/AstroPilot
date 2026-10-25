"""Render the private Sandbox launcher from reviewed sources, without running it."""
from pathlib import Path
import argparse
import base64
import hashlib
import re

TEMPLATES = Path(__file__).with_name('private_beta_windows')


def render(source_sha: str, output: Path, *, data_mode="isolated"):
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha):
        raise ValueError('Full lowercase source SHA required')
    if data_mode not in {"stable", "isolated"}:
        raise ValueError("Unknown private data mode")
    # A generated launcher must never overwrite an existing kit or profile.
    output.mkdir(parents=True, exist_ok=False)
    audit = output / 'Audit'
    audit.mkdir()
    for name in ['controller.ps1', 'launch-sandbox.ps1', 'sandbox-start.cmd']:
        text = (TEMPLATES / name).read_text(encoding='utf-8')
        text = text.replace('__SOURCE_SHA__', source_sha).replace('__SOURCE_SHORT__', source_sha[:7]).replace('__DATA_MODE__', data_mode)
        target = audit / name if name.endswith('.ps1') else output / name
        target.write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    host_hash = hashlib.sha256((audit / 'launch-sandbox.ps1').read_bytes()).hexdigest()
    # Only constant bootstrap code is executable; the host path stays an env value.
    # Verify the reviewed host script before it creates the Sandbox configuration.
    bootstrap = ("$ErrorActionPreference='Stop';"
                 "$script=Join-Path $env:NIGHTMERIT_PRIVATE_KIT 'Audit\\launch-sandbox.ps1';"
                 f"if((Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant() -cne '{host_hash}')"
                 "{throw 'Lanceur modifie. Extrayez une nouvelle copie du kit.'};"
                 "& ([ScriptBlock]::Create([IO.File]::ReadAllText($script)))")
    for name, mode in [('LANCER-TEST-WINDOWS.cmd', '0'), ('GERER-MES-DONNEES.cmd', '1')]:
        code = "$env:NIGHTMERIT_OPEN_DATA_TRANSFER='" + mode + "';" + bootstrap
        encoded = base64.b64encode(code.encode('utf-16le')).decode('ascii')
        cmd = ('@echo off\r\nset "NIGHTMERIT_PRIVATE_KIT=%~dp0"\r\n'
               f'powershell.exe -NoProfile -EncodedCommand {encoded}\r\nif errorlevel 1 pause\r\n')
        assert max(map(len, cmd.splitlines())) < 8190
        (output / name).write_bytes(cmd.encode('ascii'))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument("--data-mode", choices=["stable", "isolated"], default="isolated")
    args = parser.parse_args()
    render(args.source_sha, args.output, data_mode=args.data_mode)


if __name__ == '__main__':
    main()
