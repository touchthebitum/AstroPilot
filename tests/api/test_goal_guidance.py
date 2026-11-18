import json, subprocess, shutil
from pathlib import Path
from astropilot.project_templates import project_templates


def test_guidance_is_scoped_and_optional():
    intents=[i for t in project_templates() for i in t['acquisition_intents']]
    advised=[i for i in intents if 'exposure_guidance' in i]
    assert {i['acquisition_intent_id'] for i in advised} == {'m42_ha','ngc7000_ha','rosette_ha'}
    for i in advised:
        a=i['exposure_guidance']
        assert i['filter_type']==a['filter_type']=='Ha'
        assert a['basis']=='editorial_starting_point'
        assert 1<=a['min_hours']<=a['suggested_hours']<=a['max_hours']
        assert a['sources']


def test_frame_counts_and_explicit_choice():
    js=(Path(__file__).parents[2]/'astropilot/web/goal-guidance.js').read_text()
    harness=r"""
const assert=require('node:assert/strict');
class El { constructor(){this.children=[];this.dataset={};this.value='';this.events={};} append(...x){this.children.push(...x);} insertBefore(x){this.children.push(x);} setAttribute(){} addEventListener(k,f){(this.events[k]??=[]).push(f);} dispatchEvent(e){for(const f of this.events[e.type]||[])f();} focus(){this.focused=true;} }
const document={createElement:()=>new El(),head:new El()};
"""
    harness+=js+r"""
assert.equal(goalFrameCount(3,300),36);assert.equal(goalFrameCount(6,300),72);assert.equal(goalFrameCount(2,300),24);assert.equal(goalFrameCount(4,300),48);assert.equal(goalFrameCount(3,420),26);
for(const x of [0,-1,NaN,Infinity]){assert.equal(goalFrameCount(3,x),null);assert.equal(goalFrameCount(x,300),null);}
const row=new El(),goal=new El(),input=new El();
addProjectGoalGuidance(row,{filter_type:'Ha',exposure_guidance:{basis:'editorial_starting_point',filter_type:'Ha',min_hours:2,max_hours:4,suggested_hours:3,note:'test'}},goal,input);
assert.equal(input.value,'');assert.equal(row.dataset.goalChoice,'pending');
const box=row.children[0];box.children[1].dispatchEvent(new Event('click'));
assert.equal(input.value,'3');assert.equal(row.dataset.goalChoice,'chosen');
const details=box.children[4],exposure=details.children[1].children[0],counts=details.children[2];
exposure.value='300';exposure.dispatchEvent(new Event('input'));assert.match(counts.textContent,/24 à 48/);assert.match(counts.textContent,/36 clichés au total/);
input.value='6';input.dispatchEvent(new Event('input'));assert.match(counts.textContent,/72 clichés au total/);
const fallback=new El();addProjectGoalGuidance(fallback,{filter_type:'OIII'},new El(),new El());assert.match(fallback.children[0].children[0].textContent,/Pas encore de repère/);
"""
    subprocess.run([shutil.which('node'),'-e',harness],check=True,capture_output=True,text=True)
