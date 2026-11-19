"""Render real comparison code, including unknown data and independent filters."""
from pathlib import Path
import subprocess
import shutil
import pytest


@pytest.mark.parametrize('boundary', [None, (7199, '1 h 59', '< 1 min'),
    (7170, '1 h 59', '< 1 min'), (7200, '2 h', '0 min'),
    (1, '< 1 min', '1 h 59'), (0, '0 min', '2 h'),
    (60, '1 min', '1 h 59')])
def test_comparison_labels_zero_unknown_and_separate_filters(tmp_path, boundary):
    source=(Path(__file__).resolve().parents[2]/'astropilot/web/app.js').read_text()
    start = source.index('function comparisonDuration(') if 'function comparisonDuration(' in source else source.index('function renderProjectComparison(')
    render=source[start:source.index('function renderDecision(')]
    actual_duration=source[source.index('function duration(hours) {'):source.index('// Decision weather trust carries')]
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

function content(e){return [e.textContent,...e.children.filter(c=>!c.removed).map(content)].join(' ');}
const parent=new E();
const data={project_comparison:[{project_id:'Rosette fictive',filters:[
 {filter_type:'Ha',target_hours:1,acquired_hours:1,remaining_hours:0,status:'completed'},
 {filter_type:'OIII',target_hours:3,acquired_hours:40/60,remaining_hours:3-40/60,status:'to_complete'},
 {filter_type:'SII',target_hours:3,acquired_hours:25/60,remaining_hours:3-25/60,status:'to_complete'},
 {filter_type:'R',target_hours:null,acquired_hours:null,remaining_hours:null,status:'incomplete_data'}]}]};
'''+actual_duration+render+r'''
renderProjectComparison(data,parent);
let text=content(parent);
assert(text.includes('Hα : objectif 1 h · acquis 1 h · restant 0 min · Objectif atteint'));
assert(text.includes('OIII : objectif 3 h · acquis 40 min'));
assert(text.includes('SII : objectif 3 h · acquis 25 min'));
assert(text.includes('R : objectif non renseigné · acquis non renseigné · restant non renseigné · Données à compléter'));
assert(!text.includes('NaN'));
renderProjectComparison(data,parent);
assert.equal(parent.children.filter(e=>!e.removed).length,1,'no duplicate summary');
renderProjectComparison({},parent);
assert.equal(parent.children.filter(e=>!e.removed).length,0,'old comparison cleared');
'''
    if boundary is not None:
        seconds, acquired, remaining = boundary
        import json
        program += r'''
const edge=new E();
renderProjectComparison({project_comparison:[{project_id:'Rosette fictive',filters:[{
 filter_type:'OIII',target_hours:2,acquired_hours:SECONDS/3600,remaining_hours:(7200-SECONDS)/3600,
 status:SECONDS===7200?'completed':'to_complete'}]}]},edge);
const result=content(edge);
assert(result.includes('acquis '+ACQUIRED+' · restant '+REMAINING),result);
assert(!result.includes('1 h 60'),result);
'''.replace('SECONDS',str(seconds)).replace('ACQUIRED',json.dumps(acquired)).replace('REMAINING',json.dumps(remaining))
    script=tmp_path/'comparison.cjs';script.write_text(program)
    r=subprocess.run([shutil.which('node'),str(script)],capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stdout+r.stderr
