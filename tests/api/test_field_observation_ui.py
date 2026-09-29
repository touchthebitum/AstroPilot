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
const storageFailures = {get: false, set: false, remove: false};
const localStorage = {
  getItem(key) { if (storageFailures.get) throw new Error('get denied'); return storage.has(key) ? storage.get(key) : null; },
  setItem(key, value) { if (storageFailures.set) throw new Error('quota exceeded'); storage.set(key, value); },
  removeItem(key) { if (storageFailures.remove) throw new Error('remove denied'); storage.delete(key); },
};
let uuid = 0;
const crypto = {randomUUID: () => `observation-${++uuid}`};
const state = {acceptedMission: {decision_id: 'decision-1'}, sessions: [], activeSessionId: null,
  observationBusy: false, fieldObservationDraftContext: null, invalidFieldObservationContextKey: null};
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
  storageFailures.get = false; storageFailures.set = false; storageFailures.remove = false;
  state.sessions = []; state.activeSessionId = null;
  state.invalidFieldObservationContextKey = null;
  if (state.unreadableFieldObservationContextKeys instanceof Set) state.unreadableFieldObservationContextKeys.clear();
  resetFieldObservationForm();
  state.fieldObservationDraftContext = currentFieldObservationContext();
  element('#observation-status').textContent = '';
}
'''
    checks = r'''
