"""Execute production mission rendering with public DTOs, no application profile."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


def run_ui(tmp_path, checks, browser_zone):
    node = shutil.which("node")
    assert node, "Node is required: mission timing regressions must not skip"
    source = SCRIPT.read_text(encoding="utf-8")
    helpers = source[source.index("function missionTimezone("):source.index("function clock(")]
    render = source[source.index("// Presentation only: T"):source.index("function showAcceptanceStatus(")]
    harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor() {this.children=[];this.textContent='';this.hidden=false;}
  append(...children) {this.children.push(...children);}
  replaceChildren() {this.children=[];}
}
const elements = new Map();
const document = {
  querySelector(key) {if(!elements.has(key)) elements.set(key,new Element());return elements.get(key);},
  createElement() {return new Element();},
};
function text(key,value) {document.querySelector(key).textContent=value;}
function syncFieldObservationContext() {}
function clock() {return '';}
function duration() {return '';}
function renderSession() {}
function reloadSessions() {return Promise.resolve();}
function sessionMessage() {throw Error('Unexpected session error');}
const state={acceptedMission:null};
const tasks=[{start:'T-30 min',end:'T-20 min',title:'Installer le matériel'},
 {start:'T-20 min',end:'T-10 min',title:'Mise en station'},
 {start:'T-10 min',end:'T',title:'Autofocus'},
 {start:'Fin',end:'Fin +10 min',title:'Flats'}];
const mission={window_start:'2026-10-15T21:30:00+02:00',window_end:'2026-10-16T01:00:00+02:00',
 site_timezone:'Europe/Zurich',tasks};
function flattened(el) {return [el.textContent,...el.children.map(flattened)].filter(Boolean).join(' ');}
function label(value,m=mission) {return missionTaskTime(value,m,missionTimezone(m));}
'''
    script = tmp_path / "mission-ui.cjs"
    script.write_text(harness + helpers + render + checks, encoding="utf-8")
    env = dict(os.environ, TZ=browser_zone)
    result = subprocess.run([node, str(script)], env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("browser_zone", ["America/New_York", "Asia/Tokyo"])
@pytest.mark.parametrize("case", ["render", "midnight", "spring", "autumn", "legacy"])
def test_mission_task_local_times(tmp_path, browser_zone, case):
    checks = {
        "render": r'''
const before=JSON.stringify(mission);
Object.freeze(mission);tasks.forEach(Object.freeze);Object.freeze(tasks);
renderMission(mission);
let copy=flattened(document.querySelector('#mission-tasks'));
assert.match(copy,/15\.10\.2026.*21:00.*UTC\+2/);
assert.match(copy,/15\.10\.2026.*21:10.*UTC\+2/);
assert.match(copy,/15\.10\.2026.*21:20.*UTC\+2/);
assert.match(copy,/15\.10\.2026.*21:30.*UTC\+2/);
assert.match(copy,/16\.10\.2026.*01:10.*UTC\+2/);
assert.doesNotMatch(copy,/T-\d|Fin \+/);
for (const action of ['Installer le matériel','Effectuer la mise en station',
 'Régler la mise au point automatique','Prendre les images de calibration (flats)']) assert(copy.includes(action));
assert.equal(JSON.stringify(mission),before);
// Reopen the same persisted DTO after a configuration/site change.
state.configuration={site:{timezone:'America/Los_Angeles'}};
state.acceptedMission={mission};renderMission(mission);
assert.equal(flattened(document.querySelector('#mission-tasks')),copy);
assert.equal(JSON.stringify(mission),before);
''',
        "midnight": r'''
mission.window_start='2026-10-16T00:10:00+02:00';
assert.match(label('T-20 min'),/15\.10\.2026.*23:50.*UTC\+2/);
assert.match(label('T'),/16\.10\.2026.*00:10.*UTC\+2/);
''',
        "spring": r'''
mission.window_start='2026-03-29T03:10:00+02:00';
assert.match(label('T-20 min'),/29\.03\.2026.*01:50.*UTC\+1/);
mission.window_end='2026-03-29T01:55:00+01:00';
assert.match(label('Fin +10 min'),/29\.03\.2026.*03:05.*UTC\+2/);
''',
        "autumn": r'''
mission.window_start='2026-10-25T02:10:00+01:00';
assert.match(label('T-20 min'),/25\.10\.2026.*02:50.*UTC\+2/);
assert.match(label('T'),/25\.10\.2026.*02:10.*UTC\+1/);
mission.window_end='2026-10-25T02:55:00+02:00';
assert.match(label('Fin +10 min'),/25\.10\.2026.*02:05.*UTC\+1/);
''',
        "legacy": r'''
for(const boundary of [null,'invalid','21:30','2026-10-15T21:30:00']) {
 mission.window_start=boundary;mission.window_end=boundary;
 assert.equal(label('T−20 min'),'20 min avant le début des acquisitions · heure à confirmer');
 assert.equal(label('T'),'Début des acquisitions · heure à confirmer');
 assert.equal(label('Fin +10 min'),'10 min après la fin des acquisitions · heure à confirmer');
}
assert.equal(label('Quand le ciel est dégagé'),'Quand le ciel est dégagé');
assert.equal(label('22:15'),'22:15');
assert.equal(label(null),'Horaire non précisé');
assert.equal(missionTaskTitle('Vérifier le guidage'),'Vérifier le guidage');
mission.window_start='2026-10-15T21:30:00+02:00';
for(const zone of [null,'Invalid/Zone']) {
 mission.site_timezone=zone;
 assert.match(label('T-20 min'),/15\.10\.2026.*19:10.*UTC/);
}
''',
    }[case]
    run_ui(tmp_path, checks, browser_zone)
