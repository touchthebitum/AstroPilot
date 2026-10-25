"""Native storage primitives and pure Windows launcher contracts; no real profile."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest
from astropilot.stable_beta_data import MARKER, prepare

ROOT=Path(__file__).resolve().parents[2]
A='a'*40
B='b'*40


def test_stable_update_publication_preserves_original_and_creates_one_backup(tmp_path):
    profile=tmp_path/'beta'/'profil'
    prepare(profile,A);profile.mkdir();(profile/'user_profile.json').write_bytes(b'{"synthetic_only":true}')
    def snapshot_factory(root):
        assert root==profile
        return (root/'user_profile.json').read_bytes(),{'projects':0}
    assert prepare(profile,B,backup_factory=snapshot_factory)['backup_created']
    assert (profile/'user_profile.json').read_bytes()==b'{"synthetic_only":true}'
    backups=list((profile.parent/'SAUVEGARDES-AUTO').glob('*.zip'))
    assert len(backups)==1 and backups[0].read_bytes()==(profile/'user_profile.json').read_bytes()
    assert not prepare(profile,B,backup_factory=snapshot_factory)['backup_created']
    assert len(list((profile.parent/'SAUVEGARDES-AUTO').glob('*.zip')))==1


def test_failed_snapshot_cannot_advance_the_stable_build_marker(tmp_path):
    profile=tmp_path/'beta'/'profil';prepare(profile,A);profile.mkdir()
    (profile/'user_profile.json').write_bytes(b'{"synthetic_only":true}')
    before=(profile.parent/MARKER).read_bytes()
    def fail(root):raise OSError('simulated full disk')
    with pytest.raises(OSError,match='simulated full disk'):prepare(profile,B,backup_factory=fail)
    assert (profile.parent/MARKER).read_bytes()==before
    assert (profile/'user_profile.json').read_bytes()==b'{"synthetic_only":true}'


def test_publication_never_overwrites_an_existing_snapshot(tmp_path):
    from astropilot.stable_beta_data import _publish
    destination=tmp_path/'existing.zip';destination.write_bytes(b'keep this snapshot')
    with pytest.raises(FileExistsError):_publish(destination,b'replacement')
    assert destination.read_bytes()==b'keep this snapshot'


@pytest.mark.skipif(os.name!='nt',reason='Native Windows PowerShell contract')
def test_stable_windows_context_mapping_and_lease_are_native(tmp_path):
    render=runpy.run_path(str(ROOT/'scripts/render_private_windows_launcher.py'))['render']
    output=render(A,tmp_path/'rendered',data_mode='stable')
    host=(output/'Audit/launch-sandbox.ps1').read_text()
    mapping=next(line for line in host.splitlines() if '$stableMapping =' in line and '<MappedFolder>' in line)
    xml=host.split('$config = @"\n',1)[1].split('\n"@',1)[0]
    folder=str(tmp_path).replace("'","''")
    child=tmp_path/'prepare_child.py'
    child.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0, '+repr(str(ROOT))+')\nfrom astropilot.stable_beta_data import prepare\nprepare(Path(sys.argv[1]), '+repr(A)+')\n',encoding='utf-8')
    python=str(Path(sys.executable)).replace("'","''")
    code=f"""
$ErrorActionPreference='Stop'
$folder='{folder}'
$hostFile=Join-Path $folder 'rendered\\Audit\\launch-sandbox.ps1'
$controllerFile=Join-Path $folder 'rendered\\Audit\\controller.ps1'
foreach($spec in @(@($hostFile,'New-KitContext'),@($controllerFile,'Read-KitContext'))) {{
 $tokens=$null;$errors=$null
 $ast=[Management.Automation.Language.Parser]::ParseFile($spec[0],[ref]$tokens,[ref]$errors)
 if($errors.Count){{throw ($errors|Out-String)}}
 $name=$spec[1]
 $definition=$ast.Find({{param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name}},$true)
 . ([ScriptBlock]::Create($definition.Extent.Text))
}}
$kit=Join-Path $folder 'version 2'
$stableRoot=Join-Path $folder 'shared beta'
$copyContext=New-KitContext $kit '{A}' $stableRoot
$context=Read-KitContext $copyContext '{A}' 'stable' | ConvertFrom-Json
$inputXml=[Security.SecurityElement]::Escape($kit)
$outputXml=[Security.SecurityElement]::Escape((Join-Path $kit 'RESULTATS'))
$stableXml=[Security.SecurityElement]::Escape($stableRoot)
$transferMode='0'
{mapping}
$config=@"
{xml}
"@
[xml]$configXml=$config
New-Item -ItemType Directory -Path $stableRoot | Out-Null
$leasePath=Join-Path $stableRoot '.nightmerit-session.lock'
$first=[IO.File]::Open($leasePath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
$blocked=$false
try {{
 try {{$second=[IO.File]::Open($leasePath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$second.Dispose()}} catch [IO.IOException] {{$blocked=$true}}
 & '{python}' (Join-Path $folder 'prepare_child.py') (Join-Path $stableRoot 'profil')
 if ($LASTEXITCODE -ne 0) {{throw 'Preparation failed while parent holds Windows lease'}}
}} finally {{$first.Dispose()}}
$after=[IO.File]::Open($leasePath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$after.Dispose()
$mappings=@($configXml.Configuration.MappedFolders.MappedFolder | ForEach-Object {{ @{{HostFolder=[string]$_.HostFolder;SandboxFolder=[string]$_.SandboxFolder;ReadOnly=[string]$_.ReadOnly}} }})
@{{context=$context;mappings=$mappings;lease_blocked=$blocked}} | ConvertTo-Json -Depth 8 -Compress
"""
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',code],check=True,capture_output=True,text=True,timeout=40)
    value=json.loads(result.stdout)
    assert value['context']['host_data_directory']==str(tmp_path/'shared beta'/'profil')
    assert value['context']['guest_data_directory']==r'C:\NightMeritData\profil'
    assert len(value['mappings'])==3
    assert [m['ReadOnly'] for m in value['mappings']]==['true','false','false']
    assert value['mappings'][2]['SandboxFolder']==r'C:\NightMeritData'
    assert value['mappings'][2]['HostFolder']==str(tmp_path/'shared beta')
    assert value['lease_blocked'] is True
