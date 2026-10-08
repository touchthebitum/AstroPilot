"""Run the real presentation code against an inert DOM and fake read-only API."""
from pathlib import Path
import shutil
import subprocess
import pytest

WEB = Path(__file__).parents[2] / 'astropilot/web'


def test_status_dialog_dynamic_states_and_requests(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for UI execution')
    harness = r'''
const assert = require('node:assert/strict');
const elements = {};
for (const name of ['dialog','summary','details','note','action','enabled','channel','success','notification','updated','open','refresh','close']) {
 elements[name] = {textContent:'', hidden:false, open:false, listeners:{},
  addEventListener(name, fn) {this.listeners[name]=fn;},
  showModal() {this.open=true;}, close() {this.open=false;this.listeners.close();}};
}
const document = {querySelector: id => elements[id.replace('#alerts-status-','')]};
let payload = {state:'unknown'}, fail=false, calls=[], releases=[];
const fetch = async (url, opts) => {
 calls.push([url,opts.method]);
 const value = payload;
 if (value.slow) await new Promise(resolve=>releases.push(resolve));
 if (fail) throw Error('network');
 return {ok:true,json:async()=>value};
};
'''
    checks = r'''
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 assert.equal(calls.length,0);
 elements.open.listeners.click(); await tick();
 assert.match(elements.summary.textContent,/Aucun état/);
 assert.equal(elements.details.hidden,true);
 payload={state:'recent_activity',enabled:true,channel:'disabled',last_success_at:null,
  updated_at:'2026-10-08T12:00:00Z',notification:{status:'DELIVERED',at:'2026-10-08T12:00:00Z'},error:null};
 await elements.refresh.listeners.click();
 assert.equal(elements.enabled.textContent,'Activées');
 assert.equal(elements.channel.textContent,'Notifications désactivées');
 assert.match(elements.notification.textContent,/Acceptée par le système/);
 payload={...payload,state:'stale',error:'cycle_failed'};
 await elements.refresh.listeners.click();
 assert.match(elements.summary.textContent,/ancien/);
 assert.match(elements.action.textContent,/connexion/);
 fail=true; await elements.refresh.listeners.click();
 assert.match(elements.summary.textContent,/indisponible/);
 assert.equal(elements.details.hidden,true);
 fail=false; payload={state:'unknown',slow:true};
 const old=elements.refresh.listeners.click(); await tick();
 elements.close.listeners.click(); payload={state:'unavailable'};
 elements.open.listeners.click(); await tick();
 releases[0](); await old;
 assert.match(elements.summary.textContent,/indisponible/);
 assert(calls.every(([url,method])=>url==='/v1/opportunity-alerts/status' && method==='GET'));
 console.log('PASS');
})().catch(error=>{console.error(error);process.exit(1);});
'''
    script = tmp_path / 'status.cjs'
    script.write_text(harness + (WEB / 'alert-status.js').read_text() + checks)
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'PASS' in result.stdout
