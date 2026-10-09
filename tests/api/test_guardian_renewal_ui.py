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


def test_guardian_ui_transport_and_session_integration():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    source = (WEB / 'app.js').read_text()
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('async function recordSessionEvidence')]
    harness = r'''
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
