"""Run real UI handlers with controlled replies, without browser/profile access."""
from pathlib import Path
import subprocess
import shutil
import pytest

@pytest.mark.parametrize('scenario',['cancel','delete','restore','lost_after_commit','lost_before_send','offline','dirty','conflict'])
def test_visibility_handler(tmp_path,scenario):
    node=shutil.which('node') or '/Applications/Codex.app/Contents/Resources/node'
    if not Path(node).is_file():pytest.skip('Node unavailable')
    source=(Path(__file__).resolve().parents[2]/'astropilot/web/app.js').read_text()
    functions=source[source.index('function projectRemovalNotice('):source.index('function renderProjects()')]
    harness=r'''
const assert = require('node:assert/strict');
const scenario = SCENARIO;
let notice = {textContent:'',hidden:true};
const document={querySelector:()=>notice};
let confirmed=0,calls=[],renders=0,installed=0;
const window={confirm:message=>{confirmed++;assert.ok(message.includes('Target'));return scenario!=='cancel';}};
const state={configuration:{profile_revision:7},view:'projects'};
function guardUnresolvedAcceptance(){return false;}
function confirmDiscardProjectProgress(){return true;}
function configurationDraftMatchesSaved(){return scenario!=='dirty';}
function readableTargetName(){return 'Target';}
function beginConfigurationOperation(){return 1;}
function configurationOperationIsCurrent(){return true;}
function configurationOwnsNavigation(){return true;}
function finishConfigurationOperation(){}
function installCurrentConfiguration(p){installed++;state.configuration=p;}
function renderProjects(){renders++;}
function setView(v){state.view=v;}
const restore=scenario==='restore';
let payload={projects:restore?{target:{}}:{},archived_project_ids:restore?[]:['target'],profile_revision:8};
async function fetch(url,options){
 calls.push({url,options});
 if(options){
  assert.equal(JSON.parse(options.body).expected_revision,7);
  assert.equal(JSON.parse(options.body).confirmed,true);
  assert.equal(options.method,restore?'POST':'DELETE');
  if(['lost_after_commit','lost_before_send','offline'].includes(scenario))throw Error('lost');
  if(scenario==='conflict')return {ok:false,status:409,json:async()=>({})};
  return {ok:true,json:async()=>payload};
 }
 if(scenario==='offline')throw Error('offline');
 if(['conflict','lost_before_send'].includes(scenario))payload={projects:{target:{}},archived_project_ids:[],profile_revision:8};
 return {ok:true,json:async()=>payload};
}
(async()=>{
 await changeProjectVisibility('target',restore);
 assert.ok(!state.changingProjectVisibility);
 if(scenario==='dirty'){assert.equal(calls.length,0);assert.equal(confirmed,0);assert.match(notice.textContent,/Enregistrez/);}
 else if(scenario==='cancel'){assert.equal(calls.length,0);assert.equal(installed,0);}
 else if(scenario==='offline'){assert.equal(calls.length,2);assert.equal(installed,0);assert.match(notice.textContent,/Impossible de confirmer/);}
 else {
  assert.equal(installed,1);
  assert.equal(calls.filter(c=>c.options).length,1);
  if(['conflict','lost_before_send'].includes(scenario))assert.match(notice.textContent,/n’est pas confirmée/);
  else if(scenario==='lost_after_commit')assert.match(notice.textContent,/confirmé après relecture/);
  else assert.match(notice.textContent,restore?/rétabli/:/supprimé/);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('SCENARIO',repr(scenario))
    script=tmp_path/'handler.cjs';script.write_text(harness+'\n'+functions)
    r=subprocess.run([node,str(script)],capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
