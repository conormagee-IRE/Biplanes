$python = "C:/Users/conor/AppData/Local/Programs/Python/Python312/python.exe"

Set-Location -LiteralPath $PSScriptRoot
$source = Join-Path $PSScriptRoot "..\Flight Game 3 V3.py"
$appDir = Join-Path $PSScriptRoot "flight-game-v3"
$entryPoint = Join-Path $appDir "main.py"
$buildDir = Join-Path $appDir "build\web"
$zipPath = Join-Path $appDir "flight-game-v3-upload.zip"

Copy-Item -LiteralPath $source -Destination $entryPoint -Force
& $python -m pip install pygbag --user --upgrade
& $python -m pygbag flight-game-v3

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path (Join-Path $buildDir "*") -DestinationPath $zipPath -Force
Write-Host "Upload package created at: $zipPath"