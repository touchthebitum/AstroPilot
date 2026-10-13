param([switch]$RuntimeCheckOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Manifest-Python.json') -Raw | ConvertFrom-Json
    $runtime = Join-Path $PSScriptRoot 'python-portable-3.13.5'
    if (-not (Test-Path -LiteralPath $runtime -PathType Container)) { throw 'Python portable absent : extrayez tout le kit.' }
    $actual = @(Get-ChildItem -LiteralPath $runtime -Recurse -File)
    $expected = @($manifest.PSObject.Properties)
    if ($actual.Count -ne $expected.Count) { throw 'Inventaire Python portable incorrect.' }
    foreach ($item in $expected) {
        $path = Join-Path $PSScriptRoot $item.Name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Fichier Python absent : $($item.Name)" }
        if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Lien inattendu dans Python portable.' }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $item.Value) { throw "Empreinte Python incorrecte : $($item.Name)" }
    }
    $python = Join-Path $runtime 'python.exe'
    & $python (Join-Path $PSScriptRoot 'verifier-python.py')
    if ($LASTEXITCODE -ne 0) { throw 'Verification Python echouee.' }
    if ($RuntimeCheckOnly) { exit 0 }
    & $python (Join-Path $PSScriptRoot 'test-choix.py')
    if ($LASTEXITCODE -ne 0) { throw 'Test interrompu avant la fin. Conservez le message affiche.' }
} catch {
    Write-Host "Arret : $($_.Exception.Message)"
    exit 1
}
