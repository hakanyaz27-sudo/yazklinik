[CmdletBinding()]
param(
    [switch]$SkipNodeInstall
)

$ErrorActionPreference = 'Stop'

$baseUrl = 'https://192.168.1.50:5443'
$nodeCmd = (Get-Command node -ErrorAction SilentlyContinue)
$wingetCmd = (Get-Command winget -ErrorAction SilentlyContinue)

Write-Host "=== WebUI Araç Kurulum Seti ===" -ForegroundColor Cyan

if (-not $wingetCmd) {
    Write-Host "winget bulunamadi. Lutfen Windows 10+ App Installer kurulu oldugundan emin olun." -ForegroundColor Yellow
} else {
    Write-Host "=== 1) Figma ve Postman kurulumu ==="
    winget install --id Figma.Figma --accept-package-agreements --accept-source-agreements
    winget install --id Postman.Postman --accept-package-agreements --accept-source-agreements
    Write-Host "Not: Insomnia, Photoshop tabanli degilse winget paketini desteklemeyebilir. Alternatif link README'de." -ForegroundColor Yellow
}

if (-not $SkipNodeInstall) {
    if (-not $nodeCmd) {
        Write-Host "Node.js bulunamadi. Siteye gore (https://nodejs.org) kurmaniz gerekebilir." -ForegroundColor Yellow
    } else {
        Write-Host "=== 2) Playwright + Lighthouse paketleri ==="
        Set-Location $PSScriptRoot
        if (-not (Test-Path (Join-Path $PSScriptRoot 'package.json'))) {
            npm init -y | Out-Null
        }
        npm install -D @playwright/test playwright lighthouse
        npx playwright install chromium
    }
}

Write-Host "=== 4) Lighthouse + route smoke komutlari hazir ==="
if (Test-Path (Join-Path $PSScriptRoot 'package.json')) {
    $pkg = Get-Content (Join-Path $PSScriptRoot 'package.json') -Raw | ConvertFrom-Json
    $pkg.scripts.pw = "node ./playwright_smoke.mjs"
    $pkg.scripts.lighthouse_login = "npx lighthouse $baseUrl/giris --output html --output-path .\\lighthouse-giris.html --chrome-flags=--ignore-certificate-errors"
    $pkg.scripts.lighthouse_dashboard = "npx lighthouse $baseUrl/ --output html --output-path .\\lighthouse-dashboard.html --chrome-flags=--ignore-certificate-errors"
    $pkg | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'package.json')
}

Write-Host "=== 5) WAVE + Axe ve extension yollari ==="
Start-Process "https://wave.webaim.org/extension"
Start-Process "https://www.deque.com/axe/devtools/extension/chrome"

Write-Host "Hazir. Kalan adim: Insomnia indir (README'deki link)."
Write-Host "WAVE/Axe = browser eklentisi icin elle kurulum yapin."
Write-Host "Playwright smoke test: npm run pw"
Write-Host "Lighthouse: npm run lighthouse_login && npm run lighthouse_dashboard"
