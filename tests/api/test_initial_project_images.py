"""Initial images are explicit historical capacity, never an execution credit."""
import json
import shutil
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot.project_templates import project_templates


def test_initial_images_builder_persistence_and_stale_retry(tmp_path, monkeypatch):
    node = shutil.which('node')
    assert node
    source = (Path(__file__).parents[2] / 'astropilot/web/app.js').read_text()
    builder = source[source.index('function newProjectFromInputs('):source.index('function addNewProject(')]
    template = next(t for t in project_templates() if t['catalog_key'] == 'NorthAmerica')
    intent = template['acquisition_intents'][0]['acquisition_intent_id']
    program = '''const assert=require('node:assert/strict');const state={configurationDraft:{equipment:{preset_id:'samyang_183'}}};\n'''
    program += 'const template='+json.dumps(template)+';const id='+json.dumps(intent)+';\n'+builder
    program += '''
const entries=[{id,selected:true,hours:3}];
const initial={confirmed:true,progress:[{acquisition_intent_id:id,acquired_frames:8,exposure_seconds:300}]};
const build=(value=initial,empty=false,existing={})=>newProjectFromInputs(template,entries,empty,existing,value);
assert.throws(()=>build(null),/Confirmez/);
assert.throws(()=>build({...initial,confirmed:false}),/Confirmez/);
assert.throws(()=>build(initial,true),/un seul/);
assert.throws(()=>build(initial,false,{NorthAmerica:{hours:99}}),/existe déjà/);
for(const [frames,seconds] of [[-1,300],[1.5,300],[8,0],[8,Infinity],[1e20,300]])assert.throws(()=>build({confirmed:true,progress:[{acquisition_intent_id:id,acquired_frames:frames,exposure_seconds:seconds}]}));
assert.throws(()=>build({confirmed:true,progress:[{acquisition_intent_id:'wrong',acquired_frames:8,exposure_seconds:300}]}));
const p=build();assert.equal(p.hours,2/3);assert.equal(p.target_hours,3);assert.equal(p.acquisition_intent_progress[0].acquired_frames,8);console.log(JSON.stringify(p));
'''
    result = subprocess.run([node,'-e',program],capture_output=True,text=True,check=True)
    project = json.loads(result.stdout)
    profile = tmp_path/'profile'
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(profile))
    client=TestClient(create_app())
    base=client.put('/v1/configuration',json={'site':{'name':'TEST','latitude':46.95,'longitude':7.45,'bortle':5},'equipment':{'preset_id':'samyang_183'},'projects':{}}).json()
    payload={'site':{'name':'TEST','latitude':46.95,'longitude':7.45,'bortle':5},'equipment':{'preset_id':'samyang_183'},'projects':{'NorthAmerica':project},'expected_revision':base['profile_revision']}
    response=client.put('/v1/configuration',json=payload)
    assert response.status_code==200,response.text
    before=(profile/'user_profile.json').read_bytes()
    restarted=TestClient(create_app())
    loaded=restarted.get('/v1/configuration').json()['projects']['NorthAmerica']
    assert loaded['hours']==2/3
    assert loaded['acquisition_intent_progress']==project['acquisition_intent_progress']
    assert restarted.put('/v1/configuration',json=payload).status_code==409
    assert (profile/'user_profile.json').read_bytes()==before
    assert not list(profile.glob('execution*'))
