"""The beginner recovery route must create explicit capacity, never infer it."""
import json
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.project_templates import project_templates
from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
from decision.services.project_acquisition_intent_targets import resolve_project_acquisition_intent_targets
from decision.services.project_acquisition_intent_progress import resolve_project_acquisition_intent_progress
from decision.services.acquisition_intent_remaining_progress import derive_acquisition_intent_remaining_progress

WEB = Path(__file__).resolve().parents[2] / 'astropilot/web'


def test_templates_are_public_read_only_choices_not_user_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    sentinel = tmp_path / 'user_profile.json'
    sentinel.write_bytes(b'preserve even an unreadable existing profile')
    response = TestClient(create_app()).get('/v1/project-templates')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert sentinel.read_bytes() == b'preserve even an unreadable existing profile'
    assert list(tmp_path.iterdir()) == [sentinel]
    template = response.json()[0]
    assert template['catalog_key'] == 'Sh2-129'
    assert template['imaging_field_id'] == 'sh2-129_ou4'
    assert len(template['acquisition_intents']) == 2
    for intent in template['acquisition_intents']:
        assert intent['supported_filters'][0]['equipment_id'] == 'samyang_183'
        assert intent['supported_filters'][0]['fwhm_nm'] == 6.5


def test_real_javascript_builder_and_persisted_capacity(tmp_path, monkeypatch):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the actual project builder')
    source = (WEB / 'app.js').read_text()
    builder = source[source.index('function newProjectFromInputs('):source.index('function addNewProject(')]
    template = project_templates()[0]
    harness = '''
const assert = require('node:assert/strict');
const state = {configurationDraft:{equipment:{preset_id:'samyang_183'}}};
const template = TEMPLATE;
const selected = [{id:'sh2-129_ha',selected:true,hours:'2'}, {id:'ou4_oiii',selected:false,hours:''}];
'''.replace('TEMPLATE', json.dumps(template)) + builder + '''
const build = (entries=selected, empty=true, existing={}) => newProjectFromInputs(template,entries,empty,existing);
assert.throws(()=>build(selected,false),/Confirmez/);
assert.throws(()=>build(selected,true,{'Sh2-129':{hours:99}}),/existe déjà/);
assert.throws(()=>build([]),/Choisissez au moins/);
for(const hours of ['', '0', '-1', 'Infinity', 'NaN', '0.5']) {
 assert.throws(()=>build([{id:'sh2-129_ha',selected:true,hours}]),/au moins 1/);
}
assert.throws(()=>build([{id:'unknown',selected:true,hours:'2'}]),/filtre précis/);
state.configurationDraft.equipment={custom:{camera_model:'other'}};
assert.throws(()=>build(),/filtre précis/);
state.configurationDraft.equipment={preset_id:'samyang_183'};
const project=build();
assert.deepEqual(project.acquisition_intent_targets,[{acquisition_intent_id:'sh2-129_ha',target_hours:2}]);
assert.deepEqual(project.acquisition_intent_progress,[{acquisition_intent_id:'sh2-129_ha',acquired_duration_manual:0}]);
console.log(JSON.stringify(project));
'''
    result = subprocess.run([node, '-e', harness], capture_output=True, text=True, check=True)
    project = json.loads(result.stdout)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path / 'profile'))
    client = TestClient(create_app())
    site = {'name':'Fixture', 'latitude':47.1, 'longitude':6.8, 'bortle':4}
    initial = client.put('/v1/configuration', json={
        'site':site, 'equipment':{'preset_id':'samyang_183'},
        'projects':{'M31':{'target_hours':4,'hours':1}},
    }).json()
    payload = {'site':site,'equipment':{'preset_id':'samyang_183'},
        'expected_revision':initial['profile_revision'],
        'projects':{**initial['projects'],'Sh2-129':project}}
    saved = client.put('/v1/configuration', json=payload)
    assert saved.status_code == 200, saved.text
    loaded = client.get('/v1/configuration').json()
    assert loaded['site'] == initial['site']
    assert loaded['projects']['M31'] == initial['projects']['M31']
    assert loaded['projects']['Sh2-129'] == {**project, 'importance': None}
    resolver = build_production_imaging_field_resolver()
    field = resolver.resolve(project['imaging_field_id'])
    capacities = derive_acquisition_intent_remaining_progress(field,
        resolve_project_acquisition_intent_targets(project,resolver),
        resolve_project_acquisition_intent_progress(project,resolver))
    assert capacities[0].remaining_hours == 2
    assert capacities[0].acquired_hours == 0
    assert capacities[1].remaining_hours is None  # no fabricated OIII target/base
    before = (tmp_path/'profile/user_profile.json').read_bytes()
    stale = client.put('/v1/configuration',json=payload)
    assert stale.status_code == 409
    assert (tmp_path/'profile/user_profile.json').read_bytes() == before
    assert not list((tmp_path/'profile').glob('execution*'))
