"""Execute the real field-observation UI helpers against a small browser harness."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


def test_field_observation_retry_conflict_and_form_state_are_dynamic(tmp_path):
    engine = shutil.which("node") or shutil.which("osascript")
    if engine is None:
        pytest.skip("A JavaScript runtime is required for the dynamic UI test")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[
        source.index("const OBSERVATION_CHOICES ="):
        source.index("const PENDING_ACCEPTANCE_STORAGE_KEY =")
    ]
    harness = r'''
const assert = {
  equal(actual, expected, message = '') { if (actual !== expected) throw new Error(message || `${actual} !== ${expected}`); },
  notEqual(actual, expected, message = '') { if (actual === expected) throw new Error(message || `${actual} === ${expected}`); },
  ok(value, message = '') { if (!value) throw new Error(message || 'expected truthy value'); },
  match(value, pattern, message = '') { if (!pattern.test(value)) throw new Error(message || `${value} does not match ${pattern}`); },
};
const clone = value => JSON.parse(JSON.stringify(value));
class Element {
  constructor(id = '') {
    this.id = id; this.value = ''; this.checked = false; this.disabled = false;
    this.textContent = ''; this.open = false; this.options = []; this.listeners = {};
    this.classList = {toggle: (_name, _enabled) => {}};
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelectorAll(selector) {
    if (selector === '[data-observation-choice]') return [element('#observation-clouds'), element('#observation-transparency')];
    if (selector === 'input[type="number"]') return numberIds.map(element);
    if (selector === 'input[type="radio"]') return radioIds.map(element);
    if (selector === 'select') return selectIds.map(element);
    return [];
  }
  set selectedIndex(value) { if (value === 0) this.value = ''; }
}
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, new Element(selector));
  return elements.get(selector);
}
const numberIds = ['#observation-wind', '#observation-temperature', '#observation-humidity',
  '#observation-attempted-frames', '#observation-usable-frames', '#observation-hfr', '#observation-guiding'];
const selectIds = ['#observation-clouds', '#observation-transparency', '#observation-seeing',
  '#observation-moon-halo', '#observation-stop-reason', '#observation-hfr-unit'];
const radioIds = ['dry', 'damp', 'dew_present'].map(value => `#surface-${value}`);
const document = {
  querySelector(selector) {
    const choice = selector.match(/^\[data-observation-choice="([^"]+)"\]$/);
    if (choice) return element(`#observation-${choice[1]}`);
    if (selector === 'input[name="observation-surface"]:checked') {
      return radioIds.map(element).find(item => item.checked) || null;
    }
    const radio = selector.match(/^input\[name="observation-surface"\]\[value="([^"]+)"\]$/);
    if (radio) return element(`#surface-${radio[1]}`);
    return element(selector);
  },
};
radioIds.forEach((selector, index) => { element(selector).value = ['dry', 'damp', 'dew_present'][index]; });
element('#field-observation-form');
element('.observation-advanced');
const storage = new Map();
const localStorage = {
  getItem: key => storage.has(key) ? storage.get(key) : null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
};
let uuid = 0;
const crypto = {randomUUID: () => `observation-${++uuid}`};
const state = {acceptedMission: {decision_id: 'decision-1'}, sessions: [], activeSessionId: null, observationBusy: false};
function currentSession() { return state.sessions.find(item => item.execution.execution_id === state.activeSessionId) || null; }
async function sessionHttpError(response) {
  const error = new Error('request_refused'); error.status = response.status;
  try { error.code = (await response.json()).detail?.code; } catch (_ignored) {}
  return error;
}
const response = (status, body = {}) => ({ok: status >= 200 && status < 300, status, json: async () => clone(body)});
const event = {preventDefault() {}};
let fetch;
function setQuick({cloud = '', transparency = '', wind = ''} = {}) {
  element('#observation-clouds').value = cloud;
  element('#observation-transparency').value = transparency;
  element('#observation-wind').value = wind;
}
function storedProjection(payload) {
  return {...clone(payload), provenance: {source_type: 'user', capture_method: 'manual', source_id: null, imported_at_utc: null},
    quality: {confidence: payload.confidence, flags: payload.quality_flags}, calibration_eligible: false};
}
function clearHarness() {
  storage.clear(); state.observationBusy = false; uuid = 0;
  resetFieldObservationForm();
  element('#observation-status').textContent = '';
}
'''
    checks = r'''
async function check() {
  clearHarness();
  setQuick({cloud: 'mostly_cloudy', transparency: 'excellent', wind: '8.5'});
  let payload = buildFieldObservationPayload();
  assert.equal(payload.conditions.cloud_state, 'mostly_cloudy');
  assert.equal(payload.conditions.transparency, 'excellent');
  assert.equal(payload.conditions.wind_speed_kmh, 8.5);

  // A server-declared conflict is never reconciled into success and keeps input.
  clearHarness(); setQuick({cloud: 'overcast'});
  fetch = async () => response(409, {detail: {code: 'field_observation_conflict'}});
  await submitFieldObservation(event);
  assert.match(element('#observation-status').textContent, /Conflit/);
  assert.equal(element('#observation-clouds').value, 'overcast');

  // A lookup that finds the same id with different content is also a conflict.
  clearHarness(); setQuick({cloud: 'few'});
  const pendingPayload = buildFieldObservationPayload();
  const pendingKey = pendingObservationKey('decision-1', null);
  localStorage.setItem(pendingKey, JSON.stringify({
    payload: pendingPayload, snapshot: fieldObservationSnapshot(),
  }));
  const conflictingStored = storedProjection(pendingPayload);
  conflictingStored.conditions.cloud_state = 'overcast';
  fetch = (url, options) => {
    assert.equal(options, undefined);
    return response(200, conflictingStored);
  };
  await submitFieldObservation(event);
  assert.match(element('#observation-status').textContent, /Conflit/);
  assert.equal(element('#observation-clouds').value, 'few');

  // A timeout keeps the exact payload and a retry reuses it, yielding a 200 replay.
  clearHarness(); setQuick({cloud: 'few', transparency: 'good'});
  const posted = [];
  let phase = 0;
  fetch = async (url, options) => {
    if (options) {
      posted.push(options.body);
      if (phase++ === 0) throw new TypeError('network timeout');
      return response(200, {created: false});
    }
    return response(404, {detail: {code: 'field_observation_not_found'}});
  };
  await submitFieldObservation(event);
  assert.equal(element('#observation-clouds').value, 'few');
  await submitFieldObservation(event);
  assert.equal(posted.length, 2);
  assert.equal(posted[0], posted[1]);
  assert.equal(element('#observation-clouds').value, '');

  // Editing after a timeout creates a new snapshot/id instead of replaying stale input.
  clearHarness(); setQuick({cloud: 'few'});
  const changedPosts = [];
  fetch = async (url, options) => {
    if (!options) return response(404, {});
    changedPosts.push(JSON.parse(options.body));
    if (changedPosts.length === 1) throw new TypeError('network timeout');
    return response(201, {created: true});
  };
  await submitFieldObservation(event);
  setQuick({cloud: 'clear', transparency: 'fair'});
  await submitFieldObservation(event);
  assert.equal(changedPosts.length, 2);
  assert.notEqual(changedPosts[0].observation_id, changedPosts[1].observation_id);
  assert.equal(changedPosts[0].conditions.cloud_state, 'few');
  assert.equal(changedPosts[1].conditions.cloud_state, 'clear');
  assert.equal(changedPosts[1].conditions.transparency, 'fair');

  // Edits made while the request is in flight survive the successful response.
  clearHarness(); setQuick({cloud: 'clear'});
  let resolvePost;
  fetch = async (_url, options) => {
    assert.ok(options);
    return new Promise(resolve => { resolvePost = resolve; });
  };
  const submitting = submitFieldObservation(event);
  setQuick({cloud: 'overcast'});
  resolvePost(response(201, {created: true}));
  await submitting;
  assert.equal(element('#observation-clouds').value, 'overcast');
  assert.match(element('#observation-status').textContent, /modifications en cours sont conservées/);

  // An uncertain request is rehydrated from local storage after a page/form reset.
  clearHarness(); setQuick({cloud: 'partly_cloudy', transparency: 'poor', wind: '4.2'});
  fetch = async (url, options) => options ? Promise.reject(new TypeError('offline')) : response(404, {});
  await submitFieldObservation(event);
  resetFieldObservationForm();
  restorePendingFieldObservation();
  assert.equal(element('#observation-clouds').value, 'partly_cloudy');
  assert.equal(element('#observation-transparency').value, 'poor');
  assert.equal(element('#observation-wind').value, '4.2');

  // Native selects accept direct discrete changes (keyboard/touch behavior is browser-owned).
  element('#observation-clouds').value = 'clear';
  assert.equal(fieldObservationDraft().conditions.cloud_state, 'clear');
}
'''
    if Path(engine).name == "node":
        program = harness + helpers + checks + "\ncheck().catch(error => { console.error(error); process.exitCode = 1; });\n"
        command = [engine, "-e", program]
    else:
        synchronous_harness = harness.replace(
            "async function sessionHttpError(response)",
            "function sessionHttpError(response)",
        ).replace(
            "(await response.json()).detail?.code",
            "response.json().detail?.code",
        ).replace(
            "json: async () => clone(body)",
            "json: () => clone(body)",
        )
        synchronous_helpers = helpers.replace("async function ", "function ").replace("await ", "")
        synchronous_checks = checks.replace("async function check()", "function check()")
        synchronous_checks = synchronous_checks.replace("await submitFieldObservation(event);", "submitFieldObservation(event);")
        synchronous_checks = synchronous_checks.replace("fetch = async ", "fetch = ")
        synchronous_checks = synchronous_checks.replace(
            "  let resolvePost;\n  fetch = (_url, options) => {\n    assert.ok(options);\n    return new Promise(resolve => { resolvePost = resolve; });\n  };\n  const submitting = submitFieldObservation(event);\n  setQuick({cloud: 'overcast'});\n  resolvePost(response(201, {created: true}));\n  await submitting;",
            "  fetch = (_url, options) => {\n    assert.ok(options);\n    setQuick({cloud: 'overcast'});\n    return response(201, {created: true});\n  };\n  submitFieldObservation(event);",
        )
        synchronous_checks = synchronous_checks.replace(
            "fetch = (url, options) => options ? Promise.reject(new TypeError('offline')) : response(404, {});",
            "fetch = (url, options) => { if (options) throw new TypeError('offline'); return response(404, {}); };",
        )
        program = synchronous_harness + synchronous_helpers + synchronous_checks + "\ncheck();\n"
        file = tmp_path / "field_observation_ui.js"
        file.write_text(program, encoding="utf-8")
        command = [engine, "-l", "JavaScript", str(file)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
