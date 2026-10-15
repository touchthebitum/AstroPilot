$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$tool=Join-Path $env:GITHUB_WORKSPACE 'operations/tooling/resume'
$case=Join-Path $env:RUNNER_TEMP 'source-fixture/essai-isole-20261015-151443-f27734'
$profilePath=Join-Path $case 'ASTROPILOT_DATA_DIR/user_profile.json'
$original=[IO.File]::ReadAllBytes($profilePath)
$staging=Join-Path $env:RUNNER_TEMP 'resume-native-kit';New-Item -ItemType Directory $staging | Out-Null
Copy-Item (Join-Path $tool 'Reprendre-test.ps1') $staging
Copy-Item (Join-Path $tool 'Inventaire-binaire.json') $staging
$rows=@(Get-ChildItem $staging -File | ForEach-Object { @{path=$_.Name;sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()} })
@{files=$rows} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $staging 'Manifest-reprise.json')
function Read-Host { param([string]$Prompt);$script:answers++;if ($script:answers -eq 1) { return 'je ne sais pas' };return '  oUi  ' }
function Run-Resume([string]$name,[string]$expected) {
 $script:answers=0
 $env:TEMP=Join-Path $env:RUNNER_TEMP 'source-fixture';$env:TMP=$env:TEMP;$env:NIGHTMERIT_RESUME_CI='1'
 $canary=Join-Path $env:RUNNER_TEMP 'resume-guardian-canary.json';'unchanged' | Set-Content $canary
 $canaryHash=(Get-FileHash $canary -Algorithm SHA256).Hash
 $env:ASTROPILOT_GUARDIAN_EXPLICIT_RENEWAL='1';$env:ASTROPILOT_GUARDIAN_ATTESTATION_PATH=$canary
 & (Join-Path $staging 'Reprendre-test.ps1')
 if ((Get-FileHash $canary -Algorithm SHA256).Hash -cne $canaryHash) { throw 'Canary mutated' }
 $zip=Get-ChildItem $staging -Filter 'resultats-reprise-*.zip' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
 $extract=Join-Path $env:RUNNER_TEMP ('proof-'+$name);Expand-Archive -LiteralPath $zip.FullName -DestinationPath $extract
 $proof=Get-Content -Raw -Encoding UTF8 (Join-Path $extract 'reprise.json') | ConvertFrom-Json
 if ($proof.result -cne $expected -or $proof.source_unchanged -ne $true) { throw ($proof | ConvertTo-Json -Depth 10) }
 if ($expected -eq 'PASS_API_ONLY') {
  if ($script:answers -ne 2 -or $proof.ui_confirmed -or -not $proof.authority_unchanged) { throw 'Confirmation tolerance or replay proof failed' }
  $text=(Get-ChildItem $extract -Filter '*.log' | Get-Content) -join "`n"
  if ($text -match '"POST /v1/(executions |execution-transitions|outcome-evidence)') { throw 'Resume created execution or evidence' }
  if ($text -match '"category": "applied"') { throw 'Resume applied a new credit' }
  if (([regex]::Matches($text,'"category": "already_applied"')).Count -ne 6) { throw 'Expected six existing-credit replays' }
 }
 Copy-Item (Join-Path $extract 'reprise.json') (Join-Path $staging ('proof-'+$name+'.json'))
}
# A missing credit must fail before any replay; mutation belongs to this public setup only.
$bad=Get-Content -Raw -Encoding UTF8 $profilePath | ConvertFrom-Json
$bad.intent_progress_credits.PSObject.Properties.Remove('packaged-ui-oiii')
$bad | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $profilePath
Run-Resume 'missing-credit' 'NOT_VALIDATED'
[IO.File]::WriteAllBytes($profilePath,$original)
$occupied=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,8000)
try { $occupied.Start();Run-Resume 'occupied-port' 'NOT_VALIDATED';if (-not $occupied.Server.IsBound) { throw 'Foreign listener was stopped' } } finally { $occupied.Stop() }
Run-Resume 'healthy' 'PASS_API_ONLY'
if ((Get-FileHash $profilePath -Algorithm SHA256).Hash -cne ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($original)).Replace('-',''))) { throw 'Original source profile changed' }
if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) { throw 'Owned server remains' }
'PASS: original preserved; no creations; six already_applied; tolerant confirmation; missing-credit and foreign-port refusals'
