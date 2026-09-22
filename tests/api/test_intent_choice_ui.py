"""Execute the browser intent-choice logic with a small DOM harness."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"
PAGE = SCRIPT.with_name("index.html")
STYLES = SCRIPT.with_name("styles.css")


def _javascript_between(start: str, end: str) -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    return source[source.index(start):source.index(end)]


def _run_javascript(source: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    result = subprocess.run(
        [node, "-e", source], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_decision_hierarchy_and_visible_copy():
    page = PAGE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")
    assert page.index('id="target-name"') < page.index('id="primary-intent-choice"')
    assert page.index('id="primary-intent-choice"') < page.index('id="decision-essential"')
    assert page.index('id="decision-essential"') < page.index('id="open-mission"')
    assert page.index('id="open-mission"') < page.index('class="decision-grid"')
    assert "Retour à Classic" not in page
    assert "Retour à la recommandation" in page
    assert 'id="open-saved-mission"' in page
    assert "white-space: nowrap" in styles
    assert "flex-direction: column; min-width: 0" in styles
    assert "justify-content: center; text-align: center" in styles


def test_saved_mission_restores_only_from_server_without_acceptance():
    helpers = _javascript_between("async function restoreSavedMission() {", "function invalidateAvailabilityForSiteChange(")
    _run_javascript("""
const assert = require('node:assert/strict');
const state = {acceptedMission: null};
const entry = {hidden: true};
const choice = {value: '', children: [], replaceChildren() { this.children = []; },
  append(item) { this.children.push(item); }};
const ui = {savedMissionEntry: entry, savedMissionTarget: {textContent: ''}, savedMissionChoice: choice};
const document = {createElement() { return {value: '', textContent: ''}; }};
let calls = [];
let changeConfiguration = false;
let payload = {status: 'accepted', mission_id: 'mission-1', selection_id: 'selection-1',
  decision_id: 'decision-1', catalog_key: 'M31', mission: {
    mission_id: 'mission-1', selection_id: 'selection-1', decision_id: 'decision-1', target: 'M31'}};
