$ErrorActionPreference = 'Stop'
function New-KitContext([string]$kitDirectory, [string]$sourceSha) {
 if ($sourceSha -cnotmatch '^[0-9a-f]{40}$') { throw 'Identite de source invalide.' }
 $hostKit = [IO.Path]::GetFullPath($kitDirectory)
 $value = [ordered]@{schema='nightmerit.private_copy_context.v1'; source_sha=$sourceSha; host_kit_directory=$hostKit; host_results_directory=(Join-Path $hostKit 'RESULTATS'); guest_data_directory='C:\NightMeritResults\profil'}
 $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($value | ConvertTo-Json -Compress)))
 # Only a Base64 data argument crosses cmd/XML, never executable path text.
 if ($encoded.Length -gt 5000) { throw 'Le chemin du kit est trop long pour le lanceur.' }
 return $encoded
}
$kit = [IO.Path]::GetFullPath($env:NIGHTMERIT_PRIVATE_KIT)
$copyContext = New-KitContext $kit '__SOURCE_SHA__'
$exe = Join-Path $env:WINDIR 'System32\WindowsSandbox.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Windows Sandbox est indisponible. Aucun programme de test ne sera lance sur ce PC.' }
# On the host, only create the kit's own results folder and Sandbox configuration.
$results = Join-Path $kit 'RESULTATS'
New-Item -ItemType Directory -Force -Path $results | Out-Null
if ((Get-Item -LiteralPath $results).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Le dossier RESULTATS ne doit pas etre un lien.' }
$inputXml = [Security.SecurityElement]::Escape($kit)
$outputXml = [Security.SecurityElement]::Escape($results)
$config = @"
<Configuration>
 <vGPU>Disable</vGPU>
 <Networking>Enable</Networking>
 <ClipboardRedirection>Disable</ClipboardRedirection>
 <MappedFolders>
  <MappedFolder><HostFolder>$inputXml</HostFolder><SandboxFolder>C:\NightMeritInput</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
  <MappedFolder><HostFolder>$outputXml</HostFolder><SandboxFolder>C:\NightMeritResults</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
 </MappedFolders>
 <LogonCommand><Command>cmd.exe /c start "NightMerit - test prive" cmd.exe /k C:\NightMeritInput\sandbox-start.cmd "$copyContext"</Command></LogonCommand>
</Configuration>
"@
$target = Join-Path $kit 'TEST-ISOLE-GENERE.wsb'
[IO.File]::WriteAllText($target, $config, [Text.UTF8Encoding]::new($false))
Start-Process -FilePath $exe -ArgumentList ('"' + $target + '"')
