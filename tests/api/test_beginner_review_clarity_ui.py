"""Read-only archive context and comparison presentation regressions."""
from pathlib import Path
import shutil
from tests.timezone_ui_helpers import run_with_time_authority

WEB = Path(__file__).resolve().parents[2] / 'astropilot/web'


def test_archive_shows_requested_slot_without_repeating_summary():
    source = (WEB / 'app.js').read_text()
    render = source[source.index('function archivedRequestedRange('):source.index('document.querySelectorAll("[data-open-analysis-history]")')]
    program = r'''
const assert=require('node:assert/strict');
class Node {
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.style={};}
 append(...nodes){this.children.push(...nodes);} replaceChildren(){this.children=[];}
 setAttribute(){}
}
const root=new Node('root');
const document={querySelector:()=>root,createElement:tag=>new Node(tag)};
let appliedUiMode='simple';
function refusalSiteTimezone(){return 'Europe/Zurich';}
function noCandidateMessage(){return ['Cible trop basse','M42 exige au moins 30°.','Aucun échantillon au-dessus du seuil.'];}
function simpleProductivityRefusal(){return null;}
function refusalEvaluatedRange(){return '';}
function refusalTimeLabel(value,zone){return `${value} · ${zone}`;}
RENDER
const record={created_at_utc:'2026-11-04T07:38:00Z',request:{availability:{mode:'fixed_window',
 start:'2026-11-04T19:30:00+01:00',end:'2026-11-04T22:30:00+01:00'}},
 result:{status:'no_candidate',weather_trust:{timezone:'Europe/Zurich'}}};
const before=JSON.stringify(record);
for(const mode of ['simple','pro']){
 appliedUiMode=mode;renderArchivedAnalysis(record);
 const paragraphs=root.children.filter(n=>n.tag==='p').map(n=>n.textContent);
 assert(paragraphs.some(t=>/Vos horaires demandés.*19:30.*22:30.*Europe\/Zurich/.test(t)));
 const details=root.children.find(n=>n.tag==='details');
 assert.equal(details.children[1].textContent,'Aucun échantillon au-dessus du seuil.');
 assert.equal(details.open,mode==='pro');
}
assert.equal(JSON.stringify(record),before);
for(const availability of [undefined,{mode:'all_night'},{start:'invalid',end:'invalid'},
 {start:'2026-11-04T22:30:00Z',end:'2026-11-04T19:30:00Z'}]){
 assert.equal(archivedRequestedRange({request:{availability}},'Europe/Zurich'),'');
}
// Keep full dates and offsets at midnight and the repeated autumn hour.
for(const [start,end]of [['2026-11-04T23:30:00+01:00','2026-11-05T01:00:00+01:00'],
 ['2026-10-25T02:30:00+02:00','2026-10-25T02:30:00+01:00']]){
 const label=archivedRequestedRange({request:{availability:{start,end}}},'Europe/Zurich');
 assert(label.includes(start)&&label.includes(end));
}
'''.replace('RENDER', render)
    result = run_with_time_authority([shutil.which('node'), '-'], input=program, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_saved_comparison_controls_only_hidden_when_result_is_shown():
    source = (WEB / 'app.js').read_text()
    clear = source[source.index('function clearOutcomePresentation('):source.index('function rememberConfirmedFieldObservation(')]
    program = r'''
const assert=require('node:assert/strict');
const output={dataset:{comparisonState:'shown',simpleText:'saved',proText:'saved'}};
const trace={textContent:'saved'};
const document={querySelector:id=>id==='#outcome-result'?output:trace};
CLEAR
clearOutcomePresentation();
assert.equal(output.dataset.comparisonState,undefined);
assert.equal(output.dataset.simpleText,undefined);
assert.equal(trace.textContent,'');
'''.replace('CLEAR', clear)
    result = run_with_time_authority([shutil.which('node'), '-'], input=program, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    css = (WEB / 'styles.css').read_text()
    for control in ['outcome-read', 'outcome-compare']:
        assert f'html[data-ui-mode="simple"] .outcome-panel:has(#outcome-result[data-comparison-state="shown"]) > #{control}' in css
    assert 'resultElement.dataset.comparisonState = "shown"' in source


def test_archive_local_form_times_use_historical_zone_read_only():
    source = (WEB / 'app.js').read_text()
    helpers = source[source.index('function localDateTimeParts('):source.index('function fieldObservationDraftForContext(')]
    render = source[source.index('function archivedRequestedRange('):source.index('function renderArchivedAnalysis(')]
    program = r'''
const assert=require('node:assert/strict');
HELPERS
function refusalTimeLabel(value,zone){return new NightMeritTime.DateTimeFormat('fr-CH',{
 timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',
 hour12:false,timeZoneName:'shortOffset'}).format(new Date(value));}
RENDER
function record(start,end,zone='Europe/Zurich'){
 return {request:{availability:{mode:'fixed_window',start_local:start,end_local:end}},
 result:{weather_trust:zone?{timezone:zone}:{}}};
}
for(const [start,end,pattern] of [
 ['2026-11-04T19:30','2026-11-04T22:30',/04\.11\.2026.*19:30.*UTC\+1.*04\.11\.2026.*22:30.*UTC\+1/],
 ['2026-11-04T23:30','2026-11-04T01:00',/04\.11\.2026.*23:30.*05\.11\.2026.*01:00/],
 ['2026-10-25T01:30','2026-10-25T03:30',/01:30.*UTC\+2.*03:30.*UTC\+1/]]){
 const item=record(start,end),before=JSON.stringify(item);
 assert.match(archivedRequestedRange(item,'Europe/Zurich'),pattern);
 assert.equal(JSON.stringify(item),before);
}
// Missing historical zone, invalid, ambiguous or nonexistent local values are not guessed.
for(const item of [record('2026-11-04T19:30','2026-11-04T22:30',null),
 record('2026-10-25T02:30','2026-10-25T03:30'),
 record('2026-03-29T02:30','2026-03-29T04:30'),
 record('2026-11-04T19:30','2026-11-04T19:30'),
 record('2026-11-04T19:30','2026-11-06T22:30'),
 record('invalid','invalid')]) assert.equal(archivedRequestedRange(item,'Europe/Zurich'),'');
// Explicit aware legacy bounds still display offsets across the repeated hour.
const legacy={request:{availability:{start:'2026-10-25T02:30:00+02:00',end:'2026-10-25T02:30:00+01:00'}}};
assert.match(archivedRequestedRange(legacy,'Europe/Zurich'),/02:30.*UTC\+2.*02:30.*UTC\+1/);
'''.replace('HELPERS', helpers).replace('RENDER', render)
    for host_zone in ('America/New_York', 'Asia/Tokyo'):
        import os
        result = run_with_time_authority([shutil.which('node'), '-'], input=program,
            env={**os.environ, 'TZ': host_zone}, text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
