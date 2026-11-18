"""Fake compiler packaging test, not a native Windows validation."""
import importlib.util
from pathlib import Path
import zipfile


def test_virgin_distribution_has_both_launchers(tmp_path, monkeypatch):
    script=Path(__file__).resolve().parents[2]/'scripts/build_private_demo_windows.py'
    spec=importlib.util.spec_from_file_location('packager',script)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    source=tmp_path/'prep/Source';(source/'scripts').mkdir(parents=True)
    (source/'pyproject.toml').write_text('')
    monkeypatch.setattr(m,'__file__',str(source/'scripts/build_private_demo_windows.py'))
    monkeypatch.setattr(m.platform,'system',lambda:'Windows')
    monkeypatch.setattr(m.platform,'machine',lambda:'AMD64')
    monkeypatch.setattr(m.sys,'version_info',(3,13,15))
    home=tmp_path/'home';home.mkdir()
    monkeypatch.setattr(m.Path,'home',lambda:home)
    calls=[]
    def compiler(cmd,**kw):
        calls.append(cmd)
        if 'PyInstaller' in cmd:
            dest=Path(kw['cwd'])/'dist/AstroPilot';dest.mkdir(parents=True)
            (dest/'AstroPilot.exe').write_bytes(b'FAKE TEST ONLY')
        return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(m.subprocess,'run',compiler)
    m.main()
    with zipfile.ZipFile(next((home/'NM-Builds').glob('*/NM-DEMO.zip'))) as z:
        assert not any('DONNEES-DEMO/' in n for n in z.namelist())
        assert 'NM-DEMO/ESSAI-A-LIRE.txt' in z.namelist()
        assert b'--demo-18831' in z.read('NM-DEMO/DEMARRER-DEMO.cmd')
        assert b'--demo-data-transfer-18831' in z.read('NM-DEMO/GERER-MES-DONNEES.cmd')
    assert len(calls)==2
