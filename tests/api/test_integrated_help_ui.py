"""Integrated documentation remains independent of scientific and recovery state."""
from pathlib import Path
import shutil
import subprocess

WEB = Path(__file__).parents[2] / 'astropilot/web'


def test_help_content_and_integration():
    html = (WEB / 'index.html').read_text()
    source = (WEB / 'help.js').read_text()
    css = (WEB / 'styles.css').read_text()
    assert 'id="help-open"' in html and 'aria-haspopup="dialog"' in html
    assert 'id="help-dialog" aria-labelledby="help-title"' in html
    assert 'id="help-close" type="button" autofocus' in html
    assert html.index('/ui/help.js') < html.index('/ui/app.js')
    short = source.split('  start: {', 1)[1].split('  understand: {', 1)[0]
    for term in ['UUID', 'provenance', 'Outcome', 'supersession']:
        assert term.lower() not in short.lower()
    for text in ['Site → Matériel → Disponibilité → Préparer ma nuit', 'cible', 'filtre', 'créneau', 'risques', 's’abstenir', 'observation terrain', 'même moteur']:
        assert text in short
    assert len(short.split()) < 450
    for text in ['Fiabilité', 'prévision', 'recalibrage automatique', 'fenêtre productive', 'inconnues']:
        assert text.lower() in source.lower()
    for section in ['installation', 'site', 'equipment', 'availability', 'tonight', 'missions', 'observations', 'history', 'modes', 'weather-trace', 'recovery', 'limits', 'glossary']:
        assert f'["{section}",' in source
    assert 'html[data-ui-mode="simple"] .help-navigation [data-help-guide="start"]' in css
    assert 'overflow-y: auto' in css and '100dvh' in css
    for forbidden in ['fetch(', 'localStorage', 'currentDecision', 'acceptedMission', 'fieldObservation', 'historyState']:
        assert forbidden not in source


def test_help_node_state_and_mode_harness(tmp_path):
    node = shutil.which('node')
    assert node, 'Node is required for the integrated help harness'
    harness = r'''
const assert = require('node:assert/strict');
class Element {
 constructor(){this.listeners={};this.children=[];this.dataset={};this.attrs={};this.scrollTop=0;this.open=false;}
 addEventListener(k,f){this.listeners[k]=f;}
 setAttribute(k,v){this.attrs[k]=v;}
 removeAttribute(k){delete this.attrs[k];}
 getAttribute(k){return this.attrs[k];}
 append(...xs){this.children.push(...xs);}
 replaceChildren(){this.children=[];}
 get childElementCount(){return this.children.length;}
 focus(){focused=this;}
 showModal(){this.open=true;close.focus();}
 close(){this.open=false;this.listeners.close?.();}
 dispatchEvent(e){this.listeners[e.type]?.();}
 querySelectorAll(){return buttons;}
 querySelector(){return section;}
}
let focused, observer;
const opener=new Element(), close=new Element(), dialog=new Element(), content=new Element(), mode=new Element(), globalMode=new Element(), section=new Element();
const buttons=['start','understand','complete'].map(key=>{let b=new Element();b.dataset.helpGuide=key;return b;});
const business={currentDecision:{id:'d'},acceptedMission:{id:'m'},drafts:{text:'kept'},pending:{id:'p'},recovery:{id:'r'},filters:{site:'s'}};
const before=JSON.stringify(business);
const document={documentElement:{dataset:{uiMode:'simple'}},createElement:()=>new Element(),getElementById:()=>section,
 querySelector:s=>({'#help-dialog':dialog,'#help-content':content,'#help-open':opener,'#help-close':close,'#help-mode':mode,'#ui-mode':globalMode}[s])};
const window={};
class MutationObserver {constructor(f){observer=f;} observe(){}}
class Event {constructor(type){this.type=type;}}
globalMode.addEventListener('change',()=>{document.documentElement.dataset.uiMode=globalMode.value;observer();});
'''
    checks = r'''
opener.listeners.click();
assert(dialog.open);assert.equal(focused,close);assert.equal(buttons[0].attrs['aria-current'],'page');
buttons[2].listeners.click();content.scrollTop=137;
const children=content.children;
mode.value='pro';mode.listeners.change();
assert.equal(document.documentElement.dataset.uiMode,'pro');assert.equal(content.children,children);assert.equal(content.scrollTop,137);
mode.value='simple';mode.listeners.change();
assert.equal(buttons[2].attrs['aria-current'],'page');assert.equal(content.scrollTop,137);
close.listeners.click();assert(!dialog.open);assert.equal(focused,opener);
opener.listeners.click();assert.equal(content.scrollTop,137);
buttons[0].listeners.click();buttons[2].listeners.click();assert.equal(content.scrollTop,137);
window.nightmeritHelp.open('understand','reliability');assert.equal(focused,section);
assert.equal(JSON.stringify(business),before);
'''
    script = tmp_path / 'help-harness.js'
    script.write_text(harness + (WEB / 'help.js').read_text() + checks)
    subprocess.run([node, str(script)], check=True, capture_output=True, text=True)
