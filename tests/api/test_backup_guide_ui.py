"""The backup entry must remain a read-only guide, with stable catalogue IDs."""
from pathlib import Path
import json
import shutil
import subprocess
import pytest

WEB=Path(__file__).resolve().parents[2]/'astropilot/web'

def node_run(tmp_path,program):
    node=shutil.which('node')
    if not node:pytest.skip('Node is required')
    script=tmp_path/'guide.cjs';script.write_text(program)
    result=subprocess.run([node,str(script)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr

def test_display_alias_keeps_catalogue_and_unknown_names_unchanged(tmp_path):
    source=(WEB/'app.js').read_text()
    function=source[source.index('function readableTargetName('):source.index('function savedMissionLabel(')]
    node_run(tmp_path,"const assert=require('node:assert/strict');\n"+function+'''
const original={project_id:'Sh2-129',selected_project_id:'Sh2-129',mission:{target:'Sh2-129'}};
const before=JSON.stringify(original);
assert.equal(readableTargetName(original.project_id),'Sh2-129 + Ou4');
assert.equal(readableTargetName(original.selected_project_id),'Sh2-129 + Ou4');
assert.equal(readableTargetName(original.mission.target),'Sh2-129 + Ou4');
assert.equal(JSON.stringify(original),before);
for(const name of ['M42','Rosette','Ou4','Sh2-129 + Ou4','Un catalogue inconnu'])assert.equal(readableTargetName(name),name);
assert.equal(readableTargetName(undefined),undefined);
assert.match(readableTargetName('NorthAmerica'),/NGC 7000/);
''')

def test_backup_entry_does_not_write_or_start_a_transfer(tmp_path):
    source=(WEB/'app.js').read_text()
    start=source.index('function openBackupGuide(')
    end=source.index("document.querySelector('#data-context-open').addEventListener",start)
    html=(WEB/'index.html').read_text()
    node_run(tmp_path,'''
const assert=require('node:assert/strict');
const nodes=new Map();
function element(id){if(!nodes.has(id))nodes.set(id,{open:false,textContent:'',listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},showModal(){this.open=true;},close(){this.open=false;}});return nodes.get(id);}
const document={querySelector:element};
let identityReads=0;
function openDataContext(){identityReads++;}
function fetch(){throw Error('No server request permitted for opening the guide');}
const name=element('#copy-identity-banner .copy-name');name.textContent='<img src=x onerror=attack()> FICTIF';
''' +source[start:end]+'''
element('#backup-guide-open').listeners.click();
assert.equal(element('#backup-guide-dialog').open,true);
assert.equal(element('#backup-guide-copy').textContent,'Copie à sauvegarder : <img src=x onerror=attack()> FICTIF');
assert.equal(identityReads,0);
element('#backup-guide-close').listeners.click();assert.equal(element('#backup-guide-dialog').open,false);
name.textContent='';element('#backup-guide-open').listeners.click();
assert.match(element('#backup-guide-copy').textContent,/même dossier/);
element('#backup-guide-context').listeners.click();
assert.equal(element('#backup-guide-dialog').open,false);assert.equal(identityReads,1);
''')
    assert 'id="backup-guide-open" type="button" aria-haspopup="dialog">Sauvegarder mes données' in html
    guide=html[html.index('<dialog id="backup-guide-dialog"'):html.index('<dialog id="data-context-dialog"')]
    assert 'GERER-MES-DONNEES.command' in guide and 'téléchargements de votre navigateur' in guide
    assert 'Contrôler le fichier téléchargé' in guide and 'ne remplace et ne fusionne' in guide
