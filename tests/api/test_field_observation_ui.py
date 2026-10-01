"""Execute the real field-observation UI helpers against a small browser harness."""

from pathlib import Path
import json
import shutil
import subprocess

import pytest


RECOVERY_IDB_HARNESS = r'''

// Small asynchronous IndexedDB simulator: requests precede transaction commit.
// Its map is independent of localStorage and is shared by fresh VM contexts.
function recoveryIndexedDB(records) {
  return {open() {
    const request = {};
    Promise.resolve().then(() => {
      request.result = {createObjectStore() {}, close() {}, transaction(_store, mode) {
        const transaction = {abort() { transaction.onabort?.(); }, objectStore() {
          return {get(key) { const operation = {};
            Promise.resolve().then(() => {
              operation.result = records.has(key) ? JSON.parse(JSON.stringify(records.get(key))) : undefined;
              operation.onsuccess?.();
              Promise.resolve().then(() => transaction.oncomplete?.());
            }); return operation;
          }, put(value, key) { const operation = {};
            Promise.resolve().then(() => {
              if (records.failWrite) { transaction.onerror?.(); return; }
              records.set(key, JSON.parse(JSON.stringify(value)));
              operation.onsuccess?.();
              Promise.resolve().then(() => transaction.oncomplete?.());
            }); return operation;
          }};
        }}; return transaction;
      }};
      request.onsuccess?.();
    }); return request;
  }};
}
'''


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
function renderSavedFieldObservations() {}
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
    helpers += "\nloadSavedFieldObservations = async () => {}; renderSavedFieldObservations = () => {};\n"
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
const crypto = {subtle: require("crypto").webcrypto.subtle, randomUUID: () => `observation-${++uuid}`};
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
  storage.clear(); recoveryRecords.clear(); state.observationBusy = false; uuid = 0;
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
    harness = RECOVERY_IDB_HARNESS + '\nconst recoveryRecords = new Map(); const indexedDB = recoveryIndexedDB(recoveryRecords);\n' + harness
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
  assert.equal(state.recentFieldObservationConfirmations[0].observation_id, firstOfflinePayload.observation_id);
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
  recoveryRecords.clear(); // New independent fixture after the orphan inventory scenario.
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
  await reconcileFieldObservationEntry(fieldObservationEntryId(replacementLock));
  assert.equal(state.recentFieldObservationConfirmations[0].observation_id, originalUncertainAfterRaces.payload.observation_id);
  assert.equal(state.fieldObservationLock, null);

  // Edits made while the request is in flight survive the successful response.
  clearHarness(); setQuick({cloud: 'clear'});
  let resolvePost;
  fetch = async (_url, options) => {
    assert.ok(options);
    return new Promise(resolve => { resolvePost = resolve; });
  };
  const submitting = submitFieldObservation(event);
  while (!resolvePost) await new Promise(resolve => setImmediate(resolve));
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
  while (!resolveStalePost) await new Promise(resolve => setImmediate(resolve));
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
  while (!rejectStalePost) await new Promise(resolve => setImmediate(resolve));
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
        command = [engine, "-"]
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
    result = subprocess.run(command, input=program if Path(engine).name == "node" else None,
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def _field_observation_multicontext_program():
    """Controlled simulator, not a browser: separate globals, locks, and event tasks."""
    engine = javascript_engine()
    if engine is None or Path(engine).name != "node":
        pytest.skip("Node.js is required for the isolated multi-context harness")
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[
        source.index("const OBSERVATION_CHOICES ="):
        source.index("const PENDING_ACCEPTANCE_STORAGE_KEY =")
    ]
    helpers += "\nloadSavedFieldObservations = async () => {}; renderSavedFieldObservations = () => {};\n"
    program = r'''
const vm = require('vm');
const assert = require('assert').strict;
const helpers = HELPERS_SOURCE;
const shared = new Map();
const recoveryRecords = new Map();
// The recent context pointer is a convenience, separate from recovery artifacts.
const recoveryStorageSize = () => [...shared.keys()].filter(key => key !== 'astropilot.recent-observation-context.v1').length;
RECOVERY_IDB_SOURCE
const contexts = [];
// Controlled simulator of separate JS contexts, not a real browser. Delivery is
// a separate task: tests may hold, duplicate and reorder the storage queue.
const storageEvents = [];
function dispatch(source, event) {
  if (event.key !== null && event.oldValue === event.newValue) return;
  for (const item of contexts) if (item.sandbox !== source) storageEvents.push({item, event});
}
async function deliverStorage({reverse = false, duplicate = false} = {}) {
  const batch = storageEvents.splice(0);
  if (reverse) batch.reverse();
  for (const {item, event} of batch) {
    if (!contexts.includes(item)) continue;
    await new Promise(resolve => setImmediate(resolve));
    item.sandbox.__storageEvent = event;
    vm.runInContext('handleFieldObservationStorageEvent(__storageEvent)', item.context);
    if (duplicate) vm.runInContext('handleFieldObservationStorageEvent(__storageEvent)', item.context);
  }
}
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
    String, Number, Boolean, RegExp, Error, TypeError, Promise, encodeURIComponent, setTimeout, clearTimeout,
    TextEncoder, document, indexedDB: recoveryIndexedDB(recoveryRecords), window: {confirm: () => true}, navigator: locks ? {locks} : {},
    crypto: {subtle: require("crypto").webcrypto.subtle, randomUUID: () => `${name}-uuid-${++uuid}`}, posts: [], uuidCount: () => uuid};
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
  sandbox.networkTimers = new Map();
  sandbox.setTimeout = (callback, milliseconds) => {
    if (!sandbox.manualDeadlines) return setTimeout(callback, milliseconds);
    assert.equal(milliseconds, 15000);
    const token = {}; sandbox.networkTimers.set(token, callback); return token;
  };
  sandbox.clearTimeout = token => {
    if (sandbox.networkTimers.has(token)) sandbox.networkTimers.delete(token);
    else clearTimeout(token);
  };
  sandbox.localStorage = {get length() { return shared.size; }, key(index) { return [...shared.keys()][index] ?? null; },
    getItem(key) { return shared.has(key) ? shared.get(key) : null; },
    setItem(key, value) { const oldValue = shared.get(key) ?? null; shared.set(key, value); dispatch(sandbox, {key, oldValue, newValue: value}); },
    removeItem(key) { const oldValue = shared.get(key) ?? null; shared.delete(key); dispatch(sandbox, {key, oldValue, newValue: null}); },
    clear() { if (!shared.size) return; shared.clear(); dispatch(sandbox, {key: null, oldValue: null, newValue: null}); }};
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
const run = (tab, code) => vm.runInContext(code, tab.context);
const drainMicrotasks = async () => { for (let i = 0; i < 10; i++) await new Promise(resolve => setImmediate(resolve)); };
// Native crypto work may finish after any fixed number of event-loop turns.
const waitForRequest = async (started) => {
  const deadline = Date.now() + 5000;
  while (!started()) {
    assert.ok(Date.now() < deadline, 'reconciliation request did not start');
    await new Promise(resolve => setTimeout(resolve, 1));
  }
};
const expireNetwork = async tab => {
  await drainMicrotasks();
  assert.equal(tab.sandbox.networkTimers.size, 1);
  [...tab.sandbox.networkTimers.values()][0]();
};
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
  const savedTab = a.sandbox.posts.length ? a : b;
  assert.equal(run(savedTab, 'state.recentFieldObservationConfirmations[0].observation_id'), savedTab.sandbox.posts[0].observation_id);
  assert.ok(storageEvents.length > 0); // Both acquisitions completed before any events.
  const queued = storageEvents.length;
  const unchanged = a.sandbox.localStorage.getItem('unchanged');
  a.sandbox.localStorage.removeItem('unchanged');
  assert.equal(storageEvents.length, queued); assert.equal(unchanged, null);
  a.sandbox.localStorage.setItem('unchanged', 'x');
  const withChange = storageEvents.length;
  a.sandbox.localStorage.setItem('unchanged', 'x');
  assert.equal(storageEvents.length, withChange);
  await deliverStorage({reverse: true, duplicate: true});

  // Missing or throwing Web Locks fails before UUID creation and before POST.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0;
      const noLocks = makeContext('none', null);
      assert.equal(run(noLocks, 'webLocksAvailable()'), false);
      await run(noLocks, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(noLocks.sandbox.uuidCount(), 0); assert.equal(noLocks.sandbox.posts.length, 0);
      const denied = makeContext('denied', {request() { throw new Error('denied'); }});
      assert.equal(run(denied, 'webLocksAvailable()'), true);
  await run(denied, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(denied.sandbox.uuidCount(), 0); assert.equal(denied.sandbox.posts.length, 0);

  // Build two valid orphan entries, then resolve exactly one and abandon exactly the other.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; const tab = makeContext('inventory');
  const first = run(tab, `(() => { const payload = buildFieldObservationPayload(); return {key: pendingObservationKey('decision-1', null),
    pending: {version: PENDING_FIELD_OBSERVATION_VERSION, payload, snapshot: fieldObservationSnapshot(),
      observed_at_local: '2026-09-29T22:14', timezone: 'Europe/Zurich'}}; })()`);
  const second = structuredClone(first); second.pending.payload.decision_id = 'decision-2';
  second.pending.payload.observation_id = 'inventory-uuid-2';
      second.key = run(tab, `pendingObservationKey('decision-2', null)`);
      tab.sandbox.__second = second.pending;
      second.pending.snapshot = run(tab, `snapshotFromObservationPayload(__second.payload, __second.observed_at_local, __second.timezone)`);

      // A restored pending is read-only without Web Locks and can never reach POST.
      shared.clear(); recoveryRecords.clear(); contexts.length = 0;
      shared.set(first.key, JSON.stringify(first.pending));
      const restoredNoLocks = makeContext('restored-no-locks', null);
      await run(restoredNoLocks, 'restorePendingFieldObservationInventory()');
      await run(restoredNoLocks, 'restorePendingFieldObservation(); submitFieldObservation({preventDefault(){}})');
      assert.equal(restoredNoLocks.sandbox.posts.length, 0);
      assert.equal(shared.get(first.key), JSON.stringify(first.pending));

      // Two tabs retrying the exact same pending serialize GET/POST and produce one POST.
      shared.clear(); recoveryRecords.clear(); contexts.length = 0;
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
      shared.clear(); recoveryRecords.clear(); contexts.length = 0;
      shared.set(first.key, JSON.stringify(first.pending));
      shared.set('astropilot.fieldObservationLock', JSON.stringify(firstLock));
      const publishing = makeContext('publishing'); const abandoning = makeContext('abandoning');
      await run(publishing, '(async () => { await restorePendingFieldObservationInventory(); restorePendingFieldObservation(); })()');
      await run(abandoning, '(async () => { await restorePendingFieldObservationInventory(); restorePendingFieldObservation(); })()');
      let releasePost;
      publishing.sandbox.postGate = new Promise(resolve => { releasePost = resolve; });
      const publication = run(publishing, 'submitFieldObservation({preventDefault(){}})');
      while (publishing.sandbox.posts.length === 0) await new Promise(resolve => setImmediate(resolve));
      const abandon = run(abandoning, `abandonFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.key ? state.fieldObservationLock : state.fieldObservationLock.entries.find(e => e.key === ${JSON.stringify(first.key)})))`);
      await Promise.resolve();
      assert.equal(shared.has(first.key), true, 'abandon must wait behind publication');
      releasePost();
      await Promise.all([publication, abandon]);
      assert.equal(shared.has(first.key), false);

      // Startup never erases a valid global lock when its pending is absent or divergent.
      shared.clear(); recoveryRecords.clear(); contexts.length = 0;
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
      shared.clear(); recoveryRecords.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(legacyPending));
      const legacy = makeContext('legacy');
      await run(legacy, 'restorePendingFieldObservationInventory()');
      assert.equal(JSON.parse(shared.get(first.key)).version, 2);
      assert.equal(JSON.parse(shared.get('astropilot.fieldObservationLock')).version, 2);
      const stablePending = shared.get(first.key); const stableLock = shared.get('astropilot.fieldObservationLock');
      const legacyReload = makeContext('legacy-reload');
      await run(legacyReload, 'restorePendingFieldObservationInventory()');
      assert.equal(shared.get(first.key), stablePending); assert.equal(shared.get('astropilot.fieldObservationLock'), stableLock);
      shared.clear(); recoveryRecords.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(legacyPending));
      shared.set('astropilot.fieldObservationLock', JSON.stringify({...firstLock, version: 1,
        pending: legacyPending, generation: undefined}));
      const legacyLock = makeContext('legacy-lock');
      await run(legacyLock, 'restorePendingFieldObservationInventory()');
      assert.equal(JSON.parse(shared.get(first.key)).version, 2);
      assert.equal(JSON.parse(shared.get('astropilot.fieldObservationLock')).version, 2);
      shared.clear(); recoveryRecords.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(legacyPending));
      const legacyNoLocks = makeContext('legacy-no-locks', null);
      await run(legacyNoLocks, 'restorePendingFieldObservationInventory()');
      assert.equal(run(legacyNoLocks, 'state.fieldObservationLock.status'), 'migration_requires_web_locks');
      assert.equal(shared.get(first.key), JSON.stringify(legacyPending));

      // Waiting lock requests are abortable on close/context invalidation and cannot publish later.
      shared.clear(); recoveryRecords.clear(); contexts.length = 0;
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
      shared.clear(); recoveryRecords.clear(); contexts.length = 0; shared.set(first.key, JSON.stringify(first.pending));
      shared.set('astropilot.fieldObservationLock', lockOnlyRaw);
      const cached = makeContext('cached');
      await run(cached, 'restorePendingFieldObservationInventory()');
      shared.delete(first.key); shared.set(second.key, JSON.stringify(second.pending));
      await run(cached, 'handleFieldObservationPageShow({persisted: true})');
      assert.equal(run(cached, 'state.fieldObservationLock.status'), 'inconsistent_persistence');
      assert.equal(run(cached, 'state.fieldObservationInventoryReady'), true);

      shared.clear(); recoveryRecords.clear(); contexts.length = 0; const inventoryTab = makeContext('inventory-final');
      Object.assign(tab, inventoryTab);
      shared.set(first.key, JSON.stringify(first.pending)); shared.set(second.key, JSON.stringify(second.pending));
  await run(tab, 'restorePendingFieldObservationInventory()');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'multiple_pending');
  assert.equal(run(tab, 'state.fieldObservationLock.entries.length'), 2);
  const metadata = run(tab, 'state.fieldObservationLock.entries.map(e => [e.key, e.pending.payload.decision_id, e.pending.payload.execution_id, e.pending.payload.observation_id, e.status, e.pending.payload.observed_at_utc, e.pending.payload.recorded_at_utc])');
  assert.equal(metadata.length, 2); assert.ok(metadata.every(row => row.length === 7));
  tab.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
  await run(tab, `reconcileFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.key ? state.fieldObservationLock : state.fieldObservationLock.entries.find(e => e.key === ${JSON.stringify(first.key)})))`);
  assert.equal(shared.has(first.key), false); assert.equal(shared.has(second.key), true);
  assert.equal(run(tab, 'state.fieldObservationLock.key'), second.key);
  const postsBefore = tab.sandbox.posts.length;
  await run(tab, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(tab.sandbox.posts.length, postsBefore);
  await run(tab, `abandonFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.key ? state.fieldObservationLock : state.fieldObservationLock.entries.find(e => e.key === ${JSON.stringify(second.key)})))`);
  assert.equal(run(tab, 'state.fieldObservationLock'), null);

  // Corruption alone and beside a valid pending is retained with a structured reason.
  const badKey = 'astropilot.pendingFieldObservation.decision:bad.decision-only';
  shared.set(badKey, '{broken'); await run(tab, 'restorePendingFieldObservationInventory()');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'corrupt_pending');
  assert.equal(run(tab, 'state.fieldObservationLock.entries.length'), 0);
  await run(tab, `removeCorruptFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.corruptions.find(e => e.key === ${JSON.stringify(badKey)})))`);
  assert.equal(run(tab, 'state.fieldObservationLock'), null);
  const newOrphan = structuredClone(first.pending); newOrphan.payload.observation_id = 'new-orphan';
  shared.set(first.key, JSON.stringify(newOrphan)); shared.set(badKey, '{new-broken');
  await run(tab, 'restorePendingFieldObservationInventory()');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'corrupt_pending');
  assert.equal(run(tab, 'state.fieldObservationLock.corruptions[0].reason'), 'invalid_json');
  await run(tab, `removeCorruptFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.corruptions.find(e => e.key === ${JSON.stringify(badKey)})))`);
  assert.equal(shared.has(badKey), false); assert.equal(shared.has(first.key), true);

  // clear() is handled first for multiple, simple and busy reconciliation state.
  const newSecond = structuredClone(second.pending); newSecond.payload.observation_id = 'new-second';
  shared.set(second.key, JSON.stringify(newSecond));
  await run(tab, 'restorePendingFieldObservationInventory()');
  run(tab, 'beginFieldObservationOperation("reconcile_entry", state.fieldObservationLock.entries[0])');
  shared.clear(); run(tab, 'handleFieldObservationStorageEvent({key: null, newValue: null})');
  assert.equal(run(tab, 'state.observationBusy'), false);
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'persistence_missing');
  assert.equal(run(tab, 'state.fieldObservationLock.entries.length'), 3);
  shared.set(first.key, JSON.stringify(first.pending));
  await run(tab, 'restorePendingFieldObservationInventory()');
  run(tab, 'beginFieldObservationOperation("reconcile", state.fieldObservationLock)');
  shared.clear(); run(tab, 'handleFieldObservationStorageEvent({key: null, newValue: null})');
  assert.equal(run(tab, 'state.observationBusy'), false);
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'persistence_missing');
  assert.equal(run(tab, 'state.fieldObservationLock.persistence_missing'), true);

  // Aggregate original is never reduced by deleted/divergent inventory, even on reload.
  for (const diverge of [false, true]) {
    shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
    const owner = makeContext('aggregate'); const peer = makeContext('aggregate-peer');
    shared.set(first.key, JSON.stringify(first.pending)); shared.set(second.key, JSON.stringify(second.pending));
    await run(owner, 'restorePendingFieldObservationInventory()');
    await run(peer, 'restorePendingFieldObservationInventory()');
    const originalRaw = shared.get('astropilot.fieldObservationLock');
    const changed = structuredClone(second.pending); changed.payload.observation_id = 'divergent-second';
    if (diverge) owner.sandbox.localStorage.setItem(second.key, JSON.stringify(changed));
    else owner.sandbox.localStorage.removeItem(second.key);
    // Crash/reload and independent inventory before notification delivery.
    const reload = makeContext('aggregate-reload');
    await run(reload, 'restorePendingFieldObservationInventory()');
    assert.equal(run(reload, 'state.fieldObservationLock.status'), 'inconsistent_persistence');
    assert.equal(shared.get('astropilot.fieldObservationLock'), originalRaw);
    assert.equal(run(reload, 'state.fieldObservationLock.entries.length'), diverge ? 4 : 3);
    const globals = run(reload, 'state.fieldObservationLock.entries.filter(e => e.origin === "global_lock")');
    assert.deepEqual(Array.from(globals, e => e.pending.payload.observation_id).sort(),
      [first.pending.payload.observation_id, second.pending.payload.observation_id].sort());
    await run(reload, 'submitFieldObservation({preventDefault(){}})');
    assert.equal(reload.sandbox.posts.length, 0);
    await deliverStorage({reverse: true, duplicate: true}); await lockTail;
    assert.equal(shared.get('astropilot.fieldObservationLock'), originalRaw);
    await run(reload, 'restorePendingFieldObservationInventory()');
    const target = run(reload, `fieldObservationEntryId(state.fieldObservationLock.entries.find(e =>
      e.origin === 'global_lock' && e.key === ${JSON.stringify(second.key)}))`);
    reload.sandbox.canonical = {[second.pending.payload.observation_id]: projection(second.pending.payload)};
    await run(reload, `reconcileFieldObservationEntry(${JSON.stringify(target)})`);
    assert.equal(shared.get(first.key), JSON.stringify(first.pending));
    assert.equal(shared.get(second.key) ?? null, diverge ? JSON.stringify(changed) : null);
    assert.equal(JSON.parse(shared.get('astropilot.fieldObservationLock')).entries?.some(e =>
      e.pending.payload.observation_id === second.pending.payload.observation_id) || false, false);
  }

  // Same key, two generations/UUIDs: independent UI buttons, exact GET, 2 -> 1 -> 0.
  for (const resolveGlobalFirst of [true, false]) {
    shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
    const exact = makeContext('same-key');
    const divergent = structuredClone(first.pending); divergent.payload.observation_id = 'same-key-B';
    shared.set(first.key, JSON.stringify(divergent));
    shared.set('astropilot.fieldObservationLock', JSON.stringify(firstLock));
    await run(exact, 'restorePendingFieldObservationInventory();');
    run(exact, 'renderFieldObservationPendingDiagnostics()');
    const rows = run(exact, 'document.querySelector("#observation-pending-diagnostics").children');
    assert.equal(rows.length, 2);
    const ids = run(exact, 'state.fieldObservationLock.entries.map(fieldObservationEntryId)');
    assert.notEqual(ids[0], ids[1]);
    const gets = [];
    exact.sandbox.fetch = async url => { gets.push(decodeURIComponent(url.split('/').pop()));
      return {ok: true, status: 200, json: async () => projection(divergent.payload)}; };
    if (resolveGlobalFirst) {
      await rows[0].children[1].children[1].listeners.click(); // Abandon global A only.
      assert.equal(shared.get(first.key), JSON.stringify(divergent));
      assert.equal(run(exact, 'state.fieldObservationLock.pending.payload.observation_id'), 'same-key-B');
      // Old inventory button must still identify B exactly after promotion to simple lock.
      await rows[1].children[1].children[0].listeners.click();
      assert.deepEqual(gets, ['same-key-B']); assert.equal(recoveryStorageSize(), 0);
    } else {
      await rows[1].children[1].children[0].listeners.click();
      assert.deepEqual(gets, ['same-key-B']);
      assert.equal(shared.has(first.key), false);
      assert.equal(JSON.parse(shared.get('astropilot.fieldObservationLock')).pending.payload.observation_id,
        first.pending.payload.observation_id);
      await run(exact, `abandonFieldObservationEntry(${JSON.stringify(ids[0])})`);
      assert.equal(recoveryStorageSize(), 0);
    }
  }

  // Stale buttons cannot resolve a replaced envelope or corruption, even with same key.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
  const stale = makeContext('stale-entry');
  shared.set(first.key, JSON.stringify(first.pending)); shared.set(second.key, JSON.stringify(second.pending));
  await run(stale, 'restorePendingFieldObservationInventory()');
  const staleId = run(stale, 'fieldObservationEntryId(state.fieldObservationLock.entries[0])');
  const replacement = structuredClone(first.pending); replacement.payload.observation_id = 'replacement';
  shared.set(first.key, JSON.stringify(replacement));
  await run(stale, `abandonFieldObservationEntry(${JSON.stringify(staleId)})`);
  assert.equal(shared.get(first.key), JSON.stringify(replacement));
  assert.equal(run(stale, 'state.fieldObservationLock.status'), 'inconsistent_persistence');


  // Exact same UUID/key with different payload is still a different inventory artifact.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
  const changedPayload = makeContext('changed-payload');
  shared.set(first.key, JSON.stringify(first.pending)); shared.set(second.key, JSON.stringify(second.pending));
  await run(changedPayload, 'restorePendingFieldObservationInventory()');
  const payloadId = run(changedPayload, 'fieldObservationEntryId(state.fieldObservationLock.entries[0])');
  const mutated = structuredClone(first.pending);
  mutated.payload.recorded_at_utc = new Date(Date.parse(mutated.payload.recorded_at_utc) + 1000).toISOString();
  assert.equal(run(changedPayload, `validPendingFieldObservation(${JSON.stringify(mutated)}, recoveredFieldObservationContext(${JSON.stringify(mutated)}))`), true);
  shared.set(first.key, JSON.stringify(mutated));
  let unexpectedGets = 0;
  changedPayload.sandbox.fetch = async () => { unexpectedGets++; throw new Error('must not GET stale entry'); };
  await run(changedPayload, `reconcileFieldObservationEntry(${JSON.stringify(payloadId)})`);
  assert.equal(unexpectedGets, 0); assert.equal(shared.get(first.key), JSON.stringify(mutated));

  // Corruption identities include raw source; replacing that raw cannot be deleted by an old button.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
  const corrupt = makeContext('corrupt-target');
  shared.set(first.key, JSON.stringify(first.pending)); shared.set(badKey, '{old');
  await run(corrupt, 'restorePendingFieldObservationInventory()');
  const corruptRaw = shared.get('astropilot.fieldObservationLock');
  const corruptId = run(corrupt, 'fieldObservationEntryId(state.fieldObservationLock.corruptions[0])');
  shared.set(badKey, '{new');
  await run(corrupt, `removeCorruptFieldObservationEntry(${JSON.stringify(corruptId)})`);
  assert.equal(shared.get(badKey), '{new'); assert.equal(shared.get('astropilot.fieldObservationLock'), corruptRaw);
  assert.equal(run(corrupt, 'state.fieldObservationLock.status'), 'inconsistent_persistence');
  const globalCorruptId = run(corrupt, 'fieldObservationEntryId(state.fieldObservationLock.corruptions.find(e => e.origin === "global_lock"))');
  await run(corrupt, `removeCorruptFieldObservationEntry(${JSON.stringify(globalCorruptId)})`);
  assert.equal(shared.get(badKey), '{new'); assert.equal(shared.get(first.key), JSON.stringify(first.pending));
  const inventoryCorruptId = run(corrupt, 'fieldObservationEntryId(state.fieldObservationLock.corruptions.find(e => e.origin !== "global_lock"))');
  await run(corrupt, `removeCorruptFieldObservationEntry(${JSON.stringify(inventoryCorruptId)})`);
  assert.equal(shared.has(badKey), false); assert.equal(shared.has(first.key), true);

  // Three distinct pending entries reconstruct N -> 2 -> 1 -> 0 without dropping a sibling.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
  const many = makeContext('many');
  const third = structuredClone(second); third.key = run(many, `pendingObservationKey('decision-3', null)`);
  third.pending.payload.decision_id = 'decision-3'; third.pending.payload.observation_id = 'third-uuid';
  third.pending.snapshot = run(many, `snapshotFromObservationPayload(${JSON.stringify(third.pending.payload)}, '2026-09-29T22:14', 'Europe/Zurich')`);
  for (const entry of [first, second, third]) shared.set(entry.key, JSON.stringify(entry.pending));
  await run(many, 'restorePendingFieldObservationInventory()');
  for (const size of [3, 2, 1]) {
    assert.equal(run(many, '(state.fieldObservationLock.entries || [state.fieldObservationLock]).length'), size);
    await run(many, 'abandonFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.entries?.[0] || state.fieldObservationLock))');
  }
  assert.equal(recoveryStorageSize(), 0);

  // Non-cooperative hung fetch: controlled deadlines release the real lock queue.
  // Repeat before POST, after POST, and during confirmation. Late replies cannot clean storage.
  for (const phase of ['before', 'body', 'post', 'confirmation']) {
    shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
    const hung = makeContext(`hung-${phase}`); hung.sandbox.manualDeadlines = true;
    shared.set(first.key, JSON.stringify(first.pending));
    shared.set('astropilot.fieldObservationLock', JSON.stringify(firstLock));
    await run(hung, 'restorePendingFieldObservationInventory(); restorePendingFieldObservation()');
    let lateResolve; const attempts = [];
    hung.sandbox.fetch = (url, options) => {
      attempts.push(options?.method || 'GET');
      if (phase === 'body') return Promise.resolve({ok: true, status: 200, json: () => new Promise(resolve => { lateResolve = resolve; })});
      if (phase === 'before' || options?.method === 'POST' && phase === 'post'
          || phase === 'confirmation' && attempts.length === 3) {
        return new Promise(resolve => { lateResolve = resolve; });
      }
      if (options?.method === 'POST') return Promise.reject(new TypeError('uncertain POST'));
      return Promise.resolve({ok: false, status: 404});
    };
    const submission = run(hung, 'submitFieldObservation({preventDefault(){}})');
    // A second context queues while the first still owns the Web Lock.
    const successor = makeContext('after-timeout');
    successor.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
    let acquiredAfterDeadline = false;
    const waitingInventory = run(successor, 'restorePendingFieldObservationInventory()').then(() => { acquiredAfterDeadline = true; });
    await drainMicrotasks(); assert.equal(acquiredAfterDeadline, false);
    await expireNetwork(hung); await submission; await waitingInventory;
    assert.equal(acquiredAfterDeadline, true);
    assert.deepEqual(attempts, ['before', 'body'].includes(phase) ? ['GET'] : phase === 'post' ? ['GET', 'POST'] : ['GET', 'POST', 'GET']);
    assert.equal(hung.sandbox.networkTimers.size, 0);
    assert.equal(shared.get(first.key), JSON.stringify(first.pending));
    assert.equal(shared.get('astropilot.fieldObservationLock'), JSON.stringify(firstLock));
    assert.match(run(hung, 'document.querySelector("#observation-status").textContent'), /Réseau trop lent/);
    await run(successor, 'restorePendingFieldObservation()');
    await run(successor, 'submitFieldObservation({preventDefault(){}})');
    assert.equal(successor.sandbox.posts.length, 0); assert.equal(recoveryStorageSize(), 0);
    lateResolve({ok: true, status: 201, json: async () => projection(first.pending.payload)});
    await drainMicrotasks();
    await deliverStorage({reverse: true, duplicate: true}); await lockTail;
    assert.equal(recoveryStorageSize(), 0); assert.equal(successor.sandbox.posts.length, 0);
  }


  // A newly generated POST can hang as well; retry from another context reuses its UUID.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
  const fresh = makeContext('fresh-hang'); fresh.sandbox.manualDeadlines = true;
  let newPayload;
  fresh.sandbox.fetch = (_url, options) => {
    assert.equal(options.method, 'POST'); newPayload = JSON.parse(options.body);
    return new Promise(() => {});
  };
  const freshSubmission = run(fresh, 'submitFieldObservation({preventDefault(){}})');
  await drainMicrotasks();
  const newPendingRaw = shared.get(first.key); const newLockRaw = shared.get('astropilot.fieldObservationLock');
  await expireNetwork(fresh); await freshSubmission;
  assert.equal(shared.get(first.key), newPendingRaw); assert.equal(shared.get('astropilot.fieldObservationLock'), newLockRaw);
  const freshRetry = makeContext('fresh-retry');
  freshRetry.sandbox.canonical = {[newPayload.observation_id]: projection(newPayload)};
  await run(freshRetry, 'restorePendingFieldObservationInventory(); restorePendingFieldObservation()');
  await run(freshRetry, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(freshRetry.sandbox.posts.length, 0); assert.equal(recoveryStorageSize(), 0);

  // clear() delivers asynchronously; captured artifacts survive until explicit resolution.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
  const clearer = makeContext('clear-source'); const cleared = makeContext('clear-target');
  shared.set(first.key, JSON.stringify(first.pending));
  await run(cleared, 'restorePendingFieldObservationInventory()');
  await deliverStorage(); await lockTail;
  clearer.sandbox.localStorage.clear();
  assert.equal(run(cleared, 'state.fieldObservationLock.status'), 'pending');
  await deliverStorage({duplicate: true});
  assert.equal(run(cleared, 'state.fieldObservationLock.status'), 'persistence_missing');
  assert.equal(run(cleared, 'state.fieldObservationLock.entries[0].pending.payload.observation_id'), first.pending.payload.observation_id);
  const clearUuidCount = cleared.sandbox.uuidCount();
  for (let repeat = 0; repeat < 3; repeat++) {
    await run(cleared, 'handleFieldObservationPageShow({persisted: true})');
    await run(cleared, 'restorePendingFieldObservationInventory()');
    run(cleared, 'handleFieldObservationStorageEvent({key: null, newValue: null})');
    assert.equal(run(cleared, 'state.fieldObservationLock.entries[0].pending.payload.observation_id'), first.pending.payload.observation_id);
    await run(cleared, 'submitFieldObservation({preventDefault(){}})');
    assert.equal(cleared.sandbox.uuidCount(), clearUuidCount);
    assert.equal(cleared.sandbox.posts.length, 0);
    assert.equal(recoveryStorageSize(), 0);
  }
  await run(cleared, 'abandonFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.entries[0]))');
  assert.equal(run(cleared, 'state.fieldObservationLock'), null);

  for (let repeat = 0; repeat < 3; repeat++) {
    shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
    const source = makeContext('foreign-source'); const empty = makeContext('empty-target');
    await run(empty, 'restorePendingFieldObservationInventory()');
    source.sandbox.localStorage.setItem('foreign', 'value'); source.sandbox.localStorage.clear();
    await deliverStorage({reverse: true, duplicate: true});
    run(empty, 'handleFieldObservationStorageEvent({key: null, newValue: null})');
    await run(empty, 'handleFieldObservationPageShow({persisted: true})');
    assert.equal(run(empty, 'state.fieldObservationLock'), null);
    assert.equal(run(empty, 'document.querySelector("#observation-save").disabled'), false);

    for (const withPending of [false, true]) {
      shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
      const broken = makeContext('broken-global');
      shared.set('astropilot.fieldObservationLock', '{broken-global');
      if (withPending) shared.set(first.key, JSON.stringify(first.pending));
      await run(broken, 'restorePendingFieldObservationInventory()');
      assert.equal(run(broken, 'state.fieldObservationLock.corruptions[0].reason'), 'invalid_global_lock');
      assert.equal(run(broken, 'state.fieldObservationLock.corruptions[0].origin'), 'global_lock');
      assert.equal(run(broken, 'state.fieldObservationLock.entries.length'), withPending ? 1 : 0);
      assert.equal(run(broken, 'document.querySelector("#observation-pending-diagnostics").hidden'), false);
      assert.equal(run(broken, 'document.querySelector("#observation-pending-diagnostics").children.length'), withPending ? 2 : 1);
      assert.equal(run(broken, 'state.fieldObservationLock.corruptions[0].entry_id'), run(broken, 'fieldObservationEntryId(state.fieldObservationLock.corruptions[0])'));
      broken.sandbox.window.confirm = message => {
        assert.match(message, /verrou global illisible/); assert.match(message, /conservées/); return false;
      };
      await run(broken, 'removeCorruptFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.corruptions[0]))');
      assert.equal(shared.get('astropilot.fieldObservationLock'), '{broken-global');
      broken.sandbox.window.confirm = () => true;
      await run(broken, 'document.querySelector("#observation-pending-diagnostics").children.at(-1).children[1].children[0].listeners.click()');
      if (withPending) {
        assert.equal(shared.get(first.key), JSON.stringify(first.pending));
        assert.equal(run(broken, 'state.fieldObservationLock.status'), 'pending');
      } else {
        assert.equal(recoveryStorageSize(), 0); assert.equal(run(broken, 'state.fieldObservationLock'), null);
      }
    }
    shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
    const changed = makeContext('changed-global');
    shared.set('astropilot.fieldObservationLock', '{old-global');
    await run(changed, 'restorePendingFieldObservationInventory()');
    const oldId = run(changed, 'fieldObservationEntryId(state.fieldObservationLock.corruptions[0])');
    shared.set('astropilot.fieldObservationLock', '{new-global');
    await run(changed, `removeCorruptFieldObservationEntry(${JSON.stringify(oldId)})`);
    assert.equal(shared.get('astropilot.fieldObservationLock'), '{new-global');
    assert.equal(run(changed, 'state.fieldObservationLock.corruptions.some(e => e.raw === "{new-global")'), true);
  }

  // Exact review regressions, repeated with independent contexts and delayed/reordered events.
  const ids = tab => run(tab, 'fieldObservationArtifacts(state.fieldObservationLock).entries.map(e => e.pending.payload.observation_id).sort().join(",")');
  const prepareMemory = async (name, corruption = false) => {
    shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
    const source = makeContext(`${name}-source`); const target = makeContext(name);
    shared.set(corruption ? 'astropilot.fieldObservationLock' : first.key,
      corruption ? '{memory-global' : JSON.stringify(first.pending));
    await run(target, 'restorePendingFieldObservationInventory()');
    await deliverStorage(); await lockTail;
    source.sandbox.localStorage.clear();
    await deliverStorage({reverse: true, duplicate: true});
    await run(target, 'handleFieldObservationPageShow({persisted: true})');
    return {source, target};
  };
  const targetId = tab => run(tab, 'fieldObservationEntryId(fieldObservationArtifacts(state.fieldObservationLock).entries[0])');
  const resolve = (tab, method, id) => run(tab, `${method}(${JSON.stringify(id)})`);
  for (let repeat = 0; repeat < 3; repeat++) {
    for (const unavailable of [true, false]) {
      const {source, target} = await prepareMemory('migration-memory');
      const legacyB = {payload: second.pending.payload,
        snapshot: run(target, `legacySnapshotFromObservationPayload(${JSON.stringify(second.pending.payload)})`)};
      const setItem = target.sandbox.localStorage.setItem;
      if (unavailable) target.sandbox.navigator = {};
      else target.sandbox.localStorage.setItem = () => { throw new Error('migration-write-denied'); };
      source.sandbox.localStorage.setItem(second.key, JSON.stringify(legacyB));
      await deliverStorage({reverse: true, duplicate: true});
      for (let reload = 0; reload < 3; reload++) {
        await run(target, 'handleFieldObservationPageShow({persisted: true})');
        await run(target, 'restorePendingFieldObservationInventory()');
        assert.equal(ids(target), [first.pending.payload.observation_id, second.pending.payload.observation_id].sort().join(','));
        assert.equal(run(target, 'state.fieldObservationLock.migration_diagnostic'),
          unavailable ? 'migration_requires_web_locks' : 'migration_failed');
        await run(target, 'submitFieldObservation({preventDefault(){}})');
        assert.equal(target.sandbox.posts.length, 0);
      }
      target.sandbox.navigator = {locks: controlledLocks}; target.sandbox.localStorage.setItem = setItem;
      await run(target, 'restorePendingFieldObservationInventory()');
      const bId = run(target, 'fieldObservationEntryId(state.fieldObservationLock.entries.find(e => e.key === ' + JSON.stringify(second.key) + '))');
      await resolve(target, 'abandonFieldObservationEntry', bId);
      assert.equal(ids(target), first.pending.payload.observation_id);
      assert.equal(shared.has(first.key), false);
      assert.equal(run(target, 'document.querySelector("#observation-save").disabled'), true);
      await resolve(target, 'abandonFieldObservationEntry', targetId(target));
      assert.equal(run(target, 'state.fieldObservationLock'), null);
    }
    for (const withB of [false, true]) {
      const {source, target} = await prepareMemory('global-memory', true);
      const id = run(target, 'fieldObservationEntryId(state.fieldObservationLock.corruptions[0])');
      if (withB) source.sandbox.localStorage.setItem(second.key, JSON.stringify(second.pending));
      await deliverStorage({reverse: true, duplicate: true});
      await run(target, 'handleFieldObservationPageShow({persisted: true})');
      await resolve(target, 'removeCorruptFieldObservationEntry', id);
      assert.equal(run(target, 'fieldObservationArtifacts(state.fieldObservationLock).corruptions.length'), 0);
      if (withB) {
        assert.equal(shared.get(second.key), JSON.stringify(second.pending));
        assert.equal(run(target, 'state.fieldObservationLock.status'), 'pending');
        assert.equal(ids(target), second.pending.payload.observation_id);
      } else assert.equal(run(target, 'state.fieldObservationLock'), null);
    }
    {
      const {source, target} = await prepareMemory('global-memory-divergent', true);
      const id = run(target, 'fieldObservationEntryId(state.fieldObservationLock.corruptions[0])');
      // Replacement has not delivered its event when the user acts.
      source.sandbox.localStorage.setItem('astropilot.fieldObservationLock', '{replacement');
      await resolve(target, 'removeCorruptFieldObservationEntry', id);
      assert.equal(shared.get('astropilot.fieldObservationLock'), '{replacement');
      assert.equal(run(target, 'state.fieldObservationLock.corruptions.length'), 2);
    }
    for (const method of ['reconcileFieldObservationEntry', 'abandonFieldObservationEntry']) {
      const {source, target} = await prepareMemory('pending-memory');
      const id = targetId(target);
      source.sandbox.localStorage.setItem(second.key, JSON.stringify(second.pending));
      await deliverStorage({reverse: true, duplicate: true});
      await run(target, 'handleFieldObservationPageShow({persisted: true})');
      target.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
      await resolve(target, method, id);
      assert.equal(ids(target), second.pending.payload.observation_id);
      assert.equal(shared.get(second.key), JSON.stringify(second.pending));
      assert.equal(run(target, 'state.fieldObservationLock.status'), 'pending');
      assert.equal(target.sandbox.posts.length, 0);
      const reload = makeContext('remaining-reload');
      await run(reload, 'restorePendingFieldObservationInventory()');
      assert.equal(ids(reload), second.pending.payload.observation_id);
    }
    for (const method of ['reconcileFieldObservationEntry', 'abandonFieldObservationEntry']) {
      const {source, target} = await prepareMemory('pending-memory-divergent');
      const id = targetId(target);
      const divergent = structuredClone(first.pending);
      divergent.payload.observation_id = 'replacement-uuid';
      source.sandbox.localStorage.setItem(first.key, JSON.stringify(divergent));
      target.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
      await resolve(target, method, id);
      assert.equal(shared.get(first.key), JSON.stringify(divergent));
      assert.ok(ids(target).includes(first.pending.payload.observation_id));
      assert.equal(target.sandbox.posts.length, 0);
    }
    {
      const {source, target} = await prepareMemory('memory-get-race');
      const id = targetId(target);
      let finishGet;
      target.sandbox.fetch = () => new Promise(resolve => { finishGet = resolve; });
      const reconciliation = resolve(target, 'reconcileFieldObservationEntry', id);
      await waitForRequest(() => typeof finishGet === 'function');
      assert.equal(typeof finishGet, 'function');
      const divergent = structuredClone(first.pending); divergent.payload.observation_id = 'during-get-uuid';
      source.sandbox.localStorage.setItem(first.key, JSON.stringify(divergent));
      finishGet({ok: true, status: 200, json: async () => projection(first.pending.payload)});
      await reconciliation;
      assert.equal(shared.get(first.key), JSON.stringify(divergent));
      assert.ok(ids(target).includes(first.pending.payload.observation_id));
    }
    // N -> 1 -> 0 reconstruction, with two memory-only UUIDs and no disk artifacts.
    const {source, target} = await prepareMemory('memory-many');
    source.sandbox.localStorage.setItem(second.key, JSON.stringify(second.pending));
    await run(target, 'restorePendingFieldObservationInventory()');
    source.sandbox.localStorage.clear();
    await deliverStorage({reverse: true, duplicate: true});
    await resolve(target, 'abandonFieldObservationEntry', targetId(target));
    assert.equal(run(target, 'fieldObservationArtifacts(state.fieldObservationLock).entries.length'), 1);
    await resolve(target, 'abandonFieldObservationEntry', targetId(target));
    assert.equal(run(target, 'state.fieldObservationLock'), null);
  }

  // P1: a real reload discards every JS global, retaining only the two storage backends.
  for (let repeat = 0; repeat < 3; repeat++) {
    for (const method of ['reconcileFieldObservationEntry', 'abandonFieldObservationEntry']) {
      const {target} = await prepareMemory('durable-reload');
      const originalId = targetId(target);
      assert.equal(recoveryRecords.get('inventory').entries.length, 1);
      assert.equal(recoveryStorageSize(), 0);
      contexts.length = 0; storageEvents.length = 0; // Destroy the old page, no pageshow reuse.
      const fresh = makeContext('fresh-page');
      await run(fresh, 'restorePendingFieldObservationInventory()');
      assert.equal(ids(fresh), first.pending.payload.observation_id);
      assert.equal(targetId(fresh), originalId);
      await run(fresh, 'submitFieldObservation({preventDefault(){}})');
      assert.equal(fresh.sandbox.uuidCount(), 0); assert.equal(fresh.sandbox.posts.length, 0);
      fresh.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
      await resolve(fresh, method, originalId);
      assert.equal(recoveryRecords.get('inventory').entries.length, 0);
      assert.equal(run(fresh, 'state.fieldObservationLock'), null);
      const afterResolution = makeContext('resolved-reload');
      await run(afterResolution, 'restorePendingFieldObservationInventory()');
      assert.equal(run(afterResolution, 'state.fieldObservationLock'), null);
      await run(afterResolution, 'submitFieldObservation({preventDefault(){}})');
      assert.equal(afterResolution.sandbox.uuidCount(), 1); assert.equal(afterResolution.sandbox.posts.length, 1);
    }
    // A stale page must not reinsert an explicitly resolved journal entry.
    {
      const {target} = await prepareMemory('stale-journal');
      const fresh = makeContext('journal-resolver');
      await run(fresh, 'restorePendingFieldObservationInventory()');
      await resolve(fresh, 'abandonFieldObservationEntry', targetId(fresh));
      await run(target, 'restorePendingFieldObservationInventory()');
      assert.equal(run(target, 'state.fieldObservationLock'), null);
      assert.equal(recoveryRecords.get('inventory').entries.length, 0);
    }
    for (const failure of ['unavailable', 'blocked', 'read', 'write', 'corrupt', 'payload']) {
      const {target} = await prepareMemory('recovery-failure');
      contexts.length = 0; storageEvents.length = 0;
      const fresh = makeContext('failed-reload');
      if (failure === 'unavailable') fresh.sandbox.indexedDB = undefined;
      if (failure === 'blocked' || failure === 'read') fresh.sandbox.indexedDB = {open() {
        const request = {}; Promise.resolve().then(() => failure === 'blocked' ? request.onblocked() : request.onerror());
        return request;
      }};
      if (failure === 'write') recoveryRecords.failWrite = true;
      if (failure === 'corrupt') recoveryRecords.set('inventory', {version: 99, entries: [], resolved: []});
      if (failure === 'payload') recoveryRecords.get('inventory').entries[0].pending.payload.observation_id = 'tampered';
      await run(fresh, 'restorePendingFieldObservationInventory()');
      await run(fresh, 'submitFieldObservation({preventDefault(){}})');
      assert.equal(fresh.sandbox.uuidCount(), 0); assert.equal(fresh.sandbox.posts.length, 0);
      assert.equal(run(fresh, 'state.fieldObservationLock.status'), 'unreadable');
      assert.equal(run(fresh, 'document.querySelector("#observation-save").disabled'), true);
      delete recoveryRecords.failWrite;
    }

    // Reload also preserves a corrupt global-lock artifact and its exact confirmed removal.
    {
      await prepareMemory('corrupt-durable', true);
      contexts.length = 0; storageEvents.length = 0;
      const fresh = makeContext('corrupt-reload');
      await run(fresh, 'restorePendingFieldObservationInventory()');
      assert.equal(run(fresh, 'state.fieldObservationLock.corruptions[0].raw'), '{memory-global');
      await run(fresh, 'removeCorruptFieldObservationEntry(fieldObservationEntryId(state.fieldObservationLock.corruptions[0]))');
      assert.equal(recoveryRecords.get('inventory').entries.length, 0);
      assert.equal(run(fresh, 'state.fieldObservationLock'), null);
    }
    // Divergent persistence before action or during canonical GET cannot delete either history.
    for (const duringGet of [false, true]) {
      const {source, target} = await prepareMemory('two-history-race');
      const aId = targetId(target);
      const history = structuredClone(first.pending); history.payload.observation_id = 'race-history-2';
      source.sandbox.localStorage.setItem(first.key, JSON.stringify(history));
      await run(target, 'restorePendingFieldObservationInventory()');
      source.sandbox.localStorage.clear();
      await deliverStorage({reverse: true, duplicate: true});
      await run(target, 'restorePendingFieldObservationInventory()');
      const replacement = structuredClone(first.pending); replacement.payload.observation_id = 'race-current-3';
      target.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
      let action;
      if (duringGet) {
        let finishGet;
        target.sandbox.fetch = () => new Promise(resolve => { finishGet = resolve; });
        action = resolve(target, 'reconcileFieldObservationEntry', aId);
        await waitForRequest(() => typeof finishGet === 'function');
        assert.equal(typeof finishGet, 'function');
        source.sandbox.localStorage.setItem(first.key, JSON.stringify(replacement));
        finishGet({ok: true, status: 200, json: async () => projection(first.pending.payload)});
      } else {
        source.sandbox.localStorage.setItem(first.key, JSON.stringify(replacement));
        action = resolve(target, 'abandonFieldObservationEntry', aId);
      }
      await action;
      assert.equal(shared.get(first.key), JSON.stringify(replacement));
      assert.ok(ids(target).includes(first.pending.payload.observation_id));
      assert.ok(ids(target).includes('race-history-2'));
      assert.ok(recoveryRecords.get('inventory').entries.some(e => e.pending.payload.observation_id === first.pending.payload.observation_id));
      assert.ok(recoveryRecords.get('inventory').entries.some(e => e.pending.payload.observation_id === 'race-history-2'));
      assert.equal(target.sandbox.posts.length, 0);
    }
    // P2: two historical memory artifacts have the SAME key + origin, different full identities.
    for (const reverse of [false, true]) {
      const {source, target} = await prepareMemory('same-key-history');
      const aId = targetId(target);
      const divergent = structuredClone(first.pending);
      divergent.payload.observation_id = 'history-uuid-2';
      divergent.payload.conditions.cloud_state = 'overcast';
      divergent.snapshot = run(target, `snapshotFromObservationPayload(${JSON.stringify(divergent.payload)},
        '2026-09-29T22:14', 'Europe/Zurich')`);
      source.sandbox.localStorage.setItem(first.key, JSON.stringify(divergent));
      await run(target, 'restorePendingFieldObservationInventory()');
      source.sandbox.localStorage.clear();
      await deliverStorage({reverse: true, duplicate: true});
      await run(target, 'restorePendingFieldObservationInventory()');
      const bId = run(target, 'fieldObservationEntryId(state.fieldObservationLock.entries.find(e => e.pending.payload.observation_id === "history-uuid-2"))');
      assert.equal(run(target, 'new Set(state.fieldObservationLock.entries.map(e => e.origin || "pending_storage")).size'), 1);
      assert.equal(run(target, 'new Set(state.fieldObservationLock.entries.map(e => e.key)).size'), 1);
      target.sandbox.canonical = {[first.pending.payload.observation_id]: projection(first.pending.payload)};
      if (reverse) await resolve(target, 'abandonFieldObservationEntry', bId);
      else await resolve(target, 'reconcileFieldObservationEntry', aId);
      assert.equal(ids(target), reverse ? first.pending.payload.observation_id : 'history-uuid-2');
      assert.equal(recoveryRecords.get('inventory').entries.length, 1);
      if (reverse) await resolve(target, 'reconcileFieldObservationEntry', aId);
      else await resolve(target, 'abandonFieldObservationEntry', bId);
      assert.equal(run(target, 'state.fieldObservationLock'), null);
      assert.equal(recoveryRecords.get('inventory').entries.length, 0);
      assert.equal(target.sandbox.posts.length, 0);
    }
  }

  // Exact refresh regressions, repeated with independent page contexts.
  for (let repeat = 0; repeat < 3; repeat++) {
    for (const kind of ['decision', 'mission', 'session']) {
      shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
      const tab = makeContext(`refresh-${kind}-${repeat}`);
      if (kind === 'decision') run(tab, `state.acceptedMission = null; state.availability = {start: '22:00'};
        state.fieldObservationDraftContext = Object.freeze({...state.fieldObservationDraftContext, source: 'decision'});`);
      if (kind === 'session') tab.sandbox.currentSession = () => ({execution: {execution_id: 'execution-1'}});
      if (kind === 'session') run(tab, `state.fieldObservationSelectedExecutionId = 'execution-1';
        state.sessions = [{execution: {execution_id: 'execution-1'}, mission: {decision_id: 'decision-1', night_date: '2026-09-29'}}];
        state.fieldObservationDraftContext = Object.freeze({...state.fieldObservationDraftContext, execution_id: 'execution-1'});`);
      tab.sandbox.fetch = async () => ({ok: false, status: 404, json: async () => ({})});
      await run(tab, 'submitFieldObservation({preventDefault(){}})');
      assert.equal(run(tab, 'state.fieldObservationLock?.status'), 'invalid', kind + ': ' + run(tab, 'document.querySelector("#observation-status").textContent'));
      const envelope = run(tab, 'JSON.stringify(state.fieldObservationLock.pending)');
      const decision = tab.sandbox.state.currentDecision;
      tab.sandbox.manualDeadlines = true;
      let late, signal;
      tab.sandbox.fetch = async (url, options) => {
        if (url.includes('/field-observations/')) return {ok: false, status: 404};
        signal = options.signal;
        return new Promise(resolve => { late = resolve; });
      };
      const refreshing = run(tab, 'refreshInvalidFieldObservationContext()');
      await expireNetwork(tab); await refreshing;
      assert.ok(signal.aborted);
      assert.equal(run(tab, 'state.observationBusy'), false);
      assert.equal(run(tab, 'state.fieldObservationLock.status'), 'invalid');
      assert.equal(run(tab, 'JSON.stringify(state.fieldObservationLock.pending)'), envelope);
      assert.match(run(tab, 'document.querySelector("#observation-status").textContent'), /context_refresh_timeout/);
      late({ok: true, json: async () => ({decision_id: 'decision-1', night_date: '2026-09-29'})});
      await drainMicrotasks();
      assert.equal(run(tab, 'state.fieldObservationLock.status'), 'invalid');
      assert.equal(tab.sandbox.state.currentDecision, decision);
      // Body decoding belongs to the same deadline, even after headers arrive.
      tab.sandbox.fetch = async url => url.includes('/field-observations/')
        ? {ok: false, status: 404}
        : {ok: true, json: () => new Promise(() => {})};
      const bodyRefresh = run(tab, 'refreshInvalidFieldObservationContext()');
      await expireNetwork(tab); await bodyRefresh;
      assert.equal(run(tab, 'state.observationBusy'), false);
      assert.equal(run(tab, 'state.fieldObservationLock.status'), 'invalid');
      // Closing cancels the operation and ignores a transport that completes later.
      tab.sandbox.fetch = async (url, options) => {
        if (url.includes('/field-observations/')) return {ok: false, status: 404};
        signal = options.signal; return new Promise(resolve => {late = resolve;});
      };
      const closingRefresh = run(tab, 'refreshInvalidFieldObservationContext()');
      await drainMicrotasks();
      run(tab, 'invalidateFieldObservationOperation()');
      await closingRefresh;
      assert.ok(signal.aborted);
      late({ok: true, json: async () => ({decision_id: 'decision-1'})});
      await drainMicrotasks();
      assert.equal(run(tab, 'state.fieldObservationLock.status'), 'invalid');
      if (kind === 'decision') {
        tab.sandbox.manualDeadlines = false;
        tab.sandbox.fetch = async url => url.includes('/field-observations/')
          ? {ok: false, status: 404}
          : {ok: true, json: async () => ({decision_id: 'decision-1', night_date: '2026-09-29'})};
        await run(tab, 'refreshInvalidFieldObservationContext()');
        assert.equal(run(tab, 'state.fieldObservationLock.status'), 'pending');
        assert.equal(run(tab, 'state.fieldObservationContextInvalid'), false);
        assert.equal(run(tab, 'document.querySelector("#observation-save").disabled'), false);
        assert.equal(tab.sandbox.state.currentDecision, decision);
      }
    }
    // Native exceptions are classified, retain cause, and fail before UUID/POST.
    for (const stage of ['open', 'open-event', 'schema', 'transaction', 'put', 'put-event', 'blocked', 'upgrade']) {
      shared.clear(); recoveryRecords.clear(); contexts.length = 0;
      const tab = makeContext(`diagnostic-${stage}`);
      const cause = new Error(stage); if (stage === 'schema') cause.name = 'NotFoundError';
      tab.sandbox.indexedDB = {open() {
        if (stage === 'open') throw cause;
        const request = {error: cause};
        Promise.resolve().then(() => {
          if (stage === 'blocked') { Object.defineProperty(request, 'error', {get() {throw new Error('InvalidStateError');}}); return request.onblocked(); }
          if (stage === 'open-event') return request.onerror();
          if (stage === 'upgrade') { request.result = {createObjectStore() {throw cause;}}; return request.onupgradeneeded(); }
          request.result = {close() {}, transaction() {
            if (stage === 'schema') throw cause;
            const tx = {error: cause, abort() {}, objectStore() {return {
              get() {const op = {}; Promise.resolve().then(() => stage === 'transaction' ? tx.onabort() : (op.onsuccess(), tx.oncomplete())); return op;},
              put() {if (stage !== 'put-event') throw cause; const op = {error: cause}; Promise.resolve().then(() => op.onerror()); return op;},
            };}}; return tx;
          }};
          request.onsuccess();
        }); return request;
      }};
      await run(tab, 'submitFieldObservation({preventDefault(){}})');
      assert.equal(tab.sandbox.uuidCount(), 0); assert.equal(tab.sandbox.posts.length, 0);
      assert.match(run(tab, 'state.fieldObservationLock.recovery_error'), /^recovery_/);
      assert.match(run(tab, 'document.querySelector("#observation-status").textContent'), /recovery_/);
      assert.equal(run(tab, 'fieldObservationRecoveryError("recovery_transaction", new Error("native")).cause.message'), 'native');
    }
    // A full journal fails closed instead of discarding stale-page protection.
    shared.clear(); recoveryRecords.clear(); contexts.length = 0;
    const tab = makeContext('quota');
    recoveryRecords.set('inventory', {version: 1, entries: [], resolved: Array.from({length: 110}, (_, i) => `${i}:` + 'x'.repeat(5000))});
    await run(tab, 'submitFieldObservation({preventDefault(){}})');
    assert.equal(tab.sandbox.posts.length, 1);
    assert.equal(recoveryRecords.get('inventory').version, 2);
    assert.equal(recoveryRecords.get('inventory').resolved.length, 110);
    assert.ok(JSON.stringify(recoveryRecords.get('inventory')).length < 16000);
  }

  // 1,100 real UI acquisitions/publications: completed history stays constant size.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0; storageEvents.length = 0;
  const stress = makeContext('stress'); let maxJournalSize = 0;
  let ancient;
  for (let i = 0; i < 1100; i++) {
    run(stress, `document.querySelector('#observation-clouds').value = 'few'`);
    // Keep the first unresolved page snapshot, without delivering storage events.
    if (i === 0) {
      stress.sandbox.fetch = async (url, options) => {
        if (options?.method === 'POST') {
          if (!ancient) ancient = JSON.parse(run(stress, 'JSON.stringify(state.fieldObservationLock)'));
          stress.sandbox.posts.push(JSON.parse(options.body));
          return {ok: true, status: 201};
        }
        return {ok: false, status: 404};
      };
    }
    await run(stress, 'submitFieldObservation({preventDefault(){}})');
    assert.equal(stress.sandbox.posts.length, i + 1);
    const journal = recoveryRecords.get('inventory');
    assert.equal(journal.entries.length, 0); assert.equal(journal.resolved.length, 0);
    assert.equal(journal.epoch, i + 1); assert.equal(journal.resolved_watermark, i + 1);
    maxJournalSize = Math.max(maxJournalSize, JSON.stringify(journal).length);
  }
  assert.ok(maxJournalSize < 256, `bounded journal: ${maxJournalSize}`);
  const stable = JSON.stringify(recoveryRecords.get('inventory'));
  const reloaded = makeContext('stress-reload');
  await run(reloaded, 'restorePendingFieldObservationInventory()');
  assert.equal(run(reloaded, 'state.fieldObservationLock'), null);
  assert.equal(JSON.stringify(recoveryRecords.get('inventory')), stable);
  // Old memory and identical resurrected disk envelopes are fenced by the watermark.
  const old = makeContext('old-page'); old.sandbox.__ancient = ancient;
  run(old, 'adoptFieldObservationLock(__ancient); state.fieldObservationInventoryReady = true;');
  shared.set(ancient.key, JSON.stringify(ancient.pending));
  shared.set('astropilot.fieldObservationLock', JSON.stringify(ancient));
  await run(old, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(old.sandbox.posts.length, 0); assert.equal(old.sandbox.uuidCount(), 0);
  assert.equal(run(old, 'state.fieldObservationLock'), null);
  assert.equal(shared.has(ancient.key), false);
  assert.equal(JSON.stringify(recoveryRecords.get('inventory')), stable);
  // An old memory-only context cannot write the compacted entry either.
  run(old, 'adoptFieldObservationLock(__ancient)');
  await run(old, 'withFieldObservationWebLock(() => true)');
  assert.equal(run(old, 'state.fieldObservationLock'), null);
  assert.equal(JSON.stringify(recoveryRecords.get('inventory')), stable);


  // A live sequence gap keeps later resolutions fenced until the gap is resolved.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0;
  const gap = makeContext('watermark-gap');
  const low = structuredClone(ancient); low.pending.payload.observation_id = 'gap-low';
  low.generation = 'lock-gap-low'; low.pending.recovery_sequence = 1;
  const high = structuredClone(ancient); high.pending.payload.observation_id = 'gap-high';
  high.generation = 'lock-gap-high'; high.pending.recovery_sequence = 2;
  gap.sandbox.__low = low; gap.sandbox.__high = high;
  const makeJournalEntry = lock => {gap.sandbox.__lock = lock; return {...lock, origin: 'pending_storage',
    entry_id: run(gap, 'fieldObservationEntryId(__lock)'), created_at: new Date().toISOString(), updated_at: new Date().toISOString()};};
  const lowEntry = makeJournalEntry(low), highEntry = makeJournalEntry(high);
  recoveryRecords.set('inventory', {version: 2, entries: [lowEntry, highEntry], resolved: [], epoch: 2, resolved_watermark: 0});
  await run(gap, 'restorePendingFieldObservationInventory()');
  gap.sandbox.fetch = async url => ({ok: true, status: 200,
    json: async () => projection(url.endsWith('gap-high') ? high.pending.payload : low.pending.payload)});
  await run(gap, `reconcileFieldObservationEntry(${JSON.stringify(highEntry.entry_id)})`);
  assert.equal(recoveryRecords.get('inventory').entries.length, 1);
  assert.equal(recoveryRecords.get('inventory').resolved_watermark, 0);
  assert.equal(recoveryRecords.get('inventory').resolved[0].sequence, 2);
  // Even above the watermark, the retained digest rejects a stale later resolution.
  const lateGap = makeContext('gap-stale'); lateGap.sandbox.__high = high;
  run(lateGap, 'adoptFieldObservationLock(__high)');
  await run(lateGap, 'restorePendingFieldObservationInventory()');
  assert.ok(run(lateGap, 'recoveryFieldObservationArtifacts().every(e => e.pending.payload.observation_id !== "gap-high")'));
  await run(gap, `reconcileFieldObservationEntry(${JSON.stringify(lowEntry.entry_id)})`);
  assert.equal(recoveryRecords.get('inventory').entries.length, 0);
  assert.equal(recoveryRecords.get('inventory').resolved_watermark, 2);
  assert.equal(recoveryRecords.get('inventory').resolved.length, 0);

  // Migration hashes also fence exact unsequenced legacy artefacts after compaction.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0;
  const migrated = makeContext('legacy-compacted');
  migrated.sandbox.__legacy = {...low, pending: {...low.pending}};
  delete migrated.sandbox.__legacy.pending.recovery_sequence;
  const legacyId = run(migrated, 'fieldObservationEntryId(__legacy)');
  recoveryRecords.set('inventory', {version: 1, entries: [], resolved: [legacyId]});
  shared.set(low.key, JSON.stringify(migrated.sandbox.__legacy.pending));
  shared.set('astropilot.fieldObservationLock', JSON.stringify(migrated.sandbox.__legacy));
  run(migrated, 'adoptFieldObservationLock(__legacy)');
  await run(migrated, 'withFieldObservationWebLock(() => true)');
  assert.equal(run(migrated, 'state.fieldObservationLock'), null);
  assert.equal(recoveryStorageSize(), 0);
  assert.equal(recoveryRecords.get('inventory').resolved[0].digest.length, 64);
  assert.equal(recoveryRecords.get('inventory').entries.length, 0);
  // Restore captured before recovery load cannot reacquire the compacted legacy UUID.
  shared.set(low.key, JSON.stringify(migrated.sandbox.__legacy.pending));
  run(migrated, 'state.fieldObservationInventoryReady = true');
  await run(migrated, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(migrated.sandbox.uuidCount(), 0); assert.equal(migrated.sandbox.posts.length, 0);
  assert.equal(recoveryStorageSize(), 0);
  assert.equal(recoveryRecords.get('inventory').entries.length, 0);

  // Real remaining capacity exhaustion, after compaction, precedes UUID/storage/POST.
  shared.clear(); recoveryRecords.clear(); contexts.length = 0;
  const full = makeContext('capacity');
  const journal = {version: 2, entries: [], resolved: [], epoch: 0, resolved_watermark: 0};
  for (let i = 0; JSON.stringify(journal).length < 512 * 1024 - 500; i++) {
    journal.resolved.push({digest: i.toString(16).padStart(64, '0'), sequence: 0});
  }
  recoveryRecords.set('inventory', journal);
  const fullBefore = JSON.stringify(journal);
  await run(full, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(full.sandbox.uuidCount(), 0); assert.equal(full.sandbox.posts.length, 0);
  assert.equal(recoveryStorageSize(), 0);
  assert.equal(JSON.stringify(recoveryRecords.get('inventory')), fullBefore);
  assert.match(run(full, 'document.querySelector("#observation-status").textContent'), /recovery_quota.*Aucun UUID ni POST créé/);

  // Confirmed POST with terminal IDB failure: retain the durable pending and tell the truth.
  for (let repeat = 0; repeat < 3; repeat++) {
    shared.clear(); recoveryRecords.clear(); contexts.length = 0;
    const success = makeContext(`cleanup-success-${repeat}`); let confirmedPayload;
    success.sandbox.fetch = async (url, options) => {
      assert.equal(options.method, 'POST');
      success.sandbox.completedOperation = run(success, 'activeFieldObservationOperation');
      confirmedPayload = JSON.parse(options.body);
      success.sandbox.posts.push(confirmedPayload);
      recoveryRecords.failWrite = true;
      return {ok: true, status: 201};
    };
    await run(success, 'submitFieldObservation({preventDefault(){}})');
    assert.equal(success.sandbox.posts.length, 1);
    assert.equal(success.sandbox.completedOperation.results.network_result, 'confirmed');
    assert.equal(success.sandbox.completedOperation.results.recovery_cleanup_result, 'pending');
    assert.equal(run(success, 'document.querySelector("#observation-status").textContent'),
      run(success, 'FIELD_OBSERVATION_CONFIRMED_RECOVERY_PENDING'));
    assert.doesNotMatch(run(success, 'document.querySelector("#observation-status").textContent'), /Aucun POST/);
    assert.equal(recoveryRecords.get('inventory').entries[0].pending.payload.observation_id, confirmedPayload.observation_id);
    delete recoveryRecords.failWrite;
    shared.clear();
    const reload = makeContext('cleanup-reload');
    await run(reload, 'restorePendingFieldObservationInventory()');
    const entry = run(reload, 'fieldObservationEntryId(state.fieldObservationLock.entries[0])');
    assert.equal(run(reload, 'state.fieldObservationLock.entries[0].pending.payload.observation_id'), confirmedPayload.observation_id);
    reload.sandbox.fetch = async (url, options) => {
      assert.ok(url.endsWith('/' + confirmedPayload.observation_id));
      assert.notEqual(options?.method, 'POST');
      return {ok: true, status: 200, json: async () => projection(confirmedPayload)};
    };
    await run(reload, `reconcileFieldObservationEntry(${JSON.stringify(entry)})`);
    assert.equal(recoveryRecords.get('inventory').entries.length, 0);
    assert.equal(recoveryRecords.get('inventory').resolved.length, 0);
    assert.equal(run(reload, 'state.recentFieldObservationConfirmations[0].observation_id'), confirmedPayload.observation_id);
    assert.equal(reload.sandbox.posts.length, 0);
    const lastReload = makeContext('cleanup-stable');
    await run(lastReload, 'restorePendingFieldObservationInventory()');
    assert.equal(run(lastReload, 'state.fieldObservationLock'), null);
  }

})().catch(error => { console.error(error); process.exitCode = 1; });
'''.replace("HELPERS_SOURCE", json.dumps(helpers)).replace("RECOVERY_IDB_SOURCE", RECOVERY_IDB_HARNESS)
    return program


def test_field_observation_two_context_web_locks_inventory_and_clear():
    program = _field_observation_multicontext_program()
    result = subprocess.run([javascript_engine(), "-"], input=program, capture_output=True, text=True, check=False, timeout=90)
    assert result.returncode == 0, result.stderr


def test_decision_only_refresh_reads_actual_durable_uuid_without_new_decision(tmp_path):
    """Production UUID generation and file persistence -> HTTP GET -> real UI refresh.

    Only the upstream astronomy/weather evaluation is fixed; durable evaluation,
    storage, HTTP routing, and refresh are the production implementations.
    The pipe transport avoids opening a network socket in CI.
    """
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from astropilot.app import create_app
    from astropilot.decision_forecast_evidence_store import FileDecisionForecastEvidenceStore
    from astropilot.field_observation_store import FileFieldObservationStore
    from decision.services.durable_tonight_application_service import (
        DurableTonightApplicationService, generate_decision_id,
    )
    from decision.services.tonight_application_service import TonightResult, TonightStatus
    from decision.weather.decision_forecast_evidence import DecisionForecastEvidence

    calls = []
    result = TonightResult(
        night={"date": "2026-09-29"}, recommendation=None, mission=None,
        status=TonightStatus.NO_PRODUCTIVE_WINDOW,
        forecast_evidence=DecisionForecastEvidence(()),
    )
    def evaluate(**kwargs):
        calls.append(kwargs)
        return result

    store = FileDecisionForecastEvidenceStore(tmp_path / "decisions")
    service = DurableTonightApplicationService(
        application_service=SimpleNamespace(evaluate=evaluate), evidence_store=store,
        decision_id_factory=generate_decision_id,
        field_observation_store=FileFieldObservationStore(tmp_path / "observations"),
    )
    decision = service.evaluate()
    decision_id = decision.decision_id
    assert decision_id is not None
    before = {path.name: path.read_bytes() for path in (tmp_path / "decisions").iterdir()}
    assert len(list((tmp_path / "decisions").glob("*.json"))) == 1
    client = TestClient(create_app(service_factory=lambda: service,
        clock=lambda: datetime(2026, 9, 29, 22, tzinfo=timezone.utc)))
    prefix = _field_observation_multicontext_program().split("(async () => {\n  // Two distinct states")[0]
    checks = r'''
const fs = require('fs');
function replyFromPython(url, options) {
  process.stdout.write(JSON.stringify({url, method: options?.method || 'GET'}) + '\n');
  let line = ''; const byte = Buffer.alloc(1);
  while (fs.readSync(0, byte, 0, 1, null) && byte[0] !== 10) line += byte.toString();
  const reply = JSON.parse(line);
  return {ok: reply.status >= 200 && reply.status < 300, status: reply.status, json: async () => reply.body};
}
(async () => {
  const tab = makeContext('durable-refresh');
  tab.sandbox.__decisionId = DECISION_ID;
  run(tab, `state.acceptedMission = null;
    state.currentDecision = {decision_id: __decisionId, night_date: '2026-09-29'};
    state.fieldObservationDraftContext = Object.freeze({...state.fieldObservationDraftContext,
      source: 'decision', decision_id: __decisionId});`);
  // The publication 404 is the invalid context being recovered, not a new decision.
  tab.sandbox.fetch = async () => ({ok: false, status: 404});
  await run(tab, 'submitFieldObservation({preventDefault(){}})');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'invalid');
  const pending = run(tab, 'JSON.stringify(state.fieldObservationLock.pending)');
  const current = tab.sandbox.state.currentDecision;
  tab.sandbox.fetch = async (url, options) => replyFromPython(url, options);
  await run(tab, 'refreshInvalidFieldObservationContext()');
  assert.equal(run(tab, 'state.fieldObservationLock.status'), 'pending');
  assert.equal(run(tab, 'state.fieldObservationContextInvalid'), false);
  assert.equal(run(tab, 'JSON.stringify(state.fieldObservationLock.pending)'), pending);
  assert.equal(tab.sandbox.state.currentDecision, current);
  assert.equal(run(tab, 'state.fieldObservationLock.pending.payload.decision_id'), DECISION_ID);
  assert.equal(run(tab, 'state.observationBusy'), false);
  assert.equal(tab.sandbox.uuidCount(), 1);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''.replace("DECISION_ID", json.dumps(decision_id))
    # Keep stdin available for the Python/Node request-response transport.
    script = tmp_path / "decision_context_refresh.cjs"
    script.write_text(prefix + checks, encoding="utf-8")
    process = subprocess.Popen([javascript_engine(), str(script)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    requests = []
    try:
        for line in process.stdout:
            request = json.loads(line)
            requests.append(request)
            assert request["method"] == "GET"
            assert request["url"] != "/v1/tonight"
            response = client.request(request["method"], request["url"])
            process.stdin.write(json.dumps({"status": response.status_code, "body": response.json()}) + "\n")
            process.stdin.flush()
        assert process.wait(timeout=15) == 0, process.stderr.read()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert len(requests) == 2
    assert requests[-1]["url"] == f"/v1/decisions/{decision_id}/context"
    assert len(calls) == 1
    after = {path.name: path.read_bytes() for path in (tmp_path / "decisions").iterdir()}
    assert after == before
    assert len(list((tmp_path / "decisions").glob("*.json"))) == 1
    assert store.load(decision_id=decision_id) == decision.forecast_evidence
