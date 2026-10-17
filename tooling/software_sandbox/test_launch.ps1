$ErrorActionPreference='Stop'
$script:captures=@()
function Test-Path {
 param([string]$Path)
 if ($Path -like '*System32\WindowsSandbox.exe') { return $true }
 return Microsoft.PowerShell.Management\Test-Path -Path $Path
}
function Start-Process {
 param([string]$FilePath,[string]$ArgumentList)
 $script:captures += [pscustomobject]@{file=$FilePath;arguments=$ArgumentList}
}
$fixture=Join-Path $env:RUNNER_TEMP ('logiciel racine & espace-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
$env:NIGHTMERIT_INSTALL_KIT=$fixture
. (Join-Path $PSScriptRoot '../installation7e/launch-sandbox.ps1')
$path=Join-Path $fixture 'TEST-ISOLE-GENERE.wsb'
[xml]$config=[IO.File]::ReadAllText($path)
if ($config.Configuration.vGPU -ne 'Disable') { throw 'vGPU must be disabled in this instance only' }
if ($config.Configuration.Networking -ne 'Disable' -or $config.Configuration.ClipboardRedirection -ne 'Disable') { throw 'Isolation settings changed' }
$maps=@($config.Configuration.MappedFolders.MappedFolder)
if ($maps.Count -ne 2 -or $maps[0].ReadOnly -ne 'true' -or $maps[1].ReadOnly -ne 'false') { throw 'Folder access changed' }
if ($maps[0].HostFolder -ne $fixture -or $maps[1].HostFolder -ne (Join-Path $fixture 'RESULTATS')) { throw 'Escaped paths did not roundtrip' }
if ($maps[0].SandboxFolder -ne 'C:\NightMeritInput' -or $maps[1].SandboxFolder -ne 'C:\NightMeritResults') { throw 'Unexpected mapping' }
if ($config.Configuration.LogonCommand.Command -ne 'cmd.exe /c C:\NightMeritInput\sandbox-start.cmd') { throw 'Unexpected startup command' }
if ($script:captures.Count -ne 1 -or $script:captures[0].arguments -ne ('"'+$path+'"')) { throw 'Wrong process argument quoting' }
# The process is intercepted: no sandbox, installer, driver or system setting is changed.
[pscustomobject]@{result='PASS';vgpu='Disable';network='Disable';clipboard='Disable';folder_permissions_unchanged=$true;paths_with_spaces_and_ampersand=$true;sandbox_started=$false;system_settings_changed=$false;physical_user_test_pending=$true} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $env:RUNNER_TEMP 'software-launch-proof.json')
