"""Run production UI helpers with deterministic DOM and transport boundaries."""
from pathlib import Path
import shutil
import subprocess

import pytest

WEB = Path(__file__).resolve().parents[2] / 'astropilot/web'


def test_guardian_copy_and_explicit_wiring():
    html = (WEB / 'index.html').read_text()
    source = (WEB / 'app.js').read_text()
    assert 'Je confirme que l’acquisition est toujours en cours' in html
    assert 'Cette confirmation vient de vous. NightMerit ne vérifie pas techniquement que l’acquisition continue.' in html
    assert 'sans contrôle matériel' in html
    assert 'setInterval(renderGuardianRenewal, 1000)' in source
    assert source.count('addEventListener("click", confirmGuardianRenewal)') == 1
    assert source.count('confirmGuardianRenewal') == 2, 'only the explicit click invokes renewal'
    assert source.count('confirmation: "USER_CONFIRMS_ACQUISITION_CONTINUES"') == 1
    for selector in ['#session-start', '#session-complete', '#session-interrupt']:
        binding = next(line for line in source.splitlines() if f'document.querySelector("{selector}").addEventListener' in line)
        assert '{transition: true}' in binding


def ui_harness():
    return r'''
const assert = require('node:assert/strict');
const elements = new Map();
const document = {querySelector(id) {
  if (!elements.has(id)) elements.set(id, {hidden:false, disabled:false, textContent:'',
    value:'', checked:false, replaceChildren(){}, append(){}});
  return elements.get(id);
}, querySelectorAll(){return []}, createElement(){return {}}};
function text(id, value) {document.querySelector(id).textContent = value;}
function renderObservationLinkage() {}
function syncFieldObservationContext() {}
function missionTimezone(){return 'UTC'}
function missionDateTimeLabel(x){return x}
const localStorage = {getItem(){return null},setItem(){},removeItem(){}};
let ticks = 0;
const performance = {now: () => ticks};
let keys = 0;
const crypto = {randomUUID: () => `00000000-0000-4000-8000-${String(++keys).padStart(12,'0')}`};
const item = {execution:{execution_id:'exact',status:'in_progress',actual_start:'2026-10-09T17:00:00Z'}, evidence:[]};
const state = {activeSessionId:'exact', sessions:[item], acceptedMission:{mission_id:'mission'},sessionBusy:false};
let canonical = {schema_version:'guardian-explicit-renewal-v1',execution_id:'exact',
  guardian_mode_enabled:true,owner_instance_id:'owner',owned_here:true,renewal_eligible:true,
  confirmation_kind:'USER_ASSERTION',confirmed_at:'2026-10-09T17:00:00Z',
  expires_at:'2026-10-09T17:15:00Z',server_time:'2026-10-09T17:01:00Z'};
let requests = [], mode = 'success', release, timeoutCallback;
function setTimeout(callback) {timeoutCallback=callback;return 1}
function clearTimeout() {timeoutCallback=null}
async function fetch(url, options = {}) {
  requests.push({url,options});
  if (options.method !== 'POST' && mode === 'read-failed') throw Error('GET unavailable');
  if (options.method !== 'POST') return {ok:true,json:async()=>structuredClone(canonical)};
  if (url === '/v1/execution-transitions') return {ok:true,json:async()=>({})};
  if (mode === 'pending') await new Promise(resolve => {release=resolve});
  if (mode === 'timeout') await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('timeout'))));
  if (mode === 'lost') throw Error('response lost after commit');
  if (mode === 'malformed') return {ok:true,json:async()=>({})};
  const result = {...canonical,replayed:mode === 'replay'};
  if (mode !== 'replay') {
    result.confirmed_at = '2026-10-09T17:02:00Z';
    result.expires_at = '2026-10-09T17:17:00Z';
    canonical = {...canonical,confirmed_at:result.confirmed_at,expires_at:result.expires_at};
  }
  return {ok:true,status:200,json:async()=>result};
}
const button = () => document.querySelector('#guardian-confirm');
const posts = () => requests.filter(x=>x.options.method === 'POST' && x.url.endsWith('/guardian-renewal'));
'''


