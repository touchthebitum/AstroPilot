"""Project-scoped navigation must not turn a missing plan into another project's plan."""
from pathlib import Path
import shutil
import subprocess

SCRIPT = Path(__file__).parents[2] / 'astropilot/web/app.js'


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
    helpers = source[source.index('async function restoreSavedMission()'):source.index('function invalidateAvailabilityForSiteChange(')]
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
