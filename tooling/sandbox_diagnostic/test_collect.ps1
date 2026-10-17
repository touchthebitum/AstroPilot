$ErrorActionPreference='Stop'
$env:NIGHTMERIT_DIAG_LOAD_ONLY='1'
. (Join-Path $PSScriptRoot 'collect.ps1')
Remove-Item Env:NIGHTMERIT_DIAG_LOAD_ONLY
function Check($Condition,$Message) { if (-not $Condition) { throw $Message } }
Check (Test-RelevantEvent ([pscustomobject]@{LogName='Application';ProviderName='Application Error';Message='WindowsSandbox.exe crash'})) 'Sandbox event excluded'
Check (-not (Test-RelevantEvent ([pscustomobject]@{LogName='Application';ProviderName='Application Error';Message='unrelated-private-program.exe'}))) 'Unrelated event leaked'
Check (Test-RelevantEvent ([pscustomobject]@{LogName='System';ProviderName='Service Control Manager';Message='vmcompute stopped'})) 'Compute service excluded'
Check (-not (Test-RelevantEvent ([pscustomobject]@{LogName='System';ProviderName='Other';Message='unrelated'}))) 'Unrelated system event leaked'
$scriptFile=Join-Path $PSScriptRoot 'collect.ps1'
$tokens=$null;$parseErrors=$null
$null=[System.Management.Automation.Language.Parser]::ParseFile($scriptFile,[ref]$tokens,[ref]$parseErrors)
Check ($parseErrors.Count -eq 0) 'PowerShell parser error'
$root=Join-Path $env:RUNNER_TEMP ('host-diagnostic-test-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$archive=Invoke-NightMeritDiagnostic $root
Check (Test-Path $archive) 'Archive absent'
$dest=Join-Path $root 'verification'
Expand-Archive -LiteralPath $archive -DestinationPath $dest
$report=Get-ChildItem -LiteralPath $dest -Recurse -Filter diagnostic.json | Get-Content -Raw | ConvertFrom-Json
Check ($report.verdict -eq 'NOT_A_QUALIFICATION') 'Diagnostic falsely validates test'
Check (-not $report.settings_changed -and -not $report.sandbox_launched -and -not $report.real_profiles_read -and -not $report.security_log_read) 'Unexpected scope'
Check ((Get-ChildItem -LiteralPath $dest -Recurse -File | Where-Object Name -eq Security.json).Count -eq 0) 'Security log exported'
[pscustomobject]@{result='PASS';powershell_parser=$true;event_filter_cases=4;actual_windows_collection=$true;archive_roundtrip=$true;settings_changed=$false;sandbox_launched=$false;physical_crash_diagnosed=$false} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $root 'test-result.json')
Write-Host ('PROOF='+$root)
