# Native PowerShell 5.1 test. Parse reviewed scripts; invoke only pure context functions.
$ErrorActionPreference='Stop'
foreach ($entry in @(@('launch-sandbox.ps1','New-KitContext'),@('controller.ps1','Read-KitContext'))) {
 $file=Join-Path $PSScriptRoot $entry[0]
 $tokens=$null; $errors=$null
 $ast=[Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors)
 if ($errors.Count) { throw ('PowerShell parse failed: '+($errors | Out-String)) }
 $name=$entry[1]
 $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
 if (-not $definition) { throw 'Context function missing' }
 . ([ScriptBlock]::Create($definition.Extent.Text))
}
function Check($condition,$message) { if (-not $condition) { throw $message } }
function Reject([scriptblock]$action) {
 $rejected=$false
 try { & $action | Out-Null } catch { $rejected=$true }
 Check $rejected 'Invalid launcher context was accepted'
}
$sha='abcdef0'+('1'*33)
$personal="C:\Tests été & ' famille\Copie personnelle\Kit"
$blank="C:\Tests été & ' famille\Copie vierge\Kit"
$first=New-KitContext $personal $sha
$second=New-KitContext $blank $sha
Check ($first -match '^[A-Za-z0-9+/=]+$') 'Context argument must contain Base64 data only'
$a=(Read-KitContext $first $sha) | ConvertFrom-Json
$b=(Read-KitContext $second $sha) | ConvertFrom-Json
Check ($a.host_kit_directory -ceq $personal) 'Unicode host path did not survive roundtrip'
Check ($a.host_kit_directory -cne $b.host_kit_directory) 'Two host copies became indistinguishable'
Check ($a.host_results_directory -ceq ($personal+'\RESULTATS')) 'Host results mapping changed'
Check ($a.guest_data_directory -ceq $b.guest_data_directory) 'The guest profile path must remain unchanged'
Reject { Read-KitContext $first ('b'*40) }
Reject { Read-KitContext 'not base64' $sha }
Reject { Read-KitContext '' $sha }
Reject { New-KitContext $personal 'bad' }
$a.host_results_directory='C:\other\RESULTATS'
$bad=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($a | ConvertTo-Json -Compress)))
Reject { Read-KitContext $bad $sha }
$a.host_results_directory=$personal+'\RESULTATS';$a.guest_data_directory='C:\other\profil'
$bad=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($a | ConvertTo-Json -Compress)))
Reject { Read-KitContext $bad $sha }
# The native scripts have only two mappings: input read-only and results writable.
$hostText=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'launch-sandbox.ps1'))
Check ($hostText.Contains('<vGPU>Disable</vGPU>')) 'vGPU changed'
Check ($hostText.Contains('<ReadOnly>true</ReadOnly>') -and $hostText.Contains('<ReadOnly>false</ReadOnly>')) 'Mappings changed'
Check (-not $hostText.Contains('ExecutionPolicy')) 'Execution policy must not change'
Write-Host 'PASS: same-build host copies remain distinct; Unicode and shell metacharacters roundtrip as data; stale and inconsistent contexts rejected; no launch, profile IO or Sandbox execution.'

