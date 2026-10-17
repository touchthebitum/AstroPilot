"""Regression coverage for the actual Windows candidate workflow entry point."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/prepare_beta8_windows_artifacts.py'
SHA = 'a' * 40


def exporter():
    spec = importlib.util.spec_from_file_location('candidate_export', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_export_entrypoint_is_shipped_and_callable_without_app_startup():
    # This failed on main: the manual workflow referred to a missing file.
    result = subprocess.run([sys.executable, str(SCRIPT), '--help'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--approved-sha' in result.stdout and '--check-payload-only' in result.stdout


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    module = exporter()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='win32', version='test Python'))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'AMD64')
    monkeypatch.setattr(module, 'command', lambda args: {
        ('git', 'rev-parse', 'HEAD'): SHA,
        ('git', 'rev-parse', '--short=7', 'HEAD'): SHA[:7],
        ('git', 'status', '--porcelain', '--untracked-files=all'): '',
        ('uv', '--version'): 'uv test',
    }[tuple(args)])
    identity = dict(application='astropilot', version='1.0.0b8', build=SHA[:7], architecture='x86_64')
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *a, **k: json.dumps(identity))
    monkeypatch.setattr(module.metadata, 'version', lambda _: 'test')
    monkeypatch.setattr(module.metadata, 'distributions', lambda: [])
    data = tmp_path / 'runner/data'; data.mkdir(parents=True)
    monkeypatch.setenv('RUNNER_TEMP', str(data.parent))
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(data))
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion="1.0.0b8"\n', encoding='utf-8')
    (tmp_path / 'uv.lock').write_text('test lock', encoding='utf-8')
    monkeypatch.setenv('ISCC_PATH', str(tmp_path / 'ISCC.exe'))
    monkeypatch.setattr(module, 'inno_setup_provenance', lambda _: {
        'version': '6.5.4', 'source': 'engine_banner_no_output_compile',
        'compiler_sha256': 'c' * 64, 'engine_sha256': 'e' * 64})
    payload = tmp_path / 'dist/AstroPilot'; payload.mkdir(parents=True)
    pe = bytearray(144); pe[:2] = b'MZ'; struct.pack_into('<I', pe, 0x3c, 128)
    pe[128:132] = b'PE\0\0'; struct.pack_into('<H', pe, 132, 0x8664)
    (payload / 'AstroPilot.exe').write_bytes(pe)
    for asset in ('index.html', 'app.js', 'styles.css', 'help.js', 'alert-status.js'):
        path = payload / '_internal/astropilot/web' / asset
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'public UI')
    cert = payload / '_internal/certifi/cacert.pem'
    cert.parent.mkdir(parents=True); cert.write_bytes(b'public CA bundle')
    return module, payload, identity


def test_preinstaller_scan_requires_no_installer_and_exports_nothing(candidate):
    module, payload, _ = candidate
    assert module.prepare(SHA, check_payload_only=True) == payload
    assert not (module.ROOT / 'dist/beta8-artifacts').exists()


def test_export_preserves_payload_and_records_exact_zip_hashes_and_source(candidate):
    module, payload, identity = candidate
    before = {p.relative_to(payload).as_posix(): p.read_bytes() for p in payload.rglob('*') if p.is_file()}
    installer = module.ROOT / 'dist/installer/AstroPilot-1.0.0b8-windows-x86_64-setup.exe'
    installer.parent.mkdir(); installer.write_bytes(b'test installer')
    output = module.prepare(SHA)
    proof = json.loads((output / 'provenance.json').read_text(encoding='utf-8'))
    assert proof['source_sha'] == SHA and proof['runtime_identity'] == identity
    assert proof['inno_setup_version'] == proof['inno_setup']['version'] == '6.5.4'
    assert proof['inno_setup']['compiler_sha256'] == 'c' * 64
    assert proof['uv_lock_sha256'] == module.digest(module.ROOT / 'uv.lock')
    for name, row in proof['artifacts'].items():
        assert row['sha256'] == module.digest(output / name)
        assert row['size'] == (output / name).stat().st_size
    with zipfile.ZipFile(output / 'AstroPilot-1.0.0b8-windows-x86_64-portable.zip') as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {'AstroPilot/' + name for name in before}
        for row in proof['portable_inventory']:
            content = archive.read('AstroPilot/' + row['path'])
            assert content == before[row['path']]
            assert hashlib.sha256(content).hexdigest() == row['sha256']
    assert {p.relative_to(payload).as_posix(): p.read_bytes() for p in payload.rglob('*') if p.is_file()} == before
    with pytest.raises(RuntimeError, match='already exists'):
        module.prepare(SHA)


@pytest.mark.parametrize('relative', ['user_profile.json', 'USER_FILTERS.JSON', 'guardian_runtime.json',
    'nested/.env', 'nested/.env.local', 'private.key', 'secret.pem', 'session.sqlite3',
    'execution_lineage/one.json', 'decision_lineage/one.json', 'Logs/no-extension'])
def test_private_payload_refused_before_installer_or_export(candidate, relative):
    module, payload, _ = candidate
    bad = payload / relative; bad.parent.mkdir(parents=True, exist_ok=True); bad.write_bytes(b'private')
    with pytest.raises(RuntimeError, match='User data|Forbidden'):
        module.prepare(SHA, check_payload_only=True)
    assert not (module.ROOT / 'dist/beta8-artifacts').exists()


@pytest.mark.parametrize('damage', ['wrong-sha', 'dirty', 'wrong-build', 'wrong-architecture', 'wrong-pe', 'missing-asset', 'outside-sandbox', 'missing-installer'])
def test_candidate_identity_and_preconditions_fail_closed(candidate, monkeypatch, damage):
    module, payload, identity = candidate
    sha = SHA
    if damage == 'wrong-sha': sha = 'b' * 40
    elif damage == 'dirty':
        original = module.command
        monkeypatch.setattr(module, 'command', lambda args: '?? private.json' if args[1] == 'status' else original(args))
    elif damage == 'wrong-build': identity['build'] = 'bbbbbbb'
    elif damage == 'wrong-architecture': identity['architecture'] = 'arm64'
    elif damage == 'wrong-pe':
        path = payload / 'AstroPilot.exe'; content = bytearray(path.read_bytes()); struct.pack_into('<H', content, 132, 0x14c); path.write_bytes(content)
    elif damage == 'missing-asset': (payload / '_internal/astropilot/web/help.js').unlink()
    elif damage == 'outside-sandbox': monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(payload))
    with pytest.raises((RuntimeError, ValueError)):
        module.prepare(sha, check_payload_only=damage != 'missing-installer')
    assert not (module.ROOT / 'dist/beta8-artifacts').exists()


def test_windows_reparse_point_is_treated_as_link_even_without_is_junction(candidate, monkeypatch):
    module, _, _ = candidate
    path = SimpleNamespace(is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0x400))
    assert module.is_link(path)


@pytest.mark.parametrize('root_link', [False, True])
def test_linked_payload_or_directory_is_never_exported(candidate, tmp_path, root_link):
    module, payload, _ = candidate
    if root_link:
        link = tmp_path / 'payload-link'; target = payload
    else:
        link = payload / 'nested-link'; target = tmp_path / 'outside'
        target.mkdir(); (target / 'private.txt').write_text('private')
    if sys.platform == 'win32':
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)
    with pytest.raises(RuntimeError, match='regular payload|Unexpected link'):
        module.scan_payload(link if root_link else payload)


def test_payload_change_during_export_cannot_receive_success_provenance(candidate, monkeypatch):
    module, payload, _ = candidate
    installer = module.ROOT / 'dist/installer/AstroPilot-1.0.0b8-windows-x86_64-setup.exe'
    installer.parent.mkdir(); installer.write_bytes(b'test installer')
    original = zipfile.ZipFile.write
    def altered_write(archive, filename, *args, **kwargs):
        if Path(filename).name == 'app.js':
            Path(filename).write_bytes(b'changed after trusted inventory')
        return original(archive, filename, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, 'write', altered_write)
    with pytest.raises(RuntimeError, match='content mismatch'):
        module.prepare(SHA)
    assert not (module.ROOT / 'dist/beta8-artifacts/provenance.json').exists()


@pytest.mark.parametrize('failure', ['missing-path', 'invalid-engine'])
def test_invalid_compiler_provenance_refuses_export_before_creating_output(candidate, monkeypatch, failure):
    module, _, _ = candidate
    installer = module.ROOT / 'dist/installer/AstroPilot-1.0.0b8-windows-x86_64-setup.exe'
    installer.parent.mkdir(); installer.write_bytes(b'test installer')
    if failure == 'missing-path':
        monkeypatch.delenv('ISCC_PATH')
    else:
        def refuse(_):
            raise RuntimeError('Invalid Inno Setup engine version')
        monkeypatch.setattr(module, 'inno_setup_provenance', refuse)
    with pytest.raises(RuntimeError, match='ISCC_PATH|Inno Setup'):
        module.prepare(SHA)
    assert not (module.ROOT / 'dist/beta8-artifacts').exists()


@pytest.mark.parametrize('banner', ['6.5.4', '7.0.1', '6.5.4.1'])
def test_engine_banner_overrides_zero_environment_version(tmp_path, monkeypatch, banner):
    module = exporter()
    compiler = tmp_path / 'ISCC.exe'; compiler.write_bytes(b'compiler')
    engine = tmp_path / 'ISCmplr.dll'; engine.write_bytes(b'engine')
    monkeypatch.setenv('INNO_SETUP_VERSION', '0.0.0.0')
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=f'Inno Setup Command-Line Compiler\nCompiler engine version: Inno Setup {banner}\n')
    monkeypatch.setattr(module.subprocess, 'run', run)
    result = module.inno_setup_provenance(compiler)
    assert result['version'] == banner
    assert result['compiler_sha256'] == hashlib.sha256(b'compiler').hexdigest()
    assert result['engine_sha256'] == hashlib.sha256(b'engine').hexdigest()
    assert calls[0][0] == [str(compiler.resolve()), '/O-', '-']
    assert calls[0][1]['check'] and calls[0][1]['timeout'] == 30
    assert 'Uninstallable=no' in calls[0][1]['input']
    assert sorted(p.name for p in tmp_path.iterdir()) == ['ISCC.exe', 'ISCmplr.dll']


@pytest.mark.parametrize('output', ['', 'Compiler engine version: Inno Setup 0.0.0.0\n',
    'Compiler engine version: Inno Setup 6\n', '6.5.4\n',
    'Compiler engine version: Inno Setup 6.5.4\nCompiler engine version: Inno Setup 7.0.1\n'])
def test_unknown_zero_or_conflicting_engine_banner_is_refused(tmp_path, monkeypatch, output):
    module = exporter()
    compiler = tmp_path / 'ISCC.exe'; compiler.write_bytes(b'compiler')
    (tmp_path / 'ISCmplr.dll').write_bytes(b'engine')
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=output))
    with pytest.raises(RuntimeError, match='engine version'):
        module.inno_setup_provenance(compiler)


@pytest.mark.parametrize('failure', ['missing-engine', 'changed-engine', 'exit-error', 'timeout'])
def test_unusable_engine_cannot_be_attested(tmp_path, monkeypatch, failure):
    module = exporter()
    compiler = tmp_path / 'ISCC.exe'; compiler.write_bytes(b'compiler')
    engine = tmp_path / 'ISCmplr.dll'
    if failure != 'missing-engine': engine.write_bytes(b'engine')
    def run(*args, **kwargs):
        if failure == 'exit-error': raise subprocess.CalledProcessError(2, args[0])
        if failure == 'timeout': raise subprocess.TimeoutExpired(args[0], 30)
        engine.write_bytes(b'changed')
        return SimpleNamespace(stdout='Compiler engine version: Inno Setup 6.5.4\n')
    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises((RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired)):
        module.inno_setup_provenance(compiler)


@pytest.mark.skipif(sys.platform != 'win32', reason='Real Inno Setup is Windows-only')
def test_native_inno_engine_no_output_compile():
    module = exporter()
    import os
    compiler = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Inno Setup 6/ISCC.exe'
    # This runs on disposable Windows CI. Missing tools must fail, not silently skip.
    result = module.inno_setup_provenance(compiler)
    assert result['version'].startswith('6.')
    assert result['compiler_sha256'] == module.digest(compiler)
    assert result['engine_sha256'] == module.digest(compiler.with_name('ISCmplr.dll'))
    report = os.environ.get('INNO_PROVENANCE_TEST_REPORT')
    if report:
        Path(report).write_text(json.dumps(result, indent=2), encoding='utf-8')
