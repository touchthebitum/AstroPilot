"""Only the live refusal-return owner may navigate after a filter save."""
from pathlib import Path
import subprocess
import shutil
import pytest

SOURCE = Path(__file__).parents[2] / 'astropilot/web/filter-inventory.js'


@pytest.mark.parametrize('change,expected',[
    ('',True),
    ('owner=null;',False),
    ('state.refusedSearchResume={};',False),
    ('state.configuration={...state.configuration};',False),
    ('state.configuration.active_equipment_id="other";',False),
    ('state.configurationGeneration++;',False),
    ('state.viewRevision++;',False),
    ('state.view="availability";',False),
    ('state.decisionSiteReloadRequired=true;',False),
    ('state.dirty=true;',False),
])
def test_only_matching_context_returns_to_search(change,expected):
    source=SOURCE.read_text()
    helper=source[source.index('function filterSearchReturnIsCurrent('):source.index('(() => {')]
    script=r"""
const assert=require('node:assert/strict');
const state={refusedSearchResume:{siteFingerprint:'fixture'},configuration:{active_equipment_id:'fixtureB'},configurationGeneration:3,viewRevision:7,view:'equipment'};
function configurationDraftMatchesSaved(){return !state.dirty}
let owner={context:state.refusedSearchResume,configuration:state.configuration,equipment:'fixtureB',generation:3,viewRevision:7};
"""+helper+change+f'assert.equal(filterSearchReturnIsCurrent(owner),{str(expected).lower()});'
    result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('data,configuration,expected',[
    ({'profile_revision':2,'active_equipment_id':'fixtureB'},{'profile_revision':2,'active_equipment_id':'fixtureB'},True),
    ({'profile_revision':3,'active_equipment_id':'fixtureB'},{'profile_revision':2,'active_equipment_id':'fixtureB'},False),
    ({'profile_revision':1,'active_equipment_id':'fixtureB'},{'profile_revision':2,'active_equipment_id':'fixtureB'},False),
    ({'profile_revision':2,'active_equipment_id':'fixtureA'},{'profile_revision':2,'active_equipment_id':'fixtureB'},False),
    ({'profile_revision':2},{'profile_revision':2,'active_equipment_id':'fixtureB'},False),
    ({'active_equipment_id':'fixtureB'},{'profile_revision':2,'active_equipment_id':'fixtureB'},False),
    ({'profile_revision':'2','active_equipment_id':'fixtureB'},{'profile_revision':2,'active_equipment_id':'fixtureB'},False),
    (None,{'profile_revision':2,'active_equipment_id':'fixtureB'},False),
    ({'profile_revision':-1,'active_equipment_id':'fixtureB'},{'profile_revision':-1,'active_equipment_id':'fixtureB'},False),
    ({'profile_revision':0,'active_equipment_id':'fixtureB'},{'profile_revision':0,'active_equipment_id':'fixtureB'},True),
    ({'profile_revision':2,'active_equipment_id':''},{'profile_revision':2,'active_equipment_id':''},False),
])
def test_server_inventory_must_match_the_displayed_configuration(data,configuration,expected):
    import json
    source=SOURCE.read_text()
    helper=source[source.index('function filterInventoryMatchesConfiguration('):source.index('(() => {')]
    script="const assert=require('node:assert/strict');\n"+helper+f"assert.equal(filterInventoryMatchesConfiguration({json.dumps(data)},{json.dumps(configuration)}),{str(expected).lower()});"
    result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_reload_may_ignore_only_the_stale_flag_not_a_changed_owner():
    source=SOURCE.read_text()
    helper=source[source.index('function filterSearchReturnIsCurrent('):source.index('(() => {')]
    script=r"""
const assert=require('node:assert/strict');
const state={refusedSearchResume:{},configuration:{active_equipment_id:'fixtureB'},configurationGeneration:3,viewRevision:7,view:'equipment',decisionSiteReloadRequired:true};
function configurationDraftMatchesSaved(){return true}
const owner={context:state.refusedSearchResume,configuration:state.configuration,equipment:'fixtureB',generation:3,viewRevision:7};
"""+helper+r"""
assert.equal(filterSearchReturnIsCurrent(owner),false);
assert.equal(filterSearchReturnIsCurrent(owner,{allowReload:true}),true);
state.viewRevision++;assert.equal(filterSearchReturnIsCurrent(owner,{allowReload:true}),false);
"""
    result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
