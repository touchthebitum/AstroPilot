"""Progressive disclosure and the actual first-configuration navigation contract."""
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest

WEB = Path(__file__).resolve().parents[2] / 'astropilot' / 'web'


class Markup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.stack = []
        self.nodes = {}
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        node = {'tag': tag, 'attrs': attrs, 'parents': self.stack.copy()}
        if attrs.get('id'):
            self.nodes[attrs['id']] = node
        if tag not in {'input', 'meta', 'link', 'br', 'hr', 'img'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                self.stack = self.stack[:index]
                break


def test_quick_observation_and_correction_markup():
    source = (WEB / 'index.html').read_text()
    markup = Markup(source)
    for field in ('clouds',):
        assert not any(p['tag'] == 'details' for p in markup.nodes[f'observation-{field}']['parents'])
    for field in ('transparency', 'wind', 'temperature', 'humidity', 'seeing', 'moon-halo',
                  'attempted-frames', 'usable-frames', 'stop-reason', 'hfr', 'hfr-unit', 'guiding'):
        ancestors = markup.nodes[f'observation-{field}']['parents']
        assert any(p['tag'] == 'details' and p['attrs'].get('class') == 'observation-advanced' for p in ancestors)
        assert all('open' not in p['attrs'] for p in ancestors if p['tag'] == 'details')
    for coordinate in ('latitude', 'longitude'):
        assert any(p['tag'] == 'details' for p in markup.nodes[f'site-{coordinate}']['parents'])
    assert 'required' in markup.nodes['site-bortle']['attrs']
    assert 'hidden' in markup.nodes['custom-equipment']['attrs']
    assert [p['attrs'].get('id') for p in markup.nodes['review-step']['parents']][-1] == 'availability-step'
    assert source.count('data-progress=') == 3
    assert 'data-progress="projects"' not in source


def test_real_onboarding_handlers_preserve_projects_draft_and_custom_validation():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the onboarding harness')
    source = (WEB / 'app.js').read_text()

    def between(start, end):
        return source[source.index(start):source.index(end)]

    helpers = between('const customEquipmentFields =', 'const configurationErrorSteps =')
    helpers += between('function prefillConfiguration()', 'function selectedEquipmentName()')
    helpers += between('function toggleEquipmentKind()', 'function progressEditorSnapshot(')
    handlers = between('document.querySelector("#site-next").addEventListener', 'for (const input of document.querySelectorAll(\'input[name="equipment-kind"]\'))')
    harness = r'''
const assert = require('node:assert/strict');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, {value: '', checked: false, hidden: false,
    dataset: {}, addEventListener(name, handler) {this[name] = handler;}});
  return elements.get(selector);
}
const back = element('back'); back.dataset.back = 'equipment';
const document = {querySelector: element, querySelectorAll: selector => selector === '[data-back]' ? [back] : []};
const projects = {existing: {intent: 'must survive'}};
const state = {configurationDraft: {site: {}, equipment: {}, projects}};
const screens = [];
function setView(view) {state.view = view; screens.push(view);}
function text(selector, value) {element(selector).textContent = value;}
function renderPresetChoices() {}
function renderProjects() {}
function renderReview() {}
function showFormError(message) {state.error = message;}
function confirmDiscardProjectProgress() {return true;}
'''
    checks = r'''
prefillConfiguration();
assert.equal(element('#site-name').value, 'Mon site');
element('#site-name').value = 'Jardin';
element('#site-latitude').value = '46.2';
element('#site-longitude').value = '7.3';
element('#site-next').click();
assert.match(state.error, /Bortle/);
assert.deepEqual(screens, []);
element('#site-bortle').value = '4';
element('input[name="equipment-kind"]:checked').value = 'preset';
element('input[name="preset-equipment"]:checked').value = 'preset-1';
setView('site'); element('#site-next').click(); element('#equipment-next').click();
assert.deepEqual(screens, ['site', 'equipment', 'review']);
assert.equal(state.configurationDraft.projects, projects);
back.click();
assert.equal(state.configurationDraft.site.name, 'Jardin');
assert.equal(element('#site-name').value, 'Jardin');
assert.equal(state.configurationDraft.equipment.preset_id, 'preset-1');
toggleEquipmentKind(); assert.equal(element('#custom-equipment').hidden, true);
element('input[name="equipment-kind"]:checked').value = 'custom';
toggleEquipmentKind(); assert.equal(element('#custom-equipment').hidden, false);
assert.ok(readCustomEquipment()[1]);
for (const [name, selector, type] of customEquipmentFields) {
  element(selector).value = type === 'number' ? '10' : 'Modèle';
  element(selector).checked = true;
}
assert.equal(Object.keys(readCustomEquipment()[0]).length, 11);
element('#custom-focal-length-mm').value = '-1';
assert.ok(readCustomEquipment()[1]);
'''
    result = subprocess.run([node, '-e', harness + helpers + handlers + checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
