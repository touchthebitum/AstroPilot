from pathlib import Path
import shutil
import subprocess


def test_clearing_analysis_preserves_only_persisted_plan_access():
    source = (Path(__file__).parents[2] / "astropilot/web/app.js").read_text()
    function = source[source.index("function clearAcceptedMission() {"):source.index("function renderDecision(")]
    program = r'''const assert = require('node:assert/strict');
const state = {acceptedMission: {mission: {}}, savedMissions: []};
const ui = {savedMissionEntry: {hidden: true}, mission: {open: false}};
function showAcceptanceStatus() {} function resetMissionPresentation() {} function clearAlternatives() {}
''' + function + r'''
const saved = {source: 'persisted', mission: {mission_id:'rosette-oiii', tasks:[{start:'T-20 min'},{end:'Fin +5 min'}]}};
for (const plans of [[], [{source:'preview',mission:{}}], [{source:'persisted'}], [saved]]) {
 state.savedMissions = structuredClone(plans);
 const original = JSON.stringify(state.savedMissions);
 state.acceptedMission = {mission:{}};
 clearAcceptedMission();
 assert.equal(state.acceptedMission, null, 'A previous plan must not become the current analysis');
 assert.equal(ui.savedMissionEntry.hidden, plans.length !== 1 || plans[0] !== saved);
 assert.equal(JSON.stringify(state.savedMissions), original, 'Saved plans must stay unchanged');
 assert.equal(state.acceptingRecommendation, false);
}
'''
    result = subprocess.run([shutil.which("node"), "-"], input=program, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
