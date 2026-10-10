"""Execute the real session UI helpers against a small browser harness."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


def test_usable_duration_inputs_are_scoped_to_execution():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('async function reloadSessions')]
    harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor() { this.hidden = false; this.checked = false; this.textContent = '';
    this.value = ''; this.children = []; }
  replaceChildren() { this.children = []; }
  append(child) { this.children.push(child); }
}
const elements = new Map();
const document = {
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector); },
  createElement() { return new Element(); },
};
function text(selector, value) { document.querySelector(selector).textContent = value; }
const storage = new Map();
const localStorage = {getItem: key => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, value)};
const session = (id) => ({execution: {execution_id: id, status: 'completed', actual_start: null},
  acquisition_intent_id: 'ha', evidence: [], credit: null, historical_baseline_seconds: 0,
  historical_baseline_confirmed: false, acquired_before_seconds: 0, session_credit_seconds: 0,
  acquired_after_seconds: 0, current_acquired_seconds: 0, target_hours: null, remaining_hours: null});
const state = {acceptedMission: {mission_id: 'mission-1', acquisitionIntentId: 'ha'},
  sessions: [session('execution-1'), session('execution-2')], activeSessionId: 'execution-1',
  sessionEvidenceInputExecutionId: null};
// Keep the session test focused while preserving renderSession's Field Observation integration point.
let observationLinkageRenderCount = 0;
function renderObservationLinkage() { observationLinkageRenderCount++; }
'''
    checks = r'''
document.querySelector('#session-hours').value = '0';
document.querySelector('#session-minutes').value = '30';
localStorage.setItem('astropilot.pendingEvidence.execution-1', JSON.stringify({
  evidence_id: 'evidence-1', minutes: 30,
}));
renderSession();
assert.equal(document.querySelector('#session-minutes').value, '30');

state.activeSessionId = 'execution-2';
renderSession();
assert.equal(document.querySelector('#session-hours').value, '0');
assert.equal(document.querySelector('#session-minutes').value, '0');

state.activeSessionId = 'execution-1';
renderSession();
assert.equal(document.querySelector('#session-hours').value, '0');
assert.equal(document.querySelector('#session-minutes').value, '30');
assert.equal(observationLinkageRenderCount, 3);
'''
    result = subprocess.run([node, "-"], input=source[source.index("function missionTimezone("):source.index("function clock(")] + harness + helpers + checks, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_credit_confirmation_lost_response_and_reopen():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('const PENDING_ACCEPTANCE_STORAGE_KEY =')]
    harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor() { this.hidden = false; this.disabled = false; this.checked = false;
    this.textContent = ''; this.value = ''; this.children = []; }
  replaceChildren() { this.children = []; }
  append(child) { this.children.push(child); }
}
const elements = new Map();
const document = {
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector); },
  querySelectorAll(selector) { return selector === '.session-panel button' ? [document.querySelector('#session-apply-credit')] : []; },
  createElement() { return new Element(); },
};
function text(selector, value) { document.querySelector(selector).textContent = value; }
const storage = new Map();
const localStorage = {getItem: key => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)};
const state = {acceptedMission: {mission_id: 'mission-1', acquisitionIntentId: 'sh2-129_ha'},
  sessions: [], activeSessionId: null, sessionBusy: false};
let canonical = {execution: {execution_id: 'execution-1', mission_id: 'mission-1', status: 'completed',
    actual_start: '2026-09-21T20:00:00Z'}, acquisition_intent_id: 'sh2-129_ha',
  evidence: [{evidence_id: 'evidence-1', category: 'acquisition', usable_integration_duration: 1800}],
  credit: null, historical_baseline_seconds: 3600, historical_baseline_confirmed: false,
  acquired_before_seconds: 3600, session_credit_seconds: 0, acquired_after_seconds: 3600,
  current_acquired_seconds: 3600, target_hours: 2, remaining_hours: 1, profile_revision: 7};
let posts = 0;
async function fetch(url, options) {
  if (url.endsWith('/guardian-renewal')) return {ok: true, json: async () => ({
    schema_version: 'guardian-explicit-renewal-v1', execution_id: 'execution-1',
    guardian_mode_enabled: false, server_time: '2026-10-09T17:00:00Z'})};
  if (!options) return {ok: true, json: async () => [structuredClone(canonical)]};
  assert.equal(url, '/v1/executions/execution-1/intent-progress-credit');
  posts++;
  const body = JSON.parse(options.body);
  assert.deepEqual(body.evidence_ids, ['evidence-1']);
  assert.equal(body.expected_revision, 7);
  assert.equal(body.confirm_historical_baseline, true);
  canonical = {...canonical, credit: {execution_id: 'execution-1', total_duration_us: 1800000000},
    historical_baseline_confirmed: true, session_credit_seconds: 1800,
    acquired_after_seconds: 5400, current_acquired_seconds: 5400,
    remaining_hours: .5, profile_revision: 8};
  throw new Error('response lost after commit');
}
'''
    checks = r'''
(async () => {
  await reloadSessions({selectId: 'execution-1'});
  assert.equal(document.querySelector('#session-credit').hidden, false);
  assert.equal(document.querySelector('#session-baseline-confirm-wrap').hidden, false);
  await sessionCommand(creditSession);
  assert.equal(posts, 0, 'refusal must not write');
  document.querySelector('#session-baseline-confirm').checked = true;
  await sessionCommand(creditSession);
  assert.equal(posts, 1, 'lost response must be resolved through GET');
  assert.equal(currentSession().credit.total_duration_us, 1800000000);
  assert.equal(document.querySelector('#session-before').textContent, '1 h 00');
  assert.equal(document.querySelector('#session-added').textContent, '0 h 30');
  assert.equal(document.querySelector('#session-after').textContent, '1 h 30');
  assert.equal(document.querySelector('#session-after-label').textContent, 'Acquis après ce crédit');
  canonical.current_acquired_seconds = 6300;
  canonical.remaining_hours = .25;
  await reloadSessions();
  assert.equal(document.querySelector('#session-before').textContent, '1 h 00');
  assert.equal(document.querySelector('#session-after').textContent, '1 h 30');
  assert.equal(document.querySelector('#session-current').textContent, '1 h 45');
  assert.equal(document.querySelector('#session-remaining').textContent, '0 h 15');
  await sessionCommand(creditSession);
  assert.equal(posts, 1, 'reopen must not submit a second credit');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-"], input=source[source.index("function missionTimezone("):source.index("function clock(")] + harness + helpers + checks, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_session_actions_distinguish_lost_response_from_server_refusals():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('const PENDING_ACCEPTANCE_STORAGE_KEY =')]
    harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor() { this.hidden = false; this.disabled = false; this.checked = false;
    this.textContent = ''; this.value = ''; this.children = []; }
  replaceChildren() { this.children = []; }
  append(child) { this.children.push(child); }
}
const elements = new Map();
const document = {querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new Element());
  return elements.get(selector); }, querySelectorAll() { return [document.querySelector('#session-start')]; },
  createElement() { return new Element(); }};
function text(selector, value) { document.querySelector(selector).textContent = value; }
const storage = new Map();
const localStorage = {getItem: key => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)};
const crypto = {randomUUID: () => 'new-id'};
const state = {acceptedMission: {mission_id: 'mission-1', acquisitionIntentId: 'ha'},
  sessions: [], activeSessionId: null, sessionBusy: false};
let status = 409, lost = false, writes = 0;
let canonical = {execution: {execution_id: 'execution-1', mission_id: 'mission-1', status: 'not_started',
  actual_start: null}, acquisition_intent_id: 'ha', evidence: [], credit: null,
  historical_baseline_seconds: 0, historical_baseline_confirmed: false,
  acquired_before_seconds: 0, session_credit_seconds: 0, acquired_after_seconds: 0,
  current_acquired_seconds: 0, target_hours: null, remaining_hours: null, profile_revision: 7};
async function fetch(url, options) {
  if (url.endsWith('/guardian-renewal')) return {ok: true, json: async () => ({
    schema_version: 'guardian-explicit-renewal-v1', execution_id: 'execution-1',
    guardian_mode_enabled: false, server_time: '2026-10-09T17:00:00Z'})};
  if (!options) return {ok: true, status: 200, json: async () => [structuredClone(canonical)]};
  writes++;
  if (lost) throw new Error('transport lost');
  return {ok: false, status, json: async () => ({detail: {code: 'refused'}})};
}
'''
    checks = r'''
(async () => {
  const actions = [
    {name: 'start', command: startSession, sessionStatus: 'not_started'},
    {name: 'complete', command: (id) => closeSession(id, 'completed'), sessionStatus: 'in_progress'},
    {name: 'interrupt', command: (id) => closeSession(id, 'interrupted'), sessionStatus: 'in_progress'},
    {name: 'credit', command: creditSession, sessionStatus: 'completed', evidence: true},
  ];
  for (const action of actions) {
    for (const failure of [409, 422, 503, 'lost']) {
      canonical.execution.status = action.sessionStatus;
      canonical.execution.actual_start = action.sessionStatus === 'not_started' ? null : '2026-09-21T20:00:00Z';
      canonical.evidence = action.evidence ? [{evidence_id: 'evidence-1', category: 'acquisition', usable_integration_duration: 1800}] : [];
      state.activeSessionId = 'execution-1';
      status = failure; lost = failure === 'lost'; writes = 0;
      await sessionCommand(action.command);
      assert.equal(writes, 1, `${action.name}/${failure}`);
      const message = document.querySelector('#session-status').textContent;
      if (failure === 'lost') assert.match(message, /réponse incertaine/, action.name);
      else {
        assert.match(message, /refusée|impossible/, `${action.name}/${failure}`);
        assert.doesNotMatch(message, /réponse incertaine/, `${action.name}/${failure}`);
      }
    }
  }
  canonical.execution.status = 'unconfirmed';
  canonical.evidence = [{evidence_id: 'evidence-1', category: 'acquisition', usable_integration_duration: 1800}];
  await reloadSessions({selectId: 'execution-1'});
  assert.equal(document.querySelector('#session-start').hidden, true);
  assert.equal(document.querySelector('#session-credit').hidden, true);
  assert.match(document.querySelector('#session-status').textContent, /Session non confirmée/);
  assert.equal(document.querySelector('#session-choice').children[0].textContent, 'Sans session');
  assert.match(document.querySelector('#session-choice').children[1].textContent, /Session non confirmée/);
  for (const invalidStatus of ['interrupted', 'unknown', null]) {
    canonical.execution.status = invalidStatus;
    await reloadSessions({selectId: 'execution-1'});
    assert.equal(document.querySelector('#session-credit').hidden, true);
    assert.equal(document.querySelector('#session-apply-credit').disabled, true);
    const before = writes;
    await creditSession('mission-1', true);
    assert.equal(writes, before);
    assert.match(document.querySelector('#session-status').textContent, /aucun crédit/);
    await sessionCommand(creditSession);
    assert.equal(writes, before);
    assert.equal(document.querySelector('#session-apply-credit').disabled, true);
    assert.match(document.querySelector('#session-status').textContent,
      invalidStatus === 'interrupted' ? /Session interrompue : aucun crédit/ : /État de session non reconnu/);
    assert.equal(document.querySelector('#session-start').hidden, invalidStatus !== 'interrupted');
  }
  state.activeSessionId = null;
  renderSession();
  assert.equal(document.querySelector('#session-start').hidden, false);
  assert.equal(document.querySelector('#session-start').className, 'primary-button');
  canonical.execution.status = 'completed';
  for (const value of [null, 0]) {
    canonical.evidence[0].usable_integration_duration = value;
    await reloadSessions({selectId: 'execution-1'});
    assert.equal(document.querySelector('#session-credit').hidden, true);
    assert.equal(document.querySelector('#session-evidence').hidden, false);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-"], input=source[source.index("function missionTimezone("):source.index("function clock(")] + harness + helpers + checks, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_failed_initial_read_never_reports_uncertain_command():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('const PENDING_ACCEPTANCE_STORAGE_KEY =')]
    harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor() { this.hidden = false; this.disabled = false; this.checked = false;
    this.textContent = ''; this.value = ''; this.children = []; }
  replaceChildren() { this.children = []; }
  append(item) { this.children.push(item); }
}
const elements = new Map();
const document = {querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new Element());
  return elements.get(selector); }, querySelectorAll() { return []; },
  createElement() { return new Element(); }};
function text(selector, value) { document.querySelector(selector).textContent = value; }
const localStorage = {getItem() { return null; }, removeItem() {}};
const state = {acceptedMission: {mission_id: 'mission-1', acquisitionIntentId: 'ha'},
  sessions: [], activeSessionId: null, sessionBusy: false};
let reads = 0, writes = 0;
async function fetch(_url, options) {
  if (options) { writes++; throw new Error('unexpected write'); }
  reads++;
  if (reads === 1) throw new Error('initial read failed');
  return {ok: true, json: async () => []};
}
'''
    checks = r'''
(async () => {
  await sessionCommand(() => { throw new Error('command must not run'); });
  assert.equal(reads, 2);
  assert.equal(writes, 0);
  const message = document.querySelector('#session-status').textContent;
  assert.match(message, /Lecture ou reprise échouée/);
  assert.doesNotMatch(message, /réponse incertaine/);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-"], input=source[source.index("function missionTimezone("):source.index("function clock(")] + harness + helpers + checks, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_saved_missions_include_expired_sessions_and_open_selected_mission():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    source = SCRIPT.read_text(encoding="utf-8")
    restore = source[source.index('function configurationOperationIsCurrent('):source.index('function installCurrentConfiguration(')] + source[source.index('async function restoreSavedMission()'):source.index('function invalidateAvailabilityForSiteChange')]
    open_handler = source[source.index('ui.openSavedMission.addEventListener'):source.index('document.querySelector("#session-choice").addEventListener')]
    harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor() { this.hidden = false; this.value = ''; this.textContent = ''; this.children = []; }
  replaceChildren() { this.children = []; }
  append(item) { this.children.push(item); }
  addEventListener(_name, handler) { this.handler = handler; }
}
const ui = {savedMissionEntry: new Element(), savedMissionChoice: new Element(),
  savedMissionTarget: new Element(), openSavedMission: new Element(), mission: {showModal() { opened = true; }}};
const document = {createElement() { return new Element(); }};
const state = {configuration: {}, acceptedMission: null, savedMissions: []};
let opened = false, rendered = null;
function renderMission(mission) { rendered = mission; }
const mission = (id, target, window_start) => ({mission_id: id, selection_id: `s-${id}`,
  decision_id: `d-${id}`, target, window_start});
const old = mission('old', 'Ancienne mission', '2026-08-01T20:00:00Z');
const recent = mission('recent', 'Mission récente', '2026-09-21T20:00:00Z');
async function fetch(url) {
  if (url === '/v1/accepted-mission/current') return {ok: true, json: async () => ({status: 'accepted',
    mission_id: recent.mission_id, selection_id: recent.selection_id, decision_id: recent.decision_id,
    catalog_key: 'Sh2-129', selected_acquisition_intent_id: 'ha', mission: recent})};
  return {ok: true, json: async () => [recent, old].map((item) => ({mission_id: item.mission_id,
    mission: item, project_id: 'Sh2-129', acquisition_intent_id: 'ha'}))};
}
'''
    checks = r'''
(async () => {
  await restoreSavedMission();
  assert.equal(state.savedMissions.length, 2);
  assert.equal(ui.savedMissionChoice.children[0].value, 'recent');
  assert.equal(ui.savedMissionChoice.children[1].value, 'old');
  ui.savedMissionChoice.value = 'old';
  ui.openSavedMission.handler();
  assert.equal(state.acceptedMission.mission_id, 'old');
  assert.equal(rendered.target, 'Ancienne mission');
  assert.equal(opened, true);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-"], input=source[source.index("function missionTimezone("):source.index("function clock(")] + harness + restore + open_handler + checks, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_completion_action_hierarchy_uses_canonical_session_state():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[source.index('const SESSION_PENDING_KEY ='):source.index('async function reloadSessions')]
    harness = r'''

const assert = require('node:assert/strict');
class Element {
  constructor() { this.hidden = false; this.checked = false; this.textContent = '';
    this.value = ''; this.children = []; }
  replaceChildren() { this.children = []; }
  append(child) { this.children.push(child); }
}
const elements = new Map();
const document = {
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector); },
  createElement() { return new Element(); },
};
function text(selector, value) { document.querySelector(selector).textContent = value; }
const storage = new Map();
const localStorage = {getItem: key => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, value)};
const session = (id) => ({execution: {execution_id: id, status: 'completed', actual_start: null},
  acquisition_intent_id: 'ha', evidence: [], credit: null, historical_baseline_seconds: 0,
  historical_baseline_confirmed: false, acquired_before_seconds: 0, session_credit_seconds: 0,
  acquired_after_seconds: 0, current_acquired_seconds: 0, target_hours: null, remaining_hours: null});
const state = {acceptedMission: {mission_id: 'mission-1', acquisitionIntentId: 'ha'},
  sessions: [session('execution-1'), session('execution-2')], activeSessionId: 'execution-1',
  sessionEvidenceInputExecutionId: null};
// Keep the session test focused while preserving renderSession's Field Observation integration point.
let observationLinkageRenderCount = 0;
function renderObservationLinkage() { observationLinkageRenderCount++; }
'''
    checks = r'''
const selected = state.sessions[0];
for (const [status, evidence, credit, primary] of [
  ['in_progress', false, false, true],
  ['completed', false, false, false],
  ['completed', true, false, false],
  ['completed', true, true, true],
  ['interrupted', false, false, true],
  ['interrupted', true, false, true],
  ['unknown', true, false, true],
  ['unconfirmed', false, false, true],
]) {
  selected.execution.status = status;
  selected.evidence = evidence ? [{category:'acquisition', usable_integration_duration:1800}] : [];
  selected.credit = credit ? {execution_id:'execution-1'} : null;
  renderSession();
  assert.equal(document.querySelector('#session-start').className, primary ? 'primary-button' : 'secondary-button');
  assert.equal(document.querySelector('#session-evidence').hidden, status !== 'completed' || evidence);
  assert.equal(document.querySelector('#session-credit').hidden, status !== 'completed' || !evidence || credit);
  assert.equal(document.querySelector('#session-start').hidden, ['in_progress','unconfirmed','unknown'].includes(status));
  assert.equal(document.querySelector('#session-close-actions').hidden, status !== 'in_progress');
}
assert.equal(sessionStatus('completed'), 'Terminée');
assert.equal(sessionStatus('interrupted'), 'Interrompue');
assert.doesNotMatch(document.querySelector('#session-credit-preview').textContent, /intent|sh2|ha/i);
'''
    result = subprocess.run([node, "-"], input=source[source.index("function missionTimezone("):source.index("function clock(")] + harness + helpers + checks, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_recent_observations_without_context_reports_empty_state_without_requests():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required")
    source = SCRIPT.read_text(encoding="utf-8")
    helper = source[source.index('async function reopenRecentFieldObservations()'):source.index('const OUTCOME_REASON_TEXT =')]
    harness = r'''
const assert = require('node:assert/strict');
const message = {hidden:true, textContent:''};
const document = {querySelector: () => message};
let saved = null, loads = 0, opens = 0;
const localStorage = {getItem: () => saved};
const state = {observationBusy:false};
function invalidateFieldObservationOperation() {}
function setFieldObservationEditorDisabled() {}
function observationMessage() {}
const ui = {observation:{showModal() { opens++; }}};
async function loadSavedFieldObservations(context) {loads++; assert.equal(context.decision_id,'decision-1');}
'''
    checks = r'''
(async () => {
for (const value of [null, '{', '{}', '{"decision_id":""}']) {
  saved = value; message.hidden = true;
  await reopenRecentFieldObservations();
  assert.equal(message.hidden, false);
  assert.equal(message.textContent, 'Aucune observation enregistrée récemment.');
  assert.equal(loads, 0); assert.equal(opens, 0);
}
saved = '{"decision_id":"decision-1"}';
await reopenRecentFieldObservations();
assert.equal(message.hidden, true); assert.equal(loads, 1); assert.equal(opens, 1);
assert.equal(state.fieldObservationContextInvalid, true);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-"], input=source[source.index("function missionTimezone("):source.index("function clock(")] + harness + helper + checks, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_completion_dom_order_follows_action_priority():
    html = (SCRIPT.parent / "index.html").read_text(encoding="utf-8")
    assert html.index('id="session-record-evidence"') < html.index('id="session-apply-credit"') < html.index('id="session-start"')
    assert 'tabindex="1"' not in html


@pytest.mark.parametrize("browser_zone", ["America/New_York", "Asia/Tokyo"])
@pytest.mark.parametrize("zone,expected", [("Europe/Zurich", "20:00"), (None, "18:00"), ("Invalid/Zone", "18:00")])
def test_mission_session_labels_ignore_browser_timezone(browser_zone, zone, expected):
    import json
    import os
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[source.index("function missionTimezone("):source.index("function clock(")]
    checks = f"""
