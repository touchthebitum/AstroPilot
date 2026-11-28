"""Exercise the delivered session script without browser or external network."""
from pathlib import Path
import shutil
import subprocess


def test_new_extraction_keeps_pending_state_separate_and_stale_tab_blocked():
    script = Path(__file__).resolve().parents[2] / 'astropilot/web/session-context.js'
    result = subprocess.run([shutil.which('node'), '-', str(script)], input=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[2],'utf8');
const values=new Map();
const storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k),key:i=>[...values.keys()][i]??null,get length(){return values.size;}};
let server='session-A';const traffic=[];
function page(session,scope,store=storage){
 const notices=[];
 const context={URL,Headers,localStorage:store,NightMeritSessionBinding:{session_id:session,storage_scope:scope},
 document:{body:{prepend:n=>notices.push(n)},querySelector:()=>notices[0],createElement:()=>({setAttribute(){}})},
 window:{localStorage:store,location:new URL('http://127.0.0.1:32955/'),async fetch(input,init={}){
 const path=new URL(input,'http://127.0.0.1:32955/').pathname;
 traffic.push({path,method:init.method||'GET',session:new Headers(init.headers).get('X-NightMerit-Session')});
 return {ok:true,status:200,headers:new Headers({'X-NightMerit-Session':server}),json:async()=>({status:'managed',service:'application',session_id:server})};}}};
 vm.createContext(context);vm.runInContext(code,context);return {...context,notices};
}
(async()=>{
 // First copy retains legacy pending UUIDs and recovery namespace.
 values.set('astropilot.pendingEvidence.execution-A','original-UUID');
 const a=page('session-A','copy-A');assert.equal(a.NightMeritStorageNamespace,'');
 assert.equal(a.NightMeritStorage.getItem('astropilot.pendingEvidence.execution-A'),'original-UUID');
 const before=new Map(values);
 server='session-B';const b=page('session-B','copy-B');assert.equal(b.notices.length,0);
 assert.equal(b.NightMeritStorage.getItem('astropilot.pendingEvidence.execution-A'),null);
 assert.ok(b.NightMeritStorageNamespace.includes('copy-B'));
 await b.window.fetch('/v1/configuration');
 assert.equal(traffic.at(-1).session,'session-B');
 b.NightMeritStorage.setItem('astropilot.pendingEvidence.execution-A','B-UUID');
 assert.equal(a.NightMeritStorage.getItem('astropilot.pendingEvidence.execution-A'),'original-UUID');
 assert.equal(a.NightMeritStorage.length,1);assert.equal(a.NightMeritStorage.key(0),'astropilot.pendingEvidence.execution-A');
 assert.equal(b.NightMeritStorage.length,1);assert.equal(b.NightMeritStorage.key(0),'astropilot.pendingEvidence.execution-A');
 for(const [k,v] of before)assert.equal(values.get(k),v,'legacy data must remain byte-identical');
 const reload=page('session-B','copy-B');assert.equal(reload.NightMeritStorage.getItem('astropilot.pendingEvidence.execution-A'),'B-UUID');
 const c=page('session-C','copy-C');assert.equal(c.NightMeritStorage.getItem('astropilot.pendingEvidence.execution-A'),null);
 assert.notEqual(c.NightMeritStorageNamespace,b.NightMeritStorageNamespace,'IDB/lock namespace differs');
 const event={storageArea:storage,key:b.NightMeritStorageNamespace+'astropilot.pendingEvidence.execution-A',newValue:'B-next'};
 assert.equal(a.NightMeritStorageEvent(event),null);
 assert.equal(b.NightMeritStorageEvent({...event,key:'astropilot.pendingEvidence.execution-A'}),null);
 assert.equal(b.NightMeritStorageEvent(event).key,'astropilot.pendingEvidence.execution-A');
 assert.equal(b.NightMeritStorageEvent({key:null}).key,null);
 b.NightMeritStorage.removeItem('astropilot.pendingEvidence.execution-A');
 assert.equal(a.NightMeritStorage.getItem('astropilot.pendingEvidence.execution-A'),'original-UUID');
 // Old tab cannot adopt B or write to it; reads also reject the replacement.
 const count=traffic.filter(t=>t.method==='POST').length;
 await assert.rejects(a.window.fetch('/v1/projects',{method:'POST'}),/kit_session_changed/);
 assert.equal(traffic.filter(t=>t.method==='POST').length,count);
 await assert.rejects(a.window.fetch('/v1/configuration'),/kit_session_changed/);
 assert.equal(a.NightMeritSessionBinding.session_id,'session-A');
 server='session-D';await assert.rejects(b.window.fetch('/v1/projects',{method:'POST'}),/kit_session_changed/);
 const inaccessible=page('session-D','copy-D',{getItem(){throw Error('denied');}});
 await assert.rejects(inaccessible.window.fetch('/v1/configuration'),/kit_session_changed/);
 assert.match(inaccessible.notices[0].textContent,/ne peut pas conserver son identité/);
 console.log('PASS: new extraction, legacy retention, scoped pending UUIDs, reload, event isolation, stale reads/writes, unavailable storage');
})().catch(e=>{console.error(e);process.exitCode=1;});
''', text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
