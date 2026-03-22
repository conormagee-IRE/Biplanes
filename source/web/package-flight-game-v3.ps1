$python = "C:/Users/conor/AppData/Local/Programs/Python/Python312/python.exe"

Set-Location -LiteralPath $PSScriptRoot
$source = Join-Path $PSScriptRoot "..\Flight Game 3 V5.py"
$appDir = Join-Path $PSScriptRoot "flight-game-v3"
$entryPoint = Join-Path $appDir "main.py"
$audioSource = Join-Path $PSScriptRoot "..\assets\audio"
$audioDestination = Join-Path $appDir "audio"
$buildDir = Join-Path $appDir "build\web"
$zipPath = Join-Path $appDir "flight-game-v3-upload.zip"

New-Item -ItemType Directory -Path $appDir -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $entryPoint -Force
New-Item -ItemType Directory -Path $audioDestination -Force | Out-Null
if (Test-Path $audioSource) {
    Copy-Item -Path (Join-Path $audioSource "*") -Destination $audioDestination -Recurse -Force
}
& $python -m pip install pygbag --user --upgrade
& $python -m pygbag flight-game-v3

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path (Join-Path $buildDir "*") -DestinationPath $zipPath -Force
Write-Host "Upload package created at: $zipPath"