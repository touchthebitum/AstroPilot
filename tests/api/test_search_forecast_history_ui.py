import json
from pathlib import Path
import shutil
import subprocess
import pytest
from tests.timezone_ui_helpers import run_with_time_authority


def test_hourly_archive_ui_rereads_values_without_weather_request():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    source = Path('astropilot/web/search-forecasts.js').read_text()
    program = r'''
const assert=require('node:assert/strict');
class E {constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.textContent='';}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=[...x];}addEventListener(k,f){this.handlers[k]=f;}}
const elements={};global.document={querySelector:k=>elements[k] ||= new E(),createElement:t=>new E(t)};
const trust={retrieved_at_utc:'2026-11-14T18:34:00+00:00',timezone:'Europe/Zurich',provider:'FICTIF',requested_latitude:46.888,requested_longitude:6.55,grid_latitude:46.89,grid_longitude:6.56};
const record={request:{site:{name:'Buttes <FICTIF>'},parameters:{availability:{preparation_minutes:20,flats_minutes:5}}},weather:{trust,payload:{hourly:{time:[1794682800,1794686400],cloud_cover:[0,87.25],cloud_cover_low:[1,3.25],cloud_cover_mid:[2,4.5],cloud_cover_high:[3,6.75]}}}};
const calls=[];global.fetch=async(path,options)=>{calls.push(path);assert.equal(options.cache,'no-store');assert.match(path,/^\/v1\/search-forecasts/);return{ok:true,json:async()=>path.includes('?')?{items:[{search_id:'test',site:record.request.site,weather_trust:trust}],next_before:null}:record};};
'''+source+r'''
(async()=>{
 await new Promise(r=>setImmediate(r));
 const list=elements['#forecast-list'];assert.equal(list.children.length,1);
 await list.children[0].handlers.click();
 const detail=elements['#forecast-detail'];
 assert.equal(detail.children[0].textContent,'Buttes <FICTIF>');
 const table=detail.children.find(x=>x.tag==='table');
 const rows=table.children.find(x=>x.tag==='tbody').children;
 assert.deepEqual(rows.map(r=>r.children.slice(1).map(c=>c.textContent)),[['0','1','2','3'],['87.25','3.25','4.5','6.75']]);
 assert.equal(calls.length,2);assert.match(elements['#forecast-message'].textContent,/Aucune actualisation/);
 assert.ok(detail.children.some(x=>x.textContent.includes('préparation 20 min · flats 5 min')));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = run_with_time_authority([node, '-e', program],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_archive_page_loads_pinned_time_before_reader():
    page = Path('astropilot/web/search-forecasts.html').read_text()
    assert page.index('/ui/timezone-data.js') < page.index('/ui/timezone-authority.js') < page.index('/ui/search-forecasts.js')


@pytest.mark.parametrize('scenario', ['late_success', 'late_failure', 'latest_failure', 'pinned_time'])
def test_archive_selection_and_timezone_authority(scenario):
    node = shutil.which('node')
    assert node, 'Node required for archive regression tests'
    source = Path('astropilot/web/search-forecasts.js').read_text()
    program = r'''
const assert=require('node:assert/strict');
class E{constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.textContent='';}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=[...x];}addEventListener(k,f){this.handlers[k]=f;}}
const elements={};global.document={querySelector:k=>elements[k] ||= new E(),createElement:t=>new E(t)};
const instant='2026-11-02T12:00:00Z';
const trust={retrieved_at_utc:instant,timezone:'America/Winnipeg',provider:'FICTIF',requested_latitude:49.9,requested_longitude:-97.1,grid_latitude:49.9,grid_longitude:-97.1};
const record=name=>({request:{site:{name},parameters:{}},weather:{trust,payload:{hourly:{time:[Date.parse(instant)/1000],cloud_cover:[name==='A'?10:90]}}}});
const pending={};const calls=[];
global.fetch=async(path)=>{calls.push(path);return {ok:true,json:()=>path.includes('?')?Promise.resolve({items:['A','B'].map(name=>({search_id:name,site:{name},weather_trust:trust})),next_before:null}):new Promise((resolve,reject)=>pending[path.slice(-1)]={resolve,reject})};};
// Model a browser with different site rules: NightMerit may delegate only UTC formatting.
const NativeFormat=Intl.DateTimeFormat;
Intl.DateTimeFormat=function(locale,options){assert.equal(options.timeZone,'UTC','Archive bypassed the pinned timezone authority');return new NativeFormat(locale,options);};
''' + source + '\nconst scenario=' + json.dumps(scenario) + r''';
(async()=>{
 await new Promise(r=>setImmediate(r));
 const options={timeZone:trust.timezone,dateStyle:'short',timeStyle:'short'};
 const expected=new NightMeritTime.DateTimeFormat('fr-CH',options).format(new Date(instant));
 const buttons=elements['#forecast-list'].children;assert.equal(buttons.length,2);
 assert(buttons[0].textContent.includes(expected));
 const a=buttons[0].handlers.click();await new Promise(r=>setImmediate(r));
 if(scenario==='pinned_time'){
  pending.A.resolve(record('A'));await a;
  const detail=elements['#forecast-detail'];
  assert(detail.children.some(n=>n.textContent.includes(expected)));
  const table=detail.children.find(n=>n.tag==='table');
  assert.equal(table.children.find(n=>n.tag==='tbody').children[0].children[0].textContent,expected);
 }else{
  const b=buttons[1].handlers.click();await new Promise(r=>setImmediate(r));
  if(scenario==='latest_failure')pending.B.reject(Error('unavailable'));else pending.B.resolve(record('B'));
  await b;
  const message=elements['#forecast-message'].textContent;
  if(scenario==='late_failure')pending.A.reject(Error('old failure'));else pending.A.resolve(record('A'));
  await a;
  assert.equal(elements['#forecast-message'].textContent,message,'Old request replaced latest status');
  const detail=elements['#forecast-detail'];
  assert.deepEqual(detail.children.filter(n=>n.tag==='h2').map(n=>n.textContent),scenario==='latest_failure'?[]:['B']);
  assert.equal(detail.children.filter(n=>n.tag==='table').length,scenario==='latest_failure'?0:1);
 }
 assert(calls.every(p=>p.startsWith('/v1/search-forecasts')));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = run_with_time_authority([node, '-e', program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
