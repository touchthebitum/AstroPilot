from pathlib import Path
import shutil
import subprocess


def test_saved_plan_weather_requires_the_same_intent_window_and_fresh_evidence():
    module = Path(__file__).parents[2] / "astropilot/web/saved-plan-weather.js"
    program = r'''
const assert = require('node:assert/strict');
const {summarize} = require(process.argv[1]);
const accepted = {selectedCatalogKey:'Rosette', acquisitionIntentId:'rosette_oiii', mission:{
  acquisition_intent_id:'rosette_oiii', selected_filter:{filter_type:'OIII'},
  window_start:'2026-11-14T03:20:00+01:00', window_end:'2026-11-14T04:55:00+01:00'}};
const trust = {provider:'fixture-provider', retrieved_at_utc:'2026-11-13T07:30:00Z',
  freshness_status:'fresh', validation_status:'validated',
  valid_from:'2026-11-13T00:00:00Z', valid_until:'2026-11-15T00:00:00Z'};
const previous = {...trust, retrieved_at_utc:'2026-11-13T07:00:00Z'};
const payload = {status:'available',catalog_key:'Rosette', selected_acquisition_intent_id:'rosette_oiii',
  selected_filter:{filter_type:'OIII'}, window_start:accepted.mission.window_start,
  window_end:accepted.mission.window_end,weather_trust:trust,weather_decision:{admissibility:'admissible'}};
const before = JSON.stringify(accepted);
assert.equal(summarize(accepted,payload,previous).status,'favorable');
assert.match(summarize(accepted,payload,previous).collection,/nouvelle collecte/);
assert.match(summarize(accepted,payload,trust).collection,/identique/);
assert.equal(summarize(accepted,{...payload,weather_trust:{...trust,retrieved_at_utc:'2026-11-13T06:00:00Z'}},previous).status,'unknown');
assert.equal(summarize(accepted,{...payload,selected_acquisition_intent_id:'rosette_sii'},previous).status,'unknown');
assert.equal(summarize(accepted,{...payload,selected_filter:{filter_type:'SII'}},previous).status,'unknown');
assert.equal(summarize(accepted,{...payload,catalog_key:'Ou4'},previous).status,'unknown');
assert.equal(summarize(accepted,{...payload,window_start:'2026-11-14T04:00:00+01:00'},previous).status,'revise');
for (const changes of [{freshness_status:'stale'},{validation_status:'invalid'},
  {retrieved_at_utc:null},{valid_until:'2026-11-14T02:00:00Z'}]) {
  assert.equal(summarize(accepted,{...payload,weather_trust:{...trust,...changes}},previous).status,'unknown');
}
assert.equal(summarize(accepted,{...payload,weather_decision:{admissibility:'caution'}},previous).status,'caution');
assert.equal(summarize(accepted,{...payload,weather_trust:{...trust,provider:'Météo simulée'}},previous).status,'simulated');
assert.equal(summarize(accepted,{...payload,status:'weather_refused'},previous).status,'refused');
assert.equal(summarize(accepted,{...payload,status:'no_productive_window',acquisition_intent_assessments:[
  {acquisition_intent_id:'rosette_oiii',status:'not_eligible',reason_codes:['insufficient_actionable_productive_window']}]},previous).status,'refused');
assert.equal(summarize(accepted,null,previous).status,'unknown');
assert.equal(JSON.stringify(accepted),before);
'''
    result = subprocess.run([shutil.which("node"), "-e", program, str(module)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_filter_choice_is_distinct_from_refusal_and_never_confirms_a_plan():
    module = Path(__file__).parents[2] / "astropilot/web/saved-plan-weather.js"
    program = r'''
const assert = require('node:assert/strict');
const {summarize} = require(process.argv[1]);
const trust = {provider:'Météo simulée',retrieved_at_utc:'2026-11-13T07:30:00Z',
  freshness_status:'fresh',validation_status:'validated',valid_from:'2026-11-13T00:00:00Z',valid_until:'2026-11-15T00:00:00Z'};
const payload = {catalog_key:'Rosette',status:'no_mission',acquisition_intent_choice_available:true,
  creation_refusal:'preselection_evidence_cannot_authorize_mission',
  viable_acquisition_intent_ids:['rosette_oiii','rosette_sii'],
  acquisition_intent_options:[{acquisition_intent_id:'rosette_oiii',filter_type:'OIII'},
    {acquisition_intent_id:'rosette_sii',filter_type:'SII'}],
  acquisition_intent_assessments:[{acquisition_intent_id:'rosette_oiii',status:'eligible'},
    {acquisition_intent_id:'rosette_sii',status:'eligible'}],weather_trust:trust};
const original=JSON.stringify(payload);
for(const filter of ['OIII','SII']) {
 const id='rosette_'+filter.toLowerCase();
 const accepted={selectedCatalogKey:'Rosette',acquisitionIntentId:id,mission:{acquisition_intent_id:id,
   selected_filter:{filter_type:filter},window_start:'2026-11-14T03:20:00+01:00',window_end:'2026-11-14T04:55:00+01:00'}};
 const before=JSON.stringify(accepted),result=summarize(accepted,payload,null);
 assert.equal(result.status,'choice_required');
 assert.match(result.summary,/Choix de filtre à confirmer : OIII et SII/);
 assert(result.summary.includes('Sélectionnez '+filter));
 assert.match(result.summary,/dans cette simulation/);assert.match(result.summary,/reste à revérifier/);
 assert.doesNotMatch(result.summary,/refus|ne confirme pas ce filtre/);
 assert.equal(summarize(accepted,{...payload,status:'weather_refused'},null).status,'refused');
 assert.equal(summarize(accepted,{...payload,acquisition_intent_assessments:[{acquisition_intent_id:id,status:'not_eligible',reason_codes:['insufficient_actionable_productive_window']}]},null).status,'refused');
 for(const changes of [{freshness_status:'stale'},{validation_status:'invalid'},{retrieved_at_utc:null},{valid_until:'2026-11-14T02:00:00Z'}]) {
  assert.equal(summarize(accepted,{...payload,weather_trust:{...trust,...changes}},null).status,'unknown');
 }
 assert.equal(summarize(accepted,{...payload,viable_acquisition_intent_ids:[]},null).status,'unknown');
 assert.equal(summarize(accepted,{...payload,creation_refusal:'weather_refusal'},null).status,'unknown');
 assert.equal(JSON.stringify(accepted),before);
}
assert.equal(JSON.stringify(payload),original);
'''
    result = subprocess.run([shutil.which("node"), "-e", program, str(module)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
