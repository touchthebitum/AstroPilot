"""Guided presentation preserves exact progress, locks and late-read ownership."""
from pathlib import Path
import shutil
import subprocess

import pytest

SOURCE = Path(__file__).parents[2] / 'astropilot/web/app.js'

DOM = r'''
const assert = require('node:assert/strict');
class E {
 constructor(tag) {this.tag=tag;this.children=[];this.dataset={};this.listeners={};this.value='';this.hidden=false;}
 append(...items){this.children.push(...items);}
 replaceChildren(){this.children=[];this.textContent='';}
 addEventListener(name,fn){this.listeners[name]=fn;}
 all(){return this.children.flatMap(x=>[x,...(x.all?x.all():[])]);}
 querySelector(selector){return this.all().find(x=>x.tag===selector)||null;}
}
'''

def run_js(program):
    node=shutil.which('node')
    if not node: pytest.skip('Node is required for actual presentation logic')
    result=subprocess.run([node,'-e',program],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_human_duration_keeps_fractional_seconds_and_credit_locks():
    source=SOURCE.read_text()
    functions=source[source.index('function progressInput('):source.index('async function openProjectProgress(')]
    functions+=source[source.index('function addSimpleDurationFields('):source.index('function prefillConfiguration(')]
    run_js(DOM+r'''
const document={createElement:tag=>new E(tag)};
'''+functions+r'''
function make(seconds,locked=false,method='manual') {
 const section=new E('fieldset'),mode=new E('select');mode.value=method;
 const manual=progressInput('seconds',seconds,'acquired_duration_manual');
 let updates=0;addSimpleDurationFields(section,mode,manual,()=>updates++,locked);
 const input=name=>section.all().find(x=>x.dataset?.field===name);
 return {section,mode,manual:manual.querySelector('input'),h:input('simple_hours'),m:input('simple_minutes'),updates:()=>updates};
}
const a=make(5400.5);
assert.equal(Number(a.h.value),1);
assert.equal(Number(a.m.value),(1800.5/60));
a.mode.listeners.change();
assert.equal(Number(a.manual.value),5400.5,'a view refresh must not round or overwrite seconds');
a.h.value='2';a.m.value='15';a.m.listeners.input();
assert.equal(Number(a.manual.value),8100);
a.m.value='60';a.m.listeners.input();assert.equal(a.manual.value,'','invalid minutes must not become a duration');
const locked=make(3600,true);assert.equal(locked.h.disabled,true);assert.equal(locked.m.disabled,true);
const unknown=make(undefined,false,'unknown');assert.equal(unknown.manual.value,'');
assert.equal(unknown.h.value,'');assert.equal(unknown.m.value,'');
const button=unknown.section.all().find(x=>x.tag==='button');button.listeners.click();
assert.equal(unknown.mode.value,'manual');assert.equal(unknown.manual.value,'','choosing entry must not invent zero progress');
''')


def test_cards_use_canonical_effective_progress_and_ignore_superseded_reads():
    source=SOURCE.read_text()
    functions=source[source.index('function progressDuration('):source.index('function progressInput(')]
    functions+=source[source.index('function renderSimpleProjects('):source.index('function addSimpleDurationFields(')]
    run_js(DOM+r'''
const region=new E('div');
const document={createElement:tag=>new E(tag),querySelector:()=>region};
const configuration={projects:{'Sh2-129':{hours:99}}};
const state={configuration};
let requests=[];
function fetch(url){return new Promise((resolve,reject)=>requests.push({url,resolve,reject}));}
function prepareGuidedSession(){} function openProjectProgress(){}
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const payload={acquisition_intent_targets:[{acquisition_intent_id:'ha',target_hours:3}],
 acquisition_intents:[{acquisition_intent_id:'ha',filter_type:'Ha'}],
 intent_progress_breakdown:[{acquisition_intent_id:'ha',effective_total_seconds:6300,remaining_hours:1.25}]};
'''+functions+r'''
(async()=>{
 renderSimpleProjects([['Sh2-129',configuration.projects['Sh2-129']]]);
 const old=region.children[0].children[1];
 renderSimpleProjects([['Sh2-129',configuration.projects['Sh2-129']]]);
 const current=region.children[0],status=current.children[1];
 requests.shift().resolve({ok:true,json:async()=>payload});await flush();
 assert.equal(old.children.length,0,'superseded read cannot update previous cards');
 requests.shift().resolve({ok:true,json:async()=>payload});await flush();
 const text=status.children[0].textContent;
 assert.match(text,/1 h 45 sur 3 h/);assert.doesNotMatch(text,/99/,'legacy scalar must not override canonical credits');
 assert.match(status.children[0].children[0].textContent,/1 h 15/);
 renderSimpleProjects([['Sh2-129',configuration.projects['Sh2-129']]]);
 const failed=region.children[0];requests.shift().reject(new Error('offline'));await flush();
 assert.match(failed.children[1].textContent,/ne peut pas être relu/);
 assert.equal(failed.children[2].children[0].disabled,true);
})().catch(e=>{console.error(e);process.exitCode=1;});
''')


def test_stale_configuration_cannot_be_advanced_by_a_project_write():
    source=SOURCE.read_text()
    function=source[source.index('async function saveProjectProgress('):source.index('// Guided presentation uses')]
    run_js(DOM+r"""
const feedback={textContent:''};
const editor={querySelector:()=>feedback};
const document={querySelector:()=>editor};
const state={progressEditor:{profile_revision:8},configuration:{profile_revision:7}};
let writes=0;async function fetch(){writes++;throw new Error('must not write');}
"""+function+r"""
(async()=>{
 await saveProjectProgress();
 assert.equal(writes,0);
 assert.equal(state.configuration.profile_revision,7);
 assert.match(feedback.textContent,/n’a pas été envoyée/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
