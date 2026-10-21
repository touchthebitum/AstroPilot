"""The no-target entry must navigate and preserve unsaved configuration."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_discovery_entry_saves_dirty_configuration_and_ignores_late_completion():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for actual UI handler')
    source = (Path(__file__).parents[2] / 'astropilot/web/app.js').read_text()
    handler = source[source.index('document.querySelector("#discover-from-projects").addEventListener'):source.index('document.querySelector("#discovery-back").addEventListener')]
    program = r'''
const assert=require('node:assert/strict');let handler,saved=0,navigated=[],unchanged=true,locked=false,release;
const state={configuration:{configured:true},configurationGeneration:1,viewRevision:1};
const document={querySelector:()=>({addEventListener:(_type,fn)=>handler=fn})};
function configurationDraftMatchesSaved(){return unchanged;}
function confirmDiscardProjectProgress(){return true;}
function guardUnresolvedAcceptance(){return locked;}
function setView(view){navigated.push(view);state.viewRevision++;}
async function saveConfiguration(){saved++;}
async function setDiscoveryMode(enabled){state.discoveryMode=enabled;if(release)await new Promise(resolve=>release=resolve);}
''' + handler + r'''
(async()=>{
 await handler();assert.deepEqual(navigated,['availability']);assert.equal(saved,0);
 unchanged=false;await handler();assert.equal(saved,1);
 state.configuration.configured=false;await handler();assert.equal(saved,2);
 locked=true;state.discoveryMode=false;await handler();assert.equal(state.discoveryMode,false);assert.equal(saved,2);
 locked=false;release=true;const pending=handler();await Promise.resolve();state.viewRevision++;release();await pending;
 assert.equal(saved,2);assert.deepEqual(navigated,['availability']);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, '-e', program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_reference_license_and_retrieve_saved_alias_use_the_actual_renderer():
    """Do not relabel a BY-SA photo as BY or create a second legacy alias project."""
    import json
    from astropilot.target_discovery import TARGET_IMAGES
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for actual UI renderer')
    source = (Path(__file__).parents[2] / 'astropilot/web/app.js').read_text()
    renderer = source[source.index('function renderTargetSuggestions('):source.index('function renderEquipmentCatalogue(')]
    payload = {'suggestions': [{
        'catalog_key': key, 'existing_project_key': alias, 'already_saved': True,
        'display_name': key, 'image': TARGET_IMAGES[key],
        'filter': {'label': 'Baader Ha Highspeed', 'fwhm_nm': 6.5},
        'window_start': '2026-12-09T20:00:00+01:00', 'window_end': '2026-12-09T22:00:00+01:00',
        'guidance': {'purpose': 'Photographier le gaz', 'difficulty': 'Pour progresser', 'advice': 'Hα monochrome'},
    } for key, alias in [('IC1805', 'Heart'), ('IC1848', 'Soul')]], 'notice': 'Prévisions fictives'}
    program = r'''
const assert=require('node:assert/strict');
class E {constructor(tag='node'){this.tag=tag;this.children=[];this.handlers={};this.textContent='';}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}addEventListener(type,fn){this.handlers[type]=fn;}focus(){}}
const nodes={};const document={querySelector:key=>nodes[key] ||= new E(),createElement:tag=>new E(tag),createTextNode:text=>({textContent:text,children:[]})};
const state={configuration:{projects:{Heart:{hours:7},Soul:{hours:2}}}};
let opened=[],locked=false;
function setView(){} function renderEquipmentCatalogue(){}
function currentSiteTimezone(){return 'Europe/Zurich';}function missionDateTimeLabel(value){return value;}
function guardUnresolvedAcceptance(){return locked;}function confirmDiscardProjectProgress(){return true;}
async function setDiscoveryMode(){} function openProjectProgress(key){opened.push(key);}
function flatten(node){return [node,...node.children.flatMap(flatten)];}
''' + renderer + '\nconst payload=' + json.dumps(payload, ensure_ascii=False) + r''';
(async()=>{
const before=JSON.stringify(state.configuration);
renderTargetSuggestions(payload);
const cards=nodes['#target-suggestion-cards'].children;assert.equal(cards.length,2);
for(const [index,alias] of ['Heart','Soul'].entries()) {
 const elements=flatten(cards[index]);
 const license=elements.find(n=>n.tag==='a' && n.href==='https://creativecommons.org/licenses/by-sa/4.0/');
 assert.equal(license.textContent,'CC BY-SA 4.0');
 assert(elements.some(n=>n.textContent===payload.suggestions[index].image.note));
 assert(elements.some(n=>n.tag==='img' && n.alt===payload.suggestions[index].image.alt));
 const choose=elements.find(n=>n.tag==='button');assert.equal(choose.textContent,'Retrouver ce projet');
 await choose.handlers.click();assert.equal(opened.at(-1),alias);
 locked=true;await choose.handlers.click();assert.equal(opened.length,index+1);locked=false;
}
assert.deepEqual(opened,['Heart','Soul']);assert.equal(JSON.stringify(state.configuration),before);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, '-e', program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
