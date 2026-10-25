"""Exercise the actual offline assistant script with an isolated browser model."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_preview_confirmation_failure_and_no_html_injection():
    node = shutil.which('node')
    if not node:
        pytest.fail('Node is required for the data assistant UI regressions')
    html = Path(__file__).resolve().parents[2] / 'astropilot/web/profile-transfer.html'
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[1],'utf8');
const code=html.match(/<script nonce="[^"]+">([\s\S]+)<\/script>/)[1];
const nodes=new Map();
function el(id){if(!nodes.has(id))nodes.set(id,{hidden:true,disabled:false,textContent:'',files:[],listeners:{},addEventListener(event,fn){this.listeners[event]=fn;}});return nodes.get(id);}
const requests=[];let fail=false,aborts=0;
const context={document:{querySelector:el,querySelectorAll:()=>[el('#export'),el('#restore')],createElement:()=>({click(){}})},
 AbortController:class{constructor(){this.signal={};}abort(){aborts++;}},
 setTimeout(){return 1;},clearTimeout(){}, URL:{createObjectURL(){return 'blob:local';},revokeObjectURL(){}},
 async fetch(url,opts){requests.push({url,opts});return{ok:!fail,headers:{get(){return null;}},async json(){if(fail)return{message:'<img src=x onerror=attack()>'};if(url.endsWith('status'))return{has_data:false,can_restore:true,platform:'windows'};if(url.endsWith('preview'))return{confirmation:'nonce',summary:{projects:1,sessions:2,observations:3,comparisons:1}};return {restored:true};}};}};
vm.createContext(context);vm.runInContext(code,context);
async function flush(){for(let i=0;i<20;i++)await Promise.resolve();}
(async()=>{
 await flush();assert.equal(el('#restore-section').hidden,false);assert.equal(el('#windows-note').hidden,false);
 el('#archive').files=[{size:128}];await el('#archive').listeners.change();
 assert.equal(el('#restore').hidden,false);assert.match(el('#preview').textContent,/1 projet/);
 assert(!requests.some(r=>r.url.endsWith('restore')));
 fail=true;await el('#archive').listeners.change();assert.equal(el('#restore').hidden,true);
 assert.match(el('#message').textContent,/<img/);assert.equal(el('#message').innerHTML,undefined);
 await el('#restore').listeners.click();assert(!requests.some(r=>r.url.endsWith('restore')));
 fail=false;await el('#archive').listeners.change();await el('#restore').listeners.click();
 const restored=requests.filter(r=>r.url.endsWith('restore'));assert.equal(restored.length,1);
 assert.deepEqual(JSON.parse(restored[0].opts.body),{confirmation:'nonce',confirm:true});
 assert.equal(el('#restore-section').hidden,true);assert.match(el('#message').textContent,/reprises/);
 await el('#restore').listeners.click();assert.equal(requests.filter(r=>r.url.endsWith('restore')).length,1);
 assert.equal(aborts,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    subprocess.run([node, '-e', script, str(html)], check=True, timeout=15)
