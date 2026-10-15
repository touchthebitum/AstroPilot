$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$env:NIGHTMERIT_KIT_CI='1'
$script:promptCount=0
# The CI qualifies the launcher and real APIs, never claims browser interaction.
function Start-Process {
 param([string]$FilePath,[string]$WorkingDirectory,[switch]$PassThru,[string]$RedirectStandardOutput,[string]$RedirectStandardError)
 if ($FilePath -like 'http*') { return }
 Microsoft.PowerShell.Management\Start-Process @PSBoundParameters
}
function Read-Host {
 param([string]$Prompt)
 $script:promptCount++
 if ($script:promptCount -eq 1) {
  foreach ($label in @('ha','oiii')) {
   $eid="packaged-ui-$label";$mid="qualification-mission-$label"
   $start=[DateTimeOffset]::UtcNow.AddHours(-1);$end=$start.AddHours(1)
   $body=@{execution_id=$eid;mission_id=$mid;status='in_progress';actual_start=$start.ToString('o');actual_end=$null;actual_duration=$null}
   Invoke-Owned -Method Post -Uri 'http://127.0.0.1:8000/v1/execution-transitions' -Body ($body | ConvertTo-Json) | Out-Null
   $body.status='completed';$body.actual_end=$end.ToString('o');$body.actual_duration=3600
   Invoke-Owned -Method Post -Uri 'http://127.0.0.1:8000/v1/execution-transitions' -Body ($body | ConvertTo-Json) | Out-Null
   $seconds=if ($label -eq 'ha') {1800} else {900}
   $evidence="native-kit-evidence-$label"
   $body=@{evidence_id=$evidence;execution_id=$eid;category='acquisition';observed_at=$end.ToString('o');source='user';usable_integration_duration=$seconds}
   Invoke-Owned -Method Post -Uri 'http://127.0.0.1:8000/v1/outcome-evidence' -Body ($body | ConvertTo-Json) | Out-Null
   $profile=Get-Content -Raw (Join-Path $env:ASTROPILOT_DATA_DIR 'user_profile.json') | ConvertFrom-Json
   $body=@{expected_revision=$profile.profile_revision;evidence_ids=@($evidence);confirm_historical_baseline=($label -eq 'ha')}
   $result=Invoke-Owned -Method Post -Uri "http://127.0.0.1:8000/v1/executions/$eid/intent-progress-credit" -Body ($body | ConvertTo-Json)
   if ($result.status -ne 'applied') { throw 'Native initial credit failed' }
  }
  return 'OUI'
 }
 if ($script:promptCount -eq 2) { return 'OUI' }
 return ''
}
. (Join-Path $env:KIT_TEST_ROOT 'Lancer-qualification.ps1')
$resultFiles=@(Get-ChildItem -LiteralPath $env:KIT_TEST_ROOT -Filter 'resultats-candidat-*.zip')
if ($resultFiles.Count -ne 1) { throw 'Native result archive missing' }
$proofDir=Join-Path $env:RUNNER_TEMP 'kit-proof-export'
Expand-Archive -LiteralPath $resultFiles[0].FullName -DestinationPath $proofDir
$proof=Get-Content -Raw (Join-Path $proofDir 'qualification.json') | ConvertFrom-Json
if ($proof.result -ne 'PASS_API_ONLY' -or $proof.authority_unchanged_after_restart_replay -ne $true -or $proof.runtime.build -cne '0dcde49') { throw ($proof | ConvertTo-Json -Depth 12) }
if ($proof.ui_before_restart_confirmed -or $proof.ui_after_restart_confirmed) { throw 'CI must not claim manual UI confirmation' }
if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) { throw 'Test listener remains active' }
$names=@(Get-ChildItem -LiteralPath $proofDir -Recurse -File | ForEach-Object { $_.Name })
if (@($names | Where-Object { $_ -eq 'user_profile.json' -or $_ -like '*.key' }).Count) { throw 'Profile or key leaked into export' }
Copy-Item -LiteralPath (Join-Path $proofDir 'qualification.json') -Destination (Join-Path $env:KIT_TEST_ROOT 'Native-kit-validation.json')
'PASS: exact main binary, installed kit launcher, restart/replay, durable hashes, logs and shutdown; no UI claimed'
