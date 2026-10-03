from pathlib import Path
import runpy
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
UTIL = runpy.run_path(str(Path(__file__).with_name('test_field_observation_ui.py')))


def test_outcome_layout_keeps_result_below_controls_at_all_widths():
    from html.parser import HTMLParser
    import re

    class OutcomeParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_panel = False
            self.children = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'section' and 'outcome-panel' in attrs.get('class', '').split():
                self.in_panel = True
            elif self.in_panel:
                self.children.append((tag, attrs))

        def handle_endtag(self, tag):
            if tag == 'section':
                self.in_panel = False

    parser = OutcomeParser()
    parser.feed((ROOT / 'astropilot/web/index.html').read_text())
    assert [tag for tag, _ in parser.children] == ['h3', 'label', 'select', 'button', 'button', 'div']
    result = parser.children[-1][1]
    assert result['id'] == 'outcome-result'
    assert result['role'] == 'status' and result['aria-live'] == 'polite'
    css = (ROOT / 'astropilot/web/styles.css').read_text()
    rules = re.findall(r'([^{}]+)\{([^{}]*)\}', css)

    def declarations(selector):
        return [dict(re.findall(r'([\w-]+)\s*:\s*([^;]+)', body))
                for selectors, body in rules if selector in selectors.strip().split(', ')]

    panels = declarations('.observation-surface > .outcome-panel')
    assert panels[0]['display'] == 'grid'
    assert panels[0]['grid-template-columns'] == 'repeat(2, minmax(0, 1fr))'
    assert panels[0]['align-items'] == 'stretch'
    assert panels[-1]['grid-template-columns'] == 'minmax(0, 1fr)'
    assert re.search(r'@media\s*\(max-width:\s*760px\)\s*\{\s*\.observation-surface > \.outcome-panel', css)
    assert declarations('.outcome-panel > *')[0]['min-width'] == '0'
    for selector in ['.outcome-panel > h3', '.outcome-panel > label', '.outcome-panel > select', '#outcome-result']:
        assert any(rule.get('grid-column') == '1 / -1' for rule in declarations(selector))
    output = declarations('#outcome-result')[-1]
    assert output['white-space'] == 'pre-line'
    assert output['overflow-wrap'] == 'break-word'


