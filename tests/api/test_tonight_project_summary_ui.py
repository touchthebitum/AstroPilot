"""The summary presents one server decision, never a new ranking or progress projection."""
from pathlib import Path
import json
import shutil
import pytest
from tests.timezone_ui_helpers import run_with_time_authority

WEB = Path(__file__).parents[2] / 'astropilot/web/app.js'


def program():
    source = WEB.read_text()
    helpers = (source[source.index('function windowTimezone('):source.index('function savedMissionLabel(')]
        + source[source.index('function siteDateTime('):source.index('function renderWeatherTrust(')]
        + source[source.index('function beginnerReason('):source.index('function setList(')]
        + source[source.index('function intentMode('):source.index('const intentStatusLabels')]
        + source[source.index('function pendingIntentChoice('):source.index('function chosenIntent(')]
        + source[source.index('function comparisonDuration('):source.index('function renderDecision(')])
    return r'''
const assert=require('node:assert/strict');
class E {
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.className='';this.dataset={};}
 append(...items){this.children.push(...items);}
 querySelector(selector){for(const c of this.children.filter(x=>!x.removed)){if(selector==='.'+c.className)return c;const nested=c.querySelector(selector);if(nested)return nested;}return null;}
 remove(){this.removed=true;}
}
const document={createElement:tag=>new E(tag)};
const appliedUiMode='simple';
function siteTimezone(){return 'Europe/Zurich'}
function content(e){return [e.textContent,...e.children.filter(x=>!x.removed).map(content)].join(' ')}
function fetch(){throw Error('Summary must never request anything')}
const row=(id,type,acquired)=>({acquisition_intent_id:id,filter_type:type,target_hours:3,acquired_hours:acquired,remaining_hours:3-acquired,status:'to_complete'});
const decision={decision_id:'d',status:'available',target_decision_status:'recommended',catalog_key:'Rosette',
 selected_acquisition_intent_id:'r_oiii',acquisition_intent_selection_status:'selected',
 viable_acquisition_intent_ids:['r_oiii'],acquisition_intent_options:[{acquisition_intent_id:'r_oiii',label:'OIII'}],
 weather_decision:{admissibility:'admissible'},weather_trust:{timezone:'Europe/Zurich'},
 window_start:'2026-11-21T21:00:00+01:00',window_end:'2026-11-21T23:00:00+01:00',recommended_hours:1.5,
 explanation:{positives:[{title:'Cible bien placée',value:'Altitude favorable'}],information:[],warnings:[{title:'Nuages à surveiller'}]},
 project_comparison:[{project_id:'M42',filters:[row('m_oiii','OIII',99)]},{project_id:'Rosette',filters:[row('r_oiii','OIII',40/60),row('r_sii','SII',25/60)]}]};
''' + helpers