# Exercise the real CMD argument/environment prefix as well as the decoder.
# Pure PowerShell roundtrips cannot detect CMD splitting unquoted '=' padding.
$transportRoot=Join-Path ([IO.Path]::GetTempPath()) ('nightmerit-cmd-context-'+[Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($transportRoot) | Out-Null
try {
 $transportFile=Join-Path $transportRoot 'transport with spaces.cmd'
 $reader='$ErrorActionPreference="Stop";[IO.File]::WriteAllText($env:NIGHTMERIT_TRANSPORT_OUTPUT,$env:NIGHTMERIT_KIT_CONTEXT_B64,[Text.UTF8Encoding]::new($false))'
 $reader64=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($reader))
 $prefix=([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'sandbox-start.cmd')) -split '\r?\n')[0..1] -join "`r`n"
 [IO.File]::WriteAllText($transportFile,($prefix+"`r`npowershell.exe -NoProfile -EncodedCommand "+$reader64+"`r`n"),[Text.Encoding]::ASCII)
 function Invoke-ContextTransport([string]$argument) {
  $output=Join-Path $transportRoot ([Guid]::NewGuid().ToString('N')+'.txt')
  $info=[Diagnostics.ProcessStartInfo]::new()
  $info.FileName=Join-Path $env:WINDIR 'System32\cmd.exe'
  $info.Arguments='/d /s /c ""'+$transportFile+'" '+$argument+'"'
  $info.UseShellExecute=$false;$info.CreateNoWindow=$true
  $info.EnvironmentVariables['NIGHTMERIT_TRANSPORT_OUTPUT']=$output
  $process=[Diagnostics.Process]::Start($info)
  try {
   if (-not $process.WaitForExit(15000)) {
    & "$env:WINDIR\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null
    throw 'CMD transport test timeout'
   }
   Check ($process.ExitCode -eq 0) 'CMD transport test failed'
   return [IO.File]::ReadAllText($output,[Text.Encoding]::UTF8)
  } finally { $process.Dispose() }
 }
 $paddings=[Collections.Generic.HashSet[int]]::new()
 $originalFailures=0
 foreach ($suffix in @('','X','XX')) {
  $encoded=New-KitContext ($personal+$suffix+'\') $sha
  $padding=0;if($encoded.EndsWith('==')){$padding=2}elseif($encoded.EndsWith('=')){$padding=1}
  $paddings.Add($padding) | Out-Null
  $old=Invoke-ContextTransport $encoded
  if($old -cne $encoded){$originalFailures++}
  $fixed=Invoke-ContextTransport ('"'+$encoded+'"')
  Check ($fixed -ceq $encoded) 'Quoted context changed across the CMD boundary'
  $roundtrip=(Read-KitContext $fixed $sha) | ConvertFrom-Json
  Check ($roundtrip.host_kit_directory.TrimEnd('\') -ceq ($personal+$suffix)) 'CMD context did not preserve the host path'
  Write-Host ('CMD padding '+$padding+': original exact='+($old -ceq $encoded)+'; quoted exact=True')
 }
 # The mode is a separate fixed argument, never decoded from host context.
 $modeReader='$ErrorActionPreference="Stop";[IO.File]::WriteAllText($env:NIGHTMERIT_TRANSPORT_OUTPUT,$env:NIGHTMERIT_OPEN_DATA_TRANSFER,[Text.UTF8Encoding]::new($false))'
 $mode64=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($modeReader))
 $modePrefix=([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'sandbox-start.cmd')) -split '\r?\n')[0..3] -join "`r`n"
 [IO.File]::WriteAllText($transportFile,($modePrefix+"`r`npowershell.exe -NoProfile -EncodedCommand "+$mode64+"`r`n"),[Text.Encoding]::ASCII)
 Check ((Invoke-ContextTransport ('"'+$encoded+'" "1"')) -ceq '1') 'Assistant mode did not cross CMD boundary'
 Check ((Invoke-ContextTransport ('"'+$encoded+'" "0"')) -ceq '0') 'Normal mode did not reset assistant flag'
 Check ((Invoke-ContextTransport ('"'+$encoded+'"')) -ceq '0') 'Missing mode must keep ordinary startup'
 Check ($paddings.Count -eq 3) 'Missing CMD padding case'
 Check ($hostText.Contains('sandbox-start.cmd "$copyContext" "$transferMode"</Command>')) 'The real Sandbox startup must quote the data argument and pass the separate fixed mode'
 Write-Host ('PASS: real CMD to PowerShell context transport; all three Base64 padding cases; original transport mismatches='+$originalFailures)
} finally {
 if(Test-Path -LiteralPath $transportRoot){Remove-Item -LiteralPath $transportRoot -Recurse -Force}
}