def test_guardian_ui_transport_and_session_integration():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    source = (WEB / 'app.js').read_text()
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('async function recordSessionEvidence')]
    harness = ui_harness()
    checks = r'''
(async()=> {
  await readGuardianRenewal();
  assert.equal(button().disabled,false);
  assert.equal(document.querySelector('#guardian-renewal').hidden,false);
  for(let i=0;i<10;i++) {ticks+=100;renderGuardianRenewal();await readGuardianRenewal();}
  assert.equal(posts().length,0,'render and GET never renew');
  mode='pending';
  const pending=confirmGuardianRenewal();
  assert.equal(button().disabled,true);
  assert.match(document.querySelector('#guardian-deadline').textContent,/17:15/);
  await confirmGuardianRenewal();
  assert.equal(posts().length,1,'double click blocked');
  release();await pending;
  assert.match(document.querySelector('#guardian-deadline').textContent,/17:17/);
  const first=posts()[0];
  assert.equal(JSON.parse(first.options.body).owner_instance_id,'owner');
  assert.equal(JSON.parse(first.options.body).confirmation,'USER_CONFIRMS_ACQUISITION_CONTINUES');
  mode='replay';const before=requests.length;await confirmGuardianRenewal();
  assert.notEqual(posts()[1].options.headers['Idempotency-Key'],first.options.headers['Idempotency-Key']);
  assert.equal(requests[before+1].options.method,undefined,'replay triggers read');
  assert.match(document.querySelector('#guardian-deadline').textContent,/17:17/);
  for (const failure of ['lost','malformed','timeout']) {
    mode=failure; const request=confirmGuardianRenewal();
    if(failure==='timeout') timeoutCallback();
    await request;
    assert.equal(button().disabled,true);
    assert.equal(document.querySelector('#guardian-renewal').hidden,false,'uncertainty stays visible');
    assert.equal(document.querySelector('#guardian-message').textContent,GUARDIAN_UNCERTAIN);
    const count=posts().length; await confirmGuardianRenewal();renderGuardianRenewal();
    assert.equal(posts().length,count,'no automatic fresh key');
    await refreshGuardianRenewal();
  }
  mode='success';
  for (const change of [
    {owned_here:false,renewal_eligible:false,owner_instance_id:'restarted'},
    {owned_here:false,renewal_eligible:false,ineligibility_reason:'guardian_session_not_owned'},
    {owned_here:true,renewal_eligible:false,ineligibility_reason:'guardian_session_attestation_lost'},
  ]) {
    const original=structuredClone(canonical);canonical={...canonical,...change};
    await readGuardianRenewal();assert.equal(button().disabled,true);
    assert.match(document.querySelector('#guardian-ownership').textContent,/nouvelle session explicite/);
    const count=posts().length;await confirmGuardianRenewal();assert.equal(posts().length,count);
    canonical=original;
  }
  await readGuardianRenewal();ticks+=16*60*1000+1;renderGuardianRenewal();
  assert.equal(button().disabled,true,'local deadline disables without mutation');
  state.activeSessionId='other';renderGuardianRenewal();assert.equal(button().hidden,true);
  state.activeSessionId='exact';
  for(const enabled of [true,false]) {
    canonical.guardian_mode_enabled=enabled;
    for(const action of ['start','completed','interrupted']) {
      item.execution.status=action==='start'?'not_started':'in_progress';
      const count=requests.length;
      if(action==='start') await startSession('mission');else await closeSession('mission',action);
      const commands=requests.slice(count).filter(x=>x.options.method==='POST');
      assert.equal(commands.length,1,'exactly one transition');
      assert.equal(commands[0].url,'/v1/execution-transitions');
      const headers=commands[0].options.headers;
      if(enabled) {
        assert.equal(headers['X-Guardian-Owner-Instance-Id'],'owner');
        assert.ok(headers['Idempotency-Key']);
      } else assert.deepEqual(headers,{'Content-Type':'application/json'});
    }
  }
  await readGuardianRenewal();assert.equal(document.querySelector('#guardian-renewal').hidden,true);
  mode='read-failed';item.execution.status='not_started';
  const count=requests.filter(x=>x.options.method==='POST').length;
  await assert.rejects(()=>startSession('mission'));
  assert.equal(requests.filter(x=>x.options.method==='POST').length,count,'unknown mode never guessed');
  const error=await sessionHttpError({status:503,json:async()=>({
    code:'guardian_attestation_publication_failed',execution_commit:'committed',guardian_publication:'failed'})});
  assert.match(sessionRefusalMessage(error),/transition enregistrée/);
  assert.match(sessionRefusalMessage(error),/Guardian : échouée/);
  assert.match(sessionRefusalMessage({...error,executionCommit:'unknown'}),/résultat incertain/);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run([node, '-'], input=harness + helpers + checks, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_session_transition_request_order_latency_and_reconciliation():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    source = (WEB / 'app.js').read_text()
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('async function recordSessionEvidence')]
    checks = r'''
