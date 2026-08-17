#Requires -Version 5.1
<#
.SYNOPSIS
    BoxedLANG installer for Windows.

.DESCRIPTION
    Installs the BoxedLANG toolkit (bx.py, bxastgen.py, bxrunner.py,
    transpilebx.py, bxdebug.py) AND the BoxedLANG IDE (IDE.py) to a
    per-user location, creates `bx` / `transpilebx` / `bxdebug`
    launchers on PATH, creates a Start Menu (and optional Desktop)
    shortcut for the IDE, associates .bx files with the IDE, and
    installs the VS Code extension if VS Code / VSCodium is detected.

    Run this script from the folder that contains bx.py etc.
    (the same folder this script's "windows" directory sits next to),
    e.g. by double-clicking install.bat.

.NOTES
    No admin rights required - everything installs under the current
    user's %LOCALAPPDATA%.
#>

[CmdletBinding()]
param(
    [switch]$NoDesktopShortcut,
    [switch]$NoPathUpdate
)

$ErrorActionPreference = "Stop"

function Write-Section($text) {
    Write-Host ""
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

function Write-Ok($text)   { Write-Host "  $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  $text" -ForegroundColor Yellow }
function Write-Info($text) { Write-Host "  $text" -ForegroundColor Gray }

# ---------------------------------------------------------------------------
# Locate source files: this script lives in <repo>\windows\install.ps1,
# so the source files are one level up.
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcDir    = Split-Path -Parent $ScriptDir

$InstallDir = Join-Path $env:LOCALAPPDATA "BoxedLANG"
$BinDir     = Join-Path $InstallDir "bin"
$CoreFiles  = @("bx.py", "bxastgen.py", "bxrunner.py", "transpilebx.py", "bxdebug.py", "IDE.py")

Write-Host ""
Write-Host "BoxedLANG Windows Installer" -ForegroundColor Magenta
Write-Host "Installing to: $InstallDir"

# ---------------------------------------------------------------------------
# 1. Find Python (must have tkinter for the IDE / bxdebug)
# ---------------------------------------------------------------------------
Write-Section "Locating Python"

function Get-PythonCommand {
    $candidates = @(
        @{ Cmd = "py";     Args = "-3" },
        @{ Cmd = "python";  Args = "" },
        @{ Cmd = "python3"; Args = "" }
    )
    foreach ($c in $candidates) {
        try {
            $verArgs = @()
            if ($c.Args) { $verArgs += $c.Args }
            $verArgs += "--version"
            $out = & $c.Cmd @verArgs 2>&1
            if ($LASTEXITCODE -eq 0 -and $out -match "Python 3") {
                return $c
            }
        } catch { continue }
    }
    return $null
}

$PyCmd = Get-PythonCommand

if (-not $PyCmd) {
    Write-Warn "Python 3 was not found on PATH."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        $answer = Read-Host "  Install Python 3 now via winget? [Y/n]"
        if ($answer -eq "" -or $answer -match "^[Yy]") {
            winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
            $PyCmd = Get-PythonCommand
        }
    }
    if (-not $PyCmd) {
        Write-Warn "Please install Python 3 from https://python.org/downloads (check 'Add python.exe to PATH')"
        Write-Warn "then re-run this installer. Aborting."
        exit 1
    }
}

$PyLauncher  = $PyCmd.Cmd
$PyExtraArgs = $PyCmd.Args
Write-Ok "Using '$PyLauncher $PyExtraArgs' as the Python interpreter."

# Resolve the actual pythonw.exe (windowless) next to the interpreter, for the IDE shortcut.
$PyExe = $null
try {
    if ($PyLauncher -eq "py") {
        $verboseArgs = @()
        if ($PyExtraArgs) { $verboseArgs += $PyExtraArgs }
        $verboseArgs += @("-c", "import sys; print(sys.executable)")
        $PyExe = (& $PyLauncher @verboseArgs).Trim()
    } else {
        $PyExe = (Get-Command $PyLauncher).Source
    }
} catch { $PyExe = $null }

$PywExe = $null
if ($PyExe) {
    $candidate = Join-Path (Split-Path $PyExe) "pythonw.exe"
    if (Test-Path $candidate) { $PywExe = $candidate }
}
if (-not $PywExe) { $PywExe = $PyExe }   # fall back to console python if pythonw missing

# Check tkinter is available (needed by IDE.py and bxdebug.py)
$tkCheckArgs = @()
if ($PyExtraArgs) { $tkCheckArgs += $PyExtraArgs }
$tkCheckArgs += @("-c", "import tkinter")
& $PyLauncher @tkCheckArgs 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "tkinter is not available in this Python install."
    Write-Warn "The IDE and 'bxdebug' need it. Reinstall Python from python.org"
    Write-Warn "with the default options (tkinter is included by default)."
}

