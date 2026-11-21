"""Project-scoped navigation must not turn a missing plan into another project's plan."""
from pathlib import Path
import shutil
import subprocess
import pytest

SCRIPT = Path(__file__).parents[2] / 'astropilot/web/app.js'


def test_preparing_another_project_reconciles_the_plan_scope():
    source = SCRIPT.read_text()
    prepare = source[source.index('function prepareGuidedSession('):source.index('// One explicit user confirmation;')]
    program = r'''
const assert = require('node:assert/strict');
const state = {savedMissionProjectId:'Rosette', selectedProjectId:'Rosette', view:'projects'};
let blocked=false, unchanged=true, rendered=[];
function guardUnresolvedAcceptance(){return blocked}
function confirmDiscardProjectProgress(){return true}
function setDiscoveryMode(){}
function configurationDraftMatchesSaved(){return unchanged}
function showFormError(){}
function setView(view){state.view=view}
function renderSavedMissionChoices(){rendered.push(state.savedMissionProjectId)}
function saveConfiguration(){throw Error('No write expected')}
''' + prepare + r'''
prepareGuidedSession({projectId:'M42'});
assert.equal(state.selectedProjectId,'M42');
assert.equal(state.savedMissionProjectId,'M42','Preparing M42 must not keep the Rosette-only list');
assert.deepEqual(rendered,['M42']);
prepareGuidedSession();
assert.equal(state.savedMissionProjectId,null,'Generic preparation returns to the global plan list');
assert.deepEqual(rendered,['M42',null]);
state.savedMissionProjectId='Rosette';blocked=true;
prepareGuidedSession({projectId:'M42'});assert.equal(state.savedMissionProjectId,'Rosette');
blocked=false;unchanged=false;
prepareGuidedSession({projectId:'M42'});assert.equal(state.view,'projects');
assert.equal(state.savedMissionProjectId,'Rosette','Failed draft navigation must not change the plan scope');
'''
    result = subprocess.run([shutil.which('node'), '-'], input=program, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('transition,preserve', [
    ('unchanged', True), ('accepted', True), ('accepted', False), ('cleared', True), ('partial', True),
])
def test_history_retry_preserves_the_live_mission_context(transition, preserve):
    source = SCRIPT.read_text()
    helpers = source[source.index('async function restoreSavedMission('):source.index('function invalidateAvailabilityForSiteChange(')]
    program = r'''
const assert=require('node:assert/strict');
class Element {constructor(){this.value='';this.children=[];}replaceChildren(){this.children=[];}append(x){this.children.push(x);}}
const ui={savedMissionChoice:new Element(),savedMissionEntry:new Element(),openSavedMission:new Element()};
const status=new Element();
const document={getElementById:()=>null,querySelector:()=>status,createElement:()=>new Element()};
const mission=id=>({mission_id:id,selection_id:'s-'+id,decision_id:'d-'+id});
const payload=(id,key)=>({status:'accepted',catalog_key:key,...mission(id),mission:mission(id)});
const current=payload('server-current','M42'),saved=payload('chosen','Rosette');
const chosen={mission_id:'chosen',selectedCatalogKey:'Rosette',source:'persisted',mission:saved.mission,acceptedSiteGeneration:7};
const state={configuration:{},configurationGeneration:1,savedMissions:[chosen],savedMissionProjectId:'Rosette',acceptedMission:chosen};
function configurationOperationIsCurrent(n){return n===state.configurationGeneration}
function savedMissionLabel(p){return p.mission_id}function missionTimezone(){return 'UTC'}
let releaseHistory;
async function fetch(url){
 if(url==='/v1/accepted-mission/current')return {ok:true,json:async()=>current};
 if(url==='/v1/accepted-missions')return await new Promise(resolve=>{releaseHistory=()=>resolve({ok:process.argv[2]!=='partial',json:async()=>[current,saved]})});
 if(url==='/v1/execution-sessions')return {ok:true,json:async()=>[]};
 throw Error('Unexpected request');
}
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve()};
''' + helpers + r'''
(async()=>{
 const transition=process.argv[2];
 if(transition==='accepted')state.acceptedMission=null;
 const before=state.acceptedMission;
 const pending=restoreSavedMission({preserveActiveMission:process.argv[3]==='true'});await flush();
 assert.equal(state.acceptedMission,before,'Reading history must not clear an active mission');
 assert.equal(typeof releaseHistory,'function');
 let expected=before;
 if(transition==='accepted'){
  expected={mission_id:'new',selectedCatalogKey:'Rosette',source:'primary_recommendation',mission:mission('new'),acceptedSiteGeneration:8};
  state.acceptedMission=expected;
  state.savedMissions=[{...expected,source:'persisted'}];
 }else if(transition==='cleared'){expected=null;state.acceptedMission=null;}
 releaseHistory();await pending;
 assert.equal(state.acceptedMission,expected,'A late catalogue read must not replace the current mission context');
 assert.equal(state.savedMissionLoading,false);
 if(transition==='accepted'){
  assert.equal(state.acceptedMission.acceptedSiteGeneration,8);
  assert(state.savedMissions.some(x=>x.mission_id==='new'),'Newly confirmed plan must survive the late read');
 }
 if(transition==='partial'){
  assert.equal(state.savedMissionHistoryUnavailable,true);
  assert(state.savedMissions.some(x=>x.mission_id==='chosen'),'Known persisted plan remains available during partial history');
 }
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([shutil.which('node'), '-', transition, str(preserve).lower()], input=program, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_project_plan_scope_empty_partial_and_stale_selection():
    source = SCRIPT.read_text()
    helpers = source[source.index('function savedMissionsForProject()'):source.index('function invalidateAvailabilityForSiteChange(')]
    open_handler = source[source.index('ui.openSavedMission.addEventListener'):source.index('document.querySelector("#session-choice").addEventListener')]
    program = r'''
const assert = require('node:assert/strict');
class Element {
 constructor() { this.hidden=false;this.value='';this.children=[];this.disabled=false;this.textContent=''; }
 replaceChildren() { this.children=[]; } append(item) { this.children.push(item); }
 addEventListener(name,fn) { this[name]=fn; } focus() { focused=this; } scrollIntoView() {}
}
const elements=new Map();
const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
const document={getElementById:el,querySelector:id=>el(id.slice(1)),createElement:()=>new Element()};
const ui={savedMissionEntry:el('entry'),savedMissionChoice:el('choice'),savedMissionTarget:el('target'),openSavedMission:el('open'),mission:{showModal(){opened++}}};
const plan=(id,project)=>({mission_id:id,selectedCatalogKey:project,source:'persisted',mission:{target:project}});
const plans=[plan('m42','M42'),plan('r1','Rosette'),plan('r2','Rosette')];
const state={savedMissionLoading:false,savedMissionHistoryUnavailable:false,savedMissions:plans,acceptedMission:plans[0],configuration:{projects:{Rosette:{},M42:{},M31:{}}},view:'projects',viewRevision:1};
let blocked=false,focused=null,opened=0,rendered=null;
function readableTargetName(id){return id}function savedMissionLabel(item){return item.mission_id}
function guardUnresolvedAcceptance(){return blocked}
function prepareGuidedSession({projectId}){if(blocked)return;state.selectedProjectId=projectId;state.view='availability';state.viewRevision++}
let frames=[];function requestAnimationFrame(fn){frames.push(fn)}
function renderMission(mission){rendered=mission}
function fetch(){throw new Error('Navigation must not request anything')}
''' + helpers + open_handler + r'''
openProjectSavedMissions('Rosette');frames.splice(0).forEach(fn=>fn());
assert.equal(state.selectedProjectId,'Rosette');assert.equal(state.acceptedMission,plans[0]);
assert.equal(el('beginner-saved-missions').open,true);assert.equal(focused,ui.savedMissionChoice);
assert.deepEqual(ui.savedMissionChoice.children.map(e=>e.value),['r1','r2']);
assert.equal(ui.savedMissionChoice.value,'r1');assert.equal(ui.openSavedMission.disabled,false);
ui.savedMissionChoice.value='m42';ui.openSavedMission.click();assert.equal(opened,0,'Cross-project injected choice must be rejected');
ui.savedMissionChoice.value='r2';ui.openSavedMission.click();assert.equal(opened,1);assert.equal(rendered,plans[2].mission);
const original=JSON.stringify(plans);
openProjectSavedMissions('M31');frames.splice(0).forEach(fn=>fn());
assert.equal(ui.savedMissionChoice.disabled,true);assert.equal(ui.openSavedMission.disabled,true);
assert.equal(el('saved-mission-history-status').textContent,'Aucun plan enregistré pour ce projet.');
assert.equal(focused,el('saved-mission-history-status'));assert.equal(el('saved-mission-prepare').hidden,false);
state.savedMissionHistoryUnavailable=true;renderSavedMissionChoices();
assert.match(el('saved-mission-history-status').textContent,/incomplète/);
assert.equal(el('saved-mission-prepare').hidden,true);assert.equal(el('saved-mission-retry').hidden,false);
state.savedMissionProjectId=null;renderSavedMissionChoices();
assert.deepEqual(ui.savedMissionChoice.children.map(e=>e.value),['m42','r1','r2']);
assert.equal(JSON.stringify(plans),original);
blocked=true;state.savedMissionProjectId=null;openProjectSavedMissions('Rosette');assert.equal(state.savedMissionProjectId,null);
blocked=false;openProjectSavedMissions('Rosette');const oldFocus=focused;
state.view='projects';state.viewRevision++;frames.splice(0).forEach(fn=>fn());assert.equal(focused,oldFocus,'Late animation frame must not steal focus');
'''
    result = subprocess.run([shutil.which('node'), '-'], input=program, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_newer_plan_read_wins_on_same_configuration():
    source = SCRIPT.read_text()
    helpers = source[source.index('async function restoreSavedMission('):source.index('function invalidateAvailabilityForSiteChange(')]
    program = r'''
const assert=require('node:assert/strict');
class Element { constructor(){this.value='';this.children=[];}replaceChildren(){this.children=[];}append(x){this.children.push(x);} }
const ui={savedMissionChoice:new Element(),savedMissionEntry:new Element(),openSavedMission:new Element()};
const status=new Element();
const document={getElementById:()=>null,querySelector:()=>status,createElement:()=>new Element()};
const state={configuration:{},configurationGeneration:1,savedMissions:[],savedMissionProjectId:'Rosette'};
function configurationOperationIsCurrent(n){return n===state.configurationGeneration}
function savedMissionLabel(p){return p.mission_id}function missionTimezone(){return 'UTC'}
const queue=[];function fetch(url){return new Promise(resolve=>queue.push({url,resolve}))}
const reply=(q,data)=>q.resolve({ok:true,json:async()=>data});
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
''' + helpers + r'''
(async()=>{
 const old=restoreSavedMission();const first=queue.shift();
 const latest=restoreSavedMission();const second=queue.shift();
 reply(second,{});await flush();
 const m={mission_id:'new',selection_id:'s',decision_id:'d'};
 reply(queue.shift(),[{status:'accepted',catalog_key:'Rosette',...m,mission:m}]);await flush();
 reply(queue.shift(),[]);await latest;
 assert.equal(state.savedMissions[0].mission_id,'new');
 reply(first,{});await flush();reply(queue.shift(),[]);await old;
 assert.equal(state.savedMissions[0].mission_id,'new');
 assert.equal(ui.savedMissionChoice.value,'new');assert.equal(state.savedMissionLoading,false);
 assert.equal(queue.length,0);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([shutil.which('node'), '-'], input=program, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
