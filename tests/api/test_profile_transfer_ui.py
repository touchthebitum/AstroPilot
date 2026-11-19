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
const requests=[];let fail=false,aborts=0,statusState='runtime_only',wrongCopy=false,navigations=[];
const context={window:{location:{assign(url){navigations.push(url);}}},document:{querySelector:el,querySelectorAll:()=>[el('#export'),el('#restore')],createElement:()=>({click(){}})},
 AbortController:class{constructor(){this.signal={};}abort(){aborts++;}},
 setTimeout(){return 1;},clearTimeout(){}, URL:{createObjectURL(){return 'blob:local';},revokeObjectURL(){}},
 async fetch(url,opts){requests.push({url,opts});return{ok:!fail,headers:{get(){return null;}},async json(){if(fail)return{message:'<img src=x onerror=attack()>'};if(url.endsWith('status'))return{state:statusState,has_data:statusState==='profile',can_export:statusState==='profile',can_restore:statusState==='empty',platform:'windows',open_supported:true,can_open:statusState==='profile'};if(url.endsWith('preview'))return{confirmation:'nonce',summary:{projects:1,sessions:2,observations:3,comparisons:1}};if(url==='/transfer/open')return{opening:true,data_directory:'/fictive/profile',runtime:{build:'abc1234'}};if(url==='/v1/data-context')return{data_directory:wrongCopy?'/another/copy':'/fictive/profile',runtime:{build:'abc1234'}};return {restored:true,summary:{projects:1,sessions:2,observations:3,comparisons:1}};}};}};
vm.createContext(context);vm.runInContext(code,context);
async function flush(){for(let i=0;i<20;i++)await Promise.resolve();}
(async()=>{
 await flush();assert.equal(el('#restore-section').hidden,true);assert.equal(el('#export-section').hidden,true);
 assert.equal(el('#fresh-copy-section').hidden,false);assert.equal(el('#next-section').hidden,true);
 assert.match(el('#message').textContent,/traces techniques/);
 statusState='demo_started';await vm.runInContext('status()',context);assert.match(el('#message').textContent,/configuration n’est pas terminée/);assert.equal(el('#continue-demo-section').hidden,false);assert.equal(el('#restore-section').hidden,true);assert.equal(el('#export-section').hidden,true);
 statusState='unrecognized';await vm.runInContext('status()',context);assert.match(el('#message').textContent,/aucun profil/);
 statusState='profile';await vm.runInContext('status()',context);assert.equal(el('#export-section').hidden,false);
 statusState='empty';await vm.runInContext('status()',context);assert.equal(el('#restore-section').hidden,false);assert.equal(el('#windows-note').hidden,false);
 el('#archive').files=[{size:128}];await el('#archive').listeners.change();
 assert.equal(el('#restore').hidden,false);assert.match(el('#preview').textContent,/1 projet/);assert.equal(el('#next-section').hidden,true);
 assert(!requests.some(r=>r.url.endsWith('restore')));assert.equal(el('#not-restored').hidden,false);assert.match(el('#stage').textContent,/à confirmer/);assert.equal(el('#open-profile').hidden,true);
 fail=true;await el('#archive').listeners.change();assert.equal(el('#restore').hidden,true);
 assert.match(el('#message').textContent,/<img/);assert.equal(el('#message').innerHTML,undefined);
 await el('#restore').listeners.click();assert(!requests.some(r=>r.url.endsWith('restore')));
 fail=false;await el('#archive').listeners.change();await el('#restore').listeners.click();
 const restored=requests.filter(r=>r.url.endsWith('restore'));assert.equal(restored.length,1);
 assert.deepEqual(JSON.parse(restored[0].opts.body),{confirmation:'nonce',confirm:true});
 assert.equal(el('#restore-section').hidden,true);assert.match(el('#message').textContent,/reprises/);assert.match(el('#restored-summary').textContent,/1 projet, 2 séances photo, 3 observations, 1 comparaison/);assert.equal(el('#open-profile').hidden,false);assert.match(el('#stage').textContent,/Données reprises/);
 await el('#restore').listeners.click();assert.equal(requests.filter(r=>r.url.endsWith('restore')).length,1);
 wrongCopy=true;await el('#open-profile').listeners.click();assert.deepEqual(navigations,[]);assert.match(el('#message').textContent,/autre copie/);wrongCopy=false;await el('#open-profile').listeners.click();assert.deepEqual(navigations,['/']);assert.equal(aborts,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    subprocess.run([node, '-e', script, str(html)], check=True, timeout=15)


@pytest.mark.parametrize("failure", ["network", "timeout", "invalid_json", "server_refusal"])
def test_restore_uncertain_response_reopens_without_retry(failure):
    node = shutil.which("node")
    assert node, "Node is required"
    html = Path(__file__).resolve().parents[2] / "astropilot/web/profile-transfer.html"
    program = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8').match(/<script nonce="[^"]+">([\s\S]+)<\/script>/)[1];
const mode=process.argv[2],nodes=new Map();let profile=false,posts=0;
function el(id){if(!nodes.has(id))nodes.set(id,{hidden:true,textContent:'',files:[],listeners:{},addEventListener(e,f){this.listeners[e]=f;}});return nodes.get(id);}
const context={document:{querySelector:el,querySelectorAll:()=>[]},AbortController:class{signal={};abort(){}},setTimeout(){return 1;},clearTimeout(){},
 async fetch(url){if(url==='/transfer/status')return{ok:true,json:async()=>({state:profile?'profile':'empty',can_restore:!profile,can_export:profile,can_open:profile,open_supported:true})};
 if(url==='/transfer/preview')return{ok:true,json:async()=>({confirmation:'nonce',summary:{projects:1,sessions:0,observations:0,comparisons:0}})};
 assert.equal(url,'/transfer/restore');posts++;
 if(mode==='server_refusal')return{ok:false,json:async()=>({message:'Cette copie contient déjà des données.'})};
 profile=true;
 if(mode==='network')throw TypeError('Failed to fetch');
 if(mode==='timeout'){const e=Error('timeout');e.name='AbortError';throw e;}
 return{ok:true,json:async()=>{throw SyntaxError('response cut short');}};
 }};
vm.createContext(context);vm.runInContext(code,context);
(async()=>{await vm.runInContext('status()',context);el('#archive').files=[{size:12}];await el('#archive').listeners.change();assert.equal(el('#not-restored').hidden,false);
 await el('#restore').listeners.click();assert.equal(posts,1);assert.equal(el('#not-restored').hidden,true);assert.equal(el('#restored-summary').hidden,true);
 if(mode==='server_refusal'){assert.match(el('#message').textContent,/contient déjà/);assert.doesNotMatch(el('#message').textContent,/peut-être/);return;}
 assert.match(el('#stage').textContent,/à vérifier/);assert.match(el('#message').textContent,/peut-être déjà été reprises/);assert.match(el('#message').textContent,/Fermez puis rouvrez/);assert.doesNotMatch(el('#message').textContent,/Failed to fetch|pas encore reprises/);assert.equal(el('#restore-section').hidden,true);assert.equal(el('#next-section').hidden,true);
 await el('#restore').listeners.click();assert.equal(posts,1);
 await vm.runInContext('status()',context);assert.equal(el('#restore-section').hidden,true);assert.equal(el('#export-section').hidden,false);assert.match(el('#message').textContent,/profil enregistré/);assert.equal(posts,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    subprocess.run([node, "-e", program, str(html), failure], check=True, timeout=15)
