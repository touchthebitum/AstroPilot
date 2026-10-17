$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
function Save-DiagnosticJson($Path,$Value) {
    [IO.File]::WriteAllText($Path,(ConvertTo-Json -InputObject $Value -Depth 10),[Text.UTF8Encoding]::new($false))
}
function Test-RelevantEvent($Event) {
    $provider = [string]$Event.ProviderName
    $message = [string]$Event.Message
    if ($Event.LogName -notin @('System','Application')) { return $true }
    $platformProvider = $provider -match 'Hyper-V|Host.Compute|HostCompute|Containers|Sandbox|Hypervisor'
    $appProvider = $provider -match 'Application Error|Windows Error Reporting|Application Hang|Service Control Manager'
    $appMessage = $message -match 'WindowsSandbox|Windows Sandbox|Bac . sable|vmcompute|vmwp|CmService|Containers|AstroPilot|TestController'
    return ($platformProvider -or ($appProvider -and $appMessage))
}
function Invoke-NightMeritDiagnostic($Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw 'Dossier du collecteur introuvable.' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $id = [Guid]::NewGuid().ToString('N').Substring(0,8)
    $name = "diagnostic-sandbox-$stamp-$id"
    $out = Join-Path $Root 'RESULTATS'
    New-Item -ItemType Directory -Path $out -Force | Out-Null
    $folder = Join-Path $out $name
    New-Item -ItemType Directory -Path $folder | Out-Null
    $errors = [Collections.Generic.List[object]]::new()
    $from = (Get-Date).AddHours(-24)
    $to = Get-Date
    $summary = [ordered]@{schema_version=1;kind='host_sandbox_diagnostic_only';verdict='NOT_A_QUALIFICATION';created_utc=$to.ToUniversalTime().ToString('o');window_start_utc=$from.ToUniversalTime().ToString('o');window_end_utc=$to.ToUniversalTime().ToString('o');product_source_sha='7e98e45b2f46f57dcf959f3bf8d2b1373375cf48';real_profiles_read=$false;settings_changed=$false;sandbox_launched=$false;security_log_read=$false}
    try {
        $osInfo = Get-CimInstance Win32_OperatingSystem
        $computer = Get-CimInstance Win32_ComputerSystem
        $cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,VirtualizationFirmwareEnabled,SecondLevelAddressTranslationExtensions,VMMonitorModeExtensions)
        $summary['system'] = @{caption=$osInfo.Caption;version=$osInfo.Version;build=$osInfo.BuildNumber;total_memory_kib=$osInfo.TotalVisibleMemorySize;free_memory_kib=$osInfo.FreePhysicalMemory;hypervisor_present=$computer.HypervisorPresent;processors=$cpu}
    } catch { $errors.Add(@{stage='system_metadata';message=$_.Exception.Message}) }
    try { $summary['sandbox_executable_present'] = Test-Path (Join-Path $env:WINDIR 'System32\WindowsSandbox.exe') } catch {}
    try { $summary['virtualization_services'] = @(Get-Service -Name vmcompute,vmms,CmService,hns -ErrorAction SilentlyContinue | Select-Object Name,@{Name='status';Expression={$_.Status.ToString()}}) } catch { $errors.Add(@{stage='services_read_only';message=$_.Exception.Message}) }
    try {
        $summary['features'] = @(Get-WindowsOptionalFeature -Online -ErrorAction Stop | Where-Object FeatureName -Match 'Containers-DisposableClientVM|VirtualMachinePlatform|Microsoft-Hyper-V-Hypervisor' | Select-Object FeatureName,@{Name='state';Expression={$_.State.ToString()}})
    } catch { $errors.Add(@{stage='feature_status';message='Etat non accessible sans droits supplementaires ; aucune elevation demandee.'}) }
    $logs = @('System','Application')
    try {
        $available = @(Get-WinEvent -ListLog * -ErrorAction SilentlyContinue | Where-Object { $_.IsEnabled -and $_.LogName -match '^Microsoft-Windows-(Hyper-V-(Compute|Worker|VMMS|Hypervisor)|Host-Compute|HostCompute|Containers|Sandbox)' } | Select-Object -ExpandProperty LogName)
        $logs += $available
    } catch { $errors.Add(@{stage='log_inventory';message=$_.Exception.Message}) }
    $counts = @()
    foreach ($log in ($logs | Select-Object -Unique)) {
        $rows = @()
        try {
            $filter = @{LogName=$log;StartTime=$from;EndTime=$to}
            if ($log -in @('System','Application')) { $filter['Level'] = @(1,2,3) }
            $raw = @(Get-WinEvent -FilterHashtable $filter -MaxEvents 600 -ErrorAction Stop)
            $rows = @($raw | Where-Object { Test-RelevantEvent $_ } | Select-Object -First 150 | ForEach-Object {
                [ordered]@{time_utc=$_.TimeCreated.ToUniversalTime().ToString('o');provider=$_.ProviderName;log=$_.LogName;id=$_.Id;level=$_.Level;record_id=$_.RecordId;message=([string]$_.Message).Substring(0,[Math]::Min(([string]$_.Message).Length,32768))}
            })
        } catch {
            if ($_.FullyQualifiedErrorId -notmatch 'NoMatchingEventsFound') { $errors.Add(@{stage='event_log';log=$log;message=$_.Exception.Message}) }
        }
        $safe = $log -replace '[^a-zA-Z0-9_-]','_'
        Save-DiagnosticJson (Join-Path $folder ($safe+'.json')) @($rows)
        $counts += @{log=$log;events=$rows.Count;max_scanned=600;max_exported=150}
    }
    $summary['logs'] = @($counts)
    $summary['limitations'] = @('Evenements des dernieres 24 heures, nombre borne par journal.','Des journaux peuvent etre absents ou non accessibles.','Les evenements peuvent mentionner des chemins ou identifiants locaux. Aucun profil applicatif ni cache navigateur ne sont lu.','Ce ZIP ne valide pas le test NightMerit et ne demontre pas a lui seul la cause du plantage.')
    Save-DiagnosticJson (Join-Path $folder 'diagnostic.json') $summary
    Save-DiagnosticJson (Join-Path $folder 'collection-errors.json') @($errors)
    $archive = Join-Path $out ($name+'.zip')
    Compress-Archive -LiteralPath $folder -DestinationPath $archive -CompressionLevel Optimal
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText(($archive+'.sha256'),($hash+'  '+[IO.Path]::GetFileName($archive)+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
    Write-Host ''
    Write-Host 'Diagnostic exporte. Aucun test ni installeur n a ete lance.'
    Write-Host ('ZIP a retourner : '+$archive)
    return $archive
}
if ($env:NIGHTMERIT_DIAG_LOAD_ONLY -ne '1') {
    try { $null = Invoke-NightMeritDiagnostic $env:NIGHTMERIT_DIAG_ROOT }
    catch { Write-Host ('Collecte incomplete : '+$_.Exception.Message); exit 1 }
}