# ---------------------------------------------------------------------------
# 2. Copy core files + IDE
# ---------------------------------------------------------------------------
Write-Section "Installing BoxedLANG core + IDE to $InstallDir"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

foreach ($f in $CoreFiles) {
    $src = Join-Path $SrcDir $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $InstallDir -Force
        Write-Ok "installed $f"
    } else {
        Write-Warn "$f not found in $SrcDir, skipping"
    }
}

$ApisSrc = Join-Path $SrcDir "apis"
if (Test-Path $ApisSrc) {
    Copy-Item -Path $ApisSrc -Destination $InstallDir -Recurse -Force
    Write-Ok "installed apis\"
}

# ---------------------------------------------------------------------------
# 3. Create CLI launchers on PATH
# ---------------------------------------------------------------------------
Write-Section "Creating launchers in $BinDir"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

function New-Launcher($name, $target) {
    $cmdPath = Join-Path $BinDir "$name.cmd"
    $extra = if ($PyExtraArgs) { "$PyExtraArgs " } else { "" }
    @"
@echo off
"$PyLauncher" $extra"$InstallDir\$target" %*
"@ | Set-Content -Path $cmdPath -Encoding ASCII
    Write-Ok "$name.cmd -> $target"
}

New-Launcher "bx"          "bx.py"
New-Launcher "transpilebx" "transpilebx.py"
New-Launcher "bxdebug"     "bxdebug.py"

# Windowless launcher for the IDE (double-click friendly, no console flash)
$IdeCmd = Join-Path $BinDir "boxedlang-ide.cmd"
@"
@echo off
start "" "$PywExe" "$InstallDir\IDE.py" %*
"@ | Set-Content -Path $IdeCmd -Encoding ASCII
Write-Ok "boxedlang-ide.cmd -> IDE.py"

# ---------------------------------------------------------------------------
# 4. Add BinDir to the user's PATH
# ---------------------------------------------------------------------------
Write-Section "Checking PATH"
if ($NoPathUpdate) {
    Write-Info "Skipped (-NoPathUpdate)."
} else {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($null -eq $userPath) { $userPath = "" }
    $pathEntries = $userPath -split ";" | Where-Object { $_ -ne "" }
    if ($pathEntries -contains $BinDir) {
        Write-Ok "$BinDir is already on PATH."
    } else {
        $newPath = if ($userPath.TrimEnd(";") -eq "") { $BinDir } else { "$userPath;$BinDir" }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        # also update this session so `bx` etc. work immediately in this window
        $env:Path = "$env:Path;$BinDir"
        Write-Ok "added $BinDir to your user PATH"
        Write-Info "Open a NEW terminal window for 'bx' / 'transpilebx' / 'bxdebug' to be found."
    }
}

# ---------------------------------------------------------------------------
# 5. Start Menu + Desktop shortcuts for the IDE
# ---------------------------------------------------------------------------
Write-Section "Creating shortcuts"

$WshShell   = New-Object -ComObject WScript.Shell
$StartMenu  = [Environment]::GetFolderPath("Programs")   # per-user Start Menu\Programs
$StartMenuDir = Join-Path $StartMenu "BoxedLANG"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null

function New-Shortcut($lnkPath, $target, $argString, $workDir, $iconPath) {
    $shortcut = $WshShell.CreateShortcut($lnkPath)
    $shortcut.TargetPath = $target
    if ($argString) { $shortcut.Arguments = $argString }
    if ($workDir)   { $shortcut.WorkingDirectory = $workDir }
    if ($iconPath)  { $shortcut.IconLocation = $iconPath }
    $shortcut.Save()
}

