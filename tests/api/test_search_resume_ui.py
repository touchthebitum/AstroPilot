"""Returning from refusal describes current inputs without changing the search."""
from pathlib import Path
import shutil
import subprocess
import pytest

SOURCE = Path(__file__).parents[2] / "astropilot/web/app.js"


def run(checks):
    source = SOURCE.read_text()
    helpers = (source[source.index('function returnToRefusedSearch('):source.index('function renderProjectContinuation(')]
        + source[source.index('function hoursToIsoDuration('):source.index('function normalizeLocalDateTime(')]
        + source[source.index('function nextCivilDate('):source.index('function updateAvailabilityOvernightHint(')]
        + source[source.index('function decisionSiteFingerprint('):source.index('// Every configuration request')])
    guard = source[source.index('async function loadTonight('):source.index('  if (!availability)', source.index('async function loadTonight('))] + "}\n"
    program = r"""
const assert=require('node:assert/strict');
class E{constructor(value=''){this.value=value;this.textContent='';this.children=[];this.hidden=true;this.listeners={}}addEventListener(name,fn){this.listeners[name]=fn}append(...e){this.children.push(...e)}replaceChildren(){this.children=[]}}
const nodes={'#request-recommendation':new E(),'#search-resume':new E(),'#availability-start':new E('2026-11-21T20:00'),'#availability-end':new E('2026-11-21T23:30'),'#availability-duration':new E('2'),'#availability-preparation-minutes':new E('20'),'#availability-flats-minutes':new E('5')};
const choice=new E('fixed_window');
const find=(e,id)=>e.id===id?e:e.children.map(c=>find(c,id)).find(Boolean);
const document={createElement:()=>new E(),querySelector:s=>s.startsWith('input[')?choice:nodes[s]||find(nodes['#search-resume'],s.slice(1))||null};
nodes['#request-recommendation'].textContent='Vérifier mon projet';
const site={name:'Buttes fictif',latitude:46.889,longitude:6.55,timezone:'Europe/Zurich'};
const state={view:'availability',configuration:{site},configurationDraft:{site:{...site}},compareProjects:true};
function currentSiteTimezone(){return state.configuration.site.timezone}
function configurationDraftMatchesSaved(){return !state.dirty}
function readableTargetName(id){return id}
function setView(view){state.view=view;renderSearchResume()}
function content(e){return [e.textContent,...e.children.map(content)].join(' ')}
function fetch(){throw Error('No request allowed')}
"""+helpers+guard+checks
    result=subprocess.run([shutil.which('node'),'-'],input=program,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_only_explicit_return_arms_summary_and_render_does_not_mutate():
    run(r"""
renderSearchResume();assert(nodes['#search-resume'].hidden);
returnToRefusedSearch('availability');let text=content(nodes['#search-resume']);
assert.match(text,/Reprendre ma recherche/);assert.match(text,/Comparaison de mes projets/);
assert.match(text,/21.11.2026 à 20:00.*23:30/);assert.match(text,/Préparation : 20 min · Flats : 5 min/);
assert.match(text,/précédent refus n’a pas été réévalué/);
const before=JSON.stringify(state),values=Object.values(nodes).map(e=>e.value);
renderSearchResume();assert.equal(JSON.stringify(state),before);assert.deepEqual(Object.values(nodes).map(e=>e.value),values);
state.view='equipment';renderSearchResume();assert(nodes['#search-resume'].hidden);
""")


@pytest.mark.parametrize('mode,expected',[('all_night','Toute la nuit'),('duration','Durée souhaitée : 2 h'),('start_and_duration','Début : 21.11.2026 à 20:00'),('until','Fin : 21.11.2026 à 23:30'),('fixed_window','Du 21.11.2026 à 20:00 au 21.11.2026 à 23:30')])
def test_current_availability_mode(mode,expected):
    import json
    run('choice.value='+json.dumps(mode)+';returnToRefusedSearch("availability");assert(content(nodes["#search-resume"]).includes('+json.dumps(expected)+'));')


def test_live_edits_and_overnight_date_use_inputs_instead_of_last_request():
    run(r"""
returnToRefusedSearch('availability');state.availability={start:'obsolete',preparation_minutes:99};
nodes['#availability-start'].value='2026-12-31T23:00';nodes['#availability-end'].value='2026-12-31T01:00';
nodes['#availability-preparation-minutes'].value='0';nodes['#availability-flats-minutes'].value='7';renderSearchResume();
const text=content(nodes['#search-resume']);assert.match(text,/01.01.2027 à 01:00/);assert.match(text,/Préparation : 0 min · Flats : 7 min/);assert(!text.includes('99 min'));
state.compareProjects=false;state.selectedProjectId='Rosette fictive';renderSearchResume();assert.match(content(nodes['#search-resume']),/Projet : Rosette fictive/);
state.discoveryMode=true;renderSearchResume();assert.match(content(nodes['#search-resume']),/Recherche d’une nouvelle cible/);
""")


def test_changed_site_and_pending_configuration_do_not_claim_hours_preserved():
    run(r"""
returnToRefusedSearch('equipment');const original=state.refusedSearchResume.siteFingerprint;
state.configuration.site={...site,latitude:47,timezone:'Europe/Paris'};state.configurationDraft.site={...state.configuration.site};
nodes['#availability-start'].value='';nodes['#availability-end'].value='';state.dirty=true;setView('availability');
const text=content(nodes['#search-resume']);assert.match(text,/site ou son fuseau a changé/);assert.match(text,/Du à renseigner au à renseigner/);assert.match(text,/enregistrez vos réglages/);assert(!text.includes('horaires sont conservés'));
returnToRefusedSearch('availability');assert.equal(state.refusedSearchResume.siteFingerprint,original);
""")


def test_missing_and_invalid_durations_never_become_zero():
    run(r"""
returnToRefusedSearch('availability');nodes['#availability-preparation-minutes'].value='';nodes['#availability-flats-minutes'].value='-1';renderSearchResume();
assert.match(content(nodes['#search-resume']),/Préparation : à corriger · Flats : à corriger/);
state.refusedSearchResume=null;renderSearchResume();assert(nodes['#search-resume'].hidden);assert.equal(nodes['#search-resume'].children.length,0);
""")


def test_unsaved_configuration_blocks_resumed_analysis_before_any_request():
    run(r"""
function guardUnresolvedAcceptance(){return false}
const notices=[];function showFormError(message){notices.push(message)}
returnToRefusedSearch('availability');state.dirty=true;
loadTonight({mode:'all_night'}).then(()=>{
 assert.equal(state.view,'review');assert.match(notices.join(' '),/Enregistrez vos réglages/);
 assert(state.refusedSearchResume,'context survives blocked search');
 assert.equal(state.requestingRecommendation,undefined);
});
""")


def test_filter_save_confirmation_is_scoped_to_current_saved_configuration():
    run(r"""
returnToRefusedSearch('availability');state.configuration.profile_revision=2;
state.refusedSearchResume.filterSaveConfirmation={configuration:state.configuration,revision:2};
renderSearchResume();assert.match(content(nodes['#search-resume']),/matériel et vos choix de filtres sont enregistrés/);
state.dirty=true;renderSearchResume();assert(!content(nodes['#search-resume']).includes('matériel et vos choix de filtres sont enregistrés'));
state.dirty=false;state.configuration.profile_revision=3;renderSearchResume();assert(!content(nodes['#search-resume']).includes('matériel et vos choix de filtres sont enregistrés'));
state.configuration={...state.configuration,profile_revision:2};renderSearchResume();assert(!content(nodes['#search-resume']).includes('matériel et vos choix de filtres sont enregistrés'));
""")


def test_weather_guidance_uses_live_button_label_without_submitting():
    run(r"""
returnToRefusedSearch('availability');
assert.match(content(nodes['#search-resume']),/« Vérifier mon projet ».*réévaluer les conditions météo/);
nodes['#request-recommendation'].textContent='Quel projet avancer ce soir ?';
refreshSearchResumeAction();
assert.match(content(nodes['#search-resume']),/« Quel projet avancer ce soir \? »/);
const link=nodes['#search-resume'].children.find(e=>e.href==='#request-recommendation');
assert(link);assert.equal(link.textContent,'Aller au bouton de recherche');
const button=nodes['#request-recommendation'],events=[];
link.isConnected=true;button.getClientRects=()=>[{}];
button.scrollIntoView=()=>events.push('scroll');button.focus=()=>events.push('focus');
const event={preventDefault(){events.push('prevent')}};
const before=JSON.stringify(state);link.listeners.click(event);
assert.deepEqual(events,['prevent','scroll','focus']);assert.equal(JSON.stringify(state),before);
events.length=0;state.view='equipment';link.listeners.click(event);assert.deepEqual(events,['prevent']);
state.view='availability';link.isConnected=false;link.listeners.click(event);assert.deepEqual(events,['prevent','prevent']);
""")
