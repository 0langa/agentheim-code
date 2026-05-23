# Release automation for Agentheim Code
# Usage: powershell -ExecutionPolicy Bypass -File scripts/release.ps1 -Version 1.0.0
param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root "apps\web"
$desktop = Join-Path $root "apps\desktop"
$dist = Join-Path $root "dist"
$nsis = Join-Path $desktop "src-tauri\target\release\bundle\nsis"

Write-Step "Building web assets"
& npm --prefix $web run build
if ($LASTEXITCODE -ne 0) { throw "Web build failed" }

Write-Step "Cleaning old release artifacts"
if (Test-Path $dist) {
    Remove-Item -LiteralPath $dist -Recurse -Force
}
New-Item -ItemType Directory -Path $dist -Force | Out-Null

Write-Step "Building desktop installer"
& npm --prefix $desktop run build
if ($LASTEXITCODE -ne 0) { throw "Desktop build failed" }

Write-Step "Building Python wheel"
& python -m pip install --upgrade build
& python -m build --wheel $root
if ($LASTEXITCODE -ne 0) { throw "Wheel build failed" }

Write-Step "Generating checksums"
$wheel = Get-ChildItem "$dist\agentheim_code-$Version-*.whl" | Select-Object -First 1
$installer = Get-ChildItem "$nsis\*$Version*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $wheel) {
    throw "No wheel found for version $Version"
}
if (-not $installer) {
    throw "No NSIS installer found for version $Version"
}

$installerCopy = Join-Path $dist $installer.Name
Copy-Item -LiteralPath $installer.FullName -Destination $installerCopy -Force
$installer = Get-Item $installerCopy

$checksums = @()
if ($wheel) {
    $wh = Get-FileHash $wheel -Algorithm SHA256
    $checksums += "$($wh.Hash)  $($wheel.Name)"
}
if ($installer) {
    $ih = Get-FileHash $installer -Algorithm SHA256
    $checksums += "$($ih.Hash)  $($installer.Name)"
}

$checksumPath = Join-Path $dist "checksums-sha256.txt"
$checksums | Out-File -FilePath $checksumPath -Encoding utf8

Write-Step "Generating release notes"
$notes = @(
    "# Agentheim Code $Version",
    "",
    "## Artifacts",
    "- Wheel: $($wheel.Name)",
    "- Windows Installer: $($installer.Name)",
    "- SHA256: checksums-sha256.txt",
    "",
    "## Install",
    '```powershell',
    "pip install `"$($wheel.Name)`"",
    "# Or run the Windows installer",
    '```'
) -join [Environment]::NewLine
$notesPath = Join-Path $dist "RELEASE_NOTES.md"
$notes | Out-File -FilePath $notesPath -Encoding utf8

Write-Host "`nRelease $Version prepared in $dist" -ForegroundColor Green
Write-Host "Wheel:     $wheel"
Write-Host "Installer: $installer"
Write-Host "Checksums: $checksumPath"
Write-Host "Notes:     $notesPath"
