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
  target_hours: 2, remaining_hours: 1, profile_revision: 7};
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
    acquired_after_seconds: 5400, remaining_hours: .5, profile_revision: 8};
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
  await sessionCommand(creditSession);
  assert.equal(posts, 1, 'reopen must not submit a second credit');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-e", harness + helpers + checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
