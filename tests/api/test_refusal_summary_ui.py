"""Refusal explanations use recorded scopes and collection times, never guesses."""
from pathlib import Path
import shutil
from tests.timezone_ui_helpers import run_with_time_authority


def test_refusal_summary_distinguishes_weather_shortness_and_missing_evidence():
    source=(Path(__file__).parents[2]/'astropilot/web/app.js').read_text()
    helpers=source[source.index('function targetedIntentAssessments('):source.index('function simpleProductivityRefusal(')]
    program=r'''
const assert=require('node:assert/strict');
globalThis.NightMeritPresentation={simulatedWeather:value=>value?.provider==='SIMULE'};
'''+helpers+r'''
const payload={weather_trust:{provider:'Open-Meteo',retrieved_at_utc:'2026-11-10T13:45:00Z'},
 actionability_refusal:{evidence_scope:{evaluated_start:'2026-11-11T00:00:00+01:00',evaluated_end:'2026-11-11T02:00:00+01:00'},
 refusal_stage:'no_productive_slice',productivity_breakdown:{losses:{cloud:.693,humidity:0,altitude:.1,moon:0,wind:0}}}};
const before=JSON.stringify(payload);
const historical={...payload, weather_trust:{timezone:'Europe/Zurich'}, refusal_weather:{provider:'Open-Meteo',retrieved_at_utc:'2026-11-10T13:45:00Z'}};
assert.match(refusalEvidenceSummary(historical,'Europe/Zurich').collected,/14:45/);
let result=refusalEvidenceSummary(payload,'Europe/Zurich');
assert.match(result.collected,/10\.11\.2026.*14:45.*Open-Meteo/);
assert.match(result.rows[0].range,/11\.11\.2026.*00:00.*02:00.*Europe\/Zurich/);
assert.match(result.rows[0].factors,/nuages, faible hauteur/);
assert.doesNotMatch(result.rows[0].factors,/humidité|vent|Lune/);
const short=structuredClone(payload);short.actionability_refusal.refusal_stage='continuous_window_too_short';
short.actionability_refusal.best_productive_window_minutes=50;short.actionability_refusal.required_continuous_minutes=60;
short.acquisition_intent_assessments=[{filter_type:'OIII',status:'not_eligible',reason_codes:[],actionability_refusal:null}];
result=refusalEvidenceSummary(short,'Europe/Zurich');
assert.match(result.rows[0].factors,/trop court.*50.*60/);
assert.doesNotMatch(result.rows[0].factors,/nuages/);
const missing=structuredClone(payload);delete missing.weather_trust.retrieved_at_utc;delete missing.actionability_refusal.evidence_scope;
result=refusalEvidenceSummary(missing,'UTC');
assert.match(result.collected,/non disponible/);assert.match(result.rows[0].range,/non disponibles/);
assert.doesNotMatch(result.rows[0].factors,/nuages/);
const naive=structuredClone(payload);naive.actionability_refusal.evidence_scope.evaluated_start='2026-11-11T00:00:00';
assert.match(refusalEvidenceSummary(naive,'Europe/Zurich').rows[0].range,/non disponibles/);
const simulated=structuredClone(payload);simulated.weather_trust.provider='SIMULE';
assert.match(refusalEvidenceSummary(simulated,'Europe/Zurich').collected,/simulées datées/);
const discovery={weather_context:payload.weather_trust,refusal_evidence:[
 {display_name:'Rosette',filter_type:'OIII',evaluated_start:'2026-11-14T03:00:00+01:00',evaluated_end:'2026-11-14T05:00:00+01:00',refusal_stage:'no_productive_slice',losses:{humidity:.2,cloud:.29}},
 {display_name:'Rosette',filter_type:'SII',evaluated_start:'2026-11-15T03:00:00+01:00',evaluated_end:'2026-11-15T04:00:00+01:00',refusal_stage:'no_productive_slice',losses:null}]};
result=refusalEvidenceSummary(discovery,'Europe/Zurich');
assert.equal(result.rows.length,2);assert.match(result.rows[0].label,/Rosette.*OIII/);
assert.match(result.rows[0].range,/14\.11/);assert.match(result.rows[1].range,/15\.11/);
assert.match(result.rows[0].factors,/nuages, humidité/);assert.match(result.rows[1].factors,/non conservés/);
assert.equal(JSON.stringify(payload),before);
'''
    result=run_with_time_authority([shutil.which('node'),'-'],input=program,text=True,capture_output=True)
    assert result.returncode==0,result.stderr


def test_multiple_preselection_windows_are_distinct_from_filter_reference():
    source=(Path(__file__).parents[2]/'astropilot/web/app.js').read_text()
    helpers=source[source.index('function targetedIntentAssessments('):source.index('function simpleProductivityRefusal(')]
    program=r'''
const assert=require('node:assert/strict');
'''+helpers+r'''
const refusal=(start,end,losses)=>({evidence_scope:{evaluated_start:start,evaluated_end:end},
 refusal_stage:'no_productive_slice',productivity_breakdown:{losses}});
const payload={actionability_refusal:refusal('2026-11-17T20:00:00+01:00','2026-11-17T21:00:00+01:00',{cloud:.4}),
 preselection_window_refusals:[
 refusal('2026-11-17T20:20:00+01:00','2026-11-17T21:00:00+01:00',{cloud:.4,wind:.15}),
 refusal('2026-11-17T21:00:00+01:00','2026-11-17T23:00:00+01:00',{cloud:.7}),
 refusal('2026-11-17T23:00:00+01:00','2026-11-17T23:25:00+01:00',{cloud:.7,altitude:.1})]};
const before=JSON.stringify(payload);
const rows=preselectionRefusalSummary(payload,'Europe/Zurich');
assert.equal(rows.length,3);assert.match(rows[0].range,/20:20.*21:00/);
assert.match(rows[1].range,/21:00.*23:00/);assert.match(rows[2].range,/23:00.*23:25/);
assert.match(rows[0].factors,/nuages, vent/);assert.doesNotMatch(rows[1].factors,/vent|hauteur/);
assert.match(rows[2].factors,/hauteur/);
assert.match(refusalEvaluatedRange(payload,'Europe/Zurich'),/Fenêtre de référence/);
const old={actionability_refusal:payload.actionability_refusal};
assert.deepEqual(preselectionRefusalSummary(old,'Europe/Zurich'),[]);
assert.match(refusalEvaluatedRange(old,'Europe/Zurich'),/Plage évaluée/);
const missing={preselection_window_refusals:[{refusal_stage:'no_productive_slice',productivity_breakdown:{losses:{cloud:.7}}}]};
assert.match(preselectionRefusalSummary(missing,'Europe/Zurich')[0].factors,/aucune plage/);
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=[...items];}
}
globalThis.document={createElement:tag=>new Element(tag)};
const container=new Element('div');
renderRefusalEvidence(container,payload,'Europe/Zurich',{includeRange:false});
function texts(node){return [node.textContent,...node.children.flatMap(texts)].join(' ');}
const rendered=texts(container);
assert.match(rendered,/3 fenêtres examinées.*préparation et des flats/);
assert.match(rendered,/fenêtre de référence/);
assert.match(rendered,/avant le choix du filtre \(3\)/);
assert.match(rendered,/20:20.*21:00.*23:00.*23:25/);
assert.match(rendered,/nuages, vent/);
assert.equal(JSON.stringify(payload),before);
'''
    result=run_with_time_authority([shutil.which('node'),'-'],input=program,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
