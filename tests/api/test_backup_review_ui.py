"""Exercise the real assistant script: no success claim from a download alone."""
from pathlib import Path
import shutil,subprocess


def test_download_control_and_restore_summary_use_distinct_states_and_safe_text():
    html=Path(__file__).resolve().parents[2]/'astropilot/web/profile-transfer.html'
    program=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8').match(/<script nonce="[^"]+">([\s\S]+)<\/script>/)[1];
const nodes=new Map();function el(id){if(!nodes.has(id))nodes.set(id,{hidden:true,textContent:'',files:[],value:'',listeners:{},addEventListener(e,f){this.listeners[e]=f;}});return nodes.get(id);}
let activity={},mode='profile',invalid=false,matches=true;const calls=[],downloads=[];
const summary={projects:1,sessions:1,observations:0,comparisons:0,created_at_utc:'2026-11-16T09:00:00Z',project_details:[{project_id:'Rosette <img src=x>',archived:false,filters:[{filter_type:'Hα',acquired_seconds:null,target_hours:null},{filter_type:'OIII',acquired_seconds:2400,target_hours:3},{filter_type:'SII',acquired_seconds:1500,target_hours:4}]}]};
const context={document:{querySelector:el,querySelectorAll:()=>[],createElement:()=>({click(){downloads.push(this.download);}})},AbortController:class{signal={};abort(){}},setTimeout(){return 1;},clearTimeout(){},URL:{createObjectURL(){return 'blob:local';},revokeObjectURL(){}},
 async fetch(url,options={}){calls.push(url);let data;
 if(url==='/transfer/status')data={state:mode,can_export:mode==='profile',can_restore:mode==='empty',backup_activity:activity};
 else if(url==='/transfer/export'){activity={last_export:{filename:'NightMerit-example.zip',requested_at_utc:'2026-11-16T09:01:00Z'},last_check:null};return{ok:true,headers:{get(n){return n==='Content-Disposition'?'attachment; filename="NightMerit-example.zip"':'2026-11-16T09:01:00Z';}},blob:async()=>({})};}
 else if(url==='/transfer/check'){activity={...activity,last_check:null};if(invalid)return{ok:false,json:async()=>({message:'Fichier endommagé'})};data={verified:true,filename:'choisi.zip',checked_at_utc:'2026-11-16T09:02:00Z',matches_last_export:matches,summary};activity={...activity,last_check:data};}
 else if(url==='/transfer/preview')data={confirmation:'nonce',filename:'choisi.zip',summary,checked_at_utc:'2026-11-16T09:02:00Z'};
 else if(url==='/transfer/restore')data={restored:true,summary:{projects:1,sessions:1,observations:0,comparisons:0}};
 else throw Error(url);
 return{ok:true,headers:{get(){return null;}},json:async()=>data};
 }};vm.createContext(context);vm.runInContext(code,context);
(async()=>{await vm.runInContext('status()',context);await el('#export').listeners.click();assert.deepEqual(downloads,['NightMerit-example.zip']);assert.match(el('#export-receipt').textContent,/Téléchargement demandé/);assert.match(el('#export-receipt').textContent,/pas encore été confirmé/);assert.equal(calls.includes('/transfer/check'),false);
 el('#check-archive').files=[{name:'choisi.zip',size:200}];await el('#check-archive').listeners.change();assert.match(el('#check-result').textContent,/Fichier sélectionné contrôlé/);assert.match(el('#export-receipt').textContent,/correspond à cette demande/);assert.match(el('#checked-details').textContent,/Hα : temps acquis non renseigné/);assert.match(el('#checked-details').textContent,/OIII : 40 min acquises/);assert.match(el('#checked-details').textContent,/SII : 25 min acquises/);assert.match(el('#checked-details').textContent,/Rosette <img/);assert.equal(el('#checked-details').innerHTML,undefined);assert.equal(calls.includes('/transfer/restore'),false);
 const originalId=summary.project_details[0].project_id;
 summary.project_details[0].project_id='Sh2-129';
 await el('#check-archive').listeners.change();
 assert.match(el('#checked-details').textContent,/Sh2-129 \+ Ou4/);
 assert.equal(summary.project_details[0].project_id,'Sh2-129');
 summary.project_details[0].archived=true;
 await el('#check-archive').listeners.change();
 assert.match(el('#checked-details').textContent,/Sh2-129 \+ Ou4 — retiré, historique conservé/);
 summary.project_details[0].archived=false;summary.project_details[0].project_id=originalId;
 matches=false;await el('#check-archive').listeners.change();assert.match(el('#check-result').textContent,/différent/);assert.match(el('#export-receipt').textContent,/pas encore été confirmé/);
 invalid=true;await el('#check-archive').listeners.change();assert.equal(el('#checked-details').hidden,true);assert.doesNotMatch(el('#export-receipt').textContent,/correspond à cette demande/);assert.match(el('#message').textContent,/endommagé/);
 invalid=false;mode='empty';await vm.runInContext('status()',context);el('#archive').files=[{name:'Rosette.zip',size:200}];await el('#archive').listeners.change();assert.match(el('#preview-details').textContent,/Rosette.zip/);assert.match(el('#preview-details').textContent,/SII : 25 min/);assert.equal(calls.includes('/transfer/restore'),false);
 await el('#restore').listeners.click();assert.match(el('#restored-summary').textContent,/SII : 25 min/);assert.match(el('#restored-summary').textContent,/1 projet, 1 séance photo/);
 await el('#restore').listeners.click();assert.equal(calls.filter(x=>x==='/transfer/restore').length,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    subprocess.run([shutil.which('node'),'-e',program,str(html)],check=True,timeout=20)
