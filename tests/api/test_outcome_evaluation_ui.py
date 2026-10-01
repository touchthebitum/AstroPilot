from pathlib import Path
import runpy
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
UTIL = runpy.run_path(str(Path(__file__).with_name('test_field_observation_ui.py')))


def test_outcome_click_recovery_stale_and_readback():
    engine = UTIL['javascript_engine']()
    if not engine or engine.endswith('osascript'):
        pytest.skip('Node required')
    source = (ROOT / 'astropilot/web/app.js').read_text()
    helpers = source[source.index('// Outcome state is independent'):source.index('async function finishFieldObservationSubmission(')]
    program = r'''
const assert = require('assert').strict;
const state = {};
const elements = new Map();
function element(id) { if (!elements.has(id)) elements.set(id, {textContent:'', value:'', disabled:false,
  innerHTML:'', appendChild() {}}); return elements.get(id); }
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
const result = id => ({evaluation_id:'e', observation_id:id, status:'partial', reasons:[],
  results:[{variable:'temperature_c', status:'comparable', forecast:8, observed:7, signed_error:1, absolute_error:1,unit:'°C'},
    {variable:'wind_speed_kmh',status:'not_comparable',reasons:[{code:'forecast_variable_unavailable',variable:'wind_speed_kmh'}]},
    {variable:'cloud_cover_percent',status:'comparable',forecast:'clear',observed:'overcast',outcome:'mismatch',unit:'%'}],
  assessment:{status:'partial'}});
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
    if(options.method==='POST') { posts++; stored=result('obs-1'); return response(200,stored); }
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
  assert.equal(state.confirmedFieldObservations[0].observation_id,'obs-1');

  let resolveOld;
  fetch=()=>new Promise(resolve=>{resolveOld=resolve;});
  const old=consultOutcomeEvaluation(true);
  rememberConfirmedFieldObservation({observation_id:'obs-2',decision_id:'d'});
  element('#outcome-result').textContent='new selection';
  resolveOld(missing());
  await old;
  assert.equal(posts,3);
  assert.equal(element('#outcome-result').textContent,'new selection');

  // A local pointer is never persistence proof after reload.
  state.confirmedFieldObservations=[]; state.outcomeObservationId=null;
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
