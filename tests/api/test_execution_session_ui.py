"""Execute the real session UI helpers against a small browser harness."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


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
  await reloadSessions();
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
    result = subprocess.run([node, "-e", harness + helpers + checks], capture_output=True, text=True)
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
      state.activeSessionId = null;
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
  await reloadSessions();
  assert.equal(document.querySelector('#session-start').hidden, true);
  assert.equal(document.querySelector('#session-credit').hidden, true);
  assert.match(document.querySelector('#session-status').textContent, /Session non confirmée/);
  assert.match(document.querySelector('#session-choice').children[0].textContent, /Session non confirmée/);
  canonical.execution.status = 'completed';
  for (const value of [null, 0]) {
    canonical.evidence[0].usable_integration_duration = value;
    await reloadSessions();
    assert.equal(document.querySelector('#session-credit').hidden, true);
    assert.equal(document.querySelector('#session-evidence').hidden, false);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-e", harness + helpers + checks], capture_output=True, text=True)
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
    result = subprocess.run([node, "-e", harness + helpers + checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_saved_missions_include_expired_sessions_and_open_selected_mission():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    source = SCRIPT.read_text(encoding="utf-8")
    restore = source[source.index('async function restoreSavedMission()'):source.index('function invalidateAvailabilityForSiteChange')]
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
    result = subprocess.run([node, "-e", harness + restore + open_handler + checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
