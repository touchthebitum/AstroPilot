"""Execute the browser intent-choice logic with a small DOM harness."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


def _javascript_between(start: str, end: str) -> str:
    source = SCRIPT.read_text()
    return source[source.index(start):source.index(end)]


def _run_javascript(source: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the dynamic UI test")
    result = subprocess.run(
        [node, "-e", source], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


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
const ui = {openMission: {}, primaryIntentChoice: {}, mission: {showModal() {}}};
function chosenIntent() { return chosen; }
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
