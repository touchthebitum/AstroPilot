$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = $PSScriptRoot
$run = Join-Path ([System.IO.Path]::GetTempPath()) ('essai-isole-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $run | Out-Null
$manifest = Get-Content -Raw (Join-Path $root 'Manifest-kit.json') | ConvertFrom-Json
foreach ($item in $manifest.files) {
  $file = Join-Path $root $item.path
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant() -cne $item.sha256) { throw "Empreinte incorrecte : $($item.path)" }
}
# Refuse any listener before starting our owned process.
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,8000)
try { $listener.Start() } finally { $listener.Stop() }
foreach ($name in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','ASTROPILOT_DATA_DIR')) {
 $dir = Join-Path $run $name
 New-Item -ItemType Directory -Path $dir | Out-Null
 [Environment]::SetEnvironmentVariable($name,$dir,'Process')
}
Expand-Archive -LiteralPath (Join-Path $root 'Profil-Mac-test.zip') -DestinationPath $env:ASTROPILOT_DATA_DIR
Expand-Archive -LiteralPath (Join-Path $root 'AstroPilot-1.0.0b8-windows-x86_64-portable.zip') -DestinationPath (Join-Path $run 'runtime')
$exe = Join-Path $run 'runtime/AstroPilot/AstroPilot.exe'
$p = $null
$proof = [ordered]@{product_sha='0dcde494c8450176f445cc29b28d004eddb60734';synthetic=$true;ui_validation='manual';result='NOT_VALIDATED'}
function Assert-Owned {
 if (-not $script:p -or $script:p.HasExited) { throw 'Le processus de test n''est plus actif' }
 $owners=@(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction Stop | Where-Object { $_.LocalAddress -eq '127.0.0.1' -and $_.OwningProcess -eq $script:p.Id })
 if ($owners.Count -ne 1) { throw 'Le serveur ne peut pas être rattaché au processus de test' }
}
function Invoke-Owned {
 param([string]$Uri,[string]$Method='Get',[string]$ContentType='application/json',[string]$Body)
 Assert-Owned
 $args=@{Uri=$Uri;Method=$Method;ContentType=$ContentType;TimeoutSec=30}
 if ($Body) { $args.Body=$Body }
 Invoke-RestMethod @args
}
function Get-Authority-Inventory {
 $result=@{}
 $profile=Join-Path $env:ASTROPILOT_DATA_DIR 'user_profile.json'
 $result['user_profile.json']=(Get-FileHash -Algorithm SHA256 -LiteralPath $profile).Hash
 foreach ($store in @('decision_lineage','execution_lineage','decision_forecast_evidence','field_observations','outcome_evaluations')) {
  $directory=Join-Path $env:ASTROPILOT_DATA_DIR $store
  if (Test-Path -LiteralPath $directory) {
   Get-ChildItem -LiteralPath $directory -Recurse -File -Filter '*.json' | ForEach-Object {
    $relative=$_.FullName.Substring($env:ASTROPILOT_DATA_DIR.Length+1).Replace('\','/')
    $result[$relative]=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
   }
  }
 }
 return ($result.GetEnumerator() | Sort-Object Key | ForEach-Object { $_.Key+'='+$_.Value }) -join "`n"
}
function Start-Owned {
 $script:p = Start-Process -FilePath $exe -WorkingDirectory $run -PassThru -RedirectStandardOutput (Join-Path $run ('stdout-'+[guid]::NewGuid()+'.log')) -RedirectStandardError (Join-Path $run ('stderr-'+[guid]::NewGuid()+'.log'))
 for ($i=0;$i -lt 120;$i++) {
  if ($script:p.HasExited) { throw 'Le candidat s''est arrêté.' }
  try { $id = Invoke-Owned -Uri 'http://127.0.0.1:8000/v1/runtime-identity'; if ($id.application -cne 'astropilot' -or $id.version -cne '1.0.0b8' -or $id.architecture -cne 'x86_64' -or $id.build -cne '0dcde49') { throw 'Build incorrect' }; $proof.runtime=$id; return } catch { Start-Sleep -Milliseconds 500 }
 }
 throw 'Démarrage non confirmé'
}
function Stop-Owned {
 if ($script:p -and -not $script:p.HasExited) { Stop-Process -Id $script:p.Id; $script:p.WaitForExit(30000) | Out-Null }
 $script:p=$null
}
try {
 Start-Owned
 # Prepare discoverable NOT_STARTED sessions through the real binary API.
 foreach ($label in @('ha','oiii')) {
  $body = @{execution_id="packaged-ui-$label";mission_id="qualification-mission-$label"} | ConvertTo-Json
  Invoke-Owned -Method Post -Uri 'http://127.0.0.1:8000/v1/executions' -ContentType 'application/json' -Body $body | Out-Null
 }
 Start-Process 'http://127.0.0.1:8000/'
 Write-Host 'COPIE ISOLEE. Suivre Lisez-moi.txt : Hα puis OIII, durées fictives 30 et 15 minutes.'
 if ((Read-Host 'Les deux crédits sont-ils affichés ? Taper OUI pour redémarrer et vérifier') -cne 'OUI') { throw 'Validation visuelle initiale non confirmée' }
 $proof.ui_before_restart_confirmed=$true
 $authorityBefore=Get-Authority-Inventory
 $before = (Get-FileHash -Algorithm SHA256 (Join-Path $env:ASTROPILOT_DATA_DIR 'user_profile.json')).Hash
 Stop-Owned
 Start-Sleep -Seconds 2
 Start-Owned
 $sessions = Invoke-Owned -Uri 'http://127.0.0.1:8000/v1/execution-sessions'
 $rows=@()
 foreach ($label in @('ha','oiii')) {
  $eid="packaged-ui-$label"
  $s=Invoke-Owned -Uri "http://127.0.0.1:8000/v1/executions/$eid/session"
  $expected=if ($label -eq 'ha') {1800} else {900}
  if ($s.execution.status -ne 'completed' -or $s.session_credit_seconds -ne $expected) { throw "Session $label non validée" }
  $profile=Get-Content -Raw (Join-Path $env:ASTROPILOT_DATA_DIR 'user_profile.json') | ConvertFrom-Json
  $body=@{expected_revision=$profile.profile_revision;evidence_ids=@($s.evidence[0].evidence_id);confirm_historical_baseline=($label -eq 'ha')} | ConvertTo-Json
  for ($i=0;$i -lt 3;$i++) {
   $replay=Invoke-Owned -Method Post -Uri "http://127.0.0.1:8000/v1/executions/$eid/intent-progress-credit" -ContentType 'application/json' -Body $body
   if ($replay.status -ne 'already_applied') { throw 'Rejeu incorrect' }
  }
  $rows+=@{intent=$label;credit_seconds=$s.session_credit_seconds;replay='already_applied';replay_count=3}
 }
 $after=(Get-FileHash -Algorithm SHA256 (Join-Path $env:ASTROPILOT_DATA_DIR 'user_profile.json')).Hash
 if ($after -cne $before) { throw 'Profil modifié par le rejeu' }
 $progress=Invoke-Owned -Uri 'http://127.0.0.1:8000/v1/projects/Sh2-129/progress'
 $ha=@($progress.intent_progress_breakdown | Where-Object acquisition_intent_id -eq 'sh2-129_ha')[0]
 $oiii=@($progress.intent_progress_breakdown | Where-Object acquisition_intent_id -eq 'ou4_oiii')[0]
 if ($ha.effective_total_seconds -ne 5400 -or $oiii.effective_total_seconds -ne 900) { throw 'Totaux incorrects' }
 if ((Get-Authority-Inventory) -cne $authorityBefore) { throw 'Donnees durables modifiees par le redemarrage ou rejeu' }
 $proof.authority_unchanged_after_restart_replay=$true
 $proof.sessions=$rows;$proof.ha_seconds=5400;$proof.oiii_seconds=900;$proof.profile_unchanged_by_replay=$true;$proof.restart=$true;$proof.result='AUTOMATED_CHECKS_PASS_UI_PENDING'
 Write-Host 'Recharger la page pour vérifier les deux crédits après redémarrage.'
 if ((Read-Host 'Les deux crédits sont-ils conservés après rechargement ? Taper OUI pour exporter') -cne 'OUI') { throw 'Validation visuelle après redémarrage non confirmée' }
 $proof.ui_after_restart_confirmed=$true; $proof.result='PASS'
 if ($env:NIGHTMERIT_KIT_CI -eq '1') { $proof.result='PASS_API_ONLY'; $proof.ui_validation='automated API only'; $proof.ui_before_restart_confirmed=$false; $proof.ui_after_restart_confirmed=$false }
} catch {
 $proof.result='NOT_VALIDATED'; $proof.error=$_.Exception.Message
 Write-Host "REFUS / NON VALIDE : $($_.Exception.Message)"
} finally {
 Stop-Owned
 $export=Join-Path $run 'export';New-Item -ItemType Directory -Force $export | Out-Null
 $proof | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 (Join-Path $export 'qualification.json')
 Get-ChildItem -LiteralPath $run -Filter '*.log' | Copy-Item -Destination $export
 $logs=Join-Path $env:HOME 'AppData/Local/AstroPilot/Logs'
 # Only diagnostic logs from this owned sandbox; never export profiles or keys.
 Get-ChildItem -LiteralPath $run -Recurse -Filter 'AstroPilot.log' | Copy-Item -Destination $export -ErrorAction SilentlyContinue
 $zip=Join-Path $root ('resultats-candidat-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.zip')
 Compress-Archive -Path (Join-Path $export '*') -DestinationPath $zip
 Write-Host "Résultat : $zip"
}
Read-Host 'Entrée pour fermer' | Out-Null
