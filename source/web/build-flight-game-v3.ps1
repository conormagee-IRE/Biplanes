$python = "C:/Users/conor/AppData/Local/Programs/Python/Python312/python.exe"

Set-Location -LiteralPath $PSScriptRoot
$source = Join-Path $PSScriptRoot "..\Flight Game 3 V3.py"
$destination = Join-Path $PSScriptRoot "flight-game-v3\main.py"

Copy-Item -LiteralPath $source -Destination $destination -Force
& $python -m pip install pygbag --user --upgrade
& $python -m pygbag flight-game-v3