$python = "C:/Users/conor/AppData/Local/Programs/Python/Python312/python.exe"

Set-Location -LiteralPath $PSScriptRoot
$source = Join-Path $PSScriptRoot "..\Flight Game 3 V6.py"
$appDir = Join-Path $PSScriptRoot "flight-game-v3"
$destination = Join-Path $appDir "main.py"
$audioSource = Join-Path $PSScriptRoot "..\assets\audio"
$audioDestination = Join-Path $appDir "audio"
$buildDir = Join-Path $appDir "build\web"

New-Item -ItemType Directory -Path $appDir -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $destination -Force
New-Item -ItemType Directory -Path $audioDestination -Force | Out-Null
if (Test-Path $audioSource) {
	Copy-Item -Path (Join-Path $audioSource "*") -Destination $audioDestination -Recurse -Force
}
& $python -m pip install pygbag --user --upgrade
& $python -m pygbag flight-game-v3
& $python (Join-Path $PSScriptRoot "repack-flight-game-v3.py") $appDir $buildDir