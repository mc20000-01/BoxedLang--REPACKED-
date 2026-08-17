#Requires -Version 5.1
<#
.SYNOPSIS
    Removes everything BoxedLANG's Windows install.ps1 put in place.
    Does not touch your .bx source files or transpiled output.
#>

$ErrorActionPreference = "Continue"

function Write-Section($text) { Write-Host ""; Write-Host "=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text)      { Write-Host "  $text" -ForegroundColor Green }
function Write-Info($text)    { Write-Host "  $text" -ForegroundColor Gray }

$InstallDir = Join-Path $env:LOCALAPPDATA "BoxedLANG"
$BinDir     = Join-Path $InstallDir "bin"

Write-Host ""
Write-Host "BoxedLANG Windows Uninstaller" -ForegroundColor Magenta

Write-Section "Removing BoxedLANG core + IDE from $InstallDir"
if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
    Write-Ok "removed $InstallDir"
} else {
    Write-Info "$InstallDir not found, nothing to remove"
}

Write-Section "Removing from PATH"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $entries = $userPath -split ";" | Where-Object { $_ -ne "" -and $_ -ne $BinDir }
    [Environment]::SetEnvironmentVariable("Path", ($entries -join ";"), "User")
    Write-Ok "removed $BinDir from user PATH"
}

Write-Section "Removing shortcuts"
$StartMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "BoxedLANG"
if (Test-Path $StartMenuDir) {
    Remove-Item -Recurse -Force $StartMenuDir
    Write-Ok "removed Start Menu shortcuts"
}
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "BoxedLANG IDE.lnk"
if (Test-Path $DesktopShortcut) {
    Remove-Item -Force $DesktopShortcut
    Write-Ok "removed Desktop shortcut"
}

Write-Section "Removing .bx file association"
try {
    Remove-Item -Path "HKCU:\Software\Classes\.bx" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKCU:\Software\Classes\BoxedLANG.bxfile" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Ok "removed .bx association"
} catch { }

Write-Section "Removing VS Code / VSCodium extension"
foreach ($extDir in @(
    (Join-Path $env:USERPROFILE ".vscode\extensions\boxedlang-0.0.1"),
    (Join-Path $env:USERPROFILE ".vscode-oss\extensions\boxedlang-0.0.1")
)) {
    if (Test-Path $extDir) {
        Remove-Item -Recurse -Force $extDir
        Write-Ok "removed $extDir"
    }
}

Write-Section "Done"
Write-Host "  BoxedLANG has been uninstalled." -ForegroundColor White
Write-Host "  Your .bx source files and any transpiled output are untouched." -ForegroundColor White
Write-Host ""
