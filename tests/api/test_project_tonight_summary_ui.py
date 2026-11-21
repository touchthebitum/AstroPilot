"""Execute presentation helpers against exact project/intent identities."""
from pathlib import Path
import shutil
import subprocess


def test_project_summary_identity_unknowns_refusals_and_replacement(tmp_path):
    source = (Path(__file__).resolve().parents[2] / 'astropilot/web/app.js').read_text()
    def between(start, end):
        return source[source.index(start):source.index(end)]
    helpers = (between('function comparisonDuration(', 'function renderProjectComparison(')
               + between('function intentMode(', 'const intentStatusLabels')
               + between('function pendingIntentChoice(', 'function chosenIntent(')
               + between('function projectTonightSummary(', 'function renderDecision('))
    program = r'''
const assert=require('node:assert/strict');
class Element {
 constructor(){this.children=[];this.hidden=false;this.textContent='';}
 replaceChildren(){this.children=[];}
 append(e){this.children.push(e);}
}
const container=new Element();
const document={querySelector:()=>container,createElement:()=>new Element()};
function readableTargetName(value){return value;}
function freeze(value){if(value&&typeof value==='object'){Object.freeze(value);Object.values(value).forEach(freeze);}return value;}
const row=(id,filter,acquired)=>({acquisition_intent_id:id,filter_type:filter,target_hours:3,acquired_hours:acquired,remaining_hours:3-acquired,status:'to_complete'});
const base=freeze({status:'available',target_decision_status:'recommended',catalog_key:'Rosette',
 selected_acquisition_intent_id:'rosette_oiii',acquisition_intent_selection_status:'unique',
 viable_acquisition_intent_ids:['rosette_oiii'],acquisition_intent_options:[{acquisition_intent_id:'rosette_oiii',label:'OIII'}],
 explanation:{positives:[{title:'Raison du moteur'}],warnings:[{title:'Vigilance'}]},
 project_comparison:[{project_id:'M42',filters:[row('m42_oiii','OIII',2)]},
 {project_id:'Rosette',filters:[row('rosette_oiii','OIII',40/60),row('rosette_sii','SII',25/60)]}]});
const before=JSON.stringify(base);
const summary=projectTonightSummary(base);
assert.equal(summary.heading,'Pour ce soir : Rosette — OIII');
assert.equal(summary.progress,'Objectif 3 h · Déjà acquis 40 min · Reste à faire 2 h 20');
assert.match(summary.note,/n’ajoute aucune image/);
assert.equal(JSON.stringify(base),before,'No payload, scores, choice or warnings mutation');
renderProjectTonightSummary(base);assert.equal(container.hidden,false);assert.equal(container.children.length,3);
renderProjectTonightSummary(base);assert.equal(container.children.length,3,'No duplicate content');
const unknown={...base,project_comparison:[{project_id:'Rosette',filters:[{...base.project_comparison[1].filters[0],target_hours:null,acquired_hours:null,remaining_hours:null,status:'incomplete_data'}]}]};
assert.equal(projectTonightSummary(unknown).progress,'Objectif non renseigné · Déjà acquis non renseigné · Reste à faire non renseigné');
const completed={...base,project_comparison:[{project_id:'Rosette',filters:[{...base.project_comparison[1].filters[0],acquired_hours:3,remaining_hours:0,status:'completed'}]}]};
assert.match(projectTonightSummary(completed).progress,/Déjà acquis 3 h · Reste à faire 0 min/);
const pending={...base,status:'no_mission',acquisition_intent_choice_available:true,creation_refusal:'preselection_evidence_cannot_authorize_mission',
 selected_acquisition_intent_id:null,acquisition_intent_selection_status:'multiple',viable_acquisition_intent_ids:['rosette_oiii','rosette_sii'],
 acquisition_intent_options:[{acquisition_intent_id:'rosette_oiii',label:'OIII'},{acquisition_intent_id:'rosette_sii',label:'SII'}]};
assert.match(projectTonightSummary(pending).heading,/Filtre à confirmer$/);
assert.doesNotMatch(projectTonightSummary(pending).progress,/40 min|25 min|0 min/);
for(const change of [{status:'no_candidate'},{status:'no_mission'},{target_decision_status:'not_recommended'},
 {project_comparison:undefined},{catalog_key:'Unknown'},
 {acquisition_intent_selection_status:'no_eligible_intent'},
 {acquisition_intent_selection_status:undefined},
 {viable_acquisition_intent_ids:['other']},
 {project_comparison:[...base.project_comparison,base.project_comparison[1]]}]){
 const input={...base,...change};assert.equal(projectTonightSummary(input),null,JSON.stringify(change));
 renderProjectTonightSummary(input);assert.equal(container.hidden,true);assert.equal(container.children.length,0,'Previous context cleared');
}
for(const filters of [[row('different_intent','OIII',2)],
 [base.project_comparison[1].filters[0],base.project_comparison[1].filters[0]]]){
 const d={...base,project_comparison:[{project_id:'Rosette',filters}]};
 assert.equal(projectTonightSummary(d).progress,'Avancement de cette prise de vue non renseigné.');
}
const switched={...base,catalog_key:'M42',selected_acquisition_intent_id:'m42_oiii',viable_acquisition_intent_ids:['m42_oiii'],acquisition_intent_options:[{acquisition_intent_id:'m42_oiii',label:'OIII'}]};
renderProjectTonightSummary(switched);
assert.match(container.children[0].textContent,/M42/);assert.match(container.children[1].textContent,/Déjà acquis 2 h/);
assert.doesNotMatch(container.children.map(e=>e.textContent).join(' '),/Rosette|40 min/);
'''
    script=tmp_path/'summary.cjs';script.write_text(helpers+program)
    result=subprocess.run([shutil.which('node'),str(script)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
