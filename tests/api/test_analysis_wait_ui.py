"""A stalled response must not keep the UI busy or publish a late decision."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_analysis_wait_bounds_body_and_ignores_late_replies(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for actual UI deadline logic')
    source = (Path(__file__).parents[2] / 'astropilot/web/app.js').read_text()
    function = source[source.index('async function loadTonight('):source.index('document.querySelector("#site-next").addEventListener')]
    program = r'''
const assert=require('node:assert/strict');
let timers=new Map(),sequence=0;
function setTimeout(fn,ms){const id=++sequence;timers.set(id,{fn,ms});return id;}
function clearTimeout(id){timers.delete(id);}
function fire(ms){const entry=[...timers].find(([,x])=>x.ms===ms);assert.ok(entry);timers.delete(entry[0]);entry[1].fn();}
const message={hidden:true,textContent:''};
const document={querySelector:()=>message};
const ui={recommendationSubmit:{disabled:false},refresh:{disabled:false}};
const state={configurationGeneration:1,decisionSiteGeneration:1,view:'availability',viewRevision:0};
let requests=0,rendered=[],clears=0,lastSignal,transport;
function guardUnresolvedAcceptance(){return false;}
function decisionSiteFingerprint(){return 'retained';}
function showAvailabilityError(value){state.error=value;}
function setView(view){state.view=view;state.viewRevision++;}
function show(){setView('loading');}
function setCurrentFieldObservationDecision(value){if(value)rendered.push(value.decision_id);}
function clearAcceptedMission(){clears++;}
function renderDecision(){setView('recommendation');}
function showTonightUnavailable(){throw Error('unexpected');}
function pendingIntentChoice(){return false;}
function fetch(_url,options){requests++;lastSignal=options.signal;return transport();}
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const availability={mode:'fixed_window',start:'2026-10-19T21:00:00+02:00',end:'2026-10-19T23:00:00+02:00'};
const response=id=>({ok:true,json:async()=>({status:'available',decision_id:id})});
'''+function+r'''
(async()=>{
 // No fetch response at all; the mock deliberately ignores AbortSignal.
 let release;transport=()=>new Promise(resolve=>release=resolve);
 const first=loadTonight(availability);await flush();
 fire(10000);assert.equal(message.hidden,false);assert.match(message.textContent,/plus de temps/);
 assert.equal(ui.recommendationSubmit.disabled,true);assert.equal(requests,1);
 await loadTonight(availability);assert.equal(requests,1,'no duplicate while busy');
 fire(90000);await first;
 assert.equal(lastSignal.aborted,true);assert.equal(state.view,'availability');
 assert.equal(state.requestingRecommendation,false);assert.match(state.error,/90 secondes/);
 assert.deepEqual(state.availability,availability);assert.equal(clears,0);
 assert.equal(ui.recommendationSubmit.disabled,false);assert.equal(ui.refresh.disabled,false);
 assert.equal(timers.size,0);
 // A new response succeeds; the abandoned old response must not replace it.
 transport=async()=>response('new');await loadTonight(availability);
 assert.deepEqual(rendered,['new']);assert.equal(timers.size,0);
 release(response('late'));await flush();assert.deepEqual(rendered,['new']);assert.equal(clears,1);
 // The same deadline includes a body that never finishes decoding.
 let releaseBody;transport=async()=>({ok:true,json:()=>new Promise(r=>releaseBody=r)});
 const body=loadTonight(availability);await flush();fire(90000);await body;
 releaseBody({status:'available',decision_id:'late-body'});await flush();
 assert.deepEqual(rendered,['new']);assert.equal(timers.size,0);
 // Leaving the screen prevents the delayed notice or timeout from navigating back.
 transport=()=>new Promise(()=>{});const stale=loadTonight(availability);
 setView('projects');fire(10000);assert.equal(message.hidden,true);
 fire(90000);await stale;assert.equal(state.view,'projects');assert.equal(timers.size,0);
 // A genuine network failure keeps the availability and restores controls.
 transport=async()=>{throw Error('offline');};await loadTonight(availability);
 assert.match(state.error,/Connexion impossible/);assert.equal(timers.size,0);
 assert.deepEqual(state.availability,availability);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    script = tmp_path / 'analysis-wait.cjs'
    script.write_text(program)
    completed = subprocess.run([node, str(script)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