def test_outcome_click_recovery_stale_and_readback():
    engine = UTIL['javascript_engine']()
    if not engine or engine.endswith('osascript'):
        pytest.skip('Node required')
    source = (ROOT / 'astropilot/web/app.js').read_text()
    helpers = source[source.index('// Outcome state is independent'):source.index('async function finishFieldObservationSubmission(')]
    program = r'''
const assert = require('assert').strict;
const state = {outcomeLineageStatus:'ready',outcomeContext:{decision_id:'d',execution_id:null}};
const elements = new Map();
function element(id) { if (!elements.has(id)) elements.set(id, {textContent:'', value:'', disabled:false,
  children:[], set innerHTML(value) { this.children=[]; }, appendChild(child) {this.children.push(child);}}); return elements.get(id); }
const document = {querySelector: element, createElement: () => ({})};
const values = new Map();
const localStorage = {getItem:key => values.get(key) || null, setItem:(key,value) => values.set(key,value)};
const ui = {observation:{showModal(){}}};
function invalidateFieldObservationOperation() {}
function setFieldObservationEditorDisabled() {}
function observationMessage() {}
async function sessionHttpError(response) { const error = new Error(); error.status=response.status;
  error.code=(await response.json()).detail.code; return error; }
async function fieldObservationNetworkRequest(url, options, consume) { return consume(await fetch(url,options)); }
let fetch;
HELPERS
const result = id => ({evaluation_id:'e', observation_id:id, status:'partial', reasons:[], version:'outcome_evaluation.v1', decision_id:'d',execution_id:null, comparison_id:'c',computed_at_utc:'2026-01-01T00:00:00Z',evidence_reference:null,
  results:[{variable:'temperature_c', status:'comparable', forecast:8, observed:7, signed_error:1, absolute_error:1,unit:'°C',reasons:[]},
    {variable:'wind_speed_kmh',status:'not_comparable',unit:'km/h',reasons:[{code:'forecast_variable_unavailable',variable:'wind_speed_kmh'}]},
    {variable:'cloud_cover_percent',status:'comparable',forecast:'clear',observed:'overcast',outcome:'mismatch',unit:'%',reasons:[]}],
  assessment:{id:'a',status:'partial',assessed_at:'2026-01-01T00:00:00Z'}});
const response = (status,value) => ({ok:status>=200 && status<300,status,json:async()=>value});
const missing = () => response(404,{detail:{code:'outcome_evaluation_not_found'}});
(async () => {
  let posts=0, stored=null;
  fetch=async(_url,options)=> {
    if(options.method==='POST') { posts++; stored=result('obs-1'); throw new TypeError('lost response'); }
    return stored ? response(200,stored) : missing();
  };
  rememberConfirmedFieldObservation({observation_id:'obs-1',decision_id:'d',observed_at_utc:'time'});
  assert.equal(posts,0); // saving never evaluates
  await consultOutcomeEvaluation(false);
  assert.equal(posts,0); // reading never evaluates
  await consultOutcomeEvaluation(true);
  assert.equal(posts,1);
  assert.match(element('#outcome-result').textContent,/erreur signée/);
  assert.match(element('#outcome-result').textContent,/éléments comparables : partiels/);
  assert.match(element('#outcome-result').textContent,/catégories différentes/);
  await consultOutcomeEvaluation(true);
  assert.equal(posts,1); // found canonical result prevents another POST

  stored=null;
  fetch=async(_url,options)=> {
    if(options.method==='POST') { posts++; throw new TypeError('timeout'); } return missing();
  };
  await consultOutcomeEvaluation(true);
  assert.match(element('#outcome-result').textContent,/Cliquez à nouveau/);
  fetch=async(url,options)=> {
    assert.match(url,/obs-1\/outcome-evaluation$/);
    if(options.method==='POST') { posts++; stored=result('obs-1'); return response(200,{...stored,created:false}); }
    return stored?response(200,stored):missing();
  };
  await consultOutcomeEvaluation(true);
  assert.equal(posts,3);
  assert.equal(state.outcomeObservationId,'obs-1'); // same observation throughout retry

  // Failed reconciliation GET must never authorize a new POST.
  fetch=async()=>response(503,{detail:{code:'outcome_evaluation_unavailable'}});
  await consultOutcomeEvaluation(true);
  assert.equal(posts,3);
  assert.match(element('#outcome-result').textContent,/reste enregistrée/);
  assert.equal(state.visibleObservationsForContext[0].observation_id,'obs-1');

  let resolveOld;
  fetch=()=>new Promise(resolve=>{resolveOld=resolve;});
  const old=consultOutcomeEvaluation(true);
  rememberConfirmedFieldObservation({observation_id:'obs-2',decision_id:'d'});
  element('#outcome-result').textContent='new selection';
  resolveOld(missing());
  await old;
  assert.equal(posts,3);
  assert.equal(element('#outcome-result').textContent,'new selection');


  // Exact context snapshots: global confirmations never contaminate another editor.
  const obs = (id,d='d',e=null,parent=null) => ({observation_id:id,decision_id:d,execution_id:e,supersedes_observation_id:parent});
  const inventory=[obs('old'),obs('new','d',null,'old'),obs('exec','d','e'),obs('foreign','B')];
  fetch=async()=>response(200,inventory);
  await loadSavedFieldObservations({decision_id:'d',execution_id:null});
  assert.deepEqual(state.visibleObservationsForContext.map(o=>o.observation_id),['old','new']);
  assert.equal(state.outcomeObservationId,'new');
  assert.match(element('#outcome-observation').children[0].textContent,/Historique \/ remplacée par new/);
  rememberConfirmedFieldObservation(obs('B-confirmed','B'));
  assert.equal(state.outcomeObservationId,'new');
  assert.equal(state.visibleObservationsForContext.length,2);
  const beforeLineage=JSON.stringify(state.allObservationsForDecision);
  rememberConfirmedFieldObservation(obs('foreign-exec-confirmed','d','other-exec'));
  assert.equal(JSON.stringify(state.allObservationsForDecision),beforeLineage);
  assert.equal(state.outcomeObservationId,'new');
  assert.equal(state.visibleObservationsForContext.length,2);
  await loadSavedFieldObservations({decision_id:'d',execution_id:'e'});
  assert.deepEqual(state.visibleObservationsForContext.map(o=>o.observation_id),['exec']);
  await loadSavedFieldObservations({decision_id:'d'});
  state.outcomeObservationId='old'; renderSavedFieldObservations();
  assert.equal(element('#outcome-compare').disabled,true);
  fetch=async()=>response(200,result('old'));
  await consultOutcomeEvaluation(true);
  assert.match(element('#outcome-result').textContent,/Historique/);
  fetch=async()=>missing();
  await consultOutcomeEvaluation(true);
  assert.match(element('#outcome-result').textContent,/Observation remplacée/);
  assert.equal(posts,3);
  state.allObservationsForDecision.push(obs('newest','d',null,'new'));
  state.visibleObservationsForContext=state.allObservationsForDecision.filter(o=>outcomeContextMatches(o));
  selectDefaultOutcomeObservation();
  assert.equal(state.outcomeObservationId,'newest');
  state.allObservationsForDecision.push(obs('fork','d',null,'old'));
  selectDefaultOutcomeObservation();
  assert.equal(state.outcomeObservationId,null);
  assert.equal(outcomeCanCreate('fork'),false);
  state.allObservationsForDecision=state.visibleObservationsForContext=[obs('cycle1','d',null,'cycle2'),obs('cycle2','d',null,'cycle1')];
  assert.equal(outcomeCanCreate('cycle1'),false);
  state.allObservationsForDecision=state.visibleObservationsForContext=[obs('obs-1')]; state.outcomeObservationId='obs-1';
  for (const invalid of [null,7,{}, {...result('wrong')}, {...result('obs-1'),created:false},
    {...result('obs-1'),assessment:{}}, {...result('obs-1'),results:[{}]}]) {
    fetch=async(_url,options)=>{assert.equal(options.method,'GET');return response(200,invalid);};
    await consultOutcomeEvaluation(true);
    assert.match(element('#outcome-result').textContent,/Erreur de protocole/);
    assert.equal(posts,3);
  }
  fetch=async(_url,options)=>{assert.equal(options.method,'GET');return response(404,{detail:{code:'field_observation_not_found'}});};
  await consultOutcomeEvaluation(true);
  assert.equal(posts,3);
  // Exact absence authorizes POST; valid POST projection includes created.
  fetch=async(_url,options)=>{if(options.method==='POST'){posts++;return response(201,{...result('obs-1'),created:true});}return missing();};
  await consultOutcomeEvaluation(true); assert.equal(posts,4);
  // A local pointer is never persistence proof after reload.
  state.visibleObservationsForContext=[]; state.outcomeObservationId=null;
  fetch=async(url,options)=> {
    assert.match(url,/\/v1\/decisions\/d\/field-observations$/);
    assert.notEqual(options.method,'POST');
    assert.equal(state.outcomeObservationId,null);
    return response(200,[{observation_id:'server-observation',decision_id:'d'}]);
  };
  await reopenRecentFieldObservations();
  assert.equal(state.outcomeObservationId,'server-observation');
  assert.equal(element('#outcome-compare').disabled,false);
  fetch=async()=>response(200,[]);
  await reopenRecentFieldObservations();
  assert.equal(state.outcomeObservationId,null);
  assert.equal(element('#outcome-compare').disabled,true);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('HELPERS',helpers)
    run = subprocess.run([engine,'-'],input=program,text=True,capture_output=True,timeout=30)
    assert run.returncode == 0, run.stderr


def test_explicit_click_and_confirmation_precedes_cleanup():
    source=(ROOT/'astropilot/web/app.js').read_text()
    assert source.count('consultOutcomeEvaluation(true)') == 1
    assert 'state.outcomeManualObservationId = state.outcomeObservationId;' in source
    assert '#outcome-compare").addEventListener("click", () => consultOutcomeEvaluation(true)' in source
    for name, end in [('async function finishFieldObservationSubmission(', 'async function transitionFieldObservationLockStatus('),
                      ('function finishFieldObservationSubmissionUnlocked(', 'async function publishFieldObservationUnlocked('),
                      ('async function reconcileFieldObservationEntry(', 'async function abandonFieldObservationEntry(')]:
        body=source[source.index(name):source.index(end)]
        assert body.index('rememberConfirmedFieldObservation(') < min(i for i in
            [body.find('clearFieldObservationLockUnlocked('),body.find('removeFieldObservationEntryUnlocked(')] if i>=0)
        assert 'consultOutcomeEvaluation' not in body


def test_unchanged_context_does_not_discard_outcome_response():
    source = (ROOT/'astropilot/web/app.js').read_text()
    body = source[source.index('function syncFieldObservationContext('):source.index('function restorePendingFieldObservation(')]
    assert body.index('sameFieldObservationContext(') < body.index('state.outcomeToken =')


def run_outcome_ui(body, fixtures=None):
    import json
    engine = UTIL['javascript_engine']()
    if not engine or engine.endswith('osascript'):
        pytest.skip('Node required')
    source = (ROOT / 'astropilot/web/app.js').read_text()
    helpers = source[source.index('// Outcome state is independent'):source.index('async function finishFieldObservationSubmission(')]
    program = r'''
