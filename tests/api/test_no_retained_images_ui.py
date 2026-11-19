"""An explicit zero is durable evidence, never an automatic progress credit."""
from pathlib import Path
import shutil
import subprocess


def test_no_retained_images_distinguishes_unknown_replays_and_revised_sorting():
    source = (Path(__file__).parents[2] / 'astropilot/web/app.js').read_text()
    helpers = source[source.index('function usableEvidence('):source.index('function sessionStatus(')]
    command = source[source.index('async function recordSessionNoImages('):source.index('async function recordSessionEvidence(')]
    harness = r'''
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');
const crypto = {randomUUID};
const storage = new Map(), localStorage = {
 getItem:k=>storage.get(k)||null, setItem:(k,v)=>storage.set(k,v), removeItem:k=>storage.delete(k)};
let session = {execution:{execution_id:'fictitious',status:'completed'},credit:null,evidence:[]};
const currentSession=()=>session;
let calls=[], loseResponse=true;
async function postSession(url,payload){
 assert.equal(url,'/v1/outcome-evidence'); calls.push(JSON.parse(JSON.stringify(payload)));
 if(loseResponse) {loseResponse=false;throw Error('response lost')}
 session.evidence.push(payload);
}
'''
    checks = r'''
(async()=>{
 assert.equal(noRetainedImages(session),false);
 for(const value of [null,undefined,'0']){
  session.evidence=[{category:'acquisition',source:'user',usable_integration_duration:value}];
  assert.equal(noRetainedImages(session),false);
 }
 session.evidence=[];
 await assert.rejects(recordSessionNoImages(),/response lost/);
 await recordSessionNoImages();
 assert.deepEqual(calls[0],calls[1]);
 assert.equal(calls[1].usable_integration_duration,0);
 assert.equal(noRetainedImages(session),true);
 await recordSessionNoImages();assert.equal(calls.length,2);
 const reloaded=JSON.parse(JSON.stringify(session));assert.equal(noRetainedImages(reloaded),true);
 session.execution.status='interrupted';assert.equal(noRetainedImages(session),false);
 await recordSessionNoImages();assert.equal(calls.length,2);
 session.execution.status='completed';
 session.evidence.push({category:'acquisition',source:'user',usable_integration_duration:600});
 assert.equal(noRetainedImages(session),false);
 await recordSessionNoImages();assert.equal(calls.length,2);
 session.evidence=[];session.credit={total_duration_us:600000000};
 await recordSessionNoImages();assert.equal(calls.length,2);
})().catch(error=>{console.error(error);process.exit(1)});
'''
    result = subprocess.run([shutil.which('node'), '-'],input=harness+helpers+command+checks,text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
