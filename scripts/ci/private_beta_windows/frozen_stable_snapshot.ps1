param(
 [Parameter(Mandatory=$true)][string]$CandidateDirectory,
 [Parameter(Mandatory=$true)][string]$FixtureDirectory,
 [Parameter(Mandatory=$true)][string]$WorkDirectory,
 [Parameter(Mandatory=$true)][string]$BuildSha
)
# Run only against a newly created synthetic case. Never select operator data.
$ErrorActionPreference='Stop'
if ($BuildSha -cnotmatch '^[0-9a-f]{40}$') { throw 'Full build SHA required' }
if (Test-Path -LiteralPath $WorkDirectory) { throw 'WorkDirectory must not exist' }
$fixture=Get-Content -LiteralPath (Join-Path $FixtureDirectory 'fixture.json') -Raw | ConvertFrom-Json
if ($fixture.synthetic_only -ne $true -or $fixture.schema -cne 'nightmerit.synthetic_snapshot_fixture.v1') { throw 'Synthetic fixture required' }
New-Item -ItemType Directory -Path $WorkDirectory | Out-Null
$report=[ordered]@{synthetic_only=$true;success=$false;build_sha=$BuildSha;compiled_prepare=$true;backup_factory_mocked=$false}
$lease=$null
function Run-Prepare([string]$sha) {
 $info=[Diagnostics.ProcessStartInfo]::new()
 $info.FileName=Join-Path $WorkDirectory 'candidate\AstroPilot.exe'
 $info.WorkingDirectory=$WorkDirectory
 $info.Arguments='--prepare-stable-beta '+$sha
 $info.UseShellExecute=$false
 $info.CreateNoWindow=$true
 $info.RedirectStandardOutput=$true
 $info.RedirectStandardError=$true
 foreach($key in @($info.EnvironmentVariables.Keys)) {
  if($key -match '^(ASTROPILOT_|NIGHTMERIT_|FIELD_LAB_)') { $info.EnvironmentVariables.Remove($key) }
 }
 foreach($key in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','MPLCONFIGDIR')) {
  $folder=Join-Path $WorkDirectory ('environment\'+$key)
  New-Item -ItemType Directory -Force -Path $folder | Out-Null
  $info.EnvironmentVariables[$key]=$folder
 }
 $info.EnvironmentVariables['ASTROPILOT_DATA_DIR']=Join-Path $WorkDirectory 'stable\profil'
 $process=[Diagnostics.Process]::Start($info)
 try {
  if(-not $process.WaitForExit(120000)) { $process.Kill();throw 'Preparation timed out' }
  $diagnostic=$process.StandardError.ReadToEnd()
  if($process.ExitCode -ne 0) { throw ('Compiled preparation failed: '+$diagnostic) }
  return ($process.StandardOutput.ReadToEnd() | ConvertFrom-Json)
 } finally { $process.Dispose() }
}
function Check-Profile {
 $count=0
 foreach($entry in $fixture.domain_sha256.PSObject.Properties) {
  $path=Join-Path (Join-Path $WorkDirectory 'stable\profil') $entry.Name
  if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) { throw ('Profile changed: '+$entry.Name) }
  $count++
 }
 return $count
}
try {
 Copy-Item -LiteralPath $CandidateDirectory -Destination (Join-Path $WorkDirectory 'candidate') -Recurse
 $oldBuild='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
 if($BuildSha -ceq $oldBuild) { throw 'Target build must differ from synthetic old build' }
 $first=Run-Prepare $oldBuild
 if($first.profile_state -ne 'empty' -or $first.backup_created) { throw 'Initial store was not empty' }
 $stable=Join-Path $WorkDirectory 'stable'
 $profile=Join-Path $stable 'profil'
 New-Item -ItemType Directory -Path $profile | Out-Null
 foreach($entry in $fixture.domain_sha256.PSObject.Properties) {
  $source=Join-Path (Join-Path $FixtureDirectory 'data') $entry.Name
  if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) { throw 'Fixture hash mismatch' }
  $target=Join-Path $profile $entry.Name
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  Copy-Item -LiteralPath $source -Destination $target
 }
 $before=Check-Profile
 $lease=[IO.File]::Open((Join-Path $stable '.nightmerit-session.lock'),[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 $upgrade=Run-Prepare $BuildSha
 if(-not $upgrade.backup_created -or $upgrade.profile_state -ne 'profile') { throw 'Upgrade snapshot missing' }
 $backups=@(Get-ChildItem -LiteralPath (Join-Path $stable 'SAUVEGARDES-AUTO') -Filter '*.zip')
 if($backups.Count -ne 1) { throw 'Expected exactly one update snapshot' }
 $backupHash=(Get-FileHash -LiteralPath $backups[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
 $after=Check-Profile
 $again=Run-Prepare $BuildSha
 if($again.backup_created) { throw 'Same build created a duplicate snapshot' }
 $same=@(Get-ChildItem -LiteralPath (Join-Path $stable 'SAUVEGARDES-AUTO') -Filter '*.zip')
 if($same.Count -ne 1 -or (Get-FileHash -LiteralPath $same[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne $backupHash) { throw 'Snapshot was replaced or duplicated' }
 $marker=Get-Content -LiteralPath (Join-Path $stable 'stockage-beta.json') -Raw | ConvertFrom-Json
 if($marker.last_build -cne $BuildSha) { throw 'Build marker did not advance' }
 $report.success=$true
 $report['domain_documents_identical']=$after
 $report['profile_unchanged']=($before -eq $after)
 $report['snapshot_relative_path']=$backups[0].FullName.Substring($WorkDirectory.Length+1)
 $report['snapshot_sha256']=$backupHash
 $report['same_build_no_duplicate']=$true
 $report['parent_lease_held']=$true
 $report['expected_summary']=$fixture.summary
 $report['marker']=$marker
} catch {
 $report['error']=$_.Exception.Message
 $report['position']=$_.InvocationInfo.PositionMessage
 throw
} finally {
 if($null -ne $lease) { $lease.Dispose() }
 [IO.File]::WriteAllText((Join-Path $WorkDirectory 'proof.json'),($report|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
}