async function fetch(url, options) {
  calls.push([url, options]);
  if (changeConfiguration) state.configuration = {profile_revision: 2};
  return {ok: true, json: async () => url === '/v1/execution-sessions' ? [] : payload};
}
""" + helpers + """
(async () => {
  await restoreSavedMission();
  assert.equal(entry.hidden, false);
  assert.equal(state.acceptedMission.mission, payload.mission);
  assert.deepEqual(calls, [['/v1/accepted-mission/current', undefined],
    ['/v1/execution-sessions', undefined]]);
  payload = {...payload, selection_id: 'wrong'};
  await restoreSavedMission();
  assert.equal(entry.hidden, true);
  assert.equal(state.acceptedMission, null);
  payload = {...payload, selection_id: 'selection-1'};
  state.configuration = {profile_revision: 1};
  changeConfiguration = true;
  await restoreSavedMission();
  assert.equal(entry.hidden, true);
  assert.equal(state.acceptedMission, null);
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_configuration_changes_invalidate_restored_mission():
    initialize = _javascript_between("function initializeConfiguration(payload) {", "async function restoreSavedMission() {")
    save = _javascript_between("async function saveConfiguration() {", "const availabilityFieldsByMode")
    _run_javascript("""
const assert = require('node:assert/strict');
const entry = {hidden: false};
const button = {disabled: false};
const ui = {savedMissionEntry: entry, configurationRecover: {hidden: true},
  onboarding: {querySelector: () => ({textContent: ''})}};
const document = {querySelector: selector => selector === '#save-configuration'
  ? button : {hidden: false}};
const baseline = {configured: true, profile_revision: 1,
  site: {latitude: 1, longitude: 2, timezone: 'UTC'},
  equipment: {optics: 'A'}};
const state = {configuration: baseline, configurationDraft: {}, acceptedMission: {source: 'persisted'},
  savingConfiguration: false};
let next;
let invalidations = 0;
function clearAcceptedMission() { invalidations++; state.acceptedMission = null; entry.hidden = true; }
function invalidateAvailabilityForSiteChange() {}
function draftFromConfiguration(value) { return value; }
function hideRecoveryConfirmation() {}
function prefillConfiguration() {}
function renderAvailabilityTimezone() {}
function text() {}
function showFormError() {}
function setView(view) { state.view = view; }
function configurationPayload() { return {}; }
async function fetch() { return {ok: true, json: async () => next}; }
""" + initialize + save + """
(async () => {
  for (const changed of [
    {...baseline, site: {...baseline.site, latitude: 3}},
    {...baseline, equipment: {optics: 'B'}},
    {...baseline, profile_revision: 2},
  ]) {
    state.configuration = baseline;
    state.acceptedMission = {source: 'persisted'};
    entry.hidden = false;
    next = changed;
    await saveConfiguration();
    assert.equal(state.view, 'availability');
    assert.equal(state.acceptedMission, null);
    assert.equal(entry.hidden, true);
  }
  assert.equal(invalidations, 3);
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_failed_recommendation_retains_restored_mission_until_success():
    load = _javascript_between("async function loadTonight(availability) {", 'document.querySelector("#site-next")')
    _run_javascript("""
const assert = require('node:assert/strict');
const entry = {hidden: false};
const ui = {savedMissionEntry: entry, recommendationSubmit: {disabled: false}, refresh: {disabled: false}};
const saved = {source: 'persisted', mission: {target: 'M31'}};
const state = {acceptedMission: saved, requestingRecommendation: false, currentDecision: null};
let response;
let invalidations = 0;
function guardUnresolvedAcceptance() { return false; }
function showAvailabilityError() {}
function setView(view) { state.view = view; }
function show(view) { state.view = view; }
function clearAcceptedMission() { invalidations++; state.acceptedMission = null; entry.hidden = true; }
function normalizeError() { return ['Erreur', 'Réessayez.']; }
function renderDecision(decision) { clearAcceptedMission(); state.currentDecision = decision; state.view = 'decision'; }
async function fetch() { return response; }
""" + load + """
(async () => {
  response = {ok: false, status: 503, json: async () => ({})};
  await loadTonight({mode: 'all_night'});
  assert.equal(state.view, 'availability');
  assert.equal(state.acceptedMission, saved);
  assert.equal(entry.hidden, false);
  assert.equal(invalidations, 0);
  response = {ok: true, json: async () => ({status: 'available', decision_id: 'new'})};
  await loadTonight({mode: 'all_night'});
  assert.equal(state.view, 'decision');
  assert.equal(state.currentDecision.decision_id, 'new');
  assert.equal(state.acceptedMission, null);
  assert.equal(entry.hidden, true);
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_reopening_saved_mission_does_not_post_acceptance():
    listener = _javascript_between('ui.openSavedMission.addEventListener("click", () => {', 'document.querySelector("#session-choice").addEventListener(')
    _run_javascript("""
const assert = require('node:assert/strict');
let openSavedMission;
let shown = 0;
const saved = {source: 'persisted', mission: {target: 'M31'}};
const state = {acceptedMission: saved, savedMissions: [saved]};
const ui = {openSavedMission: {addEventListener(event, callback) { openSavedMission = callback; }},
  savedMissionChoice: {value: ''}, mission: {showModal() { shown++; }}};
function renderMission(mission) { assert.equal(mission, saved.mission); }
function fetch() { throw new Error('reopening must not make a request'); }
""" + listener + """
openSavedMission();
assert.equal(shown, 1);
state.acceptedMission = null;
state.savedMissions = [];
openSavedMission();
assert.equal(shown, 1);
""")


def test_alternative_empty_reason_and_risk_levels_are_presentation_only():
    helper = _javascript_between("function alternativeReasonText(reason) {", "function intentMode(subject) {")
    _run_javascript("""
const assert = require('node:assert/strict');
""" + helper + """
assert.equal(alternativeReasonText({message: ' . '}), null);
assert.equal(alternativeReasonText({message: '  '}), null);
assert.equal(alternativeReasonText({message: 'Fiabilité météo limitée.'}), 'Fiabilité météo limitée.');
""")
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'low: "faible", medium: "modéré", high: "élevé"' in script
    assert 'labels.riskLevels[level]' in script


def test_intent_choice_unique_multiple_none_and_legacy():
    helpers = _javascript_between("function intentMode(subject) {", "function renderAlternatives(decision) {")
    _run_javascript("""
const assert = require('node:assert/strict');
class Element {
  constructor() { this.children = []; this.hidden = false; this.value = ''; this.listeners = {}; }
  replaceChildren() { this.children = []; this.textContent = ''; }
  append(...items) { this.children.push(...items); }
  querySelector(selector) { return this.children.find(item => item.tagName === selector); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}
const document = { createElement: tag => Object.assign(new Element(), {tagName: tag}) };
function Option(label, value) { this.label = label; this.value = value; }
function showAcceptanceStatus() {}
function restoreAcceptanceControls() {}
""" + helpers + """
const options = [
  {acquisition_intent_id: 'sh2-129_ha', label: 'Hα · Sh2-129'},
  {acquisition_intent_id: 'ou4_oiii', label: 'OIII · Ou4'},
];
const unique = {acquisition_intent_selection_status: 'single_eligible_intent',
  selected_acquisition_intent_id: 'sh2-129_ha',
  viable_acquisition_intent_ids: ['sh2-129_ha'], acquisition_intent_options: [options[0]]};
let container = new Element();
renderIntentChoice(container, unique, 'primary-intent');
assert.equal(container.querySelector('select'), undefined);
assert.match(container.textContent, /Hα · Sh2-129/);
assert.equal(chosenIntent(unique, container), 'sh2-129_ha');

const multiple = {...unique, acquisition_intent_selection_status: 'no_clear_preference',
  selected_acquisition_intent_id: null, viable_acquisition_intent_ids: ['sh2-129_ha', 'ou4_oiii'],
  acquisition_intent_options: options};
container = new Element();
renderIntentChoice(container, multiple, 'primary-intent');
const select = container.querySelector('select');
assert.deepEqual(select.children.map(option => option.value), ['', 'sh2-129_ha', 'ou4_oiii']);
assert.equal(chosenIntent(multiple, container), undefined);
select.value = 'ou4_oiii';
assert.equal(chosenIntent(multiple, container), 'ou4_oiii');
select.value = 'invented';
assert.equal(chosenIntent(multiple, container), undefined);

const none = {...multiple, acquisition_intent_selection_status: 'no_eligible_intent',
  viable_acquisition_intent_ids: [], acquisition_intent_options: []};
container = new Element();
renderIntentChoice(container, none, 'primary-intent');
assert.match(container.children[0].textContent, /Aucune acquisition recommandée/);
assert.equal(chosenIntent(none, container), undefined);

const legacy = {};
container = new Element();
renderIntentChoice(container, legacy, 'primary-intent');
assert.equal(container.hidden, true);
assert.equal(chosenIntent(legacy, container), null);
""")


def test_acceptance_request_keeps_exact_choice_and_blocks_missing_choice():
    helpers = _javascript_between("async function acceptRecommendation({", "async function loadTonight(availability) {")
    _run_javascript("""
const assert = require('node:assert/strict');
let chosen = undefined;
let sent = [];
const decision = {decision_id: 'decision-1', catalog_key: 'M31',
  target_decision_status: 'recommended', alternatives: []};
const state = {currentDecision: decision, acceptingRecommendation: false,
  acceptedMission: null, acceptanceBlocked: false};
const ui = {openMission: {dataset: {acceptanceSource: 'primary_recommendation', catalogKey: 'M31'}},
  primaryIntentChoice: {}, mission: {showModal() {}}};
function chosenIntent() { return chosen; }
function intentMode() { return 'multiple'; }
function acceptanceControls() { return [ui.openMission, {dataset: {
  acceptanceSource: 'alternative', catalogKey: 'M33'},
  closest: () => ({querySelector: () => ({})})}]; }
function showAcceptedIntent() { return true; }
function showAcceptanceStatus(message) { globalThis.lastStatus = message; }
function restoreAcceptanceControls() {}
function disableAcceptanceControls() {}
function acceptanceAttempt(intent) { return {...intent, acceptance_request_id: 'request-1',
  selected_at: '2026-09-01T20:00:00.000Z'}; }
function clearPendingAcceptanceAttempt() {}
function renderMission() {}
function show() {}
function showMessage() {}
function hasUnresolvedAcceptance() { return false; }
function showUnresolvedAcceptance() { throw new Error('unexpected unresolved acceptance'); }
function acceptanceError() { return ['Choix refusé', true]; }
async function fetch(url, options) {
  const request = JSON.parse(options.body);
  sent.push(request);
  return {ok: true, json: async () => ({status: 'accepted', decision_id: 'decision-1',
    catalog_key: request.selected_catalog_key, selected_acquisition_intent_id: chosen,
    selection_id: 'selection-1', mission_id: 'mission-1',
    mission: {decision_id: 'decision-1', selection_id: 'selection-1', mission_id: 'mission-1'}})};
}
""" + helpers + """
(async () => {
  const args = {source: 'primary_recommendation', selectedCatalogKey: 'M31',
    expectedDecisionId: 'decision-1', triggerButton: {setAttribute() {}, removeAttribute() {}},
    selectedTarget: 'M31'};
  await acceptRecommendation(args);
  assert.equal(sent.length, 0);
  assert.match(lastStatus, /Choisissez d’abord/);
  chosen = 'ou4_oiii';
  await acceptRecommendation(args);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].acquisition_intent_id, 'ou4_oiii');
  state.acceptedMission = null;
  chosen = 'sh2-129_ha';
  await acceptRecommendation(args);
  assert.equal(sent[1].acquisition_intent_id, 'sh2-129_ha');
  state.acceptedMission = null;
  decision.alternatives.push({catalog_key: 'M33', target_decision_status: 'viable'});
  await acceptRecommendation({...args, source: 'alternative', selectedCatalogKey: 'M33',
    triggerButton: {...args.triggerButton, closest: () => ({querySelector: () => ({})})}});
  assert.equal(sent[2].source, 'alternative');
  assert.equal(sent[2].acquisition_intent_id, 'sh2-129_ha');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_rejected_intent_is_explained_without_internal_code():
    helper = _javascript_between("function acceptanceError(code, status) {", "async function retryPendingAcceptance() {")
    _run_javascript("""
const assert = require('node:assert/strict');
""" + helper + """
const [message, blocked] = acceptanceError('selected_acquisition_intent_not_viable', 409);
assert.equal(blocked, true);
assert.match(message, /prise de vue/);
assert.doesNotMatch(message, /selected_acquisition_intent|409/);
""")


def test_primary_none_hides_mission_and_legacy_keeps_action():
    render = _javascript_between("function renderDecision(decision) {", "const customEquipmentFields")
    mode = _javascript_between("function intentMode(subject) {", "function renderIntentChoice(container, subject, selectId) {")
    _run_javascript("""
const assert = require('node:assert/strict');
const values = {};
const state = {};
const ui = {openMission: {dataset: {}}, primaryIntentChoice: {}, recommendationConfidence: {}};
const document = {querySelector: () => ({style: {}})};
const labels = {actions: {start_project: 'Commencer ce projet'}, quality: {}, factors: {}};
function clearAcceptedMission() {}
function clock() { return null; }
function duration() { return 'Non précisée'; }
function dateLabel() { return 'Ce soir'; }
function text(key, value) { values[key] = value; }
function setList() {}
function reasonText(value) { return value; }
function renderWeatherTrust() {}
function renderIntentChoice() {}
function renderAlternatives() {}
function restoreAcceptanceControls() {}
function show() {}
function formatRecommendationConfidence() { return 'Non disponible'; }
function intentReady() { return true; }
""" + mode + render + """
const base = {decision_id: 'decision-1', catalog_key: 'M31',
  target_decision_status: 'recommended', action: 'start_project'};
renderDecision({...base, acquisition_intent_selection_status: 'no_eligible_intent',
  selected_acquisition_intent_id: null, viable_acquisition_intent_ids: []});
assert.equal(ui.openMission.hidden, true);
assert.match(values['#recommendation'], /Aucune acquisition recommandée/);
renderDecision(base);
assert.equal(ui.openMission.hidden, false);
assert.equal(ui.openMission.disabled, false);
assert.equal(values['#recommendation'], 'Commencer ce projet');
""")


def test_actionable_alternative_uses_its_own_viable_frontier():
    helpers = _javascript_between("function intentMode(subject) {", "function renderAlternatives(decision) {")
    render = _javascript_between("function renderAlternatives(decision) {", "function acceptanceControls() {")
    _run_javascript("""
const assert = require('node:assert/strict');
class Element {
  constructor(tagName = '') {
    this.tagName = tagName; this.children = []; this.dataset = {}; this.hidden = false;
    this.classList = {add() {}}; this.value = '';
  }
  replaceChildren() { this.children = []; }
  append(...items) { this.children.push(...items); }
  querySelector(tag) { return this.children.find(item => item.tagName === tag); }
  addEventListener() {}
}
const document = {createElement: tag => new Element(tag)};
function Option(label, value) { this.label = label; this.value = value; }
const ui = {alternativesList: new Element(), alternatives: {hidden: true}};
function clearAlternatives() { ui.alternativesList.replaceChildren(); ui.alternatives.hidden = true; }
function alternativeReasonText() { return null; }
function showAcceptanceStatus() {}
function restoreAcceptanceControls() {}
function acceptRecommendation() {}
""" + helpers + render + """
const alternative = {catalog_key: 'M33', target: 'Autre champ', target_decision_status: 'viable',
  acquisition_intent_selection_status: 'no_clear_preference',
  selected_acquisition_intent_id: null,
  viable_acquisition_intent_ids: ['ou4_oiii', 'sh2-129_ha'],
  acquisition_intent_options: [
    {acquisition_intent_id: 'ou4_oiii', label: 'OIII · Ou4'},
    {acquisition_intent_id: 'sh2-129_ha', label: 'Hα · Sh2-129'}]};
renderAlternatives({decision_id: 'decision-1', alternatives: [alternative]});
assert.equal(ui.alternatives.hidden, false);
const card = ui.alternativesList.children[0];
const choice = card.children[0].children.find(child => child.className === 'intent-choice');
assert.deepEqual(choice.querySelector('select').children.map(option => option.value),
  ['', 'ou4_oiii', 'sh2-129_ha']);
assert.equal(card.children[1].hidden, false);
""")


def test_accepted_intent_locks_primary_and_alternative_and_uses_canonical_replay():
    choice = _javascript_between("function intentMode(subject) {", "function renderAlternatives(decision) {")
    controls = _javascript_between("function acceptanceControls() {", "function sameAcceptanceIntent(attempt, intent) {")
    accept = _javascript_between("async function acceptRecommendation({", "async function loadTonight(availability) {")
    _run_javascript("""
const assert = require('node:assert/strict');
class Element {
  constructor(tagName = '') {
    this.tagName = tagName; this.children = []; this.dataset = {}; this.hidden = false;
    this.value = ''; this.listeners = {}; this.disabled = false; this.textContent = '';
  }
  replaceChildren() { this.children = []; this.textContent = ''; }
  append(...items) { this.children.push(...items); }
  querySelector(tag) { return this.children.find(item => item.tagName === tag); }
  querySelectorAll(tag) { return this.children.filter(item => item.tagName === tag); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute() {}
  removeAttribute() {}
  closest() { return this.card || null; }
}
const document = {createElement: tag => new Element(tag)};
function Option(label, value) { this.label = label; this.value = value; }
const options = [
  {acquisition_intent_id: 'A', label: 'Hα · Champ'},
  {acquisition_intent_id: 'B', label: 'OIII · Champ'},
];
const multi = {acquisition_intent_selection_status: 'no_clear_preference',
  selected_acquisition_intent_id: null, viable_acquisition_intent_ids: ['A', 'B'],
  acquisition_intent_options: options};
const ui = {openMission: new Element('button'), primaryIntentChoice: new Element(),
  alternativesList: new Element(), mission: {showModal() { opened++; }}};
const state = {currentDecision: null, acceptedMission: null, acceptingRecommendation: false,
  acceptanceBlocked: false, pendingAcceptanceAttempt: null};
let sent = [], canonical = 'A', opened = 0, status = '';
function showAcceptanceStatus(message) { status = message; }
function acceptanceAttempt(intent) { return {...intent, acceptance_request_id: 'request-1'}; }
function clearPendingAcceptanceAttempt() {}
function renderMission() {}
function show() {}
function showMessage() {}
function hasUnresolvedAcceptance() { return false; }
function showUnresolvedAcceptance() { throw new Error('unexpected unresolved acceptance'); }
function acceptanceError() { return ['Erreur', true]; }
async function fetch(_url, options) {
  const request = JSON.parse(options.body); sent.push(request);
  return {ok: true, json: async () => ({status: 'accepted', decision_id: request.decision_id,
    catalog_key: request.selected_catalog_key, selected_acquisition_intent_id: canonical,
    selection_id: 'selection-1', mission_id: 'mission-1',
    mission: {decision_id: request.decision_id, selection_id: 'selection-1', mission_id: 'mission-1'}})};
}
""" + choice + controls + accept + """
async function exercise(source, localChoice, serverChoice) {
  state.currentDecision = {decision_id: 'decision-1', catalog_key: 'M31', target: 'Cible',
    target_decision_status: 'recommended', ...multi, alternatives: [
      {catalog_key: 'M33', target_decision_status: 'viable', ...multi}]};
  state.acceptedMission = null;
  ui.openMission.dataset = {acceptanceSource: 'primary_recommendation', catalogKey: 'M31',
    decisionId: 'decision-1'};
  ui.openMission.textContent = 'Photographier cette cible';
  ui.alternativesList.replaceChildren();
  const card = new Element('article');
  const alternativeChoice = new Element();
  card.querySelector = tag => tag === '.intent-choice' ? alternativeChoice : null;
  const alternativeButton = new Element('button');
  alternativeButton.card = card;
  alternativeButton.dataset = {acceptanceSource: 'alternative', catalogKey: 'M33',
    decisionId: 'decision-1'};
  card.append(alternativeButton);
  ui.alternativesList.append(alternativeButton);
  renderIntentChoice(ui.primaryIntentChoice, state.currentDecision, 'primary-intent');
  renderIntentChoice(alternativeChoice, state.currentDecision.alternatives[0], 'alternative-intent');
  const container = source === 'alternative' ? alternativeChoice : ui.primaryIntentChoice;
  const select = container.querySelector('select');
  assert.equal(chosenIntent(source === 'alternative' ? state.currentDecision.alternatives[0]
    : state.currentDecision, container), undefined);
  select.value = 'B'; select.listeners.change();
  assert.equal(ui.openMission.disabled, source === 'alternative');
  select.value = localChoice; select.listeners.change();
  canonical = serverChoice;
  const button = source === 'alternative' ? alternativeButton : ui.openMission;
  const args = {source, selectedCatalogKey: source === 'alternative' ? 'M33' : 'M31',
    expectedDecisionId: 'decision-1', triggerButton: button, selectedTarget: 'Cible'};
  const before = sent.length;
  await acceptRecommendation(args);
  assert.equal(sent.length, before + 1);
  assert.equal(sent.at(-1).acquisition_intent_id, localChoice);
  assert.equal(state.acceptedMission.acquisitionIntentId, serverChoice);
  assert.equal(container.querySelector('select'), undefined);
  assert.match(container.textContent, new RegExp(serverChoice === 'A' ? 'Hα' : 'OIII'));
  assert.equal(button.textContent, 'Ouvrir la mission');
  assert.equal(button.disabled, false);
  select.value = serverChoice === 'A' ? 'B' : 'A'; select.listeners.change();
  assert.equal(button.disabled, false);
  assert.equal(container.querySelector('select'), undefined);
  await acceptRecommendation(args);
  assert.equal(sent.length, before + 1);
  assert.equal(opened > 1, true);
}
async function exerciseUniqueAndLegacy() {
  const unique = {acquisition_intent_selection_status: 'single_eligible_intent',
    selected_acquisition_intent_id: 'A', viable_acquisition_intent_ids: ['A'],
    acquisition_intent_options: [options[0]]};
  state.acceptedMission = null;
  state.currentDecision = {decision_id: 'decision-1', catalog_key: 'M31',
    target_decision_status: 'recommended', ...unique, alternatives: []};
  renderIntentChoice(ui.primaryIntentChoice, state.currentDecision, 'primary-intent');
  assert.equal(ui.primaryIntentChoice.querySelector('select'), undefined);
  canonical = 'A';
  await acceptRecommendation({source: 'primary_recommendation', selectedCatalogKey: 'M31',
    expectedDecisionId: 'decision-1', triggerButton: ui.openMission, selectedTarget: 'Cible'});
  assert.equal(state.acceptedMission.acquisitionIntentId, 'A');
  assert.match(ui.primaryIntentChoice.textContent, /Hα/);

  state.acceptedMission = null;
  state.currentDecision = {decision_id: 'decision-1', catalog_key: 'M31',
    target_decision_status: 'recommended', alternatives: [
      {catalog_key: 'M33', target_decision_status: 'viable'}]};
  ui.alternativesList.replaceChildren();
  const button = new Element('button');
  button.dataset = {acceptanceSource: 'alternative', catalogKey: 'M33', decisionId: 'decision-1'};
  button.card = {querySelector: () => null};
  ui.alternativesList.append(button);
  canonical = null;
  await acceptRecommendation({source: 'alternative', selectedCatalogKey: 'M33',
    expectedDecisionId: 'decision-1', triggerButton: button, selectedTarget: 'Cible'});
  assert.equal(state.acceptedMission.acquisitionIntentId, null);
  assert.equal(button.textContent, 'Ouvrir la mission');
}
(async () => {
  await exercise('primary_recommendation', 'A', 'A');
  await exercise('alternative', 'A', 'A');
  await exercise('primary_recommendation', 'B', 'A');
  await exercise('alternative', 'B', 'A');
  await exerciseUniqueAndLegacy();
})().catch(error => { console.error(error); process.exitCode = 1; });
""")
