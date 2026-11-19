import sys
import types
import pytest
from astropilot import portable_entry

@pytest.mark.parametrize('flag,demo',[('--demo-data-transfer-18841',True),('--private-data-transfer-18841',False)])
def test_dispatch_18841_is_explicit_and_separate(tmp_path, monkeypatch, flag, demo):
    calls=[]
    fake=types.ModuleType('astropilot.profile_transfer_app')
    fake.main=lambda **kw:calls.append(kw)
    monkeypatch.setitem(sys.modules,fake.__name__,fake)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path/'empty'))
    monkeypatch.setattr(sys,'argv',['AstroPilot',flag])
    assert portable_entry.main()==0
    assert calls==[{'port':18841,'open_browser':False,'demo':demo}]
    assert not (tmp_path/'empty').exists()

@pytest.mark.parametrize('flag',['--demo-data-transfer-18841','--private-data-transfer-18841'])
def test_isolated_transfer_never_falls_back_to_personal_profile(monkeypatch,flag):
    monkeypatch.delenv('ASTROPILOT_DATA_DIR',raising=False)
    monkeypatch.setattr(sys,'argv',['AstroPilot',flag])
    with pytest.raises(SystemExit,match='explicit absolute'):
        portable_entry.main()