$IdeShortcut = Join-Path $StartMenuDir "BoxedLANG IDE.lnk"
New-Shortcut -lnkPath $IdeShortcut -target $PywExe -argString "`"$InstallDir\IDE.py`"" -workDir $InstallDir -iconPath $PywExe
Write-Ok "Start Menu shortcut: BoxedLANG > BoxedLANG IDE"

$UninstallShortcut = Join-Path $StartMenuDir "Uninstall BoxedLANG.lnk"
$UninstallScript = Join-Path $ScriptDir "uninstall.ps1"
New-Shortcut -lnkPath $UninstallShortcut `
    -target "powershell.exe" `
    -argString "-NoLogo -ExecutionPolicy Bypass -File `"$UninstallScript`"" `
    -workDir $ScriptDir -iconPath $PywExe
Write-Ok "Start Menu shortcut: BoxedLANG > Uninstall BoxedLANG"

if (-not $NoDesktopShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $DesktopShortcut = Join-Path $Desktop "BoxedLANG IDE.lnk"
    New-Shortcut -lnkPath $DesktopShortcut -target $PywExe -argString "`"$InstallDir\IDE.py`"" -workDir $InstallDir -iconPath $PywExe
    Write-Ok "Desktop shortcut created"
}

# ---------------------------------------------------------------------------
# 6. Associate .bx files with the IDE (per-user, no admin needed)
# ---------------------------------------------------------------------------
Write-Section "Associating .bx files with the IDE"
try {
    $progId = "BoxedLANG.bxfile"
    New-Item -Path "HKCU:\Software\Classes\.bx" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\.bx" -Name "(default)" -Value $progId

    New-Item -Path "HKCU:\Software\Classes\$progId" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\$progId" -Name "(default)" -Value "BoxedLANG Source File"

    New-Item -Path "HKCU:\Software\Classes\$progId\shell\open\command" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Classes\$progId\shell\open\command" -Name "(default)" `
        -Value "`"$PywExe`" `"$InstallDir\IDE.py`" `"%1`""

    Write-Ok ".bx files now open in the BoxedLANG IDE"
} catch {
    Write-Warn "Could not set file association (non-fatal): $($_.Exception.Message)"
}

# ---------------------------------------------------------------------------
# 7. VS Code / VSCodium extension (optional, best-effort)
# ---------------------------------------------------------------------------
Write-Section "Editor support (VS Code / VSCodium)"

function Install-VscodeExtension($extDir, $label) {
    New-Item -ItemType Directory -Force -Path (Join-Path $extDir "syntaxes") | Out-Null
    Copy-Item (Join-Path $SrcDir "package.json") $extDir -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $SrcDir "language-configuration.json") $extDir -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $SrcDir "bx.tmLanguage.json") (Join-Path $extDir "syntaxes") -Force -ErrorAction SilentlyContinue

    $tarball = Join-Path $SrcDir "boxedlang-vscode.tar.gz"
    if (Test-Path $tarball) {
        $tarExe = Get-Command tar.exe -ErrorAction SilentlyContinue
        if ($tarExe) {
            & tar.exe -xzf $tarball -C $extDir --strip-components=1 2>$null
        } else {
            Write-Warn "tar.exe not found (needs Windows 10 1803+); skipping tarball extraction for $label"
        }
    }
    Write-Ok "$label extension installed to $extDir"
}

$vscodeExtRoot = Join-Path $env:USERPROFILE ".vscode\extensions"
$vscodeOssExtRoot = Join-Path $env:USERPROFILE ".vscode-oss\extensions"
$foundEditor = $false

if ((Get-Command code -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:USERPROFILE ".vscode"))) {
    Install-VscodeExtension (Join-Path $vscodeExtRoot "boxedlang-0.0.1") "VS Code"
    $foundEditor = $true
}
if ((Get-Command code-oss -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:USERPROFILE ".vscode-oss"))) {
    Install-VscodeExtension (Join-Path $vscodeOssExtRoot "boxedlang-0.0.1") "Code - OSS / VSCodium"
    $foundEditor = $true
}
if (-not $foundEditor) {
    Write-Info "No VS Code-family editor detected, skipping."
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Section "Done"
Write-Host "  BoxedLANG core:  $InstallDir" -ForegroundColor White
Write-Host "  IDE:             Start Menu > BoxedLANG > BoxedLANG IDE" -ForegroundColor White
Write-Host "  CLI:             bx / transpilebx / bxdebug (open a new terminal)" -ForegroundColor White
Write-Host ""
Write-Host "  Try it:  bx `"$SrcDir\boxcode\hello.bx`"" -ForegroundColor White
Write-Host ""
