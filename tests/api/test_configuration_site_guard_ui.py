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
    helpers += between('function initializeConfiguration(', 'async function restoreSavedMission(')
    helpers += between('async function loadConfiguration(', 'const availabilityFieldsByMode')
    helpers += between('async function acceptRecommendation(', 'async function loadTonight(')
    helpers += between('async function restoreSavedMission(', 'function invalidateAvailabilityForSiteChange(')
    harness = r'''
const assert = require('node:assert/strict');
const A = {configured: true, profile_revision: 1, equipment: {}, site: {latitude: 47, longitude: 6, timezone: 'Europe/Zurich'}};
const B = {...A, site: {...A.site, latitude: 46}};
const C = {...A, site: {...A.site, latitude: 45}};
const element = () => ({hidden: true, disabled: false, querySelector: element,
  replaceChildren() {}, append() {}, focus() {}});
const document = {querySelector: element, createElement: element};
let opened = 0, rendered = 0, queue = [];
const ui = {addObservationMessage: element(), addObservationDecision: element(),
  configurationRecover: element(), configurationRecoveryConfirm: element(),
  configurationRecoveryConfirmation: element(), onboarding: element(),
  savedMissionEntry: element(), savedMissionChoice: element(), savedMissionTarget: element(),
  primaryIntentChoice: element(), mission: {showModal() { opened++; }}};
const state = {configuration: A, configurationGeneration: 0, decisionSiteGeneration: 0,
  acceptedMission: null, currentDecision: null, savedMissions: [], configurationDraft: A};
const pending = {uuid: 'unchanged', decision_id: 'decision-A', payload: {clouds: 'few'}};
state.fieldObservationLock = pending;
const localStorage = {setItem() {}};
function fetch(url, options) { return new Promise((resolve, reject) => queue.push({url, options, resolve, reject})); }
const reply = (request, payload, ok = true) => request.resolve({ok, status: ok ? 200 : 503, json: async () => payload});
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
function text() {}
function syncFieldObservationContext() {}
function invalidateRecentDecisions() {}
function clearAcceptedMission() { state.acceptedMission = null; }
function invalidateAvailabilityForSiteChange() {}
function siteTimezone() { return state.configuration.site.timezone; }
function siteConfigurationIdentity() { return JSON.stringify(state.configuration.site); }
function currentSession() { return null; }
function draftFromConfiguration(payload) { return payload; }
function hideRecoveryConfirmation() {}
function prefillConfiguration() {}
function renderAvailabilityTimezone() {}
function restorePendingFieldObservationInventory() {}
function guardUnresolvedAcceptance() { return false; }
function setView(view) { state.view = view; }
function showFormError() {}
function renderReview() {}
function restoreAcceptanceControls() {}
function disableAcceptanceControls() {}
function showConfigurationError() { state.error = true; }
function configurationPayload() { return state.configurationDraft; }
function chosenIntent() { return null; }
function acceptanceAttempt(intent) { return {...intent, acceptance_request_id: 'canonical-uuid'}; }
function clearPendingAcceptanceAttempt() { state.pendingAcceptanceAttempt = null; }
function showAcceptanceStatus(message) { state.status = message; }
function intentMode() { return 'legacy'; }
function acceptanceControls() { return []; }
function showAcceptedIntent() { return true; }
function showUnresolvedAcceptance() { state.unresolved = true; }
function hasUnresolvedAcceptance() { return !!state.pendingAcceptanceAttempt; }
function renderMission() { rendered++; }
function show() {}
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
  assert.equal(state.view, 'loading_configuration'); // obsolete response did not navigate

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
  assert.match(state.status, /décision précédente/);

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
