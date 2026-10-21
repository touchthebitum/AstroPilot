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
