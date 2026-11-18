"""Exercise actual assistant code with lost requests/replies and tab reloads."""
from pathlib import Path
import shutil,subprocess
import pytest

PROGRAM=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const original=fs.readFileSync(process.argv[1],'utf8').match(/<script nonce="[^"]+">([\s\S]+)<\/script>/)[1];
const operation=process.argv[2],fault=process.argv[3],storage=new Map(),calls=[],downloads=[];
const summary={projects:1,sessions:1,observations:0,comparisons:0,created_at_utc:'2026-11-16T09:00:00Z',project_details:[{project_id:'Rosette',filters:[{filter_type:'OIII',acquired_seconds:2400,target_hours:3},{filter_type:'SII',acquired_seconds:1500,target_hours:4}]}]};
let activity={last_export:{filename:'ancienne.zip',requested_at_utc:'2026-11-16T09:00:00Z'},last_check:{verified:true,filename:'ancienne.zip',matches_last_export:true,checked_at_utc:'2026-11-16T09:01:00Z',summary}},broken=true,failNextStatus=false;
function response(data){return{ok:true,headers:{get(){return null;}},json:async()=>data};}
function networkError(){const e=TypeError('Failed to fetch');if(fault==='timeout')e.name='AbortError';return e;}
function page(session='session-A',denied=false){
 const nodes=new Map();function el(id){if(!nodes.has(id))nodes.set(id,{hidden:true,disabled:false,textContent:'',value:'same-file.zip',files:[],listeners:{},addEventListener(e,f){this.listeners[e]=f;}});return nodes.get(id);}
 const c={sessionStorage:{getItem(k){if(denied)throw Error('denied');return storage.get(k)??null;},setItem(k,v){if(denied)throw Error('denied');storage.set(k,v);},removeItem(k){storage.delete(k);}},document:{querySelector:el,querySelectorAll:()=>[el('#export'),el('#restore')],createElement:()=>({click(){downloads.push(this.download);}})},AbortController:class{signal={};abort(){}},setTimeout(){return 1;},clearTimeout(){},URL:{createObjectURL(){return 'blob:local';},revokeObjectURL(){}},
 async fetch(url){calls.push(url);
  if(url==='/transfer/status'){if(failNextStatus){failNextStatus=false;throw networkError();}return response({state:'profile',can_export:true,can_restore:false,backup_activity:activity});}
  if(url==='/transfer/export'){
   if(broken&&operation==='export'&&['before_send','timeout'].includes(fault))throw networkError();
   activity={last_export:{filename:'nouvelle.zip',requested_at_utc:'2026-11-16T10:00:00Z'},last_check:null};
   if(broken&&operation==='export'&&fault==='lost_response')throw networkError();
   return {ok:true,headers:{get(n){return n==='Content-Disposition'?'attachment; filename="nouvelle.zip"':'2026-11-16T10:00:00Z';}},blob:async()=>{if(broken&&operation==='export'&&fault==='body_cut')throw networkError();return {};}};
  }
  if(url==='/transfer/check'){
   if(broken&&operation==='check'&&['before_send','scope','storage'].includes(fault))throw networkError();
   const checked={verified:true,filename:'intact.zip',matches_last_export:true,checked_at_utc:'2026-11-16T10:01:00Z',summary};activity={...activity,last_check:checked};
   if(broken&&operation==='check'&&['lost_response','timeout'].includes(fault))throw networkError();
   if(broken&&operation==='check'&&fault==='invalid_json')return{ok:true,json:async()=>{throw SyntaxError('Unexpected end');}};
   if(broken&&operation==='check'&&fault==='status_lost')failNextStatus=true;
   return response(checked);
  }
  throw Error(url);
 }};vm.createContext(c);vm.runInContext(original.replaceAll('__TRANSFER_TOKEN__',session),c);return {c,el};
}
async function ready(p){await vm.runInContext('status()',p.c);}
async function check(p){p.el('#check-archive').files=[{name:'intact.zip',size:200}];await p.el('#check-archive').listeners.change();}
function safe(p){assert.equal(p.el('#checked-details').hidden,true);assert.doesNotMatch(p.el('#export-receipt').textContent,/correspond à cette demande/);assert.doesNotMatch(p.el('#check-result').textContent,/Fichier sélectionné contrôlé/);assert.match(p.el('#stage').textContent,/à vérifier/);assert.doesNotMatch(p.el('#message').textContent,/Failed to fetch|AbortError|Unexpected end/);assert.equal(p.el('#export').disabled,false);}
(async()=>{
 let p=page();await ready(p);assert.match(p.el('#export-receipt').textContent,/correspond à cette demande/);
 if(operation==='export')await p.el('#export').listeners.click();else await check(p);
 safe(p);if(operation==='check')assert.equal(p.el('#check-archive').value,'');assert.equal(downloads.length,0);
 p=page();await ready(p);safe(p);assert.equal(calls.includes('/transfer/restore'),false);
 if(fault==='scope'){const other=page('session-B');await ready(other);assert.match(other.el('#check-result').textContent,/Fichier sélectionné contrôlé/);}
 if(fault==='storage'){const other=page('session-C',true);await ready(other);safe(other);}
 broken=false;
 if(operation==='export'){
  // A fresh successful control cannot retroactively confirm a lost export.
  await check(p);assert.match(p.el('#check-result').textContent,/uniquement le fichier sélectionné/);assert.equal(p.el('#export-receipt').hidden,true);
  await p.el('#export').listeners.click();assert.match(p.el('#export-receipt').textContent,/pas encore été confirmé/);
 }
 await check(p);assert.match(p.el('#checked-details').textContent,/OIII : 40 min acquises/);assert.match(p.el('#checked-details').textContent,/SII : 25 min acquises/);assert.match(p.el('#export-receipt').textContent,/correspond à cette demande/);
 p=page();await ready(p);assert.match(p.el('#check-result').textContent,/Fichier sélectionné contrôlé/);assert.equal(calls.includes('/transfer/restore'),false);
})().catch(e=>{console.error(e);process.exitCode=1});
'''

@pytest.mark.parametrize('operation,fault',[
 ('export','before_send'),('export','lost_response'),('export','body_cut'),('export','timeout'),
 ('check','before_send'),('check','lost_response'),('check','invalid_json'),('check','status_lost'),('check','timeout'),
 ('check','scope'),('check','storage')])
def test_network_failure_is_uncertain_across_reload_then_retries_safely(operation,fault):
    html=Path(__file__).resolve().parents[2]/'astropilot/web/profile-transfer.html'
    subprocess.run([shutil.which('node'),'-e',PROGRAM,str(html),operation,fault],check=True,timeout=20)
