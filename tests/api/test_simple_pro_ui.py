"""Presentation preference must not mutate any business state."""
import json
from pathlib import Path
import shutil
import subprocess

WEB = Path(__file__).parents[2] / 'astropilot/web'


def test_mode_preference_and_reversible_disclosure(tmp_path):
    source = (WEB / 'app.js').read_text().split('initializeUiMode();', 1)[0]
    harness = r'''
function updateHistoryFilterSummary() {}
const listeners = {}, windowListeners = {}, writes = [];
const select = {value: '', addEventListener: (name, fn) => listeners[name] = fn};
const labels = {};
const details = [{open:false, inputs:{hfr:'2.15', rms:'0.63'}}];
const business = {currentDecision:{id:'decision'}, acceptedMission:{id:'mission'}, pending:{id:'pending'}, filters:{provider:'retained'}, selection:'observation'};
const before = JSON.stringify(business);
const document = {documentElement:{dataset:{}}, querySelector: () => select,
 getElementById: id => labels[id] ||= {}, querySelectorAll: selector => selector === "[data-mode-disclosure]" ? details : []};
const window = {addEventListener: (name, fn) => windowListeners[name] = fn};
let saved = null;
const localStorage = {getItem: () => saved, setItem: (key,value) => {writes.push([key,value]); saved=value;}};
'''
    checks = r'''
initializeUiMode();
const defaults = document.documentElement.dataset.uiMode;
listeners.change({target:{value:'pro'}});
const pro = [select.value, details[0].open, labels['history-open'].textContent];
initializeUiMode();
const reload = select.value;
listeners.change({target:{value:'simple'}});
const simple = [select.value, details[0].open, labels['outcome-reopen'].textContent];
details[0].open = true;
windowListeners.storage({key:UI_MODE_KEY,newValue:'simple'});
windowListeners.storage({key:UI_MODE_KEY,newValue:'simple'});
if (!details[0].open) throw Error('same Simple mode closes disclosure');
windowListeners.storage({key:UI_MODE_KEY,newValue:'pro'});
const synchronized = select.value;
details[0].open = false;
windowListeners.storage({key:UI_MODE_KEY,newValue:'pro'});
if (details[0].open) throw Error('same Pro mode churn');
windowListeners.storage({key:UI_MODE_KEY,newValue:'invalid'});
const invalid = select.value;
windowListeners.storage({key:'other',newValue:'pro'});
const ignored = select.value;
saved='invalid'; initializeUiMode();
const output = {defaults,pro,reload,simple,synchronized,invalid,ignored,
 stable:JSON.stringify(business)===before, inputs:details[0].inputs, writes};
'''
    engine = shutil.which('node') or shutil.which('osascript')
    assert engine
    script = tmp_path / 'mode.js'
    script.write_text(harness + source + checks + ('\nconsole.log(JSON.stringify(output));' if Path(engine).name == 'node' else '\nJSON.stringify(output);'))
    args = [engine] if Path(engine).name == 'node' else [engine, '-l', 'JavaScript']
    result = json.loads(subprocess.check_output([*args, str(script)], text=True))
    assert result['defaults'] == result['invalid'] == result['ignored'] == 'simple'
    assert result['reload'] == result['synchronized'] == 'pro'
    assert result['pro'] == ['pro', True, 'Historique des validations']
    assert result['simple'] == ['simple', False, 'Mes observations']
    assert result['stable'] and result['inputs'] == {'hfr':'2.15', 'rms':'0.63'}
    assert result['writes'] == [['nightmerit.ui-mode.v1','pro'],['nightmerit.ui-mode.v1','simple']]


def test_shared_dom_and_technical_disclosures():
    html = (WEB / 'index.html').read_text()
    script = (WEB / 'app.js').read_text()
    css = (WEB / 'styles.css').read_text()
    assert 'data-ui-mode="simple"' in html
    assert 'aria-label="Mode de présentation"' in html
    assert html.index('id="history-current-site"') < html.index('<summary id="history-filter-summary"')
    assert 'id="outcome-trace"' in html
    assert 'html[data-ui-mode="simple"] [data-pro-only]' in css
    summary_rule = css.split('#history-filter-summary {', 1)[1].split('}', 1)[0]
    assert 'overflow-wrap: anywhere' in summary_rule
    assert 'min-width: 0' in summary_rule
    mode = script.split('initializeUiMode();', 1)[0]
    for forbidden in ['currentDecision', 'acceptedMission', 'fetch(', 'historyParameters', '.reset(']:
        assert forbidden not in mode
