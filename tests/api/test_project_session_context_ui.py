"""Both entry paths show the same canonical progress without writing or fetching weather."""
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).parents[2] / 'astropilot/web'


def run(program):
    result = subprocess.run([shutil.which('node'), '-'], input=program, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def helpers():
    source = (SOURCE/'app.js').read_text()
    return (source[source.index('function readableTargetName('):source.index('function savedMissionLabel(')]
        + source[source.index('function progressDuration('):source.index('function progressInput(')]
        + source[source.index('let selectedProjectContextRead = null;'):source.index('function setView(view)')])


def test_project_selection_and_project_card_show_identical_effective_totals():
    app = (SOURCE/'app.js').read_text()
    beginner = (SOURCE/'beginner.js').read_text()
    paths = (app[app.index('function prepareGuidedSession('):app.index('// One explicit user confirmation;')]
        + beginner[beginner.index('  async function selectPath('):beginner.index('  const context = make(')])
    run(r'''
const assert=require('node:assert/strict');
const notice={hidden:true,textContent:''};
const document={querySelector:()=>notice};
const state={selectedProjectId:null,discoveryMode:false,configuration:{profile_revision:4,projects:{'Sh2-129':{hours:999}}}};
const projectSelect={value:'Sh2-129',addEventListener:(name,fn)=>projectSelect[name]=fn};
const discoverValue='discover';
let requests=[];function fetch(url,options){requests.push({url,options});return Promise.resolve({ok:true,json:async()=>data});}
function guardUnresolvedAcceptance(){return false;}function confirmDiscardProjectProgress(){return true;}
function configurationDraftMatchesSaved(){return true;}function showFormError(){}
function refresh(){}function setView(view){state.view=view;updateSelectedProjectContext();}
async function setDiscoveryMode(value){state.discoveryMode=value;updateSelectedProjectContext();}
function saveConfiguration(){throw new Error('Navigation must not save');}
const data={project_id:'Sh2-129',acquisition_intents:[{acquisition_intent_id:'ou4_oiii',filter_type:'OIII'}],
 acquisition_intent_targets:[{acquisition_intent_id:'ou4_oiii',target_hours:20}],
 intent_progress_breakdown:[{acquisition_intent_id:'ou4_oiii',base_seconds:3600,credits_us:39900000000,effective_total_seconds:43500}]};
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
'''+helpers()+paths+r'''
(async()=>{
 projectSelect.change();await flush();
 const fromPreparation=notice.textContent;
 assert.equal(fromPreparation,'Projet existant : Sh2-129 + Ou4 · OIII · 12 h 05 sur 20 h.');
 assert.equal(notice.hidden,false);assert.equal(state.selectedProjectId,'Sh2-129');
 selectedProjectContextRead=null;state.selectedProjectId=null;
 prepareGuidedSession({projectId:'Sh2-129',saveDraft:true});await flush();
 assert.equal(state.view,'availability');assert.equal(notice.textContent,fromPreparation);
 assert.equal(requests.length,2);
 assert.ok(requests.every(r=>r.url==='/v1/projects/Sh2-129/progress' && !r.options));
 updateSelectedProjectContext();updateSelectedProjectContext();await flush();
 assert.equal(requests.length,2,'ordinary view updates must not cause request loops');
})().catch(e=>{console.error(e);process.exitCode=1;});
''')
    assert 'Sur quel projet souhaitez-vous travailler ?' in beginner
    assert 'Préparer une séance sur ce projet' in app


def test_late_reads_unknowns_multiple_filters_and_retry_never_invent_progress():
    run(r'''
const assert=require('node:assert/strict');
const notice={hidden:true,textContent:''};const document={querySelector:()=>notice};
const state={selectedProjectId:'Sh2-129',discoveryMode:false,configuration:{profile_revision:1,projects:{'Sh2-129':{},M42:{}}}};
let requests=[];function fetch(url){return new Promise((resolve,reject)=>requests.push({url,resolve,reject}));}
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
function data(id){return {project_id:id,acquisition_intents:[{acquisition_intent_id:'ha',filter_type:'Ha'}],
 acquisition_intent_targets:[{acquisition_intent_id:'ha',target_hours:15}],
 intent_progress_breakdown:[{acquisition_intent_id:'ha',effective_total_seconds:0}]};}
'''+helpers()+r'''
(async()=>{
 updateSelectedProjectContext();state.selectedProjectId='M42';updateSelectedProjectContext();
 requests[1].resolve({ok:true,json:async()=>data('M42')});await flush();
 const current=notice.textContent;assert.match(current,/M42.*Hα.*0 h sur 15 h/);
 requests[0].resolve({ok:true,json:async()=>data('Sh2-129')});await flush();assert.equal(notice.textContent,current);
 state.configuration.profile_revision++;updateSelectedProjectContext();state.discoveryMode=true;updateSelectedProjectContext();
 requests[2].resolve({ok:true,json:async()=>data('M42')});await flush();assert.equal(notice.hidden,true);assert.equal(notice.textContent,'');
 state.discoveryMode=false;updateSelectedProjectContext();requests[3].reject(new Error('offline'));await flush();
 assert.match(notice.textContent,/Avancement indisponible/);assert.doesNotMatch(notice.textContent,/0 h|refus météo/);
 updateSelectedProjectContext();assert.equal(requests.length,5);
 requests[4].resolve({ok:true,json:async()=>data('M42')});await flush();assert.match(notice.textContent,/0 h sur 15 h/);
 const multiple={project_id:'Rosette',acquisition_intents:[{acquisition_intent_id:'oiii',filter_type:'OIII'},{acquisition_intent_id:'sii',filter_type:'SII'},{acquisition_intent_id:'untargeted',filter_type:'Ha'}],
 acquisition_intent_targets:[{acquisition_intent_id:'oiii',target_hours:3},{acquisition_intent_id:'sii',target_hours:2}],
 intent_progress_breakdown:[{acquisition_intent_id:'oiii',effective_total_seconds:2400},{acquisition_intent_id:'sii',effective_total_seconds:null}]};
 const label=projectSessionContextText('Rosette',multiple);
 assert.match(label,/OIII : 0 h 40 sur 3 h.*SII : acquis non renseigné sur 2 h/);
 assert.doesNotMatch(label,/Hα|SII : 0/);
 // A profile revision that changes during a read invalidates that response.
 state.configuration.profile_revision++;updateSelectedProjectContext();state.configuration.profile_revision++;
 const pending=notice.textContent;requests[5].resolve({ok:true,json:async()=>data('M42')});await flush();assert.equal(notice.textContent,pending);
 updateSelectedProjectContext();requests[6].resolve({ok:true,json:async()=>data('Sh2-129')});await flush();
 assert.match(notice.textContent,/Avancement indisponible/,'mismatched project response must not display another project');
})().catch(e=>{console.error(e);process.exitCode=1;});
''')
