"""Persistent backup context must stay distinct from a current transfer attempt."""
from pathlib import Path
import shutil,subprocess


def test_saved_check_current_outdated_unavailable_and_network_uncertainty_are_clear():
    html=Path(__file__).resolve().parents[2]/'astropilot/web/profile-transfer.html'
    program=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8').match(/<script nonce="[^"]+">([\s\S]+)<\/script>/)[1];
const nodes=new Map();function el(id){if(!nodes.has(id))nodes.set(id,{hidden:true,textContent:'',files:[],listeners:{},addEventListener(e,f){this.listeners[e]=f;}});return nodes.get(id);}
const record={filename:'Rosette-controlee.zip',checked_at_utc:'2026-11-16T12:00:00Z',summary:{project_details:[{project_id:'Rosette',filters:[{filter_type:'OIII',acquired_seconds:2400,target_hours:3},{filter_type:'SII',acquired_seconds:1500,target_hours:4}]}]}};
record.summary.project_details.push({project_id:'Sh2-129',archived:true,filters:[{filter_type:'OIII',acquired_seconds:2400,target_hours:3}]});
let state='current';const c={document:{querySelector:el,querySelectorAll:()=>[]},AbortController:class{signal={};abort(){}},setTimeout(){return 1;},clearTimeout(){},fetch:async()=>({ok:true,json:async()=>({state:'profile',can_export:true,backup_activity:{},last_verified_backup:{state,record:state==='unavailable'?null:record}})})};
vm.createContext(c);vm.runInContext(code,c);
(async()=>{await vm.runInContext('status()',c);assert.match(el('#last-backup-state').textContent,/Données identiques/);assert.match(el('#last-backup-details').textContent,/Rosette-controlee.zip/);assert.match(el('#last-backup-details').textContent,/OIII : 40 min/);assert.match(el('#last-backup-details').textContent,/Sh2-129 \+ Ou4 — retiré, historique conservé/);assert.equal(record.summary.project_details[1].project_id,'Sh2-129');assert.match(el('#last-backup-details').textContent,/SII : 25 min/);
state='outdated';await vm.runInContext('status()',c);assert.match(el('#last-backup-state').textContent,/À actualiser/);assert.match(el('#last-backup-details').textContent,/Rosette-controlee.zip/);
state='current';await vm.runInContext("saveRecovery({check:true,last:'check'});status()",c);assert.match(el('#last-backup-state').textContent,/ne confirme pas la tentative/);assert.doesNotMatch(el('#last-backup-state').textContent,/Données identiques/);
await vm.runInContext('saveRecovery({check:false,last:null})',c);state='unavailable';await vm.runInContext('status()',c);assert.match(el('#last-backup-state').textContent,/Rappel indisponible/);assert.equal(el('#last-backup-details').hidden,true);
state='unverifiable';await vm.runInContext('status()',c);assert.match(el('#last-backup-state').textContent,/À vérifier/);assert.doesNotMatch(el('#last-backup-state').textContent,/Données identiques/);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    subprocess.run([shutil.which('node'),'-e',program,str(html)],check=True,timeout=20)
