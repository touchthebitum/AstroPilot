$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=$PSScriptRoot
$ciMode=($env:NIGHTMERIT_RESUME_CI -eq '1')
Get-ChildItem Env: | Where-Object { $_.Name -match '^(ASTROPILOT_|NIGHTMERIT_)' } | ForEach-Object { [Environment]::SetEnvironmentVariable($_.Name,$null,'Process') }
$work=Join-Path ([System.IO.Path]::GetTempPath()) ('reprise-isole-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $work | Out-Null
$proof=[ordered]@{product_sha='0dcde494c8450176f445cc29b28d004eddb60734';result='NOT_VALIDATED';new_sessions=0;new_credits=0;ui_confirmed=$false;synthetic=$true}
$p=$null;$sourceData=$null;$sourceBefore=$null
function Safe-Files([string]$directory) {
 $stack=New-Object 'System.Collections.Generic.Stack[string]';$stack.Push($directory)
 while ($stack.Count) {
  $current=$stack.Pop();$info=Get-Item -LiteralPath $current -Force
  if ($info.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Lien ou jonction interdit dans la copie source' }
  foreach ($item in Get-ChildItem -LiteralPath $current -Force) {
   if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Lien ou jonction interdit dans la copie source' }
   if ($item.PSIsContainer) { $stack.Push($item.FullName) } else { $item }
  }
 }
}
function Inventory([string]$directory,[switch]$Logical) {
 $rows=@(Safe-Files $directory | Where-Object {
  $relative=$_.FullName.Substring($directory.Length+1);$first=$relative.Split('\')[0]
  -not $Logical -or ($_.Extension -eq '.json' -and ($relative -eq 'user_profile.json' -or $first -in @('decision_lineage','execution_lineage','decision_forecast_evidence','field_observations','outcome_evaluations')))
 } | ForEach-Object {
  $_.FullName.Substring($directory.Length+1)+'='+(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
 } | Sort-Object)
 return $rows -join "`n"
}
function Check-Binary([string]$directory) {
 $inventory=Get-Content -Raw -Encoding UTF8 (Join-Path $root 'Inventaire-binaire.json') | ConvertFrom-Json
 if ($inventory.source_sha -cne $proof.product_sha) { throw 'Provenance du binaire incorrecte' }
 $files=@(Safe-Files $directory)
 if ($files.Count -ne $inventory.files.Count) { throw 'Inventaire du binaire incomplet ou modifie' }
 foreach ($row in $inventory.files) {
  $file=[IO.Path]::GetFullPath((Join-Path $directory $row.path))
  if (-not $file.StartsWith($directory.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Chemin de binaire interdit' }
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant() -cne $row.sha256) { throw ('Binaire modifie : '+$row.path) }
 }
}
function Assert-Existing([string]$directory) {
 $profile=Get-Content -Raw -Encoding UTF8 (Join-Path $directory 'user_profile.json') | ConvertFrom-Json
 foreach ($label in @('ha','oiii')) {
  $eid='packaged-ui-'+$label;$expected=if ($label -eq 'ha') {1800000000} else {900000000}
  $entry=$profile.intent_progress_credits.$eid
  if (-not $entry -or $entry.execution_id -cne $eid -or $entry.project_id -cne 'Sh2-129' -or $entry.total_duration_us -ne $expected -or @($entry.evidence_ids).Count -ne 1) { throw ('Credit existant manquant ou incoherent : '+$label) }
 }
}
function Assert-Owned {
 if (-not $script:p -or $script:p.HasExited) { throw 'Le processus de reprise est arrete' }
 $owners=@(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction Stop | Where-Object { $_.LocalAddress -eq '127.0.0.1' -and $_.OwningProcess -eq $script:p.Id })
 if ($owners.Count -ne 1) { throw 'Le serveur local ne correspond pas au processus de reprise' }
}
function Api([string]$path,[string]$method='Get',$body=$null) {
 Assert-Owned
 # Only reads, or an identical replay of an EXISTING credit, are permitted.
 if ($method -ne 'Get' -and ($method -ne 'Post' -or $path -notmatch '^/v1/executions/packaged-ui-(ha|oiii)/intent-progress-credit$')) { throw 'Operation interdite dans la reprise' }
 $arguments=@{Uri=('http://127.0.0.1:8000'+$path);Method=$method;TimeoutSec=30}
 if ($null -ne $body) { $arguments.ContentType='application/json';$arguments.Body=($body | ConvertTo-Json -Depth 10) }
 Invoke-RestMethod @arguments
}
function Start-Owned {
 $script:p=Start-Process -FilePath $exe -WorkingDirectory $work -PassThru -RedirectStandardOutput (Join-Path $work ('stdout-'+[guid]::NewGuid()+'.log')) -RedirectStandardError (Join-Path $work ('stderr-'+[guid]::NewGuid()+'.log'))
 for ($i=0;$i -lt 120;$i++) {
  if ($script:p.HasExited) { throw 'Le binaire de reprise est arrete' }
  try {
   $id=Api '/v1/runtime-identity'
   if ($id.application -cne 'astropilot' -or $id.version -cne '1.0.0b8' -or $id.build -cne '0dcde49' -or $id.architecture -cne 'x86_64') { throw 'Identite du candidat incorrecte' }
   $proof.runtime=$id;return
  } catch { Start-Sleep -Milliseconds 500 }
 }
 throw 'Demarrage de la reprise non confirme'
}
function Stop-Owned {
 if ($script:p -and -not $script:p.HasExited) {
  Stop-Process -Id $script:p.Id
  if (-not $script:p.WaitForExit(30000)) { throw 'Arret du processus non confirme' }
 }
 $script:p=$null
}
function Read-Confirmed {
 while ($true) {
  $answer=(Read-Host 'Apres verification des deux sessions terminees : oui pour confirmer, non pour arreter').Trim().ToLowerInvariant()
  if ($answer -in @('oui','o','yes','y')) { return $true }
  if ($answer -in @('non','n','no','q','quitter')) { return $false }
  Write-Host 'Reponse non reconnue. Le serveur reste ouvert : taper oui ou non.'
 }
}
function Check-Sessions {
 foreach ($label in @('ha','oiii')) {
  $expected=if ($label -eq 'ha') {1800} else {900}
  $session=Api ('/v1/executions/packaged-ui-'+$label+'/session')
  if ($session.execution.status -cne 'completed' -or $null -eq $session.credit -or $session.session_credit_seconds -ne $expected) { throw ('Session existante non conforme : '+$label) }
 }
 $progress=Api '/v1/projects/Sh2-129/progress'
 $ha=@($progress.intent_progress_breakdown | Where-Object acquisition_intent_id -eq 'sh2-129_ha')[0]
 $oiii=@($progress.intent_progress_breakdown | Where-Object acquisition_intent_id -eq 'ou4_oiii')[0]
 if ($ha.effective_total_seconds -ne 5400 -or $oiii.effective_total_seconds -ne 900) { throw 'Totaux existants incorrects' }
}
try {
 Write-Host '1/5 Recherche et verification de la copie du test precedent...'
 $manifest=Get-Content -Raw -Encoding UTF8 (Join-Path $root 'Manifest-reprise.json') | ConvertFrom-Json
 foreach ($row in $manifest.files) {
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root $row.path)).Hash.ToLowerInvariant() -cne $row.sha256) { throw 'Fichier du lanceur modifie' }
 }
 $name='essai-isole-20261015-151443-f27734'
 $candidates=@((Join-Path ([IO.Path]::GetTempPath()) $name),(Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) ('Temp\'+$name)))
 $found=@($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Container } | ForEach-Object { (Get-Item -LiteralPath $_).FullName.TrimEnd('\') } | Sort-Object -Unique)
 if ($found.Count -ne 1) { throw 'Copie du test introuvable ou ambigue. Ne pas relancer le kit initial.' }
 $sourceRun=$found[0];$sourceData=Join-Path $sourceRun 'ASTROPILOT_DATA_DIR';$sourceRuntime=Join-Path $sourceRun 'runtime\AstroPilot'
 $sourceBefore=Inventory $sourceData
 Assert-Existing $sourceData
 Check-Binary $sourceRuntime
 $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,8000)
 try { $listener.Start() } finally { $listener.Stop() }
 Write-Host '2/5 Copie de reprise neuve. La copie precedente reste intacte...'
 $data=Join-Path $work 'data';New-Item -ItemType Directory -Path $data | Out-Null
 $stores=@('decision_lineage','execution_lineage','decision_forecast_evidence','field_observations','outcome_evaluations')
 foreach ($file in Safe-Files $sourceData) {
  $relative=$file.FullName.Substring($sourceData.Length+1);$first=$relative.Split('\')[0]
  if ($relative -eq 'user_profile.json' -or ($first -in $stores -and $file.Extension -eq '.json')) {
   $target=Join-Path $data $relative;New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null;Copy-Item -LiteralPath $file.FullName -Destination $target
  } elseif ($file.Name -eq 'guardian_runtime.json' -or $file.Name.StartsWith('.') -or $first -eq 'Logs' -or $file.Extension -eq '.log') {
   # Local keys, locks, old logs and runtime attestations are deliberately not restored.
  } else { throw ('Fichier source non classe : '+$relative) }
 }
 if ((Inventory $sourceData -Logical) -cne (Inventory $data -Logical)) { throw 'Copie logique non conforme' }
 Copy-Item -LiteralPath $sourceRuntime -Destination (Join-Path $work 'AstroPilot') -Recurse
 Check-Binary (Join-Path $work 'AstroPilot')
 foreach ($key in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME')) {
  $dir=Join-Path $work $key;New-Item -ItemType Directory -Path $dir | Out-Null;[Environment]::SetEnvironmentVariable($key,$dir,'Process')
 }
 $env:ASTROPILOT_DATA_DIR=$data;$exe=Join-Path $work 'AstroPilot\AstroPilot.exe'
 $logicalBefore=Inventory $data -Logical
 Write-Host '3/5 Lecture des credits existants, puis redemarrage du meme binaire...'
 Start-Owned;Check-Sessions;Stop-Owned;Start-Sleep -Seconds 2;Start-Owned;Check-Sessions
 $rows=@()
 Write-Host '4/5 Trois rejeux identiques par credit, sans creation...'
 foreach ($label in @('ha','oiii')) {
  $eid='packaged-ui-'+$label
  for ($i=0;$i -lt 3;$i++) {
   Assert-Existing $data
   $profile=Get-Content -Raw -Encoding UTF8 (Join-Path $data 'user_profile.json') | ConvertFrom-Json
   $entry=$profile.intent_progress_credits.$eid
   $response=Api ('/v1/executions/'+$eid+'/intent-progress-credit') 'Post' @{expected_revision=$profile.profile_revision;evidence_ids=@($entry.evidence_ids);confirm_historical_baseline=$false}
   if ($response.status -cne 'already_applied') { throw 'Le serveur ne confirme pas un simple rejeu' }
   if ((Inventory $data -Logical) -cne $logicalBefore) { throw 'Les donnees durables ont change pendant le rejeu' }
  }
  $rows+=@{intent=$label;replay='already_applied';count=3}
 }
 Check-Sessions
 if ((Inventory $data -Logical) -cne $logicalBefore) { throw 'Donnees durables modifiees au redemarrage' }
 $proof.replays=$rows;$proof.restart=$true;$proof.authority_unchanged=$true;$proof.ha_seconds=5400;$proof.oiii_seconds=900
 $proof.result='AUTOMATED_PASS_UI_PENDING'
 Write-Host '5/5 Controles automatiques reussis. Verifier les sessions terminees dans le navigateur.'
 Write-Host 'Halpha : credit 30 min, acquis 1 h 30. OIII : credit/acquis 15 min. Ne rien demarrer ni ajouter.'
 if (-not $ciMode) { Start-Process 'http://127.0.0.1:8000/' | Out-Null }
 if (Read-Confirmed) {
  if ($ciMode) { $proof.result='PASS_API_ONLY' } else { $proof.result='PASS';$proof.ui_confirmed=$true }
 } else { $proof.result='NOT_VALIDATED';$proof.error='Confirmation visuelle declinee' }
} catch {
 $proof.result='NOT_VALIDATED';$proof.error=$_.Exception.Message
 Write-Host ('REFUS / NON VALIDE : '+$_.Exception.Message)
} finally {
 try { Stop-Owned } catch { $proof.result='NOT_VALIDATED';$proof.stop_error=$_.Exception.Message }
 if ($sourceBefore) {
  try { $proof.source_unchanged=((Inventory $sourceData) -ceq $sourceBefore) } catch { $proof.source_unchanged=$false }
  if (-not $proof.source_unchanged) { $proof.result='NOT_VALIDATED';$proof.source_error='La copie source a change pendant le controle' }
 }
 $export=Join-Path $work 'export';New-Item -ItemType Directory -Path $export | Out-Null
 $proof | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $export 'reprise.json')
 Get-ChildItem -LiteralPath $work -File -Filter '*.log' | Copy-Item -Destination $export
 Get-ChildItem -LiteralPath $work -Recurse -File -Filter 'AstroPilot.log' | Where-Object { -not $_.FullName.StartsWith($export+'\') } | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $export ([guid]::NewGuid().ToString('N')+'-AstroPilot.log'))
 }
 $zip=Join-Path $root ('resultats-reprise-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)+'.zip')
 Compress-Archive -Path (Join-Path $export '*') -DestinationPath $zip
 Write-Host ('Resultat : '+$zip)
}
if (-not $ciMode) { Read-Host 'Entree pour fermer' | Out-Null }
