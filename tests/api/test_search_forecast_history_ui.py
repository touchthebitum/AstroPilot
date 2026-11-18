import json
from pathlib import Path
import shutil
import subprocess
import pytest


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
    result = subprocess.run([node, '-e', program],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
