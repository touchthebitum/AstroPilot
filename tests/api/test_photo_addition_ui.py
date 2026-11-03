"""Exercise the one-confirmation addition with lost responses and concurrent changes."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_photo_addition_reconciles_each_partial_commit(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required")
    source = (Path(__file__).parents[2] / "astropilot/web/app.js").read_text()
    helpers = source[source.index("// One explicit user confirmation;"):source.index("function renderSimpleProjects(entries)")]
    prelude = r'''
const assert = require('node:assert/strict');
class Element {
 constructor(){this.value='';this.open=true;this.children=[];this.classList={toggle(){}};}
 append(x){this.children.push(x)} replaceChildren(){this.children=[]} showModal(){this.open=true} scrollIntoView(){}
}
const elements=new Map();
const document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id)},createElement(){return new Element()}};
const storage=new Map(),localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
const crypto={randomUUID:()=> 'stable-evidence'};
const usableEvidence=s=>s?.evidence.find(e=>e.category==='acquisition'&&e.usable_integration_duration>0);
const usablePoseDuration=s=>`${Math.floor(s/3600)} h ${String(Math.floor(s/60)%60).padStart(2,'0')}`;
const missionTimezone=()=> 'Europe/Zurich',missionDateTimeLabel=d=>d,sessionStatus=s=>s;
let refreshed=0;function renderProjects(){refreshed++}
async function guardianTransitionHeaders(){return {'X-Guardian-Owner-Instance-Id':'owner'}}
const original={project_id:'Sh2-129',acquisition_intent_id:'ou4_oiii',mission_id:'m',profile_revision:7,
 execution:{execution_id:'e',status:'completed',actual_start:'2026-10-31T21:52:00Z'},evidence:[],credit:null,
 current_acquired_seconds:48900,historical_baseline_seconds:48900,historical_baseline_confirmed:false,target_hours:20,remaining_hours:6+25/60};
let canonical, fault, faultUsed, writes, gate=null;
async function sessionFetch(url,options={}){
 if(options.method!=='POST')return {ok:true,json:async()=>structuredClone(canonical)};
 const b=JSON.parse(options.body);writes.push({url,b});if(gate)await gate;
 const phase=url.endsWith('intent-progress-credit')?'credit':url==='/v1/outcome-evidence'?'evidence':'transition';
 if(fault===phase+'-http'&&!faultUsed){faultUsed=true;return {ok:false,status:500,json:async()=>({})};}
 if(phase==='transition'){assert.equal(b.status,'completed');canonical.execution.status='completed'}
 if(phase==='evidence'){assert.equal(b.usable_integration_duration,2400);assert.equal(canonical.evidence.length,0);canonical.evidence=[{...b}];}
 if(phase==='credit'){
  assert.equal(b.expected_revision,7);assert.equal(b.confirm_historical_baseline,true);
  assert.deepEqual(b.evidence_ids,['stable-evidence']);assert.equal(canonical.credit,null);
  canonical.credit={total_duration_us:2400000000};canonical.session_credit_seconds=2400;
  canonical.current_acquired_seconds=51300;canonical.remaining_hours=5.75;canonical.profile_revision=8;
 }
 if(fault===phase+'-lost'&&!faultUsed){faultUsed=true;throw Error('lost after commit')}
 return {ok:true,json:async()=>({})};
}
async function sessionHttpError(r){const e=Error('http');e.status=r.status;return e}
'''
    checks = r'''
(async()=>{
for(const status of ['completed','in_progress'])for(const failure of [null,'evidence-http','evidence-lost','credit-http','credit-lost','transition-lost']){
 refreshed=0;canonical=structuredClone(original);canonical.execution.status=status;
 fault=failure;faultUsed=false;writes=[];storage.clear();photoAddition.projectId='Sh2-129';photoAddition.selected=structuredClone(canonical);
 photoElement('frames').value='8';photoElement('seconds').value='300';renderPhotoAddition();
 assert.match(photoElement('preview').textContent,/13 h 35.*14 h 15/);
 assert.match(photoElement('baseline').textContent,/ne sont pas déjà comptés/);
 await submitPhotoAddition();
 if(!canonical.credit)await submitPhotoAddition();
 assert.equal(canonical.current_acquired_seconds,51300);assert.equal(canonical.remaining_hours,5.75);
 assert.equal(canonical.evidence.length,1);const count=writes.length;await submitPhotoAddition();assert.equal(writes.length,count);
 assert.equal(photoElement('submit').hidden,true);
 assert.equal(refreshed,1,'refresh project cards exactly once after confirmed credit, including lost responses');
 assert.equal(storage.size,0,'clear pending evidence after confirmed credit');
}
// Freeze the POST while a second click and close are attempted.
canonical=structuredClone(original);fault=null;writes=[];photoAddition.selected=structuredClone(canonical);
let release;gate=new Promise(r=>release=r);const saving=submitPhotoAddition();await new Promise(r=>setImmediate(r));
assert.equal(photoElement('close').disabled,true);await submitPhotoAddition();assert.equal(writes.length,1);
release();gate=null;await saving;assert.equal(canonical.evidence.length,1);
// A changed baseline is never confirmed unseen: re-read and require another explicit click.
canonical=structuredClone(original);photoAddition.selected=structuredClone(canonical);canonical.profile_revision=9;
writes=[];await submitPhotoAddition();assert.equal(writes.length,0);assert.equal(photoAddition.selected.profile_revision,9);
for(const status of ['interrupted','unconfirmed','not_started','unknown']){
 refreshed=0;canonical=structuredClone(original);canonical.execution.status=status;photoAddition.selected=canonical;writes=[];
 renderPhotoAddition();await submitPhotoAddition();assert.equal(writes.length,0);assert.equal(photoElement('submit').hidden,true);
}
// Discovery is project-scoped and never silently chooses among several nights/filters.
writes=[];
const second={...structuredClone(original),acquisition_intent_id:'sh2-129_ha',execution:{...original.execution,execution_id:'second'}};
sessionFetch=async url=>({ok:true,json:async()=>url.includes('/progress')?{acquisition_intents:[{acquisition_intent_id:'ou4_oiii',filter_type:'OIII'},{acquisition_intent_id:'sh2-129_ha',filter_type:'Ha'}]}:[structuredClone(original),second,{...original,project_id:'Other'}]});
await openPhotoAddition('Sh2-129');assert.equal(photoAddition.sessions.length,2);assert.equal(photoAddition.selected,null);
assert.equal(photoElement('choice').children.length,3);assert.match(photoElement('choice').children[1].textContent,/OIII/);assert.match(photoElement('choice').children[2].textContent,/Hα/);assert.equal(writes.length,0);
// A finished-session panel may explicitly select only a session of this project.
await openPhotoAddition('Sh2-129',{executionId:'second'});assert.equal(photoAddition.selected.execution.execution_id,'second');
await openPhotoAddition('Sh2-129',{executionId:'foreign-or-missing'});assert.equal(photoAddition.selected,null);
assert.equal(writes.length,0);
// Distinct executions in the same displayed minute/filter must have distinct stable labels.
const credited={...structuredClone(original),execution:{...original.execution,execution_id:'already-credited'},credit:{total_duration_us:2400000000},session_credit_seconds:2400};
const collisions=[structuredClone(original),credited,second];
sessionFetch=async url=>({ok:true,json:async()=>url.includes('/progress')?{acquisition_intents:[{acquisition_intent_id:'ou4_oiii',filter_type:'OIII'},{acquisition_intent_id:'sh2-129_ha',filter_type:'Ha'}]}:collisions});
await openPhotoAddition('Sh2-129');
const firstLabels=new Map(photoElement('choice').children.slice(1).map(o=>[o.value,o.textContent]));
assert.equal(new Set(firstLabels.values()).size,3);
assert.match(firstLabels.get('e'),/Séance 2 sur 2.*Photos à renseigner/);
assert.match(firstLabels.get('already-credited'),/Séance 1 sur 2.*Déjà ajouté : 0 h 40/);
collisions.reverse();await openPhotoAddition('Sh2-129');
for(const option of photoElement('choice').children.slice(1))assert.equal(option.textContent,firstLabels.get(option.value));
assert.equal(writes.length,0);
console.log('PASS: one confirmation, exact baseline+credit, lost responses at each step, HTTP errors, concurrent baseline, no duplicate, blocked states, project/date/filter discovery.');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    script=tmp_path/'photos.cjs'
    script.write_text(prelude+helpers+checks)
    result=subprocess.run([node,str(script)],capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr


def test_oiii_evidence_and_credit_survive_restart_without_changing_other_data(tmp_path, monkeypatch):
    from tests.api.test_execution_session_api import setup, create_completed, OIII, HA, FIELD
    from astropilot.user_profile import load_user_profile

    factory = setup(tmp_path, monkeypatch)
    api = factory()
    response = api.put('/v1/projects/Sh2-129/progress', json={
        'expected_revision': load_user_profile()['profile_revision'], 'imaging_field_id': FIELD,
        'acquisition_intent_progress': [
            {'acquisition_intent_id': HA, 'acquired_duration_manual': 3600},
            {'acquisition_intent_id': OIII, 'acquired_frames': 163, 'exposure_seconds': 300}],
        'acquisition_intent_targets': [{'acquisition_intent_id': HA, 'target_hours': 2},
                                     {'acquisition_intent_id': OIII, 'target_hours': 20}],
    })
    assert response.status_code == 200, response.text
    create_completed(api, 'session-photos', mission_id='mission-oiii')
    # Historical observation/comparison documents are outside the credit write path.
    history = tmp_path / 'historical-observations'
    history.mkdir()
    (history / 'observation.json').write_bytes(b'{"fixture":"existing observation"}')
    (history / 'comparison.json').write_bytes(b'{"fixture":"existing comparison"}')
    immutable = {p: p.read_bytes() for p in history.iterdir()}
    evidence = dict(evidence_id='eight-retained', execution_id='session-photos', category='acquisition',
                    source='user', observed_at='2026-11-01T18:00:00Z', usable_integration_duration=2400)
    assert api.post('/v1/outcome-evidence', json=evidence).status_code == 200
    session = api.get('/v1/executions/session-photos/session').json()
    assert session['current_acquired_seconds'] == 48900
    assert session['credit'] is None
    credit = dict(expected_revision=session['profile_revision'], evidence_ids=['eight-retained'],
                  confirm_historical_baseline=True)
    assert api.post('/v1/executions/session-photos/intent-progress-credit', json=credit).status_code == 200
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
    resumed = factory().get('/v1/executions/session-photos/session').json()
    assert resumed['current_acquired_seconds'] == 51300
    assert resumed['remaining_hours'] == 5.75
    credit['expected_revision'] = resumed['profile_revision']
    assert factory().post('/v1/executions/session-photos/intent-progress-credit', json=credit).json()['status'] == 'already_applied'
    assert {p: p.read_bytes() for p in before} == before
    assert {p: p.read_bytes() for p in immutable} == immutable
    progress = factory().get('/v1/projects/Sh2-129/progress').json()
    assert next(x for x in progress['intent_progress_breakdown'] if x['acquisition_intent_id'] == HA)['effective_total_seconds'] == 3600