const assert=require('assert').strict;
const state={outcomeLineageStatus:'ready',outcomeContext:{decision_id:'d',execution_id:null}};
const elements=new Map();
function element(id) {if(!elements.has(id)) elements.set(id,{textContent:'',value:'',disabled:false,children:[],
 set innerHTML(v){this.children=[];},appendChild(c){this.children.push(c);}});return elements.get(id);}
const document={querySelector:element,createElement:()=>({})};
const localStorage={setItem(){}};
const response=(status,value)=>({ok:status>=200&&status<300,status,json:async()=>value});
const missing=()=>response(404,{detail:{code:'outcome_evaluation_not_found'}});
async function sessionHttpError(r){const e=new Error();e.status=r.status;e.code=(await r.json()).detail.code;return e;}
async function fieldObservationNetworkRequest(url,options,consume){return consume(await fetch(url,options));}
let fetch;
const obs=(id,time='2026-01-01T00:00:00Z',execution=null,parent=null)=>({observation_id:id,decision_id:'d',execution_id:execution,observed_at_utc:time,supersedes_observation_id:parent});
const projection=(id='o',execution=null)=>({observation_id:id,decision_id:'d',execution_id:execution,evaluation_id:'eval',version:'outcome_evaluation.v1',comparison_id:'c',computed_at_utc:'2026-01-01T00:00:00Z',status:'comparable',results:[{variable:'temperature_c',status:'comparable',unit:'°C',forecast:8,observed:7,signed_error:1,absolute_error:1,reasons:[]}],reasons:[],assessment:null,evidence_reference:null});
HELPERS
(async()=>{BODY})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('HELPERS', helpers).replace('BODY', body)
    context_helpers = '\n'.join(source[source.index(start):source.index(end)] for start, end in [
        ('function observationContext(', 'function setFieldObservationEditorDisabled('),
        ('function sameFieldObservationContext(', 'function localDateTimeParts('),
        ('function syncFieldObservationContext(', 'function restorePendingFieldObservation('),
    ])
    program = program.replace('(async()=>{', context_helpers + '\n' + CONTEXT_FIXTURE + '(async()=>{', 1)
    program = 'const fixtures=' + json.dumps(fixtures) + ';\n' + program
    result = subprocess.run([engine, '-'], input=program, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('method', ['GET', 'POST'])
@pytest.mark.parametrize('mismatch', ['decision', 'execution', 'absent', 'empty', 'invalid'])
def test_projection_exact_context_identity(method, mismatch):
    run_outcome_ui(r'''
rememberConfirmedFieldObservation(obs('o'));
let calls=[];
const bad=projection();
switch(fixtures.mismatch){case 'decision':bad.decision_id='foreign';break;
case 'execution':bad.execution_id='foreign-exec';break;case 'absent':delete bad.execution_id;break;
case 'empty':bad.execution_id='';break;case 'invalid':bad.execution_id=7;break;}
fetch=async(_url,options)=>{calls.push(options.method);
 if(fixtures.method==='POST'&&options.method==='GET')return missing();
 return response(200,fixtures.method==='POST'?{...bad,created:false}:bad);};
await consultOutcomeEvaluation(true);
assert.deepEqual(calls,fixtures.method==='POST'?['GET','POST']:['GET']);
assert.match(element('#outcome-result').textContent,/Erreur de protocole/);
assert.doesNotMatch(element('#outcome-result').textContent,/erreur signée/);
''', {'method': method, 'mismatch': mismatch})


def test_execution_identity_null_and_recovery_mismatch():
    run_outcome_ui(r'''
state.outcomeContext={decision_id:'d',execution_id:'exec'};
rememberConfirmedFieldObservation(obs('o',undefined,'exec'));
for(const execution of [null,undefined,'other']){
 const value=projection('o',execution);if(execution===undefined)delete value.execution_id;
 let calls=[];fetch=async(_url,options)=>{calls.push(options.method);return response(200,value);};
 await consultOutcomeEvaluation(true);assert.deepEqual(calls,['GET']);
 assert.match(element('#outcome-result').textContent,/Erreur de protocole/);
}
let calls=[];
fetch=async(_url,options)=>{calls.push(options.method);if(calls.length===1)return missing();
 if(options.method==='POST')throw new TypeError('lost');return response(200,projection('o','foreign'));};
await consultOutcomeEvaluation(true);assert.deepEqual(calls,['GET','POST','GET']);
assert.match(element('#outcome-result').textContent,/Erreur de protocole/);
fetch=async()=>response(200,projection('o','exec'));
await consultOutcomeEvaluation(true);assert.match(element('#outcome-result').textContent,/erreur signée/);
''')


@pytest.mark.parametrize('kind', ['global', 'assessment', 'reason'])
def test_unknown_structured_statuses_render_neutrally(kind):
    run_outcome_ui(r'''
rememberConfirmedFieldObservation(obs('o'));
const value=projection();
if(fixtures==='global')value.status='future_status';
if(fixtures==='assessment')value.assessment={id:'a',status:'future_status',assessed_at:value.computed_at_utc};
if(fixtures==='reason')value.reasons=[{code:'future_reason',variable:null}];
fetch=async(_url,options)=>{assert.equal(options.method,'GET');return response(200,value);};
await consultOutcomeEvaluation(true);
const output=element('#outcome-result').textContent;
assert.doesNotMatch(output,/Erreur de protocole|score|classement/);
assert.match(output,fixtures==='reason'?/Raison non reconnue/:/Statut non reconnu/);
if(fixtures==='global')assert.doesNotMatch(output,/erreur signée|Suffisance/);
if(fixtures==='assessment')assert.doesNotMatch(output,/suffisants|partiels|insuffisants/);
''', kind)


@pytest.mark.parametrize('field', ['status', 'assessment'])
@pytest.mark.parametrize('value', [None, 7, {}, [] , ''])
def test_invalid_status_forms_are_protocol_errors(field, value):
    run_outcome_ui(r'''
rememberConfirmedFieldObservation(obs('o'));
const value=projection();
if(fixtures.field==='status')value.status=fixtures.value;
else value.assessment={id:'a',status:fixtures.value,assessed_at:value.computed_at_utc};
fetch=async(_url,options)=>{assert.equal(options.method,'GET');return response(200,value);};
await consultOutcomeEvaluation(true);assert.match(element('#outcome-result').textContent,/Erreur de protocole/);
''', {'field': field, 'value': value})


def test_multi_active_selection_confirmation_refresh_and_manual_choice():
    run_outcome_ui(r'''
const older=obs('older','2026-01-01T00:00:00Z'),newer=obs('newer','2026-01-02T00:00:00Z');
let inventory=[older];fetch=async()=>response(200,inventory);
await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'older');
rememberConfirmedFieldObservation(newer);assert.equal(state.outcomeObservationId,'newer');
inventory=[older,newer];
await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'newer');
assert.match(element('#outcome-observation').children[0].textContent,/Plusieurs observations actives/);
rememberConfirmedFieldObservation(newer);
await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'newer');
inventory=[older,newer,obs('third','2026-01-03T00:00:00Z')];
await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'third');
const equal=obs('z-tie','2026-01-03T00:00:00+00:00');inventory.push(equal);
await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'z-tie');
inventory.reverse();await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'z-tie');
state.outcomeManualObservationId=state.outcomeObservationId='older';
await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'older');
rememberConfirmedFieldObservation(obs('latest','2026-01-04T00:00:00Z'));assert.equal(state.outcomeObservationId,'older');
inventory=inventory.filter(o=>o.observation_id!=='older');
await loadSavedFieldObservations({decision_id:'d'});assert.equal(state.outcomeObservationId,'z-tie');
''')


def test_cross_context_lineage_with_real_store_and_historical_outcome(tmp_path):
    api = runpy.run_path(str(Path(__file__).with_name('test_outcome_evaluation_api.py')))
    _, orchestration, client = api['setup'](tmp_path)
    url = api['URL']
    historical = client.post(url).json()
    assert historical.pop('created') is True
    orchestration.observation_store.save(observation=api['builders']['observation'](
        observation_id='child', execution_id='execution-1', supersedes_observation_id='observation-1'))
    inventory = client.get('/v1/decisions/decision-1/field-observations').json()
    assert len(inventory) == 2
    assert client.post(url).status_code == 409
    assert client.get(url).json() == historical
    child_url = url.replace('observation-1', 'child')
    child = client.post(child_url)
    assert child.status_code == 201
    run_outcome_ui(r'''
let resolveCanonical;
fetch=()=>new Promise(resolve=>resolveCanonical=resolve);
const pending=loadSavedFieldObservations({decision_id:'decision-1',execution_id:null});
rememberConfirmedFieldObservation(fixtures.inventory.find(o=>o.observation_id==='observation-1'));
assert.equal(element('#outcome-compare').disabled,true);
assert.equal(outcomeCanCreate('observation-1'),false);
resolveCanonical(response(200,fixtures.inventory));await pending;
assert.equal(state.allObservationsForDecision.length,2);
assert.match(element('#outcome-observation').children[0].textContent,/Historique.*child.*execution-1/);
assert.equal(element('#outcome-compare').disabled,true);
fetch=async(url,options)=>{assert.equal(url,'/v1/decisions/decision-1/field-observations');return response(200,fixtures.inventory);};
await loadSavedFieldObservations({decision_id:'decision-1',execution_id:null});
assert.deepEqual(state.visibleObservationsForContext.map(o=>o.observation_id),['observation-1']);
assert.equal(state.allObservationsForDecision.length,2);
assert.match(element('#outcome-observation').children[0].textContent,/Historique.*child.*execution-1/);
state.outcomeObservationId='observation-1';renderSavedFieldObservations();
assert.equal(element('#outcome-compare').disabled,true);
let calls=[];fetch=async(_url,options)=>{calls.push(options.method);return missing();};
await consultOutcomeEvaluation(true);assert.deepEqual(calls,['GET']);
assert.match(element('#outcome-result').textContent,/Observation remplacée/);
fetch=async(_url,options)=>{assert.equal(options.method,'GET');return response(200,fixtures.historical);};
await consultOutcomeEvaluation(true);assert.match(element('#outcome-result').textContent,/Historique/);
assert.match(element('#outcome-result').textContent,/erreur signée/);
fetch=async()=>response(200,fixtures.inventory);
await loadSavedFieldObservations({decision_id:'decision-1',execution_id:'execution-1'});
assert.deepEqual(state.visibleObservationsForContext.map(o=>o.observation_id),['child']);
assert.equal(state.outcomeObservationId,'child');assert.equal(outcomeCanCreate('child'),true);
assert.equal(element('#outcome-compare').disabled,false);
calls=[];fetch=async(_url,options)=>{calls.push(options.method);return options.method==='GET'?missing():response(201,fixtures.child);};
await consultOutcomeEvaluation(true);assert.deepEqual(calls,['GET','POST']);
assert.match(element('#outcome-result').textContent,/erreur signée/);
assert.doesNotMatch(element('#outcome-result').textContent,/Historique|incohérente/);
''', {'inventory': inventory, 'historical': historical, 'child': child.json()})


@pytest.mark.parametrize('foreign', [False, True])
def test_recovery_confirmation_does_not_cancel_pending_canonical_lineage(foreign):
    run_outcome_ui(r'''
const parent=obs('parent'),child=obs('child','2026-01-02T00:00:00Z','execution-1','parent');
let resolveList,posts=0;
fetch=(url,options)=>{assert.notEqual(options.method,'POST');return new Promise(resolve=>resolveList=resolve);};
const loading=loadSavedFieldObservations({decision_id:'d'});
const generation=state.outcomeLineageGeneration;
rememberConfirmedFieldObservation(fixtures ? {...parent,execution_id:'other'} : parent);
assert.equal(state.outcomeLineageGeneration,generation);
assert.equal(state.outcomeLineageStatus,'pending');
assert.equal(element('#outcome-compare').disabled,true);
if(!fixtures) {
 assert.match(element('#outcome-observation').children[0].textContent,/supersession inconnue/);
 const listResolver=resolveList;
 fetch=async(_url,options)=>{if(options.method==='POST')posts++;return missing();};
 await consultOutcomeEvaluation(true);assert.equal(posts,0);
 resolveList=listResolver;
}
resolveList(response(200,[parent,child]));await loading;
assert.equal(state.outcomeLineageStatus,'ready');
assert.deepEqual(state.allObservationsForDecision.map(o=>o.observation_id),['parent','child']);
assert.equal(state.visibleObservationsForContext.length,1);
assert.equal(state.outcomeObservationId,null);
state.outcomeManualObservationId=state.outcomeObservationId='parent';renderSavedFieldObservations();
assert.match(element('#outcome-observation').children[0].textContent,/Historique.*child.*execution-1/);
assert.equal(element('#outcome-compare').disabled,true);
fetch=async(_url,options)=>{if(options.method==='POST')posts++;return missing();};
await consultOutcomeEvaluation(true);assert.equal(posts,0);
''', foreign)


def test_canonical_loader_context_change_ignores_old_response():
    run_outcome_ui(r'''
let oldResolve;fetch=()=>new Promise(resolve=>oldResolve=resolve);
const old=loadSavedFieldObservations({decision_id:'d'});
fetch=async()=>response(200,[obs('current',undefined,'new-context')]);
await loadSavedFieldObservations({decision_id:'d',execution_id:'new-context'});
oldResolve(response(200,[obs('obsolete')]));await old;
assert.equal(state.outcomeObservationId,'current');
assert.deepEqual(state.allObservationsForDecision.map(o=>o.observation_id),['current']);
assert.equal(state.outcomeLineageStatus,'ready');
''')


def test_confirmed_identity_merges_without_duplicate_or_lineage_loss():
    run_outcome_ui(r'''
state.outcomeLineageStatus=undefined;
const parent=obs('parent'),child=obs('child',undefined,'execution-1','parent');
rememberConfirmedFieldObservation(parent);
assert.equal(outcomeCanCreate('parent'),false);
fetch=async()=>response(200,[parent,child]);
await loadSavedFieldObservations({decision_id:'d'});
assert.deepEqual(state.allObservationsForDecision.map(o=>o.observation_id),['parent','child']);
assert.equal(outcomeCanCreate('parent'),false);
''')


@pytest.mark.parametrize('failure', ['http', 'timeout', 'invalid', 'missing_confirmation'])
def test_canonical_loader_failure_blocks_creation_and_allows_retry(failure):
    run_outcome_ui(r'''
let settle,posts=0;fetch=()=>new Promise((resolve,reject)=>settle={resolve,reject});
const loading=loadSavedFieldObservations({decision_id:'d'});
rememberConfirmedFieldObservation(obs('parent'));
if(fixtures==='http')settle.resolve(response(503,{detail:{code:'unavailable'}}));
else if(fixtures==='timeout')settle.reject(Object.assign(new Error('timeout'),{networkTimeout:true}));
else settle.resolve(response(200,fixtures==='invalid'?{}:[]));
await loading;
assert.equal(state.outcomeLineageStatus,'error');
assert.equal(element('#outcome-compare').disabled,true);
assert.match(element('#outcome-result').textContent,/Supersession inconnue.*Rouvrez/);
fetch=async(_url,options)=>{if(options.method==='POST')posts++;return missing();};
await consultOutcomeEvaluation(true);assert.equal(posts,0);
fetch=async()=>response(200,[obs('parent')]);await loadSavedFieldObservations({decision_id:'d'});
assert.equal(state.outcomeLineageStatus,'ready');assert.equal(outcomeCanCreate('parent'),true);
''', failure)


CONTEXT_FIXTURE = r'''
let executionId=null;
function currentSession(){return {execution:{execution_id:executionId}};}
function siteTimezone(){return 'Europe/Zurich';}
function siteConfigurationIdentity(){return 'site';}
function invalidateFieldObservationOperation(){}
function updateFieldObservationSubmitState(){}
function observationMessage(message){element('#observation-message').textContent=message;}
function openContext(){
 state.acceptedMission={decision_id:'d'};
 state.fieldObservationSelectedExecutionId=executionId;
 state.fieldObservationDraftContext=observationContext('mission');
 element('#field-observation-dialog').open=true;
}
function changeContext(kind){
 if(kind==='decision')state.acceptedMission={decision_id:'other'};
 else {executionId='other-execution';state.fieldObservationSelectedExecutionId=executionId;}
 syncFieldObservationContext();
}
'''


@pytest.mark.parametrize('kind', ['decision', 'execution'])
def test_sync_context_immediately_refreshes_compare_and_selection(kind):
    run_outcome_ui(r'''
openContext();rememberConfirmedFieldObservation(obs('o'));
assert.equal(element('#outcome-compare').disabled,false);
const token=state.outcomeToken||0,generation=state.outcomeLineageGeneration||0;
element('#outcome-result').textContent='historical result';
changeContext(fixtures);
assert.equal(state.outcomeLineageStatus,'pending');
assert.equal(state.outcomeToken,token+1);
assert.equal(state.outcomeLineageGeneration,generation+1);
assert.equal(state.fieldObservationContextInvalid,true);
assert.equal(element('#outcome-compare').disabled,true);
assert.equal(element('#outcome-observation').value,'o');
assert.match(element('#outcome-observation').children[0].textContent,/supersession inconnue/);
assert.equal(element('#outcome-result').textContent,'historical result');
assert.match(element('#observation-message').textContent,/éditeur est bloqué/);
''', kind)


@pytest.mark.parametrize('reply', ['missing', 'found'])
def test_sync_context_ignores_inflight_outcome_get(reply):
    run_outcome_ui(r'''
openContext();rememberConfirmedFieldObservation(obs('o'));
let resolveGet,calls=[];
fetch=(_url,options)=>{calls.push(options.method);return new Promise(resolve=>resolveGet=resolve);};
const pending=consultOutcomeEvaluation(true);
changeContext('decision');element('#outcome-result').textContent='current display';
resolveGet(fixtures==='missing'?missing():response(200,projection()));await pending;
assert.deepEqual(calls,['GET']);
assert.equal(element('#outcome-result').textContent,'current display');
assert.equal(state.outcomeLineageStatus,'pending');
assert.equal(element('#outcome-compare').disabled,true);
''', reply)


def test_sync_context_ignores_inflight_canonical_list():
    run_outcome_ui(r'''
openContext();let resolveList;fetch=()=>new Promise(resolve=>resolveList=resolve);
const pending=loadSavedFieldObservations({decision_id:'d'});
rememberConfirmedFieldObservation(obs('o'));
const inventory=JSON.stringify(state.allObservationsForDecision);
changeContext('execution');element('#outcome-result').textContent='current display';
resolveList(response(200,[obs('obsolete')]));await pending;
assert.equal(state.outcomeLineageStatus,'pending');
assert.equal(JSON.stringify(state.allObservationsForDecision),inventory);
assert.equal(state.outcomeObservationId,'o');
assert.equal(element('#outcome-compare').disabled,true);
assert.match(element('#outcome-observation').children[0].textContent,/supersession inconnue/);
assert.equal(element('#outcome-result').textContent,'current display');
''')


def test_sync_context_stale_compare_handler_never_posts():
    run_outcome_ui(r'''
openContext();rememberConfirmedFieldObservation(obs('o'));changeContext('decision');
let calls=[];fetch=async(_url,options)=>{calls.push(options.method);return missing();};
await consultOutcomeEvaluation(true);assert.deepEqual(calls,['GET']);
assert.match(element('#outcome-result').textContent,/Supersession inconnue/);
assert.equal(element('#outcome-compare').disabled,true);
''')


def test_sync_unchanged_context_preserves_nominal_get_then_post():
    run_outcome_ui(r'''
openContext();rememberConfirmedFieldObservation(obs('o'));
const token=state.outcomeToken,generation=state.outcomeLineageGeneration;
const labels=element('#outcome-observation').children.map(c=>c.textContent);
syncFieldObservationContext();
assert.equal(state.outcomeToken,token);assert.equal(state.outcomeLineageGeneration,generation);
assert.equal(state.outcomeLineageStatus,'ready');
assert.notEqual(state.fieldObservationContextInvalid,true);
assert.equal(element('#outcome-compare').disabled,false);
assert.deepEqual(element('#outcome-observation').children.map(c=>c.textContent),labels);
let resolveGet,calls=[];
fetch=(_url,options)=>{calls.push(options.method);return options.method==='GET'
 ?new Promise(resolve=>resolveGet=resolve):Promise.resolve(response(201,{...projection(),created:true}));};
const pending=consultOutcomeEvaluation(true),inflightToken=state.outcomeToken;
syncFieldObservationContext();assert.equal(state.outcomeToken,inflightToken);
resolveGet(missing());await pending;
assert.deepEqual(calls,['GET','POST']);
assert.match(element('#outcome-result').textContent,/erreur signée/);
assert.equal(element('#outcome-compare').disabled,false);
''')
