$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcDir = Join-Path $projectRoot "src"

Start-Process powershell -Verb RunAs -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$srcDir'; py client.py"
)