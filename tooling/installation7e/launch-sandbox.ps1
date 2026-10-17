$ErrorActionPreference = 'Stop'
$kit = $env:NIGHTMERIT_INSTALL_KIT
$exe = Join-Path $env:WINDIR 'System32\WindowsSandbox.exe'
if (-not (Test-Path $exe)) { throw 'Windows Sandbox est indisponible. Aucun installeur ne sera lancé sur ce PC. Transmettez ce message pour préparer une autre machine de test isolée.' }
$results = Join-Path $kit 'RESULTATS'
New-Item -ItemType Directory -Force -Path $results | Out-Null
$inputXml = [System.Security.SecurityElement]::Escape($kit)
$outputXml = [System.Security.SecurityElement]::Escape($results)
$config = @"
<Configuration>
 <vGPU>Disable</vGPU>
 <Networking>Disable</Networking>
 <ClipboardRedirection>Disable</ClipboardRedirection>
 <MappedFolders>
  <MappedFolder><HostFolder>$inputXml</HostFolder><SandboxFolder>C:\NightMeritInput</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
  <MappedFolder><HostFolder>$outputXml</HostFolder><SandboxFolder>C:\NightMeritResults</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
 </MappedFolders>
 <LogonCommand><Command>cmd.exe /c C:\NightMeritInput\sandbox-start.cmd</Command></LogonCommand>
</Configuration>
"@
$target = Join-Path $kit 'TEST-ISOLE-GENERE.wsb'
[IO.File]::WriteAllText($target,$config,[Text.UTF8Encoding]::new($false))
Start-Process -FilePath $exe -ArgumentList ('"' + $target + '"')
