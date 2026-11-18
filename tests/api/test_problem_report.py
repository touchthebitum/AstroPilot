"""Diagnostics never read profiles or raw logs and never export automatically."""
from pathlib import Path
import json
import shutil
import subprocess
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot import demo_mode
import pytest

@pytest.mark.parametrize('demo', [False,True])
def test_report_has_allowlisted_metadata_and_no_profile_access(tmp_path,monkeypatch,demo):
    root=tmp_path/'profile-must-not-exist'
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(root))
    monkeypatch.setattr(demo_mode,'_active',demo)
    response=TestClient(create_app()).get('/v1/problem-report')
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    data=response.json()
    assert set(data)=={'schema','version','build','architecture','system','weather_mode','scope'}
    assert data['weather_mode']==('simulated' if demo else 'real')
    assert str(tmp_path) not in response.text
    assert not root.exists()


def test_report_preview_is_explicit_and_ignores_private_error_details():
    node=shutil.which('node');assert node
    script=Path(__file__).resolve().parents[2]/'astropilot/web/problem-report.js'
    harness=r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const nodes=new Map(),events={},downloads=[];let calls=0,fail=false;
function el(id){if(!nodes.has(id))nodes.set(id,{listeners:{},disabled:false,value:'',addEventListener(n,f){this.listeners[n]=f},showModal(){},close(){this.listeners.close()}});return nodes.get(id)}
const ctx={window:{addEventListener(n,f){events[n]=f}},document:{querySelector:el,createElement(){return{click(){downloads.push('download')}}}},AbortController:class{abort(){}},setTimeout(){return 1},clearTimeout(){},URL:{createObjectURL(blob){downloads.push(blob);return'blob:test'},revokeObjectURL(){}},Blob:class{constructor(parts){this.raw=parts.join('')}},fetch:async()=>{calls++;if(fail)throw Error('SECRET PATH');return{ok:true,json:async()=>({schema:'nightmerit.problem_report.v1',version:'1',build:'abcdef0',architecture:'x86_64',system:'Windows',weather_mode:'simulated',scope:'metadata_only_no_profile_or_logs',secret:'SECRET PROFILE'})}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
(async()=>{
assert.equal(calls,0);assert.equal(downloads.length,0);
events.error({message:'SECRET USER',filename:'SECRET PATH',error:{stack:'SECRET STACK'}});
events.unhandledrejection({reason:'SECRET TOKEN'});
await el('#problem-report-open').listeners.click();assert.equal(calls,1);assert.equal(downloads.length,0);
const preview=el('#problem-report-preview').value;assert(!preview.includes('SECRET'));assert.deepEqual(JSON.parse(preview).browser_errors,['browser_error','unhandled_promise']);
el('#problem-report-download').listeners.click();assert.equal(downloads.length,2);assert.equal(downloads[0].raw,preview);
el('#problem-report-dialog').close();assert.equal(el('#problem-report-download').disabled,true);
fail=true;await el('#problem-report-open').listeners.click();assert.equal(el('#problem-report-download').disabled,true);assert(!el('#problem-report-status').textContent.includes('SECRET'));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    subprocess.run([node,'-e',harness,str(script)],check=True,timeout=15)


def test_simulation_copy_requires_simulated_provider_and_keeps_real_weather():
    node=shutil.which('node');assert node
    web=Path(__file__).resolve().parents[2]/'astropilot/web'
    app=(web/'app.js').read_text()
    render=app[app.index('function renderWeatherTrust('):app.index('function reasonText(')]
    harness=r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');const result={};
const ctx={text:(key,value)=>result[key]=value,siteDateTime:(value)=>value};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);vm.runInContext(process.argv[2],ctx);
const trust={provider:'NightMerit — météo simulée (démonstration)',validation_status:'validated',freshness_status:'fresh',timezone:'Europe/Zurich',snapshot_age_minutes:0,maximum_age_minutes:90};
ctx.trust=trust;vm.runInContext('renderWeatherTrust(trust,{presentation:{label:"Validation météo partielle",summary:"Historique absent"}},"classic")',ctx);
assert.equal(result['#classic-weather-status'],'Météo simulée');assert.match(result['#classic-weather-title'],/La visibilité des cibles/);assert.match(result['#weather-context-label'],/démonstration/);
trust.provider='Open-Meteo';vm.runInContext('renderWeatherTrust(trust,{presentation:{label:"Réel",summary:"Prévisions réelles"}},"classic")',ctx);
assert.equal(result['#classic-weather-status'],'Réel');assert.equal(result['#classic-weather-title'],'Prévisions réelles');assert.equal(result['#weather-context-label'],'Confiance météo');
assert(!ctx.NightMeritPresentation.discoveryCopy(true).includes('selon les prévisions'));
'''
    subprocess.run([node,'-e',harness,str(web/'demo-presentation.js'),render],check=True,timeout=15)
