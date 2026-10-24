$ErrorActionPreference = 'Stop'
$expected = '__SOURCE_SHA__'
function Read-KitContext([string]$encoded, [string]$sourceSha) {
 if (-not $encoded -or $encoded.Length -gt 5000) { throw 'Contexte du lanceur absent ou trop long.' }
 $json = ([Text.UTF8Encoding]::new($false,$true)).GetString([Convert]::FromBase64String($encoded))
 $value = $json | ConvertFrom-Json
 if ($value.schema -cne 'nightmerit.private_copy_context.v1' -or $value.source_sha -cne $sourceSha -or $sourceSha -cnotmatch '^[0-9a-f]{40}$') { throw 'Contexte du lanceur incompatible.' }
 foreach ($name in @('host_kit_directory','host_results_directory','guest_data_directory')) {
  $path = $value.$name
  if ($path -isnot [string] -or -not $path -or $path.Length -gt 2048 -or $path -match '[\x00-\x1f]' -or -not [IO.Path]::IsPathRooted($path) -or $path -match '(^|[\\/])\.\.([\\/]|$)') { throw 'Chemin de contexte invalide.' }
  if ([IO.Path]::GetFullPath($path).TrimEnd('\') -ine $path.TrimEnd('\')) { throw 'Chemin de contexte non absolu.' }
 }
 if ($value.host_results_directory.TrimEnd('\') -ine (Join-Path $value.host_kit_directory 'RESULTATS').TrimEnd('\') -or $value.guest_data_directory -ine 'C:\NightMeritResults\profil') { throw 'Correspondance de contexte invalide.' }
 return ($value | ConvertTo-Json -Compress)
}
$inputRoot = 'C:\NightMeritInput'
$workRoot = 'C:\NightMeritWork'
$results = 'C:\NightMeritResults'
$appProcess = $null
$browserProcess = $null
$lock = $null
$run = [ordered]@{ source_sha=$expected; started_utc=[DateTime]::UtcNow.ToString('o'); status='starting'; restarts=0; sandbox=$true; software_rendering=$true; native_physical_validation='pending_operator'; usual_profile_used=$false; weather='real'; profile_initial_state='empty_or_resumed_from_this_kit_only' }
function Write-Run {
 [IO.File]::WriteAllText((Join-Path $results 'dernier-test.json'), ($run | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
}
function Stop-Owned($process) {
 if ($null -ne $process -and -not $process.HasExited) {
  # Stop only the process object launched here and its own children.
  & "$env:WINDIR\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null
  $process.WaitForExit(15000) | Out-Null
  if (-not $process.HasExited) { throw 'Un processus de cette copie ne s est pas arrete.' }
 }
}
function Stop-Copy {
 Stop-Owned $script:browserProcess
 Stop-Owned $script:appProcess
 $script:browserProcess = $null; $script:appProcess = $null
}
function Start-Copy {
 $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
 if ($listener.Count) { throw 'Le port 8000 est occupe dans Sandbox. Aucun processus existant ne sera arrete.' }
 $start = [Diagnostics.ProcessStartInfo]::new()
 $start.FileName = Join-Path $workRoot 'candidate\AstroPilot.exe'
 $start.WorkingDirectory = $workRoot
 $start.UseShellExecute = $false
 foreach ($key in @($start.EnvironmentVariables.Keys)) {
  if ($key -match '^(ASTROPILOT_|NIGHTMERIT_|FIELD_LAB_)' -or $key -in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','SSL_CERT_FILE','SSL_CERT_DIR')) { $start.EnvironmentVariables.Remove($key) }
 }
 foreach ($key in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','MPLCONFIGDIR')) {
  $folder = Join-Path $workRoot ('environment\'+$key)
  New-Item -ItemType Directory -Force -Path $folder | Out-Null
  $start.EnvironmentVariables[$key] = $folder
 }
 $start.EnvironmentVariables['ASTROPILOT_DATA_DIR'] = Join-Path $results 'profil'
 # Display-only metadata. It never selects the application or data locations.
 if ($script:copyContext) { $start.EnvironmentVariables['NIGHTMERIT_PRIVATE_COPY_CONTEXT'] = $script:copyContext }
 $start.EnvironmentVariables['BROWSER'] = 'C:\Windows\System32\cmd.exe /c C:\NightMeritWork\no-browser.cmd %s'
 $script:appProcess = [Diagnostics.Process]::Start($start)
 $ready = $false
 $http = [Net.WebClient]::new(); $http.Proxy = $null
 try {
  for ($i=0; $i -lt 120; $i++) {
   if ($script:appProcess.HasExited) { throw 'NightMerit s est arrete au lancement.' }
   try { $identity = $http.DownloadString('http://127.0.0.1:8000/v1/runtime-identity') | ConvertFrom-Json } catch { Start-Sleep -Milliseconds 500; continue }
   if ($identity.application -ne 'astropilot' -or $identity.build -cne $expected.Substring(0,7) -or $identity.version -ne '1.0.0b8' -or $identity.architecture -ne 'x86_64') { throw 'Identite de NightMerit incorrecte.' }
   $owners = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique)
   if ($owners.Count -ne 1) { throw 'Proprietaire du serveur ambigu.' }
   $owner = [int]$owners[0]; $owned = $false
   for ($n=0; $n -lt 8 -and $owner -gt 0; $n++) {
    if ($owner -eq $script:appProcess.Id) { $owned=$true; break }
    $item = Get-CimInstance Win32_Process -Filter "ProcessId=$owner"
    if (-not $item) { break }; $owner=[int]$item.ParentProcessId
   }
   if (-not $owned) { throw 'Le serveur ne fait pas partie de cette copie.' }
   $run.runtime_identity=$identity; $ready=$true; break
  }
 } finally {
  $run.stage='dispose_runtime_http_client'; Write-Run
  $http.Dispose()
 }
 if (-not $ready) { throw 'Le demarrage de NightMerit a depasse le delai prevu.' }
 $run.stage='launch_browser'; Write-Run
 $chrome = Join-Path $workRoot 'browser\chrome.exe'
 $arguments = @('--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-gpu',('--user-data-dir='+$workRoot+'\navigateur'),'http://127.0.0.1:8000/')
 $script:browserProcess = Start-Process -FilePath $chrome -ArgumentList $arguments -WorkingDirectory $workRoot -PassThru
 $run.stage='browser_started'; $run.status='running'; Write-Run
}
try {
 if (-not (Test-Path 'C:\NightMeritResults' -PathType Container) -or -not (Test-Path 'C:\NightMeritInput\manifest.json' -PathType Leaf)) { throw 'Ouvrir ce test uniquement avec LANCER-TEST-WINDOWS.cmd, dans Windows Sandbox.' }
 $lock = [IO.File]::Open((Join-Path $results 'test.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
 $manifest = Get-Content -LiteralPath (Join-Path $inputRoot 'manifest.json') -Raw | ConvertFrom-Json
 if ($manifest.source_sha -cne $expected) { throw 'Mauvaise version du kit.' }
 foreach ($entry in $manifest.files.PSObject.Properties) {
  $relative = $entry.Name
  if ($relative.Contains('..') -or [IO.Path]::IsPathRooted($relative) -or $relative.Contains(':')) { throw 'Chemin de kit invalide.' }
  $file = Join-Path $inputRoot $relative
  if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value.sha256) { throw ('Fichier de test modifie : '+$relative) }
 }
 # Context absence never prevents resuming a valid existing profile. Tell the UI
 # explicitly that identification failed instead of retaining an inherited path.
 $script:copyContext = '{"schema":"unavailable"}'
 try { $script:copyContext = Read-KitContext $env:NIGHTMERIT_KIT_CONTEXT_B64 $expected } catch { Write-Host 'Emplacement du kit sur le PC non disponible. Les donnees utilisees restent celles de RESULTATS.' -ForegroundColor Yellow }
 $profile = Join-Path $results 'profil'
 if (Test-Path -LiteralPath $profile) {
  if ((Get-Item -LiteralPath $profile).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Profil lie refuse.' }
 } else { New-Item -ItemType Directory -Path $profile | Out-Null }
 $marker=Join-Path $results 'profil-source.txt'
 if (Test-Path $marker) { if ((Get-Content $marker -Raw).Trim() -cne $expected) { throw 'Ce dossier de donnees appartient a un autre kit.' } }
 elseif (@(Get-ChildItem -LiteralPath $profile -Force).Count) { throw 'Profil non vide sans provenance : aucun import automatique.' }
 else { [IO.File]::WriteAllText($marker,$expected) }
 if (Test-Path -LiteralPath $workRoot) { throw 'Cette instance Sandbox contient deja une copie. Fermez Sandbox puis relancez le kit.' }
 New-Item -ItemType Directory -Path $workRoot | Out-Null
 Copy-Item -LiteralPath (Join-Path $inputRoot 'candidate') -Destination $workRoot -Recurse
 Copy-Item -LiteralPath (Join-Path $inputRoot 'browser') -Destination $workRoot -Recurse
 [IO.File]::WriteAllText((Join-Path $workRoot 'no-browser.cmd'), "@exit /b 0`r`n")
 Write-Run; Start-Copy
 $run.stage='interactive_console'; Write-Run
 Write-Host 'TEST PRIVE NightMerit - profil separe - meteo reelle' -ForegroundColor Cyan
 Write-Host 'Gardez cette fenetre ouverte pendant votre essai.'
 do {
  Write-Host ''
  Write-Host 'R : redemarrer NightMerit et verifier que vos saisies sont conservees'
  Write-Host 'T : terminer et exporter les resultats'
  $run.stage='read_operator_choice'; Write-Run
  $answer = Read-Host 'Votre choix'
  if ($null -eq $answer) { throw 'La console ne recoit pas les saisies. Fermez Sandbox puis utilisez le lanceur corrige.' }
  $choice = $answer.Trim().ToUpperInvariant()
  if ($choice -eq 'R') { Stop-Copy; $run.restarts++; Start-Copy }
 } while ($choice -ne 'T')
 Stop-Copy
 $run.status='stopped'; $run.completed_utc=[DateTime]::UtcNow.ToString('o'); Write-Run
 $export = Join-Path $results ('resultats-kit-__SOURCE_SHORT__-windows-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,6)+'.zip')
 # Export the operator report only; the retained profile stays local in RESULTATS.
 Compress-Archive -LiteralPath (Join-Path $results 'dernier-test.json'),(Join-Path $inputRoot 'LIRE-MOI.txt') -DestinationPath $export -ErrorAction Stop
 Write-Host ('Resultats exportes : '+$export) -ForegroundColor Green
 Write-Host 'Le profil reste dans RESULTATS\profil. Ne le supprimez pas.'
} catch {
 $run.status='error'; $run.error=$_.Exception.Message
 $run.error_line=$_.InvocationInfo.ScriptLineNumber
 $run.error_position=$_.InvocationInfo.PositionMessage
 $run.error_stack=$_.ScriptStackTrace
 if (Test-Path $results) { try { Write-Run } catch {} }
 Write-Host ('ARRET : '+$_.Exception.Message) -ForegroundColor Red
} finally {
 try { Stop-Copy } catch { Write-Host $_.Exception.Message -ForegroundColor Red }
 if ($null -ne $lock) { $lock.Dispose() }
 Read-Host 'Appuyez sur Entree pour fermer cette fenetre' | Out-Null
}
