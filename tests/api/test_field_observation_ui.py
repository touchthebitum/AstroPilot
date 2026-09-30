"""Execute the real field-observation UI helpers against a small browser harness."""

from pathlib import Path
import json
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


def javascript_engine():
    node = shutil.which("node")
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    if node:
        return node
    if bundled.exists():
        return str(bundled)
    return shutil.which("osascript")


def test_session_control_is_explicit_and_invalidates_open_observation_immediately():
    engine = javascript_engine()
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
function siteConfigurationIdentity() { return null; }
function observationMessage(message) { document.querySelector('#observation-status').textContent = message; }
function invalidateFieldObservationOperation() {}
function webLocksAvailable() { return true; }
function pendingObservationKey(decisionId, executionId) { return `${decisionId}:${executionId || 'none'}`; }
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

  // startSession-style visual selection does not bind Field Observation.
  await reloadSessions({selectId: 'session-only'});
  assert.equal(choice.value, 'session-only');
  assert.equal(state.activeSessionId, 'session-only');
  assert.equal(state.fieldObservationSelectedExecutionId, null);

  // The sole session is linked only through the real change handler.
  choice.value = 'session-only';
  choice.listeners.change({target: choice});
  assert.equal(state.activeSessionId, 'session-only');
  assert.equal(state.fieldObservationSelectedExecutionId, 'session-only');
  assert.equal(observationContext('mission').execution_id, 'session-only');
  await reloadSessions();
  assert.equal(state.fieldObservationSelectedExecutionId, 'session-only');

  document.querySelector('#field-observation-dialog').open = true;
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-only',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich', site_identity: null, mission_id: 'mission-1'});
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
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich', site_identity: null, mission_id: 'mission-1'});
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
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich', site_identity: null, mission_id: 'mission-1'});
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
    engine = javascript_engine()
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
  showModal() { this.open = true; }
  close() { this.open = false; }
  querySelectorAll(selector) {
    if (selector === '[data-observation-choice]') return [element('#observation-clouds'), element('#observation-transparency')];
    if (selector === 'input[type="number"]') return numberIds.map(element);
    if (selector === 'input[type="radio"]') return radioIds.map(element);
    if (selector === 'select') return selectIds.map(element);
    if (selector === 'input, select, button') return [...numberIds, ...radioIds, ...selectIds,
      '#observation-observed-at', '#observation-save'].map(element);
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
function text(selector, value) { element(selector).textContent = value; }
radioIds.forEach((selector, index) => { element(selector).value = ['dry', 'damp', 'dew_present'][index]; });
element('#field-observation-form');
element('.observation-advanced');
const ui = {observation: element('#field-observation-dialog')};
const storage = new Map();
const storageFailures = {get: false, set: false, remove: false};
const localStorage = {
  get length() { return storage.size; },
  key(index) { return [...storage.keys()][index] ?? null; },
  getItem(key) { if (storageFailures.get) throw new Error('get denied'); return storage.has(key) ? storage.get(key) : null; },
  setItem(key, value) { if (storageFailures.set) throw new Error('quota exceeded'); storage.set(key, value); },
  removeItem(key) { if (storageFailures.remove) throw new Error('remove denied'); storage.delete(key); },
};
let uuid = 0;
const crypto = {randomUUID: () => `observation-${++uuid}`};
let webLockRequests = 0;
const navigator = {locks: {request(name, options, callback) {
  assert.equal(name, FIELD_OBSERVATION_WEB_LOCK_NAME);
  assert.equal(options.mode, 'exclusive');
  webLockRequests += 1;
  return callback();
}}};
const state = {configuration: {site: {name: 'Site A', latitude: 47.1, longitude: 6.8, bortle: 4, timezone: 'Europe/Zurich'}},
  currentDecision: {decision_id: 'decision-1', night_date: '2026-09-29'},
  acceptedMission: {decision_id: 'decision-1', mission: {night_date: '2026-09-29'}},
  sessions: [], activeSessionId: null, fieldObservationSelectedExecutionId: null,
  observationBusy: false,
  fieldObservationDraftContext: null, fieldObservationContextInvalid: false,
  invalidFieldObservationContextKey: null, fieldObservationConflict: null, fieldObservationLock: null};
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
function assertReadRequest(options) {
  assert.ok(options === undefined || (options.signal && options.method === undefined && options.body === undefined));
}
function clearHarness() {
  storage.clear(); state.observationBusy = false; uuid = 0;
  activeFieldObservationOperation = null; fieldObservationOperationGeneration = 0;
  storageFailures.get = false; storageFailures.set = false; storageFailures.remove = false;
  state.sessions = []; state.activeSessionId = null;
  state.fieldObservationSelectedExecutionId = null;
  state.currentDecision = {decision_id: 'decision-1', night_date: '2026-09-29'};
  state.acceptedMission = {decision_id: 'decision-1', mission: {night_date: '2026-09-29'}};
  state.configuration.site = {name: 'Site A', latitude: 47.1, longitude: 6.8, bortle: 4, timezone: 'Europe/Zurich'};
  state.fieldObservationContextInvalid = false;
  state.invalidFieldObservationContextKey = null;
  state.fieldObservationConflict = null;
  state.fieldObservationLock = null;
  if (state.unreadableFieldObservationContextKeys instanceof Set) state.unreadableFieldObservationContextKeys.clear();
  resetFieldObservationForm();
  element('#observation-observed-at').value = '2026-09-29T22:14';
  element('#field-observation-dialog').open = true;
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: null,
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich',
    site_identity: siteConfigurationIdentity(), mission_id: null});
  element('#observation-status').textContent = '';
  updateFieldObservationSubmitState();
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
  assert.equal(localDateTimeToUtc('0001-01-01T00:00', 'UTC'), '0001-01-01T00:00:00.000Z');
  assert.equal(localDateTimeToUtc('9999-12-31T23:59', 'UTC'), '9999-12-31T23:59:00.000Z');
  assert.equal(formatDateTimeLocalInZone(new Date('0001-01-01T00:00:00.000Z'), 'UTC'), '0001-01-01T00:00');
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
    expectTimezoneUnavailable(function DateTimeFormatReturningHour24() {
      return {formatToParts() { return [
        {type: 'year', value: '2026'}, {type: 'month', value: '09'}, {type: 'day', value: '29'},
        {type: 'hour', value: '24'}, {type: 'minute', value: '00'}, {type: 'second', value: '00'},
      ]; }};
    });
  } finally {
    Intl.DateTimeFormat = nativeDateTimeFormat;
  }

  // Opening through the real handler always shows a blocked diagnostic when site-time conversion is unavailable.
  const assertBlockedOpening = (pattern) => {
    assert.equal(element('#field-observation-dialog').open, true);
    assert.equal(element('#observation-observed-at').value, '');
    assert.equal(state.fieldObservationContextInvalid, true);
    assert.match(element('#observation-status').textContent, pattern);
    for (const control of element('#field-observation-form').querySelectorAll('input, select, button')) {
      assert.equal(control.disabled, true);
    }
    assert.equal(element('#observation-save').disabled, true);
    element('#field-observation-dialog').close();
  };
  const nativeIntl = Intl;
  try {
    Intl = undefined;
    openFieldObservation('mission');
    assertBlockedOpening(/indisponible sur cet appareil/);
  } finally {
    Intl = nativeIntl;
  }
  try {
    Intl.DateTimeFormat = function DateTimeFormatWithoutParts() { return {}; };
    openFieldObservation('mission');
    assertBlockedOpening(/indisponible sur cet appareil/);
    Intl.DateTimeFormat = function DateTimeFormatThrowingParts() {
      return {formatToParts() { throw new Error('runtime unavailable'); }};
    };
    openFieldObservation('mission');
    assertBlockedOpening(/indisponible sur cet appareil/);
    Intl.DateTimeFormat = function DateTimeFormatMissingParts() {
      return {formatToParts() { return [{type: 'year', value: '2026'}]; }};
    };
    openFieldObservation('mission');
    assertBlockedOpening(/indisponible sur cet appareil/);
  } finally {
    Intl.DateTimeFormat = nativeDateTimeFormat;
  }
  state.configuration.site.timezone = 'Not/A_Timezone';
  openFieldObservation('mission');
  assertBlockedOpening(/fuseau du site configuré n’est pas reconnu/);
  state.configuration.site.timezone = 'Europe/Zurich';
  clearHarness(); setQuick({cloud: 'clear'});
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
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich',
    site_identity: siteConfigurationIdentity(), mission_id: null});
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

  // Site identity is part of the frozen context; identical refreshes are stable.
  clearHarness(); setQuick({cloud: 'clear'});
  syncFieldObservationContext();
  assert.equal(state.fieldObservationContextInvalid, false);
  state.configuration.site = {...state.configuration.site};
  syncFieldObservationContext();
  assert.equal(state.fieldObservationContextInvalid, false);
  state.configuration.site = {...state.configuration.site, latitude: 46.2, longitude: 7.1};
  syncFieldObservationContext();
  assert.equal(state.fieldObservationContextInvalid, true);

  // A timezone mutation invalidates immediately as well.
  clearHarness(); setQuick({cloud: 'clear'});
  state.configuration.site = {...state.configuration.site, timezone: 'Europe/Paris'};
  syncFieldObservationContext();
  assert.equal(state.fieldObservationContextInvalid, true);
  let sessionPosts = 0;
  fetch = async () => { sessionPosts += 1; return response(201, {}); };
  await submitFieldObservation(event);
  assert.equal(sessionPosts, 0);
  resetFieldObservationForm();
  element('#observation-observed-at').value = '2026-09-29T22:14';
  state.configuration.site = {name: 'Site A', latitude: 47.1, longitude: 6.8, bortle: 4, timezone: 'Europe/Zurich'};
  state.sessions = [{execution: {execution_id: 'session-a'}}, {execution: {execution_id: 'session-b'}}];
  state.activeSessionId = 'session-b';
  state.fieldObservationContextInvalid = false;
  state.fieldObservationSelectedExecutionId = 'session-b';
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-b',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich',
    site_identity: siteConfigurationIdentity(), mission_id: null});
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
    night_date: '2026-09-29', source: 'decision', timezone: 'Europe/Zurich',
    site_identity: siteConfigurationIdentity(), mission_id: null});
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
  assert.equal(element('#observation-save').disabled, true);
  const originalConflictKey = pendingObservationKey('decision-1', null);
  const originalConflictPending = storage.get(originalConflictKey);
  const originalConflictId = JSON.parse(originalConflictPending).payload.observation_id;
  assert.equal(storage.has(originalConflictKey), true);
  assert.equal(state.fieldObservationConflict.key, originalConflictKey);
  assert.equal(state.fieldObservationConflict.pending.payload.observation_id, originalConflictId);
  await submitFieldObservation(event);
  assert.equal(conflictRequests, 1);
  assert.match(element('#observation-status').textContent, /doit être résolu avant tout nouvel envoi/);

  // The persisted global conflict survives a full page-state reset.
  const persistedConflictLock = storage.get(FIELD_OBSERVATION_LOCK_KEY);
  state.fieldObservationLock = null;
  state.fieldObservationConflict = null;
  assert.equal(restoreFieldObservationLock(), true);
  assert.equal(state.fieldObservationLock.status, 'conflict');
  assert.equal(state.fieldObservationLock.pending.payload.observation_id, originalConflictId);
  assert.equal(storage.get(FIELD_OBSERVATION_LOCK_KEY), persistedConflictLock);

  // Closing, changing session and reopening cannot bypass the page-wide conflict lock.
  element('#field-observation-dialog').close();
  state.sessions = [{execution: {execution_id: 'session-b'}}];
  state.activeSessionId = 'session-b';
  state.fieldObservationSelectedExecutionId = 'session-b';
  openFieldObservation('mission');
  assert.equal(state.fieldObservationDraftContext.execution_id, 'session-b');
  assert.equal(element('#observation-save').disabled, true);
  assert.match(element('#observation-status').textContent, /doit être résolu avant tout nouvel envoi/);
  setQuick({cloud: 'clear'});
  await submitFieldObservation(event);
  assert.equal(conflictRequests, 1);
  assert.equal(uuid, 1);
  assert.equal(storage.get(originalConflictKey), originalConflictPending);
  assert.equal(JSON.parse(storage.get(originalConflictKey)).payload.observation_id, originalConflictId);

  // Reconciliation reads only the original UUID and clears the lock on an exact canonical match.
  fetch = (url, options) => {
    assertReadRequest(options);
    assert.match(url, new RegExp(originalConflictId));
    return response(200, storedProjection(JSON.parse(originalConflictPending).payload));
  };
  await reconcileFieldObservationLock();
  assert.equal(state.fieldObservationLock, null);
  assert.equal(storage.has(FIELD_OBSERVATION_LOCK_KEY), false);
  assert.equal(storage.has(originalConflictKey), false);

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
    assertReadRequest(options);
    return response(200, conflictingStored);
  };
  await submitFieldObservation(event);
  assert.match(element('#observation-status').textContent, /Conflit/);
  assert.equal(element('#observation-clouds').value, 'few');
  fetch = (_url, options) => {
    assertReadRequest(options);
    return response(404, {});
  };
  await reconcileFieldObservationLock();
  assert.equal(state.fieldObservationLock.status, 'conflict');
  assert.equal(element('#observation-save').disabled, true);

  // A 404 preserves the original pending and remains blocked across close/open.
  clearHarness(); setQuick({cloud: 'few'});
  const staleKey = pendingObservationKey('decision-1', null);
  fetch = async (_url, options) => {
    assert.ok(options);
    return response(404, {detail: {code: 'field_observation_context_not_found'}});
  };
  await submitFieldObservation(event);
  const staleEnvelope = storage.get(staleKey);
  assert.equal(storage.has(staleKey), true);
  assert.equal(state.fieldObservationLock.status, 'invalid');
  assert.equal(element('#observation-clouds').value, 'few');
  assert.match(element('#observation-status').textContent, /introuvable ou périmée/);
  assert.match(element('#observation-status').textContent, /UUID sont conservés/);
  for (const control of element('#field-observation-form').querySelectorAll('input, select, button')) {
    assert.equal(control.disabled, true);
  }
  assert.equal(element('#observation-save').disabled, true);
  await submitFieldObservation(event);
  assert.match(element('#observation-status').textContent, /Actualiser le contexte/);
  assert.equal(element('#observation-save').disabled, true);
  element('#field-observation-dialog').close();
  openFieldObservation('mission');
  assert.equal(element('#observation-save').disabled, true);
  assert.equal(storage.get(staleKey), staleEnvelope);

  // Canonical refresh leaves the invalid lock in place while the context is absent.
  fetch = (url, options) => {
    assertReadRequest(options);
    if (url.includes('/field-observations/')) return response(404, {});
    return response(200, null);
  };
  await refreshInvalidFieldObservationContext();
  assert.equal(state.fieldObservationLock.status, 'invalid');
  assert.equal(element('#observation-save').disabled, true);

  // Once the canonical mission confirms the exact decision, refresh downgrades to the original pending.
  fetch = (url, options) => {
    assertReadRequest(options);
    if (url.includes('/field-observations/')) return response(404, {});
    assert.equal(url, '/v1/accepted-mission/current');
    return response(200, {status: 'accepted', decision_id: 'decision-1', mission_id: null});
  };
  await refreshInvalidFieldObservationContext();
  assert.equal(state.fieldObservationLock.status, 'pending');
  assert.equal(state.fieldObservationContextInvalid, false);
  assert.equal(element('#observation-save').disabled, false);
  assert.equal(JSON.parse(storage.get(staleKey)).payload.observation_id,
    state.fieldObservationLock.pending.payload.observation_id);

  // A 404 never depends on deleting the authoritative envelope.
  clearHarness(); setQuick({cloud: 'few'});
  fetch = async (_url, options) => {
    assert.ok(options); storageFailures.remove = true;
    return response(404, {detail: {code: 'field_observation_context_not_found'}});
  };
  await submitFieldObservation(event);
  const invalidated = JSON.parse(storage.get(staleKey));
  assert.equal(invalidated.payload.observation_id, state.fieldObservationLock.pending.payload.observation_id);
  assert.equal(state.fieldObservationLock.status, 'invalid');
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
  assert.equal(storage.has(pendingObservationKey('decision-1', null)), true);
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
  await restorePendingFieldObservationInventory();
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
    if (options?.method === 'POST') {
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

  // Editing after a committed/lost response never replaces the original UUID or issues another POST.
  clearHarness(); setQuick({cloud: 'few'});
  const changedPosts = [];
  fetch = async (url, options) => {
    if (options?.method !== 'POST') return response(404, {});
    changedPosts.push(JSON.parse(options.body));
    throw new TypeError('network timeout');
  };
  await submitFieldObservation(event);
  const originalUncertain = clone(state.fieldObservationLock.pending);
  setQuick({cloud: 'clear', transparency: 'fair'});
  await submitFieldObservation(event);
  assert.equal(changedPosts.length, 1);
  assert.equal(uuid, 1);
  assert.equal(changedPosts[0].conditions.cloud_state, 'few');
  assert.equal(state.fieldObservationLock.pending.payload.observation_id,
    originalUncertain.payload.observation_id);
  assert.equal(state.fieldObservationLock.pending.snapshot, originalUncertain.snapshot);
  assert.match(element('#observation-status').textContent, /modifications sont conservées séparément/);

  // Every lock transition is disabled and defensively ignored while a POST is in flight.
  clearHarness(); setQuick({cloud: 'few'});
  fetch = (_url, options) => {
    assert.ok(options);
    assert.equal(state.observationBusy, true);
    assert.equal(element('#observation-reconcile').disabled, true, 'reconcile busy');
    assert.equal(element('#observation-refresh-context').disabled, true, 'refresh busy');
    assert.equal(element('#observation-abandon-pending').disabled, true, 'abandon busy');
    const busyLock = state.fieldObservationLock;
    abandonFieldObservationLock();
    assert.equal(state.fieldObservationLock.generation, busyLock.generation);
    return response(201, {created: true});
  };
  await submitFieldObservation(event);
  assert.equal(state.fieldObservationLock, null);
  assert.ok(webLockRequests > 0);

  // A stale reconciliation response cannot mutate a newer lock generation.
  clearHarness(); setQuick({cloud: 'few'});
  fetch = (_url, options) => options?.method === 'POST' ? Promise.reject(new TypeError('offline')) : response(404, {});
  await submitFieldObservation(event);
  const oldLock = clone(state.fieldObservationLock);
  const replacementPending = clone(oldLock.pending);
  replacementPending.payload.observation_id = 'observation-replacement';
  replacementPending.snapshot = snapshotFromObservationPayload(
    replacementPending.payload, replacementPending.observed_at_local, replacementPending.timezone,
  );
  const replacementLock = {...oldLock, generation: fieldObservationLockGeneration(replacementPending),
    pending: replacementPending};
  fetch = () => {
    storage.set(oldLock.key, JSON.stringify(replacementPending));
    storage.set(FIELD_OBSERVATION_LOCK_KEY, JSON.stringify(storedFieldObservationLockValue(replacementLock)));
    handleFieldObservationStorageEvent({key: FIELD_OBSERVATION_LOCK_KEY,
      newValue: JSON.stringify(storedFieldObservationLockValue(replacementLock))});
    return response(200, storedProjection(oldLock.pending.payload));
  };
  await reconcileFieldObservationLock();
  assert.equal(state.fieldObservationLock.generation, replacementLock.generation);
  assert.equal(storage.has(FIELD_OBSERVATION_LOCK_KEY), true, 'replacement persisted');

  // Two simulated tabs share storage: B adopts A, cannot overwrite it, and A cannot delete B's successor.
  clearHarness(); setQuick({cloud: 'few'});
  const tabAPending = {
    version: PENDING_FIELD_OBSERVATION_VERSION,
    payload: buildFieldObservationPayload(), snapshot: fieldObservationSnapshot(),
    observed_at_local: '2026-09-29T22:14', timezone: 'Europe/Zurich',
  };
  const tabAKey = pendingObservationKey('decision-1', null);
  const tabALock = {version: FIELD_OBSERVATION_LOCK_VERSION,
    generation: fieldObservationLockGeneration(tabAPending), status: 'pending', key: tabAKey,
    pending: tabAPending, context: clone(state.fieldObservationDraftContext)};
  assert.equal(acquireFieldObservationLockUnlocked(tabALock), true, 'tab A acquisition');
  const tabAState = state.fieldObservationLock;
  state.fieldObservationLock = null;
  handleFieldObservationStorageEvent({key: FIELD_OBSERVATION_LOCK_KEY,
    newValue: JSON.stringify(storedFieldObservationLockValue(tabALock))});
  assert.equal(state.fieldObservationLock.generation, tabALock.generation);
  const tabBPending = clone(tabAPending);
  tabBPending.payload.observation_id = 'observation-tab-b';
  tabBPending.snapshot = snapshotFromObservationPayload(
    tabBPending.payload, tabBPending.observed_at_local, tabBPending.timezone,
  );
  const tabBLock = {...tabALock, generation: fieldObservationLockGeneration(tabBPending), pending: tabBPending};
  assert.equal(acquireFieldObservationLockUnlocked(tabBLock), false);
  storage.set(tabAKey, JSON.stringify(tabBPending));
  storage.set(FIELD_OBSERVATION_LOCK_KEY, JSON.stringify(storedFieldObservationLockValue(tabBLock)));
  state.fieldObservationLock = tabAState;
  assert.equal(clearFieldObservationLockUnlocked(tabAState), false);
  assert.equal(state.fieldObservationLock.generation, tabBLock.generation);
  assert.equal(storage.has(FIELD_OBSERVATION_LOCK_KEY), true, 'tab B lock preserved');

  // Startup inventory reconstructs one orphan and blocks explicitly instead of choosing among several.
  clearHarness();
  storage.set(tabAKey, JSON.stringify(tabAPending));
  assert.equal(await restorePendingFieldObservationInventory(), true, 'single inventory');
  assert.equal(state.fieldObservationLock.generation, tabALock.generation);
  storage.delete(FIELD_OBSERVATION_LOCK_KEY);
  state.fieldObservationLock = null;
  const blockedCandidatePending = clone(tabAPending);
  blockedCandidatePending.payload.decision_id = 'decision-2';
  blockedCandidatePending.payload.observation_id = 'observation-blocked-candidate';
  blockedCandidatePending.snapshot = snapshotFromObservationPayload(
    blockedCandidatePending.payload, blockedCandidatePending.observed_at_local, blockedCandidatePending.timezone,
  );
  const blockedCandidateContext = {...clone(state.fieldObservationDraftContext), decision_id: 'decision-2'};
  const blockedCandidateLock = {version: FIELD_OBSERVATION_LOCK_VERSION,
    generation: fieldObservationLockGeneration(blockedCandidatePending), status: 'pending',
    key: pendingObservationKey('decision-2', null), pending: blockedCandidatePending,
    context: blockedCandidateContext};
  assert.equal(acquireFieldObservationLockUnlocked(blockedCandidateLock), false);
  assert.equal(state.fieldObservationLock.generation, tabALock.generation);
  storage.delete(FIELD_OBSERVATION_LOCK_KEY);
  state.fieldObservationLock = null;
  const secondPending = clone(tabAPending);
  secondPending.payload.decision_id = 'decision-2';
  secondPending.payload.observation_id = 'observation-second';
  secondPending.snapshot = snapshotFromObservationPayload(
    secondPending.payload, secondPending.observed_at_local, secondPending.timezone,
  );
  storage.set(pendingObservationKey('decision-2', null), JSON.stringify(secondPending));
  assert.equal(await restorePendingFieldObservationInventory(), true, 'multiple inventory');
  assert.equal(state.fieldObservationLock.status, 'multiple_pending');
  assert.equal(state.fieldObservationLock.entries.length, 2);
  assert.match(fieldObservationLockMessage(), /observations locales non résolues/);

  // An external localStorage.clear() cannot silently remove the in-memory reconciliation lock.
  state.fieldObservationLock = replacementLock;
  storage.set(replacementLock.key, JSON.stringify(replacementLock.pending));
  storage.set(FIELD_OBSERVATION_LOCK_KEY, JSON.stringify(storedFieldObservationLockValue(replacementLock)));
  const originalUncertainAfterRaces = clone(replacementLock.pending);
  storage.clear();
  handleFieldObservationStorageEvent({key: null, newValue: null});
  assert.equal(state.fieldObservationLock.persistence_missing, true);
  await submitFieldObservation(event);
  assert.equal(changedPosts.length, 1);
  assert.match(element('#observation-status').textContent, /a disparu ou est illisible/);

  // The original in-memory envelope remains reconcilable even after external storage deletion.
  fetch = (url, options) => {
    assertReadRequest(options);
    assert.match(url, new RegExp(originalUncertainAfterRaces.payload.observation_id));
    return response(200, storedProjection(originalUncertainAfterRaces.payload));
  };
  await reconcileFieldObservationEntry(replacementLock.key);
  assert.equal(state.fieldObservationLock, null);

  // Edits made while the request is in flight survive the successful response.
  clearHarness(); setQuick({cloud: 'clear'});
  let resolvePost;
  fetch = async (_url, options) => {
    assert.ok(options);
    return new Promise(resolve => { resolvePost = resolve; });
  };
  const submitting = submitFieldObservation(event);
  while (!resolvePost) await Promise.resolve();
  setQuick({cloud: 'overcast'});
  resolvePost(response(201, {created: true}));
  await submitting;
  assert.equal(element('#observation-clouds').value, 'overcast');
  assert.match(element('#observation-status').textContent, /modifications en cours sont conservées/);

  // A decision change during a successful request remains disabled after finally.
  clearHarness(); setQuick({cloud: 'clear'});
  let resolveStalePost;
  fetch = (_url, options) => {
    assert.ok(options);
    return new Promise(resolve => { resolveStalePost = resolve; });
  };
  const staleSuccess = submitFieldObservation(event);
  while (!resolveStalePost) await Promise.resolve();
  state.acceptedMission = {decision_id: 'decision-2', mission: {night_date: '2026-09-30'}};
  syncFieldObservationContext();
  resolveStalePost(response(201, {created: true}));
  await staleSuccess;
  assert.equal(state.fieldObservationContextInvalid, true);
  for (const control of element('#field-observation-form').querySelectorAll('input, select, button')) {
    assert.equal(control.disabled, true);
  }
  assert.equal(element('#observation-save').disabled, true);

  // A session change during a rejected request also remains disabled after lookup and finally.
  clearHarness();
  state.sessions = [{execution: {execution_id: 'session-a'}}, {execution: {execution_id: 'session-b'}}];
  state.activeSessionId = 'session-a';
  state.fieldObservationSelectedExecutionId = 'session-a';
  state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: 'session-a',
    night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich',
    site_identity: siteConfigurationIdentity(), mission_id: null});
  setQuick({cloud: 'few'});
  let rejectStalePost;
  fetch = (_url, options) => options
    ? new Promise((_resolve, reject) => { rejectStalePost = reject; })
    : response(404, {detail: {code: 'field_observation_not_found'}});
  const staleFailure = submitFieldObservation(event);
  while (!rejectStalePost) await Promise.resolve();
  state.activeSessionId = 'session-b';
  state.fieldObservationSelectedExecutionId = 'session-b';
  syncFieldObservationContext();
  rejectStalePost(new TypeError('network timeout'));
  await staleFailure;
  assert.equal(state.fieldObservationContextInvalid, true);
  for (const control of element('#field-observation-form').querySelectorAll('input, select, button')) {
    assert.equal(control.disabled, true);
  }
  assert.equal(element('#observation-save').disabled, true);

  // An uncertain request is rehydrated from local storage after a page/form reset.
  clearHarness(); setQuick({cloud: 'partly_cloudy', transparency: 'poor', wind: '4.2'});
  fetch = async (url, options) => options?.method === 'POST' ? Promise.reject(new TypeError('offline')) : response(404, {});
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
        synchronous_checks = synchronous_checks.replace("await reconcileFieldObservationLock();", "reconcileFieldObservationLock();")
        synchronous_checks = synchronous_checks.replace("await refreshInvalidFieldObservationContext();", "refreshInvalidFieldObservationContext();")
        synchronous_checks = synchronous_checks.replace("fetch = async ", "fetch = ")
        synchronous_checks = synchronous_checks.replace(
            "  let resolvePost;\n  fetch = (_url, options) => {\n    assert.ok(options);\n    return new Promise(resolve => { resolvePost = resolve; });\n  };\n  const submitting = submitFieldObservation(event);\n  setQuick({cloud: 'overcast'});\n  resolvePost(response(201, {created: true}));\n  await submitting;",
            "  fetch = (_url, options) => {\n    assert.ok(options);\n    setQuick({cloud: 'overcast'});\n    return response(201, {created: true});\n  };\n  submitFieldObservation(event);",
        )
        synchronous_checks = synchronous_checks.replace(
            "  let resolveStalePost;\n  fetch = (_url, options) => {\n    assert.ok(options);\n    return new Promise(resolve => { resolveStalePost = resolve; });\n  };\n  const staleSuccess = submitFieldObservation(event);\n  state.acceptedMission = {decision_id: 'decision-2', mission: {night_date: '2026-09-30'}};\n  syncFieldObservationContext();\n  resolveStalePost(response(201, {created: true}));\n  await staleSuccess;",
            "  fetch = (_url, options) => {\n    assert.ok(options);\n    state.acceptedMission = {decision_id: 'decision-2', mission: {night_date: '2026-09-30'}};\n    syncFieldObservationContext();\n    return response(201, {created: true});\n  };\n  submitFieldObservation(event);",
        )
        synchronous_checks = synchronous_checks.replace(
            "  let rejectStalePost;\n  fetch = (_url, options) => options\n    ? new Promise((_resolve, reject) => { rejectStalePost = reject; })\n    : response(404, {detail: {code: 'field_observation_not_found'}});\n  const staleFailure = submitFieldObservation(event);\n  state.activeSessionId = 'session-b';\n  state.fieldObservationSelectedExecutionId = 'session-b';\n  syncFieldObservationContext();\n  rejectStalePost(new TypeError('network timeout'));\n  await staleFailure;",
            "  fetch = (_url, options) => {\n    if (!options) return response(404, {detail: {code: 'field_observation_not_found'}});\n    state.activeSessionId = 'session-b';\n    state.fieldObservationSelectedExecutionId = 'session-b';\n    syncFieldObservationContext();\n    throw new TypeError('network timeout');\n  };\n  submitFieldObservation(event);",
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


def test_field_observation_two_context_web_locks_inventory_and_clear():
    """Two isolated JS globals share one origin/storage and a controlled Web Locks queue."""
    engine = javascript_engine()
    if engine is None or Path(engine).name != "node":
        pytest.skip("Node.js is required for the isolated multi-context harness")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[
        source.index("const OBSERVATION_CHOICES ="):
        source.index("const PENDING_ACCEPTANCE_STORAGE_KEY =")
    ]
    program = r'''
const vm = require('vm');
const assert = require('assert').strict;
const helpers = HELPERS_SOURCE;
const shared = new Map();
const contexts = [];
let lockTail = Promise.resolve();
const controlledLocks = {request(_name, options, callback) {
  assert.equal(options.mode, 'exclusive');
  const run = lockTail.then(() => {
    if (options.signal?.aborted) throw new Error('AbortError');
    return callback();
  });
  lockTail = run.catch(() => {});
  return run;
}};
class Element {
  constructor(id = '') { this.id = id; this.value = ''; this.checked = false; this.disabled = false;
    this.hidden = false; this.textContent = ''; this.open = true; this.children = []; this.listeners = {};
    this.classList = {toggle() {}}; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelectorAll(selector) {
    if (selector === '[data-observation-choice]') return [this.owner('#observation-clouds'), this.owner('#observation-transparency')];
    if (selector === 'input[type="number"]') return numberIds.map(this.owner);
    if (selector === 'input[type="radio"]') return radioIds.map(this.owner);
    if (selector === 'select') return selectIds.map(this.owner);
    if (selector === 'input, select, button') return [...numberIds, ...radioIds, ...selectIds,
      '#observation-observed-at', '#observation-save'].map(this.owner);
    return [];
  }
  replaceChildren() { this.children = []; }
  append(...children) { this.children.push(...children); }
  set selectedIndex(value) { if (value === 0) this.value = ''; }
}
const numberIds = ['#observation-wind', '#observation-temperature', '#observation-humidity',
  '#observation-attempted-frames', '#observation-usable-frames', '#observation-hfr', '#observation-guiding'];
const selectIds = ['#observation-clouds', '#observation-transparency', '#observation-seeing',
  '#observation-moon-halo', '#observation-stop-reason', '#observation-hfr-unit'];
const radioIds = ['dry', 'damp', 'dew_present'].map(value => `#surface-${value}`);
function makeContext(name, locks = controlledLocks) {
  const elements = new Map();
  const element = selector => {
    if (!elements.has(selector)) { const item = new Element(selector); item.owner = element; elements.set(selector, item); }
    return elements.get(selector);
  };
  const document = {querySelector(selector) {
    const choice = selector.match(/^\[data-observation-choice="([^"]+)"\]$/);
    if (choice) return element(`#observation-${choice[1]}`);
    if (selector === 'input[name="observation-surface"]:checked') return radioIds.map(element).find(item => item.checked) || null;
    const radio = selector.match(/^input\[name="observation-surface"\]\[value="([^"]+)"\]$/);
    return radio ? element(`#surface-${radio[1]}`) : element(selector);
  }, createElement() { const item = new Element(); item.owner = element; return item; }};
  let uuid = 0;
      const sandbox = {console, structuredClone, URL, TextEncoder, Intl, Date, JSON, Map, Set, Object, Array, AbortController,
    String, Number, Boolean, RegExp, Error, TypeError, Promise, encodeURIComponent,
    document, window: {confirm: () => true}, navigator: locks ? {locks} : {},
    crypto: {randomUUID: () => `${name}-uuid-${++uuid}`}, posts: [], uuidCount: () => uuid};
  sandbox.state = {configuration: {site: {name: 'Site A', latitude: 47.1, longitude: 6.8, bortle: 4, timezone: 'Europe/Zurich'}},
    currentDecision: {decision_id: 'decision-1', night_date: '2026-09-29'},
    acceptedMission: {decision_id: 'decision-1', mission: {night_date: '2026-09-29'}},
    sessions: [], activeSessionId: null, fieldObservationSelectedExecutionId: null, observationBusy: false,
    fieldObservationDraftContext: null, fieldObservationContextInvalid: false,
    invalidFieldObservationContextKey: null, fieldObservationConflict: null, fieldObservationLock: null};
  sandbox.currentSession = () => null;
  sandbox.text = (selector, value) => { element(selector).textContent = value; };
  sandbox.observationMessage = (message) => { element('#observation-status').textContent = message; };
  sandbox.sessionHttpError = async response => { const error = new Error('request_refused'); error.status = response.status; return error; };
  sandbox.ui = {observation: element('#field-observation-dialog')};
      sandbox.fetch = async (url, options) => {
            if (options?.method === 'POST') {
              sandbox.posts.push(JSON.parse(options.body));
              if (sandbox.postGate) await sandbox.postGate;
              return {ok: true, status: 201, json: async () => ({})};
            }
    const id = decodeURIComponent(url.split('/').pop());
    const stored = sandbox.canonical?.[id];
    return stored ? {ok: true, status: 200, json: async () => stored}
      : {ok: false, status: 404, json: async () => ({})};
  };
  sandbox.localStorage = {get length() { return shared.size; }, key(index) { return [...shared.keys()][index] ?? null; },
    getItem(key) { return shared.has(key) ? shared.get(key) : null; },
    setItem(key, value) { const oldValue = shared.get(key) ?? null; shared.set(key, value); dispatch(sandbox, {key, oldValue, newValue: value}); },
    removeItem(key) { const oldValue = shared.get(key) ?? null; shared.delete(key); dispatch(sandbox, {key, oldValue, newValue: null}); }};
  const context = vm.createContext(sandbox); contexts.push({sandbox, context});
  vm.runInContext(helpers, context);
  vm.runInContext(`
    document.querySelector('#observation-observed-at').value = '2026-09-29T22:14';
    document.querySelector('#observation-clouds').value = 'few';
    state.fieldObservationDraftContext = Object.freeze({decision_id: 'decision-1', execution_id: null,
      night_date: '2026-09-29', source: 'mission', timezone: 'Europe/Zurich',
      site_identity: siteConfigurationIdentity(), mission_id: null});
    updateFieldObservationSubmitState();`, context);
  return {sandbox, context};
}
function dispatch(source, event) {
  for (const item of contexts) if (item.sandbox !== source) {
    item.sandbox.__storageEvent = event;
    vm.runInContext('handleFieldObservationStorageEvent(__storageEvent)', item.context);
  }
}
const run = (tab, code) => vm.runInContext(code, tab.context);
const projection = payload => ({...structuredClone(payload),
  quality: {confidence: payload.confidence, flags: payload.quality_flags}});
(async () => {
  // Two distinct states contend concurrently; the controlled exclusive queue permits one POST only.
  const a = makeContext('a'); const b = makeContext('b');
  await Promise.all([run(a, 'submitFieldObservation({preventDefault(){}})'), run(b, 'submitFieldObservation({preventDefault(){}})')]);
      assert.equal(a.sandbox.posts.length + b.sandbox.posts.length, 1,
        JSON.stringify({a: run(a, 'state.fieldObservationLock'), b: run(b, 'state.fieldObservationLock'),
          am: run(a, 'document.querySelector("#observation-status").textContent'),
          bm: run(b, 'document.querySelector("#observation-status").textContent'), keys: [...shared.keys()]}));
      assert.equal([...shared.keys()].filter(key => key.startsWith('astropilot.pendingFieldObservation.')).length, 0);

  // Missing or throwing Web Locks fails before UUID creation and before POST.
  shared.clear(); contexts.length = 0;
      const noLocks = makeContext('none', null);
      assert.equal(run(noLocks, 'webLocksAvailable()'), false);
      await run(noLocks, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(noLocks.sandbox.uuidCount(), 0); assert.equal(noLocks.sandbox.posts.length, 0);
      const denied = makeContext('denied', {request() { throw new Error('denied'); }});
      assert.equal(run(denied, 'webLocksAvailable()'), true);
  await run(denied, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(denied.sandbox.uuidCount(), 0); assert.equal(denied.sandbox.posts.length, 0);

  // Build two valid orphan entries, then resolve exactly one and abandon exactly the other.
  shared.clear(); contexts.length = 0; const tab = makeContext('inventory');
  const first = run(tab, `(() => { const payload = buildFieldObservationPayload(); return {key: pendingObservationKey('decision-1', null),
    pending: {version: PENDING_FIELD_OBSERVATION_VERSION, payload, snapshot: fieldObservationSnapshot(),
      observed_at_local: '2026-09-29T22:14', timezone: 'Europe/Zurich'}}; })()`);
  const second = structuredClone(first); second.pending.payload.decision_id = 'decision-2';
  second.pending.payload.observation_id = 'inventory-uuid-2';
      second.key = run(tab, `pendingObservationKey('decision-2', null)`);
      tab.sandbox.__second = second.pending;
      second.pending.snapshot = run(tab, `snapshotFromObservationPayload(__second.payload, __second.observed_at_local, __second.timezone)`);

      // A restored pending is read-only without Web Locks and can never reach POST.
      shared.clear(); contexts.length = 0;
      shared.set(first.key, JSON.stringify(first.pending));
      const restoredNoLocks = makeContext('restored-no-locks', null);
      await run(restoredNoLocks, 'restorePendingFieldObservationInventory()');
      await run(restoredNoLocks, 'restorePendingFieldObservation(); submitFieldObservation({preventDefault(){}})');
      assert.equal(restoredNoLocks.sandbox.posts.length, 0);
      assert.equal(shared.get(first.key), JSON.stringify(first.pending));

      // Two tabs retrying the exact same pending serialize GET/POST and produce one POST.
      shared.clear(); contexts.length = 0;
      shared.set(first.key, JSON.stringify(first.pending));
      const lockContext = run(tab, `recoveredFieldObservationContext(__second || ${JSON.stringify(first.pending)})`);
      const firstLock = {version: 2, generation: `lock-${first.pending.payload.observation_id}`,
        status: 'pending', key: first.key, pending: first.pending,
        context: {...lockContext, decision_id: first.pending.payload.decision_id}};
      shared.set('astropilot.fieldObservationLock', JSON.stringify(firstLock));
      const retryA = makeContext('retry-a'); const retryB = makeContext('retry-b');
      await run(retryA, '(async () => { await restorePendingFieldObservationInventory(); restorePendingFieldObservation(); })()');
      await run(retryB, '(async () => { await restorePendingFieldObservationInventory(); restorePendingFieldObservation(); })()');
      await Promise.all([run(retryA, 'submitFieldObservation({preventDefault(){}})'),
        run(retryB, 'submitFieldObservation({preventDefault(){}})')]);
      assert.equal(retryA.sandbox.posts.length + retryB.sandbox.posts.length, 1);

      // Publication retains the origin-wide lock; a concurrent abandon cannot delete its pending.
      shared.clear(); contexts.length = 0;
      shared.set(first.key, JSON.stringify(first.pending));
      shared.set('astropilot.fieldObservationLock', JSON.stringify(firstLock));
      const publishing = makeContext('publishing'); const abandoning = makeContext('abandoning');
      await run(publishing, '(async () => { await restorePendingFieldObservationInventory(); restorePendingFieldObservation(); })()');
      await run(abandoning, '(async () => { await restorePendingFieldObservationInventory(); restorePendingFieldObservation(); })()');
      let releasePost;
      publishing.sandbox.postGate = new Promise(resolve => { releasePost = resolve; });
      const publication = run(publishing, 'submitFieldObservation({preventDefault(){}})');
      while (publishing.sandbox.posts.length === 0) await Promise.resolve();
      const abandon = run(abandoning, `abandonFieldObservationEntry(${JSON.stringify(first.key)})`);
      await Promise.resolve();
      assert.equal(shared.has(first.key), true, 'abandon must wait behind publication');
      releasePost();
      await Promise.all([publication, abandon]);
      assert.equal(shared.has(first.key), false);

      // Startup never erases a valid global lock when its pending is absent or divergent.
      shared.clear(); contexts.length = 0;
      const lockOnlyRaw = JSON.stringify(firstLock);
      shared.set('astropilot.fieldObservationLock', lockOnlyRaw);
      const lockOnly = makeContext('lock-only');
      await run(lockOnly, 'restorePendingFieldObservationInventory()');
      assert.equal(run(lockOnly, 'state.fieldObservationLock.status'), 'inconsistent_persistence');
      assert.equal(shared.get('astropilot.fieldObservationLock'), lockOnlyRaw);
      shared.set(second.key, JSON.stringify(second.pending));
      await run(lockOnly, 'restorePendingFieldObservationInventory()');
      assert.equal(run(lockOnly, 'state.fieldObservationLock.status'), 'inconsistent_persistence');
      assert.equal(run(lockOnly, 'state.fieldObservationLock.entries.length'), 2);
      assert.equal(shared.get('astropilot.fieldObservationLock'), lockOnlyRaw);

      // An externally deleted pending is diagnosed fail-closed and the lock payload survives.
      shared.clear(); shared.set(first.key, JSON.stringify(first.pending));
      shared.set('astropilot.fieldObservationLock', lockOnlyRaw);
      await run(lockOnly, 'restorePendingFieldObservationInventory()');
      shared.delete(first.key);
      await run(lockOnly, `(async () => {
        handleFieldObservationStorageEvent({key: ${JSON.stringify(first.key)}, newValue: null});
        await restorePendingFieldObservationInventory();
      })()`);
      assert.equal(run(lockOnly, 'state.fieldObservationLock.status'), 'inconsistent_persistence');
      assert.equal(run(lockOnly, 'state.fieldObservationLock.entries[0].pending.payload.observation_id'),
        first.pending.payload.observation_id);

      // Legacy pending migration is a real v2 write under Web Locks, with or without a v1 lock.
      const legacyPending = {payload: first.pending.payload,
        snapshot: run(lockOnly, `legacySnapshotFromObservationPayload(${JSON.stringify(first.pending.payload)})`)};
      shared.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(legacyPending));
      const legacy = makeContext('legacy');
      await run(legacy, 'restorePendingFieldObservationInventory()');
      assert.equal(JSON.parse(shared.get(first.key)).version, 2);
      assert.equal(JSON.parse(shared.get('astropilot.fieldObservationLock')).version, 2);
      const stablePending = shared.get(first.key); const stableLock = shared.get('astropilot.fieldObservationLock');
      const legacyReload = makeContext('legacy-reload');
      await run(legacyReload, 'restorePendingFieldObservationInventory()');
      assert.equal(shared.get(first.key), stablePending); assert.equal(shared.get('astropilot.fieldObservationLock'), stableLock);
      shared.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(legacyPending));
      shared.set('astropilot.fieldObservationLock', JSON.stringify({...firstLock, version: 1,
        pending: legacyPending, generation: undefined}));
      const legacyLock = makeContext('legacy-lock');
      await run(legacyLock, 'restorePendingFieldObservationInventory()');
      assert.equal(JSON.parse(shared.get(first.key)).version, 2);
      assert.equal(JSON.parse(shared.get('astropilot.fieldObservationLock')).version, 2);
      shared.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(legacyPending));
      const legacyNoLocks = makeContext('legacy-no-locks', null);
      await run(legacyNoLocks, 'restorePendingFieldObservationInventory()');
      assert.equal(run(legacyNoLocks, 'state.fieldObservationLock.status'), 'migration_requires_web_locks');
      assert.equal(shared.get(first.key), JSON.stringify(legacyPending));

      // Waiting lock requests are abortable on close/context invalidation and cannot publish later.
      shared.clear(); contexts.length = 0;
      let releaseBlocker;
      const blocker = controlledLocks.request('blocker', {mode: 'exclusive'},
        () => new Promise(resolve => { releaseBlocker = resolve; }));
      await Promise.resolve();
      const waiting = makeContext('waiting');
      const waitingSubmit = run(waiting, 'submitFieldObservation({preventDefault(){}})');
      run(waiting, 'invalidateFieldObservationOperation()');
      releaseBlocker(); await blocker; await waitingSubmit;
      assert.equal(waiting.sandbox.posts.length, 0);
      assert.equal([...shared.keys()].filter(key => key.startsWith('astropilot.pendingFieldObservation.')).length, 0);
      let releaseContextBlocker;
      const contextBlocker = controlledLocks.request('blocker', {mode: 'exclusive'},
        () => new Promise(resolve => { releaseContextBlocker = resolve; }));
      await Promise.resolve();
      const contextSubmit = run(waiting, 'submitFieldObservation({preventDefault(){}})');
      run(waiting, `state.acceptedMission = {decision_id: 'changed', mission: {night_date: '2026-09-30'}};
        syncFieldObservationContext()`);
      releaseContextBlocker(); await contextBlocker; await contextSubmit;
      assert.equal(waiting.sandbox.posts.length, 0);

      // bfcache restore re-inventories storage under Web Locks before mutations resume.
      shared.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(first.pending));
      shared.set('astropilot.fieldObservationLock', lockOnlyRaw);
      const cached = makeContext('cached');
      await run(cached, 'restorePendingFieldObservationInventory()');
      shared.delete(first.key); shared.set(second.key, JSON.stringify(second.pending));
      await run(cached, 'handleFieldObservationPageShow({persisted: true})');
      assert.equal(run(cached, 'state.fieldObservationLock.status'), 'inconsistent_persistence');
      assert.equal(run(cached, 'state.fieldObservationInventoryReady'), true);

      shared.clear(); contexts.length = 0; const inventoryTab = makeContext('inventory-final');
      Object.assign(tab, inventoryTab);
      shared.set(first.key, JSON.stringify(first.pending)); shared.set(second.key, JSON.stringify(second.pending));
  await run(tab, 'restorePendingFieldObservationInventory()');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'multiple_pending');
  assert.equal(run(tab, 'state.fieldObservationLock.entries.length'), 2);
  const metadata = run(tab, 'state.fieldObservationLock.entries.map(e => [e.key, e.pending.payload.decision_id, e.pending.payload.execution_id, e.pending.payload.observation_id, e.status, e.pending.payload.observed_at_utc, e.pending.payload.recorded_at_utc])');
  assert.equal(metadata.length, 2); assert.ok(metadata.every(row => row.length === 7));
  tab.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
  await run(tab, `reconcileFieldObservationEntry(${JSON.stringify(first.key)})`);
  assert.equal(shared.has(first.key), false); assert.equal(shared.has(second.key), true);
  assert.equal(run(tab, 'state.fieldObservationLock.key'), second.key);
  const postsBefore = tab.sandbox.posts.length;
  await run(tab, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(tab.sandbox.posts.length, postsBefore);
  await run(tab, `abandonFieldObservationEntry(${JSON.stringify(second.key)})`);
  assert.equal(run(tab, 'state.fieldObservationLock'), null);

  // Corruption alone and beside a valid pending is retained with a structured reason.
  const badKey = 'astropilot.pendingFieldObservation.decision:bad.decision-only';
  shared.set(badKey, '{broken'); await run(tab, 'restorePendingFieldObservationInventory()');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'corrupt_pending');
  assert.equal(run(tab, 'state.fieldObservationLock.entries.length'), 0);
  await run(tab, `removeCorruptFieldObservationEntry(${JSON.stringify(badKey)})`);
  assert.equal(run(tab, 'state.fieldObservationLock'), null);
  shared.set(first.key, JSON.stringify(first.pending)); shared.set(badKey, '{broken');
  await run(tab, 'restorePendingFieldObservationInventory()');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'corrupt_pending');
  assert.equal(run(tab, 'state.fieldObservationLock.corruptions[0].reason'), 'invalid_json');
  await run(tab, `removeCorruptFieldObservationEntry(${JSON.stringify(badKey)})`);
  assert.equal(shared.has(badKey), false); assert.equal(shared.has(first.key), true);

  // clear() is handled first for multiple, simple and busy reconciliation state.
  shared.set(second.key, JSON.stringify(second.pending));
  await run(tab, 'restorePendingFieldObservationInventory()');
  run(tab, 'beginFieldObservationOperation("reconcile_entry", state.fieldObservationLock.entries[0])');
  shared.clear(); run(tab, 'handleFieldObservationStorageEvent({key: null, newValue: null})');
  assert.equal(run(tab, 'state.observationBusy'), false);
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'persistence_missing');
  assert.equal(run(tab, 'state.fieldObservationLock.entries.length'), 2);
  shared.set(first.key, JSON.stringify(first.pending));
  await run(tab, 'restorePendingFieldObservationInventory()');
  run(tab, 'beginFieldObservationOperation("reconcile", state.fieldObservationLock)');
  shared.clear(); run(tab, 'handleFieldObservationStorageEvent({key: null, newValue: null})');
  assert.equal(run(tab, 'state.observationBusy'), false);
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'persistence_missing');
  assert.equal(run(tab, 'state.fieldObservationLock.persistence_missing'), true);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''.replace("HELPERS_SOURCE", json.dumps(helpers))
    result = subprocess.run([engine, "-e", program], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
