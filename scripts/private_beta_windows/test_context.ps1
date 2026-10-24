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
