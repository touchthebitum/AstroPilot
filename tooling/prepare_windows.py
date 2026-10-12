"""Export only the freshly built beta 8 Windows candidate and its provenance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def command(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


USER_DATA_DIRECTORIES = frozenset({
    'field_observations', 'outcome_evaluations', 'execution_records',
    'execution_lineage', 'decision_lineage', 'decision_acceptance_lineage', 'decision_forecast_evidence',
    'guardian_scheduler', 'opportunity_alert_scheduler',
})
USER_DATA_FILENAMES = frozenset({
    'user_profile.json', 'user_filters.json', '.env',
    'opportunity_alert_ledger.json', 'opportunity_alert_status.json',
    'opportunity_alert_scheduler.json', '.outcome_history_cursor.key.lock',
})


def scan_payload(payload: Path) -> tuple[list[Path], list[dict]]:
    require(payload.is_dir() and not payload.is_symlink() and not payload.is_junction(),
            'A regular payload directory is required.')
    def fail(error: OSError) -> None:
        raise error

    files = []
    inventory = []
    for parent, directories, names in os.walk(payload, followlinks=False, onerror=fail):
        for name in directories + names:
            path = Path(parent) / name
            require(name.lower() not in USER_DATA_DIRECTORIES, f'User data directory: {path}')
            require(not path.is_symlink() and not path.is_junction(), f'Unexpected link: {path}')
        for name in names:
            path = Path(parent) / name
            require(path.is_file(), f'Unexpected file type: {path}')
            lower = name.lower()
            relative = path.relative_to(payload).as_posix().lower()
            require(lower not in USER_DATA_FILENAMES
                    and not lower.startswith(('.env.', '.user_profile.', '.opportunity_alert_', '.guardian_', '.outcome_history_' ))
                    and path.suffix.lower() not in {'.p12', '.pfx', '.key', '.db', '.sqlite', '.sqlite3', '.log', '.jsonl'}
                    and (path.suffix.lower() != '.pem' or relative == '_internal/certifi/cacert.pem'),
                    f'Forbidden user data or credential file: {path}')
            files.append(path)
            inventory.append({'path': path.relative_to(payload).as_posix(),
                              'size': path.stat().st_size, 'sha256': digest(path)})
    require(files, 'Empty portable payload.')
    return files, inventory


def prepare(approved_sha: str, *, check_payload_only: bool = False) -> Path:
    require(sys.platform == 'win32' and platform.machine().lower() in {'amd64', 'x86_64'},
            'Windows x86_64 is required.')
    require(re.fullmatch('[0-9a-f]{40}', approved_sha) is not None, 'Full source SHA required.')
    require(command(['git', 'rev-parse', 'HEAD']) == approved_sha, 'Source SHA mismatch.')
    require(not command(['git', 'status', '--porcelain', '--untracked-files=all']),
            'A clean committed checkout is required.')
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    require(version == '1.0.0b8', 'Only beta 8 is accepted.')
    short_sha = command(['git', 'rev-parse', '--short=7', 'HEAD'])
    require(re.fullmatch('[0-9a-f]{7}', short_sha) is not None, 'Unexpected short build identity.')
    data_dir = os.environ.get('ASTROPILOT_DATA_DIR')
    runner_temp = os.environ.get('RUNNER_TEMP')
    require(data_dir and runner_temp, 'An isolated runner data directory is required.')
    Path(data_dir).resolve(strict=True).relative_to(Path(runner_temp).resolve(strict=True))

    payload = ROOT / 'dist/AstroPilot'
    executable = payload / 'AstroPilot.exe'
    installer = ROOT / f'dist/installer/AstroPilot-{version}-windows-x86_64-setup.exe'
    files, inventory = scan_payload(payload)
    require(executable.is_file(), 'Built executable required.')
    identity = json.loads(subprocess.check_output(
        [str(executable), '--runtime-identity'], cwd=payload, text=True, timeout=60))
    require(isinstance(identity, dict), 'Executable identity must be a JSON object.')
    require(all(identity.get(k) == v for k, v in {
        'application': 'astropilot', 'version': version,
        'build': short_sha, 'architecture': 'x86_64',
    }.items()), 'Executable runtime identity mismatch.')
    with executable.open('rb') as stream:
        require(stream.read(2) == b'MZ', 'Invalid executable.')
        stream.seek(0x3c)
        offset = struct.unpack('<I', stream.read(4))[0]
        stream.seek(offset)
        require(stream.read(4) == b'PE\0\0' and struct.unpack('<H', stream.read(2))[0] == 0x8664,
                'The executable must be PE x86_64.')

    for name in ('index.html', 'app.js', 'styles.css', 'help.js', 'alert-status.js'):
        require((payload / '_internal/astropilot/web' / name).is_file(), f'Missing UI asset: {name}')
    require((payload / '_internal/certifi/cacert.pem').is_file(), 'certifi CA bundle is missing.')

    if check_payload_only:
        return payload
    require(installer.is_file() and not installer.is_symlink() and not installer.is_junction(),
            'A regular built installer is required.')
    output = ROOT / 'dist/beta8-artifacts'
    require(not output.exists(), 'Artifact output already exists; use a fresh build.')
    output.mkdir()
    setup = output / installer.name
    shutil.copy2(installer, setup)
    portable = output / f'AstroPilot-{version}-windows-x86_64-portable.zip'
    with zipfile.ZipFile(portable, 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, 'AstroPilot/' + path.relative_to(payload).as_posix())
    with zipfile.ZipFile(portable) as archive:
        require(archive.testzip() is None, 'Portable ZIP integrity failure.')
        require(len(archive.infolist()) == len(inventory), 'Portable ZIP inventory mismatch.')
        for row in inventory:
            require(hashlib.sha256(archive.read('AstroPilot/' + row['path'])).hexdigest() == row['sha256'],
                    'Portable ZIP content mismatch.')
    require(digest(setup) == digest(installer), 'Installer copy mismatch.')
    artifacts = {path.name: {'sha256': digest(path), 'size': path.stat().st_size}
                 for path in (setup, portable)}
    sums = ''.join(f"{entry['sha256']}  {name}\n" for name, entry in sorted(artifacts.items()))
    (output / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8')
    for name, entry in artifacts.items():
        (output / (name + '.sha256')).write_text(f"{entry['sha256']}  {name}\n", encoding='utf-8')
    provenance = {
        'application': 'AstroPilot', 'version': version,
        'source_sha': approved_sha, 'runtime_identity': identity,
        'target': 'windows-x86_64', 'signature': 'unsigned',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'uv_lock_sha256': digest(ROOT / 'uv.lock'),
        'python': sys.version, 'uv': command(['uv', '--version']),
        'pyinstaller': metadata.version('pyinstaller'),
        'inno_setup_version': os.environ.get('INNO_SETUP_VERSION'),
        'installed_distributions': sorted(
            [{'name': d.metadata['Name'], 'version': d.version} for d in metadata.distributions()],
            key=lambda row: (row['name'].lower(), row['version'])),
        'runner_image': {'os': os.environ.get('ImageOS'), 'version': os.environ.get('ImageVersion')},
        'workflow': {key: os.environ.get(key) for key in (
            'GITHUB_REPOSITORY', 'GITHUB_WORKFLOW_REF', 'GITHUB_WORKFLOW_SHA',
            'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
        'artifacts': artifacts, 'portable_inventory': sorted(inventory, key=lambda row: row['path']),
        'validation': 'Build candidate only; Windows 11 physical-PC validation remains required.',
        'guardian_live_transport': 'Frozen Windows worker implemented with strict certifi TLS; native Windows 11 qualification pending.',
    }
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    require(not command(['git', 'status', '--porcelain', '--untracked-files=all']),
            'Tracked sources changed during packaging.')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-sha', required=True)
    parser.add_argument('--check-payload-only', action='store_true',
                        help='Validate the payload before creating the installer; do not export files.')
    args = parser.parse_args()
    print(prepare(args.approved_sha, check_payload_only=args.check_payload_only))