let failure = null, guardianReads = 0, created = false;
const stored = new Map();
localStorage.getItem = key => stored.get(key) || null;
localStorage.setItem = (key,value) => stored.set(key,value);
localStorage.removeItem = key => stored.delete(key);
fetch = async (url,options={}) => {
  requests.push({url,options}); ticks += 10;
  if (url.endsWith('/executions') && options.method !== 'POST')
    return {ok:true,json:async()=>created || state.sessions.length ? [structuredClone(item)] : []};
  if (url.endsWith('/guardian-renewal')) {
    guardianReads++;
    if (failure === 'preflight' || (failure === 'final-read' && guardianReads === 2)) {
      ticks += 15000;
      throw Error('network unavailable');
    }
    const value = {...canonical,execution_id:item.execution.execution_id,execution_status:item.execution.status};
    if (failure === 'invalid-status') value.guardian_mode_enabled = null;
    if (['completed','interrupted'].includes(item.execution.status)) Object.assign(value,{
      owned_here:false,renewal_eligible:false,confirmed_at:null,expires_at:null});
    return {ok:true,json:async()=>value};
  }
  if (url.endsWith('/session')) return {ok:false,status:404};
  if (url === '/v1/executions') {
    created = true;
    item.execution.execution_id = JSON.parse(options.body).execution_id;
    item.execution.status = 'not_started';
    return {ok:true,json:async()=>({...item.execution})};
  }
  assert.equal(url,'/v1/execution-transitions');
  if (failure === 'refused') return {ok:false,status:409,json:async()=>({code:'changed'})};
  const payload = JSON.parse(options.body);
  item.execution = {...item.execution,...payload};
  if (failure === 'lost') throw Error('response lost after commit');
  if (failure === 'partial') return {ok:false,status:503,json:async()=>({
    execution_commit:'committed',guardian_publication:'failed'})};
  return {ok:true,status:200,json:async()=>{
    if (failure === 'malformed') throw Error('truncated JSON');
    return {...item.execution};
  }};
};
const paths = () => requests.map(x=>`${x.options.method || 'GET'} ${x.url}`);
const transitionPosts = () => requests.filter(x=>x.url === '/v1/execution-transitions');
function reset(status='in_progress', enabled=true) {
  failure=null;guardianReads=0;requests=[];ticks=0;created=false;stored.clear();
  item.execution = {execution_id:'exact',mission_id:'mission',status,actual_start:'2026-10-09T17:00:00Z'};
  state.sessions=[structuredClone(item)];state.activeSessionId='exact';state.sessionBusy=false;
  canonical.guardian_mode_enabled=enabled;
  guardianUI.status={...canonical};guardianUI.displayStatus={...canonical};
  guardianUI.readAt=0;guardianUI.pending=false;guardianUI.uncertain=false;
  guardianUI.message='Confirmation utilisateur acceptée.';
}
const run = action => sessionCommand(action === 'start' ? startSession : m=>closeSession(m,action),{transition:true});
(async()=>{
  for (const enabled of [true,false]) for (const action of ['start','completed','interrupted']) {
    reset(action === 'start' ? 'not_started' : 'in_progress',enabled);
    await run(action);
    assert.deepEqual(paths(),[
      'GET /v1/missions/mission/executions',
      'GET /v1/executions/exact/guardian-renewal',
      'POST /v1/execution-transitions',
      'GET /v1/missions/mission/executions',
      'GET /v1/executions/exact/guardian-renewal',
    ]);
    assert.equal(ticks,50,'only the required reads contribute logical latency');
    assert.equal(transitionPosts().length,1);
    assert.equal(JSON.parse(transitionPosts()[0].options.body).status,action === 'start' ? 'in_progress' : action);
    const headers=transitionPosts()[0].options.headers;
    if(enabled) {assert.equal(headers['X-Guardian-Owner-Instance-Id'],'owner');assert.ok(headers['Idempotency-Key']);}
    else assert.deepEqual(headers,{'Content-Type':'application/json'});
    if(action !== 'start') {
      assert.equal(guardianUI.message,'');assert.equal(button().hidden,true);assert.equal(button().disabled,true);
      assert.equal(document.querySelector('#guardian-message').textContent,'');
      assert.equal(document.querySelector('#guardian-last-confirmation').textContent,'Aucune confirmation acceptée');
      assert.equal(document.querySelector('#guardian-deadline').textContent,'Aucune échéance');
      assert.match(document.querySelector('#guardian-ownership').textContent,/Session clôturée/);
    }
  }
  reset('completed');state.sessions=[];state.activeSessionId=null;
  await run('start');
  assert.equal(transitionPosts().length,1,'new session still has one transition POST');
  assert.equal(requests.filter(x=>x.url === '/v1/executions').length,1,'creation is separate from transition');
  assert.equal(guardianReads,2,'no Guardian read during creation reconciliation');
  assert.deepEqual(paths().map(x=>x.replace(/00000000-0000-4000-8000-\d+/g,'new')),[
    'GET /v1/missions/mission/executions','GET /v1/executions/new/session','POST /v1/executions',
    'GET /v1/missions/mission/executions','GET /v1/executions/new/guardian-renewal',
    'POST /v1/execution-transitions','GET /v1/missions/mission/executions',
    'GET /v1/executions/new/guardian-renewal']);
  for(const enabled of [true,false]) for(const reason of ['preflight','invalid-status']) {
    reset('in_progress',enabled);failure=reason;await run('completed');
    assert.equal(transitionPosts().length,0,'never infer mode from an old snapshot');
    assert.equal(guardianReads,1,'a failed preflight is not retried in recovery');
    assert.equal(guardianUI.status,null);
    assert.equal(ticks,reason === 'preflight' ? 15030 : 30,'never accumulate two network waits');
  }
  for(const reason of ['lost','malformed','partial','refused','final-read']) {
    reset();failure=reason;await run('completed');
    assert.equal(transitionPosts().length,1,'ambiguous responses never replay transition');
    assert.equal(guardianReads,2);
    if(['lost','malformed'].includes(reason)) assert.match(document.querySelector('#session-status').textContent,/réponse incertaine/);
    if(reason === 'partial') assert.match(document.querySelector('#session-status').textContent,/transition enregistrée.*Guardian : échouée/);
    if(reason === 'refused') assert.equal(currentSession().execution.status,'in_progress');
    else {
      assert.equal(guardianUI.message,'');assert.equal(button().hidden,true);
      assert.equal(document.querySelector('#guardian-deadline').textContent,'Aucune échéance');
    }
    if(reason === 'final-read') assert.equal(guardianUI.status,null,'read failure never invents an INACTIVE attestation');
    assert.equal(state.sessionBusy,false);
  }
  reset();guardianUI.pending=true;await run('completed');assert.equal(requests.length,0,'renewal and stop cannot overlap');
  reset();state.sessionBusy=true;await run('completed');assert.equal(requests.length,0,'double click cannot post');
  assert.equal(requests.filter(x=>x.options.method==='POST' && x.url.endsWith('/guardian-renewal')).length,0);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run([node, '-'], input=ui_harness() + helpers + checks, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
