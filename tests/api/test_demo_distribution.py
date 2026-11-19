"""Fake compiler packaging test, not a native Windows validation."""
import importlib.util
from pathlib import Path
import zipfile
import json
import subprocess
import pytest


def git(source, *args):
    return subprocess.run(['git', *args], cwd=source, check=True, capture_output=True, text=True).stdout.strip()


def commit_fixture(source):
    git(source, 'init')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=Synthetic Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Synthetic source only')
    return git(source, 'rev-parse', 'HEAD')


def packager():
    script=Path(__file__).resolve().parents[2]/'scripts/build_private_demo_windows.py'
    spec=importlib.util.spec_from_file_location('packager',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_virgin_distribution_has_both_launchers(tmp_path, monkeypatch):
    m=packager()
    source=tmp_path/'prep/Source';(source/'scripts').mkdir(parents=True)
    (source/'pyproject.toml').write_text('')
    source_commit = commit_fixture(source)
    monkeypatch.setenv('ASTROPILOT_BUILD_COMMIT', 'badbeef')
    monkeypatch.setattr(m,'__file__',str(source/'scripts/build_private_demo_windows.py'))
    monkeypatch.setattr(m.platform,'system',lambda:'Windows')
    monkeypatch.setattr(m.platform,'machine',lambda:'AMD64')
    monkeypatch.setattr(m.sys,'version_info',(3,13,15))
    home=tmp_path/'home';home.mkdir()
    monkeypatch.setattr(m.Path,'home',lambda:home)
    calls=[]
    actual_run = subprocess.run
    def compiler(cmd,**kw):
        if cmd[0] == 'git': return actual_run(cmd, **kw)
        assert kw['env']['ASTROPILOT_BUILD_COMMIT'] == source_commit[:7]
        calls.append(cmd)
        if 'PyInstaller' in cmd:
            dest=Path(kw['cwd'])/'dist/AstroPilot';dest.mkdir(parents=True)
            (dest/'AstroPilot.exe').write_bytes(b'FAKE TEST ONLY')
        return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(m.subprocess,'run',compiler)
    m.main()
    with zipfile.ZipFile(next((home/'NM-Builds').glob('*/NM-DEMO.zip'))) as z:
        provenance = json.loads(z.read('NM-DEMO/provenance.json'))
        assert provenance['source_commit'] == source_commit
        assert len(provenance['source_tree_sha256']) == 64
        assert 'base_commit' not in provenance
        assert not any('DONNEES-DEMO/' in n for n in z.namelist())
        assert 'NM-DEMO/ESSAI-A-LIRE.txt' in z.namelist()
        assert b'--demo-18831' in z.read('NM-DEMO/DEMARRER-DEMO.cmd')
        assert b'--demo-data-transfer-18831' in z.read('NM-DEMO/GERER-MES-DONNEES.cmd')
    assert len(calls)==2


@pytest.mark.parametrize('invalid', ['no_git', 'modified', 'untracked', 'nested'])
def test_demo_build_refuses_unverifiable_source_before_writing(tmp_path, monkeypatch, invalid):
    m = packager()
    source = tmp_path/'source'; source.mkdir()
    (source/'file.txt').write_text('original')
    if invalid != 'no_git': commit_fixture(source)
    if invalid == 'modified': (source/'file.txt').write_text('changed')
    if invalid == 'untracked': (source/'other.txt').write_text('not committed')
    if invalid == 'nested': source = source/'nested'; source.mkdir()
    monkeypatch.setattr(m, '__file__', str(source/'scripts/build_private_demo_windows.py'))
    monkeypatch.setattr(m.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(m.platform, 'machine', lambda: 'AMD64')
    monkeypatch.setattr(m.sys, 'version_info', (3, 13, 0))
    home = tmp_path/'home'; home.mkdir(); monkeypatch.setattr(m.Path, 'home', lambda: home)
    with pytest.raises(SystemExit, match='source Git'):
        m.main()
    assert not list(home.iterdir()), 'An unverifiable source must not create build outputs'


def test_demo_source_change_during_copy_prevents_compilation(tmp_path, monkeypatch):
    m = packager()
    source = tmp_path/'source'; source.mkdir(); (source/'file.txt').write_text('original'); commit_fixture(source)
    monkeypatch.setattr(m, '__file__', str(source/'scripts/build_private_demo_windows.py'))
    monkeypatch.setattr(m.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(m.platform, 'machine', lambda: 'AMD64')
    monkeypatch.setattr(m.sys, 'version_info', (3, 13, 0))
    home = tmp_path/'home'; home.mkdir(); monkeypatch.setattr(m.Path, 'home', lambda: home)
    copytree = m.shutil.copytree
    def changed(*args, **kwargs):
        result = copytree(*args, **kwargs)
        (source/'file.txt').write_text('changed while copying')
        return result
    monkeypatch.setattr(m.shutil, 'copytree', changed)
    actual_run = subprocess.run; commands = []
    def runner(command, **kwargs):
        commands.append(command); assert command[0] == 'git', 'Compiler must not run after a source change'
        return actual_run(command, **kwargs)
    monkeypatch.setattr(m.subprocess, 'run', runner)
    with pytest.raises(SystemExit, match='source Git'):
        m.main()
    assert not list(home.glob('NM-Builds/*/NM-DEMO.zip'))