const assert = require('node:assert/strict');
const zone = missionTimezone({{}}, {{windowTimezone:{json.dumps(zone)}}});
assert.equal(zone, {json.dumps('Europe/Zurich' if zone == 'Europe/Zurich' else 'UTC')});
const label = missionDateTimeLabel('2026-10-04T18:00:00Z', zone);
assert.ok(label.includes({json.dumps(expected)}), label);
assert.ok(label.endsWith(' · ' + zone));
"""
    result = subprocess.run([node, "-e", helpers + checks], env={**os.environ, "TZ": browser_zone}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_session_timing_logs_once_without_retrying_or_changing_response():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the dynamic UI test')
    source = SCRIPT.read_text()
    helper = source[source.index('async function sessionFetch('):source.index('const guardianUI =')]
    harness = r'''
const assert = require('node:assert/strict');
let calls=0, ticks=0, fail=false; const logs=[];
const console={info:(...args)=>logs.push(args),error:()=>{}};
const performance={now:()=>ticks+=10};
const response={status:200,headers:{get:name=>name==='Server-Timing'?'session;dur=8':null}};
async function fetch() {calls++;if(fail)throw new Error('network');return response;}
'''
    checks = r'''
(async()=>{
  globalThis.ASTROPILOT_SESSION_TIMING=true;
  assert.equal(await sessionFetch('/v1/execution-transitions',{method:'POST'}),response);
  assert.deepEqual(logs[0],['session-request','POST','/v1/execution-transitions',10,200,'session;dur=8']);
  fail=true;
  await assert.rejects(()=>sessionFetch('/v1/execution-transitions',{method:'POST'}));
  assert.equal(calls,2,'failed POST is never retried by instrumentation');
  assert.equal(logs[1][4],'network-error');
  globalThis.ASTROPILOT_SESSION_TIMING=false;fail=false;
  await sessionFetch('/v1/executions/x/session');
  assert.equal(calls,3);assert.equal(logs.length,2,'disabled timing emits no diagnostics');
})().catch(()=>{process.exitCode=1;});
'''
    subprocess.run([node, '-e', harness + helper + checks], check=True, capture_output=True, text=True)
