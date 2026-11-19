"""Render real comparison code, including unknown data and independent filters."""
from pathlib import Path
import subprocess
import shutil


def test_comparison_labels_zero_unknown_and_separate_filters(tmp_path):
    source=(Path(__file__).resolve().parents[2]/'astropilot/web/app.js').read_text()
    render=source[source.index('function renderProjectComparison('):source.index('function renderDecision(')]
    program=r'''
const assert=require('node:assert/strict');
class E {
 constructor(){this.children=[];this.textContent='';this.className='';}
 append(...items){this.children.push(...items);}
 querySelector(){return this.children.find(c=>!c.removed && c.className==='project-comparison');}
 remove(){this.removed=true;}
}
const document={createElement:()=>new E()};
function readableTargetName(s){return s;}
function duration(h){return h*60+' min';}
function content(e){return [e.textContent,...e.children.filter(c=>!c.removed).map(content)].join(' ');}
const parent=new E();
const data={project_comparison:[{project_id:'Rosette fictive',filters:[
 {filter_type:'Ha',target_hours:1,acquired_hours:1,remaining_hours:0,status:'completed'},
 {filter_type:'OIII',target_hours:3,acquired_hours:40/60,remaining_hours:3-40/60,status:'to_complete'},
 {filter_type:'SII',target_hours:3,acquired_hours:25/60,remaining_hours:3-25/60,status:'to_complete'},
 {filter_type:'R',target_hours:null,acquired_hours:null,remaining_hours:null,status:'incomplete_data'}]}]};
'''+render+r'''
renderProjectComparison(data,parent);
let text=content(parent);
assert(text.includes('Hα : objectif 60 min · acquis 60 min · restant 0 min · Objectif atteint'));
assert(text.includes('OIII : objectif 180 min · acquis 40 min'));
assert(text.includes('SII : objectif 180 min · acquis 25 min'));
assert(text.includes('R : objectif non renseigné · acquis non renseigné · restant non renseigné · Données à compléter'));
assert(!text.includes('NaN'));
renderProjectComparison(data,parent);
assert.equal(parent.children.filter(e=>!e.removed).length,1,'no duplicate summary');
renderProjectComparison({},parent);
assert.equal(parent.children.filter(e=>!e.removed).length,0,'old comparison cleared');
'''
    script=tmp_path/'comparison.cjs';script.write_text(program)
    r=subprocess.run([shutil.which('node'),str(script)],capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stdout+r.stderr
