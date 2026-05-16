$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

& (Join-Path $Root "YazKlinik_WebShell_Windows.bat")

Write-Host "Windows terminal web surumle WebShell uzerinden eslendi."
