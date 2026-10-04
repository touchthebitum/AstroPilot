from pathlib import Path
import runpy
import subprocess

import pytest

ROOT = Path(__file__).parents[2]
UTIL = runpy.run_path(str(ROOT / 'tests/api/test_field_observation_ui.py'))


def test_history_ui_empty_degraded_stale_filters_navigation_cursor():
    engine = UTIL['javascript_engine']()
    if not engine or engine.endswith('osascript'):
        pytest.skip('Node required')
    source = (ROOT / 'astropilot/web/app.js').read_text()
    helpers = source[source.index('// Outcome History:'):source.index('// End Outcome History.')]
    program = r'''
const assert = require('assert').strict;
const state = {configuration:{site:{latitude:46.12,longitude:7.34}}};
const historyState = {generation:0, cursor:null, open:true};
const elements = new Map();
function make() { return {textContent:'', value:'', checked:false, hidden:false, children:[], events:{}, classList:{toggle(){}},
  replaceChildren(){this.children=[];}, appendChild(node){this.children.push(node);},
  addEventListener(event,fn){this.events[event]=fn;}, showModal(){}, close(){this.events.close?.();}}; }
function element(id) { if(!elements.has(id)) elements.set(id, make()); return elements.get(id); }
const document = {documentElement:{dataset:{uiMode:"simple"}},querySelector:element,createElement:make};
const fields = new Map();
element('#history-filters').elements = {namedItem(name){if(!fields.has(name))fields.set(name,make());return fields.get(name);}};
let fetch;
HELPERS
const empty = {rows:[], statistics:null, readable_filtered_rows:0, next_cursor:null,
  completeness:'degraded', certification:'statistics_suspended', diagnostics:[{code:'corrupt_document'}]};
const response = (status,data) => ({ok:status===200,status,json:async()=>data});
function content(node){return [node.textContent,...node.children.map(content)].join(' ');}
(async()=>{
  fetch=async(url,options)=>{assert.equal(options.method,'GET');return response(200,empty);};
  await loadOutcomeHistory();
  assert.match(content(element('#history-table')),/Aucune comparaison/);
  assert.match(content(element('#history-statistics')),/suspendues/);
  assert.match(element('#history-message').textContent,/corrupt_document/);
  let resolve;
  fetch=()=>new Promise(r=>resolve=r);
  const old=loadOutcomeHistory();
  fields.get('provider').value='new-provider';
  element('#history-filters').events.input();
  element('#history-message').textContent='new filter';
  resolve(response(200,empty));await old;
  assert.equal(element('#history-message').textContent,'new filter');
  const navigation=loadOutcomeHistory();invalidateOutcomeHistory();
  element('#history-message').textContent='navigation';resolve(response(200,empty));await navigation;
  assert.equal(element('#history-message').textContent,'navigation');
  const closing=loadOutcomeHistory();element('#history-dialog').events.close();
  element('#history-message').textContent='closed';resolve(response(200,empty));await closing;
  assert.equal(element('#history-message').textContent,'closed');
  historyState.open=true;
  fetch=async()=>response(409,{});
  historyState.cursor='opaque';await loadOutcomeHistory(true);
  assert.match(element('#history-message').textContent,/données ont changé/);
  assert.equal(historyState.cursor,null);
  fields.get('include_superseded').checked=true;
  fields.get('observed_from').value='2026-01-01T00:00:00';
  fetch=async(url)=>{assert.match(url,/include_superseded=true/);assert.match(url,/observed_from=2026-01-01T00%3A00%3A00Z/);return response(200,empty);};
  await loadOutcomeHistory();
  fields.get('provider').value='retained';
  fields.get('mode').value='execution'; fields.get('status').value='partial';
  fields.get('latitude').value='46.12'; fields.get('longitude').value='7.34';
  updateHistoryFilterSummary();
  assert.equal(element('#history-filter-summary').textContent,'Filtres actifs : ce site · source : retained · exécution · couverture partielle · observations remplacées incluses — Modifier');
  await loadOutcomeHistory();
  assert.match(element('#history-filter-summary').textContent,/ce site/);
  document.documentElement.dataset.uiMode='pro'; updateHistoryFilterSummary();
  assert.equal(element('#history-filter-summary').textContent,'Filtres avancés');
  document.documentElement.dataset.uiMode='simple'; updateHistoryFilterSummary();
  assert.match(element('#history-filter-summary').textContent,/retained/);
  for(const field of fields.values()){field.value='';field.checked=false;}
  updateHistoryFilterSummary();
  assert.equal(element('#history-filter-summary').textContent,'Filtres actifs : observations actuelles — Modifier');
  fields.get('variable').value='temperature_c';fields.get('latitude').value='0';
  updateHistoryFilterSummary();
  assert.match(element('#history-filter-summary').textContent,/site personnalisé · température/);
  const row={observation_id:'o',evaluation_id:'e',decision_id:'d',execution_id:null,observed_at_utc:null,site:null,context:{},mode:'decision_only',
    status:'not_comparable',supersession:'indeterminate',results:[],compared_providers:[],evidence_providers:['p'],unknown_dimensions:{site:'missing'},assessment:{status:'partial'}};
  renderOutcomeHistory({...empty,rows:[row],readable_filtered_rows:1});
  const rendered=content(element('#history-table'));
  assert.match(rendered,/Inconnue/);assert.match(rendered,/Inconnu/);assert.match(rendered,/Providers comparés : inconnus/);
  assert.match(rendered,/Suffisance des éléments d’évaluation/);
  assert.doesNotMatch(rendered,/meilleur provider|qualité forecast|réussite photo/);
  const stats={n_evaluations:0,n_observations:0,n_decisions:0,n_executions:0,coverage:{comparable:0,partial:0,not_comparable:0},variables:{},
    clouds:{n:0,match:0,mismatch:0,forecast_x_observed:{}},reason_observation_counts:{}};
  renderOutcomeHistory({...empty,statistics:stats,completeness:'complete',certification:'certified'});
  assert.match(content(element('#history-statistics')),/N évaluations = 0/);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('HELPERS',helpers)
    completed = subprocess.run([engine, '-e', program], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_history_markup_and_navigation_invalidation():
    source = (ROOT / 'astropilot/web/app.js').read_text()
    markup = (ROOT / 'astropilot/web/index.html').read_text()
    assert 'function setView(view) {\n  invalidateOutcomeHistory();' in source
    assert 'id="history-dialog"' in markup
    assert 'partly_cloudy' in source[source.index('// Outcome History:'):source.index('// End Outcome History.')]
    assert 'textContent = value' in source[source.index('// Outcome History:'):source.index('// End Outcome History.')]


@pytest.mark.parametrize(('values', 'included', 'expected'), [
    ({'provider': 'retained'}, False, 'source : retained · observations actuelles'),
    ({'provider': 'open-meteo'}, False, 'Open-Meteo · observations actuelles'),
    ({}, True, 'observations remplacées incluses'),
    ({'mode': 'decision_only'}, False, 'décision seule · observations actuelles'),
    ({'status': 'not_comparable'}, False, 'couverture non comparable · observations actuelles'),
    ({'latitude': '46.12', 'longitude': '7.34'}, False, 'ce site · observations actuelles'),
    ({'latitude': '0', 'longitude': '0'}, False, 'site personnalisé · observations actuelles'),
    ({}, False, 'observations actuelles'),
])
def test_live_advanced_filter_summary(values, included, expected):
    import json
    engine = UTIL['javascript_engine']()
    if not engine or engine.endswith('osascript'):
        pytest.skip('Node required')
    source = (ROOT / 'astropilot/web/app.js').read_text()
    helper = source[source.index('function updateHistoryFilterSummary()'):source.index('function historyParameters()')]
    program = r'''
const assert = require('assert').strict;
const fields = Object.fromEntries(['latitude','longitude','provider','variable','mode','status','include_superseded'].map(name=>[name,{value:'',checked:false}]));
const summary = {textContent:''};
const form = {elements:{namedItem:name=>fields[name]}};
const state = {configuration:{site:{latitude:46.12,longitude:7.34}}};
const document = {documentElement:{dataset:{uiMode:'simple'}},querySelector:selector=>selector==='#history-filters'?form:summary};
''' + helper + f'''
for (const [name,value] of Object.entries({json.dumps(values)})) fields[name].value=value;
fields.include_superseded.checked={json.dumps(included)};
updateHistoryFilterSummary();
assert.equal(summary.textContent,{json.dumps('Filtres actifs : ' + expected + ' — Modifier')});
'''
    result = subprocess.run([engine, '-e', program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
