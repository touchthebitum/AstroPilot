"""Candidate ports preserve existing listeners and profiles."""
import socket
import pytest
from astropilot.isolated_runtime import isolated_port, main

@pytest.mark.parametrize('raw', ['0', '8000', '18831', '18841', '18871', '19999', '65536', '-1', '20000.0', '+20000', '２００００', '', 'x'])
def test_invalid_or_protected_port_is_refused_before_profile_write(tmp_path, monkeypatch, raw):
    profile=tmp_path/'absent';monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(profile))
    with pytest.raises(ValueError):main('--isolated-test-server',raw)
    assert not profile.exists()

@pytest.mark.parametrize('raw', ['20000','65535','032123'])
def test_only_five_digit_decimal_ports_are_accepted(raw):
    if len(raw)>5:
        with pytest.raises(ValueError):isolated_port(raw)
    else:assert isolated_port(raw)==int(raw)

@pytest.mark.parametrize('mode', ['--isolated-test-server','--isolated-demo-server','--isolated-data-transfer','--isolated-demo-transfer'])
def test_occupied_port_is_not_contacted_or_reused(tmp_path,monkeypatch,mode):
    profile=tmp_path/'absent';monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(profile))
    with socket.socket() as owner:
        owner.bind(('127.0.0.1',0));owner.listen();port=owner.getsockname()[1]
        if port<20000:pytest.skip('System assigned port outside candidate range')
        with pytest.raises((OSError,SystemExit)):main(mode,str(port))
        assert not profile.exists()
        owner.settimeout(.05)
        with pytest.raises(socket.timeout):owner.accept()

@pytest.mark.parametrize('mode', ['--isolated-test-server','--isolated-demo-server','--isolated-data-transfer'])
def test_explicit_absolute_profile_is_required(monkeypatch,mode):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR','relative')
    with pytest.raises(ValueError,match='absolu'):main(mode,'30000')
