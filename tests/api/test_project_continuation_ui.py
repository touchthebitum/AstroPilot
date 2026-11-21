"""Continuation uses recorded evidence and never writes or recalculates a decision."""
from pathlib import Path
import json
import shutil
import subprocess
import pytest

SOURCE = Path(__file__).parents[2] / "astropilot/web/app.js"


def run(checks):
    source = SOURCE.read_text()
    helpers = source[source.index("function projectContinuationAdvice("):source.index("function showTonightUnavailable(")]
    program = r"""
const assert = require('node:assert/strict');
const state={}; const calls=[];
const ui={retry:{hidden:false,click(){calls.push('retry')}}};
function pendingIntentChoice(p){return !!p.acquisition_intent_choice_available}
function targetedIntentAssessments(p){return (p.acquisition_intent_assessments||[]).filter(i=>!(i.reason_codes||[]).includes('intent_not_targeted_by_project'))}
function guardUnresolvedAcceptance(){return !!state.blocked}
function navigateGuidedProjects(){calls.push('projects')}
function setView(view){calls.push(view)}
class E {
 constructor(){this.children=[];this.dataset={};this.hidden=false;this.textContent='';}
 append(...items){this.children.push(...items)}
 replaceChildren(){this.children=[]}
 addEventListener(event,callback){this.callback=callback}
 click(){this.callback()}
}
const nodes={'#message-continuation':new E(),'#message-edit-availability':new E()};
const document={querySelector:s=>nodes[s]||null,createElement:()=>new E()};
const base={status:'no_candidate',project_comparison:[{project_id:'Rosette fictive',filters:[{status:'completed',target_hours:3,acquired_hours:3,remaining_hours:0}]}]};
function content(e){return [e.textContent,...e.children.map(content)].join(' ')}
""" + helpers + checks
    result = subprocess.run([shutil.which("node"), "-"],input=program,text=True,capture_output=True,timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("filters,other,expected,absent", [
    ([{"status":"completed"}],False,"Tous les objectifs", "Une valeur manquante"),
    ([{"status":"incomplete_data"}],False,"Vérifiez les objectifs", "Tous les objectifs"),
    ([{"status":"completed"},{"status":"incomplete_data"}],False,"Certains objectifs", "Tous les objectifs"),
    ([{"status":"completed"}],True,"Certains objectifs", "Tous les objectifs"),
    ([],False,"Vérifiez les objectifs", "Tous les objectifs"),
])
def test_completed_unknown_and_mixed_are_distinguished(filters,other,expected,absent):
    run("base.project_comparison[0].filters="+json.dumps(filters)+";"+
        ("base.project_comparison.push({project_id:'Autre fictif',filters:[]});" if other else "")+
        f"const a=projectContinuationAdvice(base);assert.match(a.lines.join(' '),/{expected}/);assert.doesNotMatch(a.lines.join(' '),/{absent}/);assert.deepEqual(a.actions,['projects']);")


def test_weather_is_not_inferred_from_a_missing_cause():
    run(r"""
let a=projectContinuationAdvice({...base,status:'weather_refused'});
assert.match(a.lines.join(' '),/décision météo refuse/);assert(a.actions.includes('refresh'));assert(!a.actions.includes('hours'));
a=projectContinuationAdvice({...base,status:'no_recommendation'});
assert.match(a.lines.join(' '),/motif peut varier/);assert(!a.actions.includes('refresh'));assert(!a.actions.includes('hours'));
assert(!a.lines.some(s=>s.includes('décision météo refuse')));
""")


def test_short_duration_and_filter_evidence_can_coexist_without_changing_payload():
    run(r"""
const p={...base,status:'no_productive_window',actionability_refusal:{refusal_stage:'continuous_window_too_short',best_productive_window_minutes:35,required_continuous_minutes:60},acquisition_intent_assessments:[{reason_codes:['required_filter_unavailable','intent_progress_evidence_insufficient']}]};
const before=JSON.stringify(p),a=projectContinuationAdvice(p);
assert.match(a.lines.join(' '),/35 min.*60 min/);assert.match(a.lines.join(' '),/sans garantie/);
assert.deepEqual(a.actions,['hours','refresh','equipment','projects']);assert.equal(JSON.stringify(p),before);
const unknown=projectContinuationAdvice({...p,actionability_refusal:{}});assert(!unknown.lines.join(' ').includes('35 min'));
""")


def test_no_advice_for_an_available_or_pending_decision_or_noncomparison():
    run(r"""
assert.equal(projectContinuationAdvice({...base,status:'available'}),null);
assert.equal(projectContinuationAdvice({...base,status:'no_mission',acquisition_intent_choice_available:true}),null);
assert.equal(projectContinuationAdvice({status:'weather_refused'}),null);
""")


def test_render_replaces_advice_and_navigation_does_not_trigger_a_search():
    run(r"""
renderProjectContinuation(base);const box=nodes['#message-continuation'];assert(!box.hidden);
assert.match(content(box),/Comment continuer/);assert.match(content(box),/aucun plan, séance ni crédit/);
box.children.find(e=>e.className==='message-actions').children[0].click();assert.deepEqual(calls,['projects']);
renderProjectContinuation({...base,status:'no_productive_window'});
const buttons=box.children.find(e=>e.className==='message-actions').children;
buttons.find(b=>b.dataset.continuationAction==='hours').click();assert.deepEqual(calls,['projects','availability']);
buttons.find(b=>b.dataset.continuationAction==='refresh').click();assert.deepEqual(calls,['projects','availability','retry']);
state.blocked=true;buttons[0].click();assert.equal(calls.length,3);
renderProjectContinuation({status:'weather_refused'});assert(box.hidden);assert.equal(box.children.length,0);
""")