async function check() {
  clearHarness();
  setQuick({cloud: 'mostly_cloudy', transparency: 'excellent', wind: '8.5'});
  element('#surface-damp').checked = true;
  element('#observation-temperature').value = '-2.4';
  element('#observation-humidity').value = '87';
  element('#observation-seeing').value = 'fair';
  element('#observation-moon-halo').value = 'true';
  element('#observation-attempted-frames').value = '120';
  element('#observation-usable-frames').value = '95';
  element('#observation-stop-reason').value = 'clouds';
  element('#observation-hfr').value = '2.35';
  element('#observation-hfr-unit').value = 'arcsec';
  element('#observation-guiding').value = '0.72';
  let payload = buildFieldObservationPayload();
  assert.equal(payload.conditions.cloud_state, 'mostly_cloudy');
  assert.equal(payload.conditions.transparency, 'excellent');
  assert.equal(payload.conditions.wind_speed_kmh, 8.5);
  assert.equal(payload.conditions.surface_condition, 'damp');
  assert.equal(payload.conditions.temperature_c, -2.4);
  assert.equal(payload.conditions.relative_humidity_percent, 87);
  assert.equal(payload.conditions.seeing, 'fair');
  assert.equal(payload.conditions.moon_halo, true);
  assert.equal(payload.acquisition.attempted_frames, 120);
  assert.equal(payload.acquisition.usable_frames, 95);
  assert.equal(payload.acquisition.stop_reason, 'clouds');
  assert.equal(payload.technical.hfr, 2.35);
  assert.equal(payload.technical.hfr_unit, 'arcsec');
  assert.equal(payload.technical.guiding_rms_arcsec, 0.72);
  assert.equal(payload.technical.sky_background, null);
  assert.equal(payload.technical.sky_background_unit, null);

  // Empty controls stay null, including the HFR unit, and do not invent facts.
  clearHarness(); setQuick({cloud: 'clear'});
  element('#observation-hfr-unit').value = 'px';
  payload = buildFieldObservationPayload();
  assert.equal(payload.conditions.temperature_c, null);
  assert.equal(payload.conditions.relative_humidity_percent, null);
  assert.equal(payload.conditions.transparency, null);
  assert.equal(payload.conditions.seeing, null);
  assert.equal(payload.conditions.wind_speed_kmh, null);
  assert.equal(payload.conditions.surface_condition, null);
  assert.equal(payload.conditions.moon_halo, null);
  assert.equal(payload.acquisition.attempted_frames, null);
  assert.equal(payload.acquisition.usable_frames, null);
  assert.equal(payload.acquisition.stop_reason, null);
  assert.equal(payload.technical.hfr, null);
  assert.equal(payload.technical.hfr_unit, null);
  assert.equal(payload.technical.guiding_rms_arcsec, null);
  clearHarness();
  assert.equal(fieldObservationDraft(), null);
  assert.equal(buildFieldObservationPayload(), null);

  // Typed key components keep valid lookalike identifiers distinct.
  const keyContexts = [
    ['alpha', null],
    ['alpha', 'decision'],
    ['alpha', 'decision-only'],
    ['alpha', 'execution'],
    ['alpha', 'a.b_c-d'],
    ['alpha.decision', null],
    ['alpha', 'decision.decision-only'],
  ];
  const pendingKeys = keyContexts.map(([decisionId, executionId]) => pendingObservationKey(decisionId, executionId));
  assert.equal(new Set(pendingKeys).size, keyContexts.length);
  assert.notEqual(pendingObservationKey('alpha', null), pendingObservationKey('alpha', 'decision'));
  assert.match(pendingObservationKey('a.b_c-d', null), /decision:a\.b_c-d\.decision-only$/);
  assert.match(pendingObservationKey('a.b_c-d', 'decision'), /execution:decision$/);

  // Switching from session A to B clears A's values and cannot submit them as B.
  clearHarness();
  state.sessions = [
    {execution: {execution_id: 'session-a'}},
    {execution: {execution_id: 'session-b'}},
  ];
  state.activeSessionId = 'session-a'; syncFieldObservationContext();
  setQuick({cloud: 'overcast', transparency: 'poor', wind: '12'});
  state.activeSessionId = 'session-b'; syncFieldObservationContext();
  assert.equal(element('#observation-clouds').value, '');
  assert.equal(element('#observation-transparency').value, '');
  assert.equal(element('#observation-wind').value, '');
  assert.match(element('#observation-status').textContent, /session précédente a été effacée/);
  let sessionPosts = 0;
  fetch = async () => { sessionPosts += 1; return response(201, {}); };
  await submitFieldObservation(event);
  assert.equal(sessionPosts, 0);
  setQuick({cloud: 'clear'});
  let sessionPayload;
  fetch = async (_url, options) => { sessionPosts += 1; sessionPayload = JSON.parse(options.body); return response(201, {}); };
  await submitFieldObservation(event);
  assert.equal(sessionPosts, 1);
  assert.equal(sessionPayload.execution_id, 'session-b');
  assert.equal(sessionPayload.conditions.cloud_state, 'clear');
  assert.equal(sessionPayload.conditions.transparency, null);
  assert.equal(sessionPayload.conditions.wind_speed_kmh, null);

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

  // A 404 invalidates the pending payload and identifies the stale context.
  clearHarness(); setQuick({cloud: 'few'});
  const staleKey = pendingObservationKey('decision-1', null);
  fetch = async (_url, options) => {
    assert.ok(options);
    return response(404, {detail: {code: 'field_observation_context_not_found'}});
  };
  await submitFieldObservation(event);
  assert.equal(storage.has(staleKey), false);
  assert.equal(element('#observation-clouds').value, 'few');
  assert.match(element('#observation-status').textContent, /introuvable ou périmée/);
  assert.match(element('#observation-status').textContent, /Rechargez puis re-sélectionnez/);
  await submitFieldObservation(event);
  assert.match(element('#observation-status').textContent, /contexte est périmé/);

  // A failing removeItem during 404 invalidation falls back to a safe tombstone.
  clearHarness(); setQuick({cloud: 'few'});
  fetch = async (_url, options) => {
    assert.ok(options); storageFailures.remove = true;
    return response(404, {detail: {code: 'field_observation_context_not_found'}});
  };
  await submitFieldObservation(event);
  const invalidated = JSON.parse(storage.get(staleKey));
  assert.equal(invalidated.invalidated, true);
  assert.equal(invalidated.payload, undefined);
  assert.match(element('#observation-status').textContent, /introuvable ou périmée/);

  // Storage read/write failures block all network traffic with an explicit error.
  clearHarness(); setQuick({cloud: 'few'});
  let blockedFetches = 0;
  fetch = async () => { blockedFetches += 1; return response(201, {}); };
  storageFailures.get = true;
  await submitFieldObservation(event);
  assert.equal(blockedFetches, 0);
  assert.match(element('#observation-status').textContent, /stockage local est indisponible/i);
  storageFailures.get = false; storageFailures.set = true;
  await submitFieldObservation(event);
  assert.equal(blockedFetches, 0);
  assert.match(element('#observation-status').textContent, /Envoi bloqué/);

  // Corrupt JSON stays fail-closed even when cleanup succeeds; no identity is generated.
  clearHarness(); setQuick({cloud: 'few'});
  storage.set(pendingObservationKey('decision-1', null), '{broken');
  blockedFetches = 0;
  fetch = async () => { blockedFetches += 1; return response(201, {}); };
  await submitFieldObservation(event);
  assert.equal(blockedFetches, 0);
  assert.equal(uuid, 0);
  assert.equal(storage.has(pendingObservationKey('decision-1', null)), false);
  assert.match(element('#observation-status').textContent, /brouillon local est illisible/i);
  assert.match(element('#observation-status').textContent, /idempotence n’est plus garantie/i);
  await submitFieldObservation(event);
  assert.equal(blockedFetches, 0);
  assert.equal(uuid, 0);

  // Valid JSON with an invalid structure/surface cannot build a selector or reach the network.
  clearHarness(); setQuick({cloud: 'few'});
  const malformedPayload = buildFieldObservationPayload();
  malformedPayload.conditions.surface_condition = 'dry\"]:not-valid[';
  resetFieldObservationForm();
  storage.set(pendingObservationKey('decision-1', null), JSON.stringify({
    payload: malformedPayload, snapshot: snapshotFromObservationPayload(malformedPayload),
  }));
  blockedFetches = 0;
  fetch = async () => { blockedFetches += 1; return response(201, {}); };
  restorePendingFieldObservation();
  assert.match(element('#observation-status').textContent, /brouillon local est illisible/i);
  setQuick({cloud: 'few'});
  await submitFieldObservation(event);
  assert.equal(blockedFetches, 0);
  assert.equal(uuid, 1);
  assert.match(element('#observation-status').textContent, /brouillon local est illisible/i);

  // Corrupt JSON with a failing cleanup is equally blocking.
  clearHarness(); setQuick({cloud: 'few'});
  storage.set(pendingObservationKey('decision-1', null), '{broken');
  storageFailures.remove = true; blockedFetches = 0;
  fetch = async () => { blockedFetches += 1; return response(201, {}); };
  await submitFieldObservation(event);
  assert.equal(blockedFetches, 0);
  assert.equal(uuid, 0);
  assert.match(element('#observation-status').textContent, /brouillon local est illisible/i);

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
