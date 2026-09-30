"""Execute the real field-observation UI helpers against a small browser harness."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


def test_session_control_is_explicit_and_invalidates_open_observation_immediately():
    engine = shutil.which("node") or shutil.which("osascript")
    if engine is None:
        pytest.skip("A JavaScript runtime is required for the dynamic session control test")
    source = SCRIPT.read_text(encoding="utf-8")
    session_helpers = source[
        source.index("const SESSION_PENDING_KEY ="):
        source.index("async function sessionCommand")
    ]
    context_helpers = source[
        source.index("function observationContext("):
        source.index("function openFieldObservation(")
    ]
    same_context = source[
        source.index("function sameFieldObservationContext("):
        source.index("function localDateTimeParts(")
    ]
    sync_context = source[
        source.index("function syncFieldObservationContext("):
        source.index("function restorePendingFieldObservation(")
    ]
    choice_listener = source[
        source.index('document.querySelector("#session-choice").addEventListener'):
        source.index('document.querySelector("#session-start").addEventListener')
    ]
    harness = r'''
const assert = {
  equal(actual, expected, message = '') { if (actual !== expected) throw new Error(message || `${actual} !== ${expected}`); },
  ok(value, message = '') { if (!value) throw new Error(message || 'expected truthy value'); },
  match(value, pattern, message = '') { if (!pattern.test(value)) throw new Error(message || `${value} does not match ${pattern}`); },
};
const clone = value => JSON.parse(JSON.stringify(value));
class Element {
  constructor() {
    this.hidden = false; this.disabled = false; this.checked = false; this.open = false;
    this.textContent = ''; this.value = ''; this.children = []; this.listeners = {};
    this.classList = {toggle() {}};
  }
  replaceChildren() { this.children = []; this.value = ''; }
  append(child) { this.children.push(child); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelectorAll(selector) { return selector === 'input, select, button' ? formControls : []; }
}
const elements = new Map();
const formControls = [new Element(), new Element(), new Element()];
const document = {
  querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  },
  createElement() { return new Element(); },
};
function text(selector, value) { document.querySelector(selector).textContent = value; }
function renderObservationLinkage() {}
function siteTimezone() { return 'Europe/Zurich'; }
function observationMessage(message) { document.querySelector('#observation-status').textContent = message; }
const storage = new Map();
const localStorage = {
  getItem(key) { return storage.get(key) || null; },
  removeItem(key) { storage.delete(key); },
};
const session = (id) => ({
  execution: {execution_id: id, status: 'completed', actual_start: null},
  acquisition_intent_id: 'ha', evidence: [], credit: null,
  historical_baseline_seconds: 0, historical_baseline_confirmed: false,
  acquired_before_seconds: 0, session_credit_seconds: 0, acquired_after_seconds: 0,
  current_acquired_seconds: 0, target_hours: null, remaining_hours: null,
});
const state = {
  acceptedMission: {mission_id: 'mission-1', decision_id: 'decision-1', acquisitionIntentId: 'ha',
    mission: {night_date: '2026-09-29'}},
  currentDecision: {decision_id: 'decision-1', night_date: '2026-09-29'},
  sessions: [], activeSessionId: null, fieldObservationSelectedExecutionId: null,
  sessionEvidenceInputExecutionId: null, fieldObservationDraftContext: null,
  fieldObservationContextInvalid: false, invalidFieldObservationContextKey: null,
};
let serverSessions = [session('session-only')];
async function fetch() { return {ok: true, json: async () => clone(serverSessions)}; }
'''
    checks = r'''
(async () => {
  const choice = document.querySelector('#session-choice');
  await reloadSessions();
  assert.equal(choice.children.length, 2);
  assert.equal(choice.children[0].value, '');
  assert.equal(choice.children[0].textContent, 'Sans session');
  assert.equal(choice.value, '');
  assert.equal(state.activeSessionId, null);
  assert.equal(state.fieldObservationSelectedExecutionId, null);

  // The sole session is linked only through the real change handler.
  choice.value = 'session-only';
  choice.listeners.change({target: choice});
  assert.equal(state.activeSessionId, 'session-only');
  assert.equal(state.fieldObservationSelectedExecutionId, 'session-only');
  assert.equal(observationContext('mission').execution_id, 'session-only');

  document.querySelector('#field-observation-dialog').open = true;
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-only',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich'});
  state.fieldObservationContextInvalid = false;
  formControls.forEach(control => { control.disabled = false; });
  choice.value = '';
  choice.listeners.change({target: choice});
  assert.equal(state.fieldObservationContextInvalid, true);
  assert.ok(formControls.every(control => control.disabled));
  assert.match(document.querySelector('#observation-status').textContent, /éditeur est bloqué/);
  assert.equal(state.fieldObservationDraftContext.execution_id, 'session-only');

  // A different explicit session selection also invalidates without rebinding.
  document.querySelector('#field-observation-dialog').open = false;
  serverSessions = [session('session-a'), session('session-b')];
  await reloadSessions();
  choice.value = 'session-a';
  choice.listeners.change({target: choice});
  document.querySelector('#field-observation-dialog').open = true;
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-a',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich'});
  state.fieldObservationContextInvalid = false;
  formControls.forEach(control => { control.disabled = false; });
  choice.value = 'session-b';
  choice.listeners.change({target: choice});
  assert.equal(state.fieldObservationContextInvalid, true);
  assert.ok(formControls.every(control => control.disabled));
  assert.equal(state.fieldObservationDraftContext.execution_id, 'session-a');

  // A refresh that removes the selected session invalidates immediately too.
  document.querySelector('#field-observation-dialog').open = false;
  choice.value = 'session-a';
  choice.listeners.change({target: choice});
  document.querySelector('#field-observation-dialog').open = true;
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-a',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich'});
  state.fieldObservationContextInvalid = false;
  formControls.forEach(control => { control.disabled = false; });
  serverSessions = [session('session-b')];
  await reloadSessions();
  assert.equal(state.activeSessionId, null);
  assert.equal(state.fieldObservationSelectedExecutionId, null);
  assert.equal(choice.value, '');
  assert.equal(state.fieldObservationContextInvalid, true);
  assert.ok(formControls.every(control => control.disabled));
  assert.equal(state.fieldObservationDraftContext.execution_id, 'session-a');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    program = harness + session_helpers + context_helpers + same_context + sync_context + choice_listener + checks
    command = [engine, "-e", program] if Path(engine).name == "node" else [engine, "-l", "JavaScript", "-e", program]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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
    if (selector === 'input, select, button') return [...numberIds, ...radioIds, ...selectIds,
      '#observation-observed-at', '#observation-submit'].map(element);
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
const state = {configuration: {site: {timezone: 'Europe/Zurich'}},
  currentDecision: {decision_id: 'decision-1', night_date: '2026-09-29'},
  acceptedMission: {decision_id: 'decision-1', mission: {night_date: '2026-09-29'}},
  sessions: [], activeSessionId: null, fieldObservationSelectedExecutionId: null,
  observationBusy: false,
  fieldObservationDraftContext: null, fieldObservationContextInvalid: false,
  invalidFieldObservationContextKey: null, conflictingFieldObservationContextKey: null};
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
  state.fieldObservationSelectedExecutionId = null;
  state.currentDecision = {decision_id: 'decision-1', night_date: '2026-09-29'};
  state.acceptedMission = {decision_id: 'decision-1', mission: {night_date: '2026-09-29'}};
  state.fieldObservationContextInvalid = false;
  state.invalidFieldObservationContextKey = null;
  state.conflictingFieldObservationContextKey = null;
  if (state.unreadableFieldObservationContextKeys instanceof Set) state.unreadableFieldObservationContextKeys.clear();
  resetFieldObservationForm();
  element('#observation-observed-at').value = '2026-09-29T22:14';
  element('#field-observation-dialog').open = true;
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: null,
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich'});
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
  assert.equal(payload.execution_id, null);
  assert.equal(payload.observed_at_utc, '2026-09-29T20:14:00.000Z');
  assert.notEqual(payload.observed_at_utc, payload.recorded_at_utc);

  // IANA conversion is deterministic in winter/summer, including fractional and historical offsets.
  assert.equal(localDateTimeToUtc('2026-07-15T22:00', 'Europe/Zurich'), '2026-07-15T20:00:00.000Z');
  assert.equal(localDateTimeToUtc('2026-01-15T22:00', 'Europe/Zurich'), '2026-01-15T21:00:00.000Z');
  assert.equal(localDateTimeToUtc('2026-07-15T12:00', 'Asia/Kathmandu'), '2026-07-15T06:15:00.000Z');
  assert.equal(localDateTimeToUtc('2026-07-15T12:00', 'Australia/Eucla'), '2026-07-15T03:15:00.000Z');
  assert.equal(localDateTimeToUtc('1985-07-15T12:00', 'Asia/Kathmandu'), '1985-07-15T06:30:00.000Z');
  let timezoneError = null;
  try { localDateTimeToUtc('2026-03-29T02:30', 'Europe/Zurich'); } catch (error) { timezoneError = error.message; }
  assert.equal(timezoneError, 'nonexistent_local_datetime');
  timezoneError = null;
  try { localDateTimeToUtc('2026-10-25T02:30', 'Europe/Zurich'); } catch (error) { timezoneError = error.message; }
  assert.equal(timezoneError, 'ambiguous_local_datetime');
  timezoneError = null;
  try { localDateTimeToUtc('2026-09-29T22:14', 'Not/A_Timezone'); } catch (error) { timezoneError = error.message; }
  assert.equal(timezoneError, 'unsupported_site_timezone');

  const nativeDateTimeFormat = Intl.DateTimeFormat;
  const expectTimezoneUnavailable = (replacement) => {
    Intl.DateTimeFormat = replacement;
    let message = null;
    try { localDateTimeToUtc('2026-09-29T22:14', 'Europe/Zurich'); } catch (error) { message = error.message; }
    assert.equal(message, 'timezone_unavailable');
  };
  try {
    expectTimezoneUnavailable(function DateTimeFormatWithoutParts() { return {}; });
    expectTimezoneUnavailable(function DateTimeFormatThrowingParts() {
      return {formatToParts() { throw new Error('runtime unavailable'); }};
    });
    expectTimezoneUnavailable(function DateTimeFormatMissingParts() {
      return {formatToParts() { return [{type: 'year', value: '2026'}]; }};
    });
  } finally {
    Intl.DateTimeFormat = nativeDateTimeFormat;
  }
  timezoneError = null;
  try { buildFieldObservationPayload(fieldObservationDraft(), '2026-09-29T20:13:00.000Z'); } catch (error) { timezoneError = error.message; }
  assert.equal(timezoneError, 'observed_at_in_future');

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

  // Merely loading a mission session does not link it to an observation.
  clearHarness();
  state.sessions = [{execution: {execution_id: 'session-a'}}];
  state.activeSessionId = 'session-a';
  assert.equal(observationContext('mission').execution_id, null);

  // Switching from session A to B preserves the frozen draft and blocks submission.
  clearHarness();
  state.sessions = [
    {execution: {execution_id: 'session-a'}},
    {execution: {execution_id: 'session-b'}},
  ];
  state.activeSessionId = 'session-a';
  state.fieldObservationSelectedExecutionId = 'session-a';
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-a',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich'});
  setQuick({cloud: 'overcast', transparency: 'poor', wind: '12'});
  state.activeSessionId = 'session-b';
  state.fieldObservationSelectedExecutionId = 'session-b';
  syncFieldObservationContext();
  assert.equal(element('#observation-clouds').value, 'overcast');
  assert.equal(element('#observation-transparency').value, 'poor');
  assert.equal(element('#observation-wind').value, '12');
  assert.equal(state.fieldObservationContextInvalid, true);
  assert.match(element('#observation-status').textContent, /éditeur est bloqué/);
  for (const control of element('#field-observation-form').querySelectorAll('input, select, button')) {
    assert.equal(control.disabled, true);
  }
  let sessionPosts = 0;
  fetch = async () => { sessionPosts += 1; return response(201, {}); };
  await submitFieldObservation(event);
  assert.equal(sessionPosts, 0);
  resetFieldObservationForm();
  element('#observation-observed-at').value = '2026-09-29T22:14';
  state.fieldObservationContextInvalid = false;
  state.fieldObservationSelectedExecutionId = 'session-b';
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-b',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich'});
  setQuick({cloud: 'clear'});
  let sessionPayload;
  fetch = async (_url, options) => { sessionPosts += 1; sessionPayload = JSON.parse(options.body); return response(201, {}); };
  await submitFieldObservation(event);
  assert.equal(sessionPosts, 1);
  assert.equal(sessionPayload.execution_id, 'session-b');
  assert.equal(sessionPayload.conditions.cloud_state, 'clear');
  assert.equal(sessionPayload.conditions.transparency, null);
  assert.equal(sessionPayload.conditions.wind_speed_kmh, null);

  // A decision switch also invalidates the open editor without rebinding or erasing it.
  clearHarness(); setQuick({cloud: 'few'});
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: null,
    night_date: '2026-09-29', source: 'decision', timezone: 'Europe/Zurich'});
  state.currentDecision = {decision_id: 'decision-2', night_date: '2026-09-30'};
  syncFieldObservationContext();
  assert.equal(state.fieldObservationContextInvalid, true);
  assert.equal(element('#observation-clouds').value, 'few');
  assert.equal(state.fieldObservationDraftContext.decision_id, 'decision-1');
  for (const control of element('#field-observation-form').querySelectorAll('input, select, button')) {
    assert.equal(control.disabled, true);
  }

  // A server-declared conflict is never reconciled into success and keeps input.
  clearHarness(); setQuick({cloud: 'overcast'});
  let conflictRequests = 0;
  fetch = async () => {
    conflictRequests += 1;
    return response(409, {detail: {code: 'field_observation_conflict'}});
  };
  await submitFieldObservation(event);
  assert.match(element('#observation-status').textContent, /Conflit/);
  assert.equal(element('#observation-clouds').value, 'overcast');
  assert.equal(storage.has(pendingObservationKey('decision-1', null)), true);
  await submitFieldObservation(event);
  assert.equal(conflictRequests, 1);
  assert.match(element('#observation-status').textContent, /bloqué par un conflit/);

  // A lookup that finds the same id with different content is also a conflict.
  clearHarness(); setQuick({cloud: 'few'});
  const pendingPayload = buildFieldObservationPayload();
  const pendingKey = pendingObservationKey('decision-1', null);
  localStorage.setItem(pendingKey, JSON.stringify({
    version: PENDING_FIELD_OBSERVATION_VERSION,
    payload: pendingPayload, snapshot: fieldObservationSnapshot(),
    observed_at_local: '2026-09-29T22:14', timezone: 'Europe/Zurich',
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
  assert.match(element('#observation-status').textContent, /formulaire est conservé mais bloqué/);
  await submitFieldObservation(event);
  assert.match(element('#observation-status').textContent, /contexte du relevé a changé/);

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

  // The implicit v1 envelope migrates to v2 and restores its local wall clock.
  clearHarness(); setQuick({cloud: 'few'});
  const legacyPayload = buildFieldObservationPayload(fieldObservationDraft(), '2026-09-29T20:20:00.000Z');
  const legacyKey = pendingObservationKey('decision-1', null);
  storage.set(legacyKey, JSON.stringify({
    payload: legacyPayload, snapshot: legacySnapshotFromObservationPayload(legacyPayload),
  }));
  resetFieldObservationForm();
  element('#observation-observed-at').value = '2026-09-29T21:00';
  restorePendingFieldObservation();
  const migrated = JSON.parse(storage.get(legacyKey));
  assert.equal(migrated.version, PENDING_FIELD_OBSERVATION_VERSION);
  assert.equal(migrated.observed_at_local, '2026-09-29T22:14');
  assert.equal(element('#observation-observed-at').value, '2026-09-29T22:14');

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
  const offlineEnvelope = JSON.parse(storage.get(pendingObservationKey('decision-1', null)));
  assert.equal(offlineEnvelope.version, PENDING_FIELD_OBSERVATION_VERSION);
  const firstOfflinePayload = JSON.parse(posted[0]);
  assert.equal(offlineEnvelope.payload.observed_at_utc, firstOfflinePayload.observed_at_utc);
  assert.equal(offlineEnvelope.payload.recorded_at_utc, firstOfflinePayload.recorded_at_utc);
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
  assert.equal(element('#observation-observed-at').value, '2026-09-29T22:14');

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
