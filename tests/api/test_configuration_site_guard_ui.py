"""Execute production async configuration/site guards with controlled responses."""
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'astropilot/web/app.js'


def test_configuration_and_acceptance_generation_races():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the async generation harness')
    source = SCRIPT.read_text()

    def between(start, end):
        return source[source.index(start):source.index(end)]

    helpers = between('const DECISION_SITE_STORAGE_KEY', 'function activeObservationContext(')
    helpers += between('function setView(', 'const labels = Object.freeze')
    helpers += between('function show(view)', 'function duration(')
    helpers += between('function setCurrentFieldObservationDecision(', 'function normalizeError(')
    helpers += between('function initializeConfiguration(', 'async function restoreSavedMission(')
    helpers += between('async function loadConfiguration(', 'const availabilityFieldsByMode')
    helpers += between('async function retryPendingAcceptance(', 'document.querySelector("#site-next")')
    edit_start = source.index("function editConfiguration()")
    helpers += source[edit_start:source.index('document.querySelector("#save-configuration")', edit_start)]
    helpers += between('function sameAcceptanceIntent(', 'function resetMissionPresentation(')
    helpers += between('function windowTimezone(', 'function clock(')
    helpers += between('function resetMissionPresentation(', 'function renderDecision(')
    helpers += between('async function restoreSavedMission(', 'function invalidateAvailabilityForSiteChange(')
    harness = r'''
const assert = require('node:assert/strict');
const A = {configured: true, profile_revision: 1, equipment: {}, site: {latitude: 47, longitude: 6, timezone: 'Europe/Zurich'}};
const B = {...A, site: {...A.site, latitude: 46}};
const C = {...A, site: {...A.site, latitude: 45}};
const element = () => ({hidden: true, disabled: false, querySelector: element,
  setAttribute() {}, removeAttribute() {}, replaceChildren() {}, append() {}, focus() {}});
const crypto = require("node:crypto");
const PENDING_ACCEPTANCE_STORAGE_KEY = "astropilot.pendingAcceptance";
const PENDING_ACCEPTANCE_STORAGE_VERSION = 2;
const document = {querySelector: element, querySelectorAll: () => [], createElement: element};
const wizardStates = ["site", "equipment", "projects", "review"];
function requestAnimationFrame(callback) {callback();}
function invalidateOutcomeHistory() {}
let opened = 0, rendered = 0, queue = [];
const ui = {availabilityTimezoneWarning: element(), addObservationMessage: element(), addObservationDecision: element(),
  configurationLoading: element(), configurationError: element(), availability: element(),
  loading: element(), message: element(), pendingAcceptance: element(), decision: element(),
  editAvailability: element(), editConfiguration: element(), recommendationSubmit: element(), refresh: element(), configurationRecover: element(), configurationRecoveryConfirm: element(),
  configurationRecoveryConfirmation: element(), onboarding: element(),
  savedMissionEntry: element(), savedMissionChoice: element(), savedMissionTarget: element(),
  primaryIntentChoice: element(), retryPendingAcceptance: element(), pendingAcceptanceMessage: element(), mission: {close() {}, showModal() { opened++; }}};
const state = {configuration: A, configurationGeneration: 0, decisionSiteGeneration: 0,
  acceptedMission: null, currentDecision: null, savedMissions: [], configurationDraft: A};
const pending = {uuid: 'unchanged', decision_id: 'decision-A', payload: {clouds: 'few'}};
state.fieldObservationLock = pending;
const storage = new Map();
const localStorage = {setItem(k,v) {storage.set(k,v);}, getItem(k) {return storage.get(k) ?? null;}, removeItem(k) {storage.delete(k);}};
function fetch(url, options) { return new Promise((resolve, reject) => queue.push({url, options, resolve, reject})); }
const reply = (request, payload, ok = true) => request.resolve({ok, status: ok ? 200 : 503, json: async () => payload});
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
function text() {}
function syncFieldObservationContext() {}
function invalidateRecentDecisions() {}

function invalidateAvailabilityForSiteChange() {}
function siteTimezone() { return state.configuration.site.timezone; }
function siteConfigurationIdentity() { return JSON.stringify(state.configuration.site); }
function currentSession() { return null; }
function draftFromConfiguration(payload) { return payload; }
function hideRecoveryConfirmation() {}
function prefillConfiguration() {}
function renderAvailabilityTimezone() {}
function restorePendingFieldObservationInventory() {}


function showFormError() {}
function renderReview() {}
function restoreAcceptanceControls() {}
function disableAcceptanceControls() {}
function showConfigurationError(message) { state.error = message; setView("configuration_error"); }
function clearAlternatives() {}
function configurationPayload() { return state.configurationDraft; }
function chosenIntent() { return null; }


function showAcceptanceStatus(message) { state.status = message; }
function intentMode() { return 'legacy'; }
function acceptanceControls() { return []; }
function showAcceptedIntent() { return true; }


function renderMission() { rendered++; }

function showAvailabilityError(message) { state.availabilityError = message; }
function renderDecision() { setView("recommendation"); }
function showMessage() {}
'''
    checks = r'''
(async () => {
  // P2 #1: obsolete ordinary load cannot remove a failed reload's blockade.
  const loadA = loadConfiguration(); const oldLoad = queue.shift();
  const reloadB = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: JSON.stringify([46,6,'Europe/Zurich'])});
  const requestB = queue.shift(); requestB.reject(new Error('offline')); await reloadB;
  reply(oldLoad, A); await loadA;
  assert.equal(state.configuration, A);
  assert.equal(state.decisionSiteReloadRequired, true);
  assert.equal(observationContext('catalogue'), null);
  assert.equal(currentDecisionMatchesSite(), false);
  assert.equal(state.view, 'configuration_error'); // current failure owns the loading view

  // First load, repeated identical events and B -> C before first install.
  for (const final of [B, C]) {
    state.configuration = null;
    const firstLoad = loadConfiguration(); const staleLoad = queue.shift();
    const firstEvent = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(B.site)});
    const staleReload = queue.shift();
    const lastEvent = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(final.site)});
    const currentReload = queue.shift();
    reply(staleLoad, A); await firstLoad;
    reply(staleReload, B); await firstEvent;
    assert.equal(state.configuration, null); assert.equal(state.decisionSiteReloadRequired, true);
    reply(currentReload, final); await flush();
    reply(queue.shift(), {}); await flush(); reply(queue.shift(), []); await lastEvent;
    assert.equal(state.configuration, final); assert.equal(state.view, 'availability');
  }
  // Storage takes ownership of loading; stale success cannot navigate, errors allow retry.
  for (const fail of [false, true]) {
    installCurrentConfiguration(A, beginConfigurationOperation());
    const old = loadConfiguration(); const stale = queue.shift();
    const reload = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(B.site)});
    const latest = queue.shift();
    if (fail) latest.reject(new Error('offline'));
    else {reply(latest, B); await flush(); reply(queue.shift(), {}); await flush(); reply(queue.shift(), []);}
    await reload; reply(stale, A); await old;
    assert.equal(state.view, fail ? 'configuration_error' : 'availability');
    assert.equal(state.decisionSiteReloadRequired, fail);
    if (fail) {
      const retry = loadConfiguration(); reply(queue.shift(), B); await flush();
      reply(queue.shift(), {}); await flush(); reply(queue.shift(), []); await retry;
      assert.equal(state.view, 'availability');
    }
  }
  // Normal post-configuration routes also apply to a replacement storage read.
  for (const payload of [{...B, configured: false}, {...B, needs_configuration_confirmation: true}]) {
    const load = loadConfiguration(); const old = queue.shift();
    const reload = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(B.site)});
    reply(queue.shift(), payload); await reload; reply(old, A); await load;
    assert.equal(state.view, 'site'); assert.equal(state.decisionSiteReloadRequired, false);
  }
  // A user navigation, even away and back to the same view, revokes the owner.
  const awayLoad = loadConfiguration(); const away = queue.shift();
  setView('review'); setView('loading_configuration'); reply(away, A); await awayLoad;
  assert.equal(state.view, 'loading_configuration');
  const navigating = loadConfiguration(); const previous = queue.shift();
  const storageRead = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(B.site)});
  const read = queue.shift(); setView('review'); reply(read, B); await storageRead;
  reply(previous, A); await navigating; assert.equal(state.view, 'review');

  // ABA, ABC and identical notifications all supersede the older reload.
  for (const final of [A, C, B]) {
    installCurrentConfiguration(A, beginConfigurationOperation());
    const first = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(B.site)});
    const stale = queue.shift();
    const second = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(final.site)});
    const latest = queue.shift();
    assert.ok(latest);
    reply(stale, B); await first;
    assert.equal(state.configuration, A);
    assert.equal(state.decisionSiteReloadRequired, true);
    reply(latest, final); await second;
    assert.equal(state.configuration, final);
    assert.equal(state.decisionSiteReloadRequired, false);
  }
  // Same fingerprint is ignored only with no relevant operation in flight.
  await handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint()});
  assert.equal(queue.length, 0);

  // Nominal load/save/recovery and stale write/recovery guards.
  const normalLoad = loadConfiguration(); reply(queue.shift(), A); await flush();
  reply(queue.shift(), {}); await flush(); reply(queue.shift(), []); await normalLoad;
  assert.equal(state.view, 'availability');
  state.configurationDraft = B;
  const save = saveConfiguration(); reply(queue.shift(), B); await save;
  assert.equal(state.configuration, B); assert.equal(state.view, 'availability');
  for (const operation of [saveConfiguration, recoverConfiguration]) {
    state.configurationErrorCode = 'configuration_corrupt';
    const old = operation(); const request = queue.shift();
    const latest = loadConfiguration({afterConflict: true}); reply(queue.shift(), C); await latest;
    reply(request, {...A, configured: false}); await old;
    assert.equal(state.configuration, C);
    assert.equal(state.view, 'review');
  }
  state.configurationErrorCode = 'configuration_corrupt';
  const recovery = recoverConfiguration(); const recovered = {...A, configured: false};
  reply(queue.shift(), recovered); await recovery;
  assert.equal(state.configuration, recovered); assert.equal(state.view, 'site');

  // Mission restore rejects a configuration change even during response.json().
  installCurrentConfiguration(A, beginConfigurationOperation());
  const restore = restoreSavedMission(); const currentRequest = queue.shift();
  reply(currentRequest, {}); await flush(); const sessionsRequest = queue.shift();
  let releaseJSON;
  sessionsRequest.resolve({ok: true, json: () => new Promise(resolve => { releaseJSON = resolve; })});
  await flush(); installCurrentConfiguration(B, beginConfigurationOperation());
  releaseJSON([{mission_id: 'old', mission: {decision_id: 'old'}}]); await restore;
  assert.equal(state.acceptedMission, null); assert.deepEqual(state.savedMissions, []);

  const decision = {decision_id: 'decision-A', catalog_key: 'M31', target_decision_status: 'recommended'};
  const args = {source: 'primary_recommendation', selectedCatalogKey: 'M31', expectedDecisionId: 'decision-A'};
  const accepted = {status: 'accepted', decision_id: 'decision-A', catalog_key: 'M31', mission_id: 'mission-A', selection_id: 'selection-A',
    mission: {mission_id: 'mission-A', selection_id: 'selection-A', decision_id: 'decision-A'}};
  installCurrentConfiguration(A, beginConfigurationOperation()); state.currentDecision = decision;
  const acceptA = acceptRecommendation(args); const acceptRequest = queue.shift();
  installCurrentConfiguration(B, beginConfigurationOperation());
  reply(acceptRequest, accepted); await acceptA;
  assert.equal(state.acceptedMission, null); assert.equal(opened, 0); assert.equal(rendered, 0);
  assert.equal(state.lastHistoricalAcceptance, accepted);
  assert.equal(observationContext('mission'), null);
  assert.equal(state.acceptingRecommendation, false);

  // Real pending persistence/clear/lock: retry A cannot erase newer B, on success, failure or timeout B.
  for (const outcome of ['success', 'failure', 'timeout', 'stale_failure']) {
    clearAcceptedMission(); installCurrentConfiguration(A, beginConfigurationOperation()); state.currentDecision = decision;
    const first = acceptRecommendation(args); const firstRequest = queue.shift();
    const attemptA = state.pendingAcceptanceAttempt;
    installCurrentConfiguration(B, beginConfigurationOperation());
    const retry = acceptRecommendation({...args, attemptOverride: attemptA}); const retryRequest = queue.shift();
    assert.equal(firstRequest.options.body, retryRequest.options.body);
    reply(firstRequest, accepted); await first;
    assert.equal(state.pendingAcceptanceAttempt, null); assert.equal(state.acceptingRecommendation, false);
    state.currentDecision = {...decision, decision_id: 'decision-B'};
    const argsB = {...args, expectedDecisionId: 'decision-B'};
    const current = acceptRecommendation(argsB); const requestB = queue.shift();
    const attemptB = state.pendingAcceptanceAttempt; const storedB = localStorage.getItem(PENDING_ACCEPTANCE_STORAGE_KEY);
    const ownerB = state.acceptanceRequestOwner;
    reply(retryRequest, accepted, outcome !== 'stale_failure'); await retry;
    assert.equal(state.pendingAcceptanceAttempt, attemptB);
    assert.equal(localStorage.getItem(PENDING_ACCEPTANCE_STORAGE_KEY), storedB);
    assert.equal(state.acceptanceRequestOwner, ownerB); assert.equal(state.acceptingRecommendation, true);
    assert.equal(state.acceptedMission, null);
    if (outcome === 'timeout') requestB.reject(new Error('timeout'));
    else reply(requestB, {...accepted, decision_id: 'decision-B', mission: {...accepted.mission, decision_id: 'decision-B'}}, ['success', 'stale_failure'].includes(outcome));
    await current;
    assert.equal(state.acceptingRecommendation, false);
    assert.equal(state.pendingAcceptanceAttempt, outcome === 'timeout' ? attemptB : null);
    if (outcome === 'timeout') {
      state.pendingAcceptanceAttempt = null; assert.equal(restorePendingAcceptanceAttempt(), true);
      assert.deepEqual(state.pendingAcceptanceAttempt, attemptB);
      clearPendingAcceptanceAttempt(attemptB);
    }
  }
  clearAcceptedMission();
  opened = 0; rendered = 0;
  // Strict production parser: both identity fields reject implicit coercion, in v1/v2.
  const request = {acceptance_request_id: 'request-A', decision_id: 'decision-A', source: 'primary_recommendation',
    selected_catalog_key: 'M31', acquisition_intent_id: null, selected_at: '2026-10-03T10:00:00.000Z'};
  for (const version of [1, 2]) {
    for (const key of ['acceptance_request_id', 'decision_id']) {
      for (const value of [undefined, null, 123, true, {}, '', '   ', 'bad/id']) {
        const invalid = {...request, [key]: value}; if (version === 1) delete invalid.acquisition_intent_id;
        assert.equal(parsePendingAcceptance(JSON.stringify({version, state: 'unresolved', request: invalid})), null);
      }
    }
    const valid = {...request}; if (version === 1) delete valid.acquisition_intent_id;
    assert.equal(parsePendingAcceptance(JSON.stringify({version, state: 'unresolved', request: valid})).decision_id, 'decision-A');
  }
  // Storage-only reopen, site switch, superseding navigation/B, and real retry failures.
  for (const outcome of ['reopen', 'site', 'navigation', 'B', 'network', 'http', 'malformed']) {
    state.pendingAcceptanceAttempt = null; state.acceptedMission = null; state.acceptingRecommendation = false;
    let recoveredAttempt = request;
    if (outcome === 'reopen') {
      installCurrentConfiguration(A, beginConfigurationOperation()); state.currentDecision = decision;
      const initial = acceptRecommendation(args); queue.shift().reject(new Error('timeout')); await initial;
      recoveredAttempt = state.pendingAcceptanceAttempt;
      state.pendingAcceptanceAttempt = null; // restart: only localStorage survives
    } else persistPendingAcceptanceAttempt(request);
    state.configuration = null; state.currentDecision = null;
    assert.equal(restorePendingAcceptanceAttempt(), true); showUnresolvedAcceptance();
    const recovery = retryPendingAcceptance(); const retry = queue.shift();
    assert.deepEqual(JSON.parse(retry.options.body), recoveredAttempt);
    if (outcome === 'site') installCurrentConfiguration(B, beginConfigurationOperation());
    if (outcome === 'navigation') { setView('review'); setView('unresolved_acceptance'); }
    let attemptB, currentB, requestB;
    if (outcome === 'B') {
      installCurrentConfiguration(B, beginConfigurationOperation());
      clearPendingAcceptanceAttempt(state.pendingAcceptanceAttempt);
      clearAcceptedMission(); state.currentDecision = {...decision, decision_id: 'decision-B'};
      setView('review');
      currentB = acceptRecommendation({...args, expectedDecisionId: 'decision-B'});
      requestB = queue.shift(); attemptB = state.pendingAcceptanceAttempt;
    }
    if (outcome === 'network') retry.reject(new Error('offline'));
    else reply(retry, outcome === 'malformed' ? {} : accepted, outcome !== 'http');
    await flush();
    if (['reopen', 'site'].includes(outcome)) {
      assert.equal(state.view, 'loading_configuration');
      const config = queue.shift(); assert.equal(config.url, '/v1/configuration'); reply(config, B); await flush();
      reply(queue.shift(), {}); await flush(); reply(queue.shift(), []);
    }
    await recovery;
    assert.equal(state.acceptedMission, null);
    if (['reopen', 'site'].includes(outcome)) assert.equal(state.view, 'availability');
    if (['reopen', 'site'].includes(outcome)) assert.equal(ui.pendingAcceptance.hidden, true);
    if (outcome === 'navigation') assert.equal(state.view, 'unresolved_acceptance');
    if (outcome === 'B') {
      assert.equal(state.view, 'review'); assert.equal(state.pendingAcceptanceAttempt, attemptB);
      assert.equal(state.acceptanceRequestOwner, attemptB.acceptance_request_id);
      assert.equal(state.acceptingRecommendation, true);
      assert.deepEqual(parsePendingAcceptance(storage.get(PENDING_ACCEPTANCE_STORAGE_KEY)), attemptB);
      requestB.reject(new Error('timeout-B')); await currentB;
    }
    if (['network', 'http', 'malformed'].includes(outcome)) {
      assert.equal(state.view, 'unresolved_acceptance'); assert.deepEqual(state.pendingAcceptanceAttempt, request);
      assert.equal(ui.retryPendingAcceptance.disabled, false);
      assert.deepEqual(parsePendingAcceptance(storage.get(PENDING_ACCEPTANCE_STORAGE_KEY)), request);
    }
    state.pendingAcceptanceAttempt = null; storage.delete(PENDING_ACCEPTANCE_STORAGE_KEY);
  }
  // Exact P2: A times out, B is installed, then blocked edit/guards refresh
  // the unresolved screen during the historical retry without revoking its owner.
  for (const outcome of ['resolved', 'navigation', 'B', 'network', 'http', 'malformed']) {
    state.pendingAcceptanceAttempt = null; state.acceptingRecommendation = false;
    clearAcceptedMission(); installCurrentConfiguration(A, beginConfigurationOperation());
    state.currentDecision = decision;
    const initial = acceptRecommendation(args); const initialRequest = queue.shift();
    initialRequest.reject(new Error('timeout-A')); await initial;
    const attemptA = state.pendingAcceptanceAttempt;
    const storedA = storage.get(PENDING_ACCEPTANCE_STORAGE_KEY);
    installCurrentConfiguration(B, beginConfigurationOperation());
    showUnresolvedAcceptance();
    const recovery = retryPendingAcceptance(); const retry = queue.shift();
    assert.equal(retry.options.body, initialRequest.options.body);
    const owner = state.acceptanceRecoveryNavigationOwner;
    const revision = state.viewRevision;
    editConfiguration(); // actual production action, blocked by its guard
    for (let i = 0; i < 3; i++) assert.equal(guardUnresolvedAcceptance(), true);
    assert.equal(state.viewRevision, revision);
    assert.equal(state.acceptanceRecoveryNavigationOwner, owner);
    assert.equal(state.view, 'unresolved_acceptance');
    assert.equal(ui.retryPendingAcceptance.disabled, true);
    let currentB, requestB, attemptB;
    if (outcome === 'navigation') {
      setView('review'); setView('unresolved_acceptance');
      assert.equal(state.viewRevision, revision + 2);
    }
    if (outcome === 'B') {
      clearPendingAcceptanceAttempt(attemptA);
      state.acceptingRecommendation = false;
      state.currentDecision = {...decision, decision_id: 'decision-B'};
      setView('review');
      currentB = acceptRecommendation({...args, expectedDecisionId: 'decision-B'});
      requestB = queue.shift(); attemptB = state.pendingAcceptanceAttempt;
    }
    if (outcome === 'network') retry.reject(new Error('offline'));
    else reply(retry, outcome === 'malformed' ? {} : accepted, outcome !== 'http');
    await flush();
    if (outcome === 'resolved') {
      assert.equal(state.pendingAcceptanceAttempt, null);
      assert.equal(state.view, 'loading_configuration');
      const configurationRequest = queue.shift();
      assert.equal(configurationRequest.url, '/v1/configuration');
      reply(configurationRequest, B); await flush();
      reply(queue.shift(), {}); await flush(); reply(queue.shift(), []);
    }
    await recovery;
    assert.equal(state.acceptedMission, null);
    assert.equal(opened, 0); assert.equal(rendered, 0);
    if (outcome === 'resolved') {
      assert.equal(state.view, 'availability'); assert.equal(ui.pendingAcceptance.hidden, true);
    } else if (outcome === 'navigation') {
      assert.equal(state.view, 'unresolved_acceptance'); assert.equal(state.pendingAcceptanceAttempt, null);
    } else if (outcome === 'B') {
      assert.equal(state.view, 'review'); assert.equal(state.pendingAcceptanceAttempt, attemptB);
      assert.equal(state.acceptanceRequestOwner, attemptB.acceptance_request_id);
      requestB.reject(new Error('timeout-B')); await currentB;
    } else {
      assert.equal(state.pendingAcceptanceAttempt, attemptA);
      assert.equal(storage.get(PENDING_ACCEPTANCE_STORAGE_KEY), storedA);
      assert.equal(state.view, 'unresolved_acceptance');
      assert.equal(ui.retryPendingAcceptance.disabled, false);
      assert.equal(state.viewRevision, revision);
    }
    assert.equal(queue.length, 0);
    state.pendingAcceptanceAttempt = null; storage.delete(PENDING_ACCEPTANCE_STORAGE_KEY);
  }
  // Delayed Tonight success/catch preserves configuration error, and away/back revokes navigation.
  for (const outcome of ['stale-success', 'stale-network', 'navigation', 'nominal', 'nominal-network']) {
    installCurrentConfiguration(A, beginConfigurationOperation()); setView('availability');
    const tonight = loadTonight({mode: 'tonight'}); const tonightRequest = queue.shift();
    if (outcome.startsWith('stale')) {
      const load = loadConfiguration(); const old = queue.shift();
      const reload = handleDecisionSiteStorageEvent({key: DECISION_SITE_STORAGE_KEY, newValue: decisionSiteFingerprint(B.site)});
      queue.shift().reject(new Error('offline')); await reload; reply(old, A); await load;
      assert.equal(state.view, 'configuration_error');
    }
    if (outcome === 'navigation') {setView('review'); setView('loading_recommendation');}
    if (outcome.endsWith('network')) tonightRequest.reject(new Error('offline'));
    else reply(tonightRequest, {...decision, status: 'available'});
    await tonight;
    assert.equal(state.view, outcome.startsWith('stale') ? 'configuration_error'
      : outcome === 'navigation' ? 'loading_recommendation'
      : outcome === 'nominal' ? 'recommendation' : 'availability');
    if (outcome.startsWith('stale')) {assert.equal(state.decisionSiteReloadRequired, true); assert.equal(state.currentDecision, null); assert.equal(ui.configurationError.hidden, false);}
    assert.equal(state.requestingRecommendation, false);
  }
  // Nominal acceptance retains its presentation and mission observation context.
  installCurrentConfiguration(A, beginConfigurationOperation()); state.currentDecision = decision;
  const nominal = acceptRecommendation(args); reply(queue.shift(), accepted); await nominal;
  assert.equal(opened, 1); assert.equal(rendered, 1);
  assert.equal(observationContext('mission').decision_id, 'decision-A');
  state.decisionSiteGeneration++;
  assert.equal(observationContext('mission'), null); // same coordinates, stale generation
  state.decisionSiteGeneration--; state.configuration = B;
  assert.equal(observationContext('mission'), null); // defensive fingerprint check
  state.configuration = A; delete state.acceptedMission.acceptedSiteGeneration;
  assert.equal(observationContext('mission'), null); // persisted/historical mission has no local provenance
  assert.equal(state.fieldObservationLock, pending);
  assert.deepEqual(pending, {uuid: 'unchanged', decision_id: 'decision-A', payload: {clouds: 'few'}});
  assert.equal(queue.length, 0);
  console.log('all-generation-scenarios-completed');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', harness + helpers + checks], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'all-generation-scenarios-completed', 'Harness did not finish all awaited scenarios'
