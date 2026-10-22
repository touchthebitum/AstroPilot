"""Explicit empty-project consent survives views, without leaking to other drafts."""
from pathlib import Path
import shutil
import subprocess

import pytest

SOURCE = Path(__file__).parents[2] / 'astropilot/web/app.js'


def test_start_confirmation_scoped_to_target_and_draft():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to exercise UI consent state')
    source = SOURCE.read_text()
    functions = source[source.index('function restoreNewProjectEmptyConfirmation('):
                       source.index('function renderNewProjectIntents(')]
    program = r'''
const assert=require('node:assert/strict');
const control={checked:false};
const document={querySelector:()=>control};
const state={configurationDraft:{projects:{}}};
''' + functions + r'''
restoreNewProjectEmptyConfirmation('A');
assert.equal(control.checked,false,'no implicit zero-progress consent');
control.checked=true;
restoreNewProjectEmptyConfirmation('A');
assert.equal(control.checked,true,'same project survives a new panel/render');
restoreNewProjectEmptyConfirmation('B');
assert.equal(control.checked,false,'a different target needs its own explicit choice');
control.checked=true;
restoreNewProjectEmptyConfirmation('A');
assert.equal(control.checked,true,'returning to A restores only A');
control.checked=false;
restoreNewProjectEmptyConfirmation('A');
assert.equal(control.checked,false,'explicit withdrawal is preserved');
restoreNewProjectEmptyConfirmation('B');
assert.equal(control.checked,true,'B remains independent');
consumeNewProjectEmptyConfirmation('B');
restoreNewProjectEmptyConfirmation('B');
assert.equal(control.checked,false,'creating a project consumes its consent');
control.checked=true;
state.configurationDraft={projects:{}};
restoreNewProjectEmptyConfirmation('B');
assert.equal(control.checked,false,'a new draft/profile cannot inherit consent');
control.checked=true;
restoreNewProjectEmptyConfirmation(null);
assert.equal(control.checked,false,'an unknown target cannot acquire consent');
'''
    result = subprocess.run([node, '-e', program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