def run(checks):
    result = run_with_time_authority([shutil.which('node'), '-'], input=program()+checks,
        text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_exact_project_and_intent_no_mutation_and_context_replacement():
    run(r'''
const before=JSON.stringify(decision),p=new E('main');
renderProjectComparison(decision,p);
let summary=p.querySelector('.project-tonight-summary');assert(summary);
assert.match(content(summary),/Rosette — OIII/);
assert.match(content(summary),/Objectif 3 h · Déjà acquis 40 min · Reste à faire 2 h 20/);
assert.match(content(summary),/21\.11\.2026.*21:00/);assert.match(content(summary),/Europe\/Zurich/);
assert.match(content(summary),/Durée productive estimée : 1 h 30/);
assert.match(content(summary),/Cible bien placée — Altitude favorable/);
assert.doesNotMatch(content(summary),/99 h|25 min|choisi parce|plus urgent|moins bon|Nuages à surveiller/);
assert.equal(JSON.stringify(decision),before);
const next=structuredClone(decision);next.catalog_key='M42';next.selected_acquisition_intent_id='m_oiii';
next.viable_acquisition_intent_ids=['m_oiii'];next.acquisition_intent_options=[{acquisition_intent_id:'m_oiii',label:'OIII'}];
renderProjectComparison(next,p);summary=p.querySelector('.project-tonight-summary');
assert.match(content(summary),/M42 — OIII/);assert.doesNotMatch(content(summary),/Rosette/);
assert.equal(p.children.filter(x=>!x.removed).length,1);
renderProjectComparison({},p);assert.equal(p.children.filter(x=>!x.removed).length,0);
''')


def test_pending_filter_never_invents_progress_or_timing():
    run(r'''
const p=structuredClone(decision);p.status='no_mission';p.creation_refusal='preselection_evidence_cannot_authorize_mission';
p.acquisition_intent_choice_available=true;p.acquisition_intent_selection_status='no_clear_preference';p.selected_acquisition_intent_id=null;
p.viable_acquisition_intent_ids=['r_oiii','r_sii'];p.acquisition_intent_options=[{acquisition_intent_id:'r_oiii',label:'OIII'},{acquisition_intent_id:'r_sii',label:'SII'}];
const summary=createTonightProjectSummary(p);assert(summary);
assert.match(content(summary),/Rosette — Filtre à confirmer/);
assert.match(content(summary),/Créneau et durée à confirmer/);
assert.doesNotMatch(content(summary),/Rosette — OIII|Rosette — SII|40 min|25 min|21:00|1 h 30/);
''')


@pytest.mark.parametrize('status', ['weather_refused','no_candidate','no_productive_window','no_mission','insufficient_evidence'])
def test_refusals_never_gain_a_favorable_summary(status):
    run('decision.status='+json.dumps(status)+r''';assert.equal(createTonightProjectSummary(decision),null);
const parent=new E('main');renderProjectComparison(decision,parent);
assert.equal(parent.querySelector('.project-tonight-summary'),null);assert.match(content(parent),/M42/);
''')


@pytest.mark.parametrize('change', [
    "decision.weather_decision.admissibility='refused'",
    "decision.acquisition_intent_selection_status='no_eligible_intent'",
    "decision.target_decision_status='insufficient_evidence'",
    "decision.catalog_key='missing'",
])
def test_unqualified_or_missing_project_has_no_summary(change):
    run(change+';assert.equal(createTonightProjectSummary(decision),null);')


@pytest.mark.parametrize('change,expected', [
    ("decision.project_comparison[1].filters[0].acquired_hours=null", 'Déjà acquis non renseigné'),
    ("decision.project_comparison[1].filters[0].remaining_hours=null", 'Reste à faire non renseigné'),
    ("decision.project_comparison[1].filters[0].acquired_hours=0", 'Déjà acquis 0 min'),
    ("decision.project_comparison[1].filters[0].acquisition_intent_id='other'", 'Avancement non renseigné'),
    ("decision.explanation={}", 'Aucune justification détaillée n’est disponible'),
])
def test_unknowns_and_missing_reasons_stay_explicit(change, expected):
    run(change+';assert(content(createTonightProjectSummary(decision)).includes('+json.dumps(expected)+'));')


def test_confirmation_uses_the_matching_server_mission_and_keeps_its_warning():
    run(r'''
const p=structuredClone(decision);p.status='no_mission';p.creation_refusal='preselection_evidence_cannot_authorize_mission';
p.acquisition_intent_choice_available=true;p.acquisition_intent_selection_status='no_clear_preference';p.selected_acquisition_intent_id=null;
p.viable_acquisition_intent_ids=['r_oiii','r_sii'];p.acquisition_intent_options=[{acquisition_intent_id:'r_oiii',label:'OIII'},{acquisition_intent_id:'r_sii',label:'SII'}];
const accepted={mission_id:'m',decision_id:'d',selectedCatalogKey:'Rosette',acquisitionIntentId:'r_sii',
 mission:{mission_id:'m',decision_id:'d',acquisition_intent_id:'r_sii',site_timezone:'Europe/Zurich',window_start:'2026-11-21T22:00:00+01:00',window_end:'2026-11-21T23:00:00+01:00',recommended_hours:1,
 reasons:[{severity:'info',title:'Justification confirmée',value:'Valeur fournie'},{severity:'warning',title:'Rosée à surveiller',value:'Contrôler sur place'}]}};
const before=JSON.stringify({p,accepted});
let text=content(createTonightProjectSummary(p,accepted));
assert.match(text,/Plan confirmé pour ce soir/);assert.match(text,/Rosette — SII/);
assert.match(text,/Déjà acquis 25 min/);assert.doesNotMatch(text,/40 min|à confirmer|Altitude favorable/);
assert.match(text,/22:00/);assert.match(text,/Durée productive estimée : 1 h/);
assert.match(text,/Justification confirmée — Valeur fournie/);assert.match(text,/Rosée à surveiller — Contrôler sur place/);
for(const change of [x=>x.decision_id='other',x=>x.selectedCatalogKey='M42',x=>x.mission.acquisition_intent_id='other',x=>x.mission.decision_id='other']){
 const wrong=structuredClone(accepted);change(wrong);text=content(createTonightProjectSummary(p,wrong));
 assert.match(text,/Filtre à confirmer/);assert.doesNotMatch(text,/Plan confirmé pour ce soir|Déjà acquis 25 min/);
}
assert.equal(JSON.stringify({p,accepted}),before);
''')


def test_summary_distinguishes_repeated_local_hours_at_clock_change():
    run(r'''
decision.window_start='2026-10-25T02:10:00+02:00';decision.window_end='2026-10-25T02:40:00+01:00';
const text=content(createTonightProjectSummary(decision));
assert.match(text,/02:10.*UTC\+2/);assert.match(text,/02:40.*UTC\+1/);assert.match(text,/Europe\/Zurich/);
''')
