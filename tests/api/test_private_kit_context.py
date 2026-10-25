"""Host locations are display-only metadata, never a source of storage paths."""
import json
from pathlib import Path
import runpy

import pytest
from astropilot.private_kit_context import ENVIRONMENT_KEY, private_kit_context

BUILD = 'abcdef0'
SHA = BUILD + '1' * 33


def context(kit=r"C:\Users\Franck\Tests été & ' famille\Kit"):
    return {'schema': 'nightmerit.private_copy_context.v1', 'source_sha': SHA,
            'host_kit_directory': kit, 'host_results_directory': kit + r'\RESULTATS',
            'guest_data_directory': r'C:\NightMeritResults\profil'}


def read(value, **kwargs):
    return private_kit_context(json.dumps(value), build=kwargs.get('build', BUILD),
                               data_directory=kwargs.get('data', r'C:\NightMeritResults\profil'))


def test_two_same_build_kits_with_identical_guest_paths_have_distinct_host_locations():
    first = read(context(r'C:\Tests\Copie personnelle\Kit'))
    second = read(context(r'C:\Tests\Copie vierge\Kit'))
    assert first['status'] == second['status'] == 'provided_by_launcher'
    assert first['host']['data_directory'] == r'C:\Tests\Copie personnelle\Kit\RESULTATS\profil'
    assert first['host'] != second['host']
    assert read(context())['host']['kit_directory'] == context()['host_kit_directory']
    assert read(context(r'\\test-server\partage\kit'))['status'] == 'provided_by_launcher'


@pytest.mark.parametrize('mutation', [
    {'schema': 'unknown'}, {'source_sha': 'b' * 40}, {'source_sha': SHA.upper()},
    {'host_kit_directory': r'C:relative'}, {'host_kit_directory': 'relative'},
    {'host_kit_directory': 'C:\\bad\npath'}, {'host_kit_directory': 'C:\\bad\ud800path'},
    {'host_results_directory': r'C:\someone_else\RESULTATS'},
    {'host_results_directory': r'C:\Tests\..\RESULTATS'},
    {'guest_data_directory': r'C:\external\profil'}, {'host_kit_directory': None},
    {'host_kit_directory': 'C:\\' + 'x' * 2049},
])
def test_invalid_metadata_cannot_publish_a_host_location(mutation):
    value = context(); value.update(mutation)
    assert read(value) == {'status': 'unavailable', 'host': None}


def test_metadata_is_not_applied_to_another_runtime_or_profile():
    assert read(context(), build='development')['status'] == 'unavailable'
    assert read(context(), data=r'C:\other-profile')['status'] == 'unavailable'
    for raw in ['{bad', '[]', 'null', 'x' * 16385]:
        assert private_kit_context(raw, build=BUILD, data_directory='ignored')['host'] is None
    assert private_kit_context(None, build=BUILD, data_directory='ignored')['status'] == 'not_provided'


def test_metadata_never_redirects_the_profile_or_reads_host_files(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import astropilot.app as app_module
    from astropilot.app import create_app
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ASTROPILOT_BUILD_COMMIT', BUILD)
    monkeypatch.setenv(ENVIRONMENT_KEY, json.dumps(context()))
    client = TestClient(create_app())
    response = client.get('/v1/data-context')
    assert response.status_code == 200
    payload = response.json()
    assert payload['data_directory'] == str(tmp_path)
    assert payload['private_copy'] == {'status': 'unavailable', 'host': None}
    assert list(tmp_path.iterdir()) == []
    assert 'host_kit_directory' not in client.get('/v1/runtime-identity').text
    # The exact Windows guest path is exercised on the native Windows CI runner.
    if app_module.os.name == 'nt':
        monkeypatch.setenv('ASTROPILOT_DATA_DIR', r'C:\NightMeritResults\profil')
        payload = client.get('/v1/data-context').json()
        assert payload['private_copy'] == read(context())
        assert payload['data_directory'] == r'C:\NightMeritResults\profil'


def test_rendered_launcher_roundtrip_and_existing_destination_refusal(tmp_path):
    import base64
    import hashlib
    root = Path(__file__).resolve().parents[2]
    render = runpy.run_path(str(root / 'scripts/render_private_windows_launcher.py'))['render']
    output = render(SHA, tmp_path / 'new kit')
    cmd = (output / 'LANCER-TEST-WINDOWS.cmd').read_text(encoding='ascii')
    bootstrap = base64.b64decode(cmd.split('-EncodedCommand ', 1)[1].splitlines()[0]).decode('utf-16le')
    host = output / 'Audit/launch-sandbox.ps1'
    assert hashlib.sha256(host.read_bytes()).hexdigest() in bootstrap
    assert 'ReadAllText($script)' in bootstrap
    assert max(map(len, cmd.splitlines())) < 8190
    transfer = (output / 'GERER-MES-DONNEES.cmd').read_text(encoding='ascii')
    transfer_code = base64.b64decode(transfer.split('-EncodedCommand ', 1)[1].splitlines()[0]).decode('utf-16le')
    assert "NIGHTMERIT_OPEN_DATA_TRANSFER='0'" in bootstrap
    assert "NIGHTMERIT_OPEN_DATA_TRANSFER='1'" in transfer_code
    assert hashlib.sha256(host.read_bytes()).hexdigest() in transfer_code
    controller = (output / 'Audit/controller.ps1').read_text(encoding='utf-8')
    assert '__SOURCE_' not in controller and SHA in controller
    assert 'Compress-Archive -LiteralPath (Join-Path $results' in controller
    assert 'NIGHTMERIT_PRIVATE_COPY_CONTEXT' not in controller.split('# Export the operator report only;', 1)[1]
    assert '-ExecutionPolicy' not in cmd + bootstrap + controller + host.read_text(encoding='utf-8')
    for source in output.rglob('*'):
        if source.is_file():
            assert 'no-sandbox' not in source.read_text(encoding='utf-8')
    before = host.read_bytes()
    with pytest.raises(FileExistsError):
        render(SHA, output)
    assert host.read_bytes() == before
    with pytest.raises(ValueError):
        render('bad', tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()
