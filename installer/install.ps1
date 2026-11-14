<#
detectTOL installer for Windows (per user, no administrator rights needed).

What it does, in order (nothing else):
  1. Finds conda (Miniforge / Miniconda / Anaconda). If there is none, it offers to
     download Miniforge from its official GitHub release and install it for this user.
  2. Creates the conda environment "detecttol" from installer/environment-app.yml,
     or, if it already exists, adds the app's packages (nicegui, pywin32, pillow).
  3. Installs detectTOL from this folder into that environment (editable when this
     folder is a git clone, so `git pull` updates the app).
  4. Checks that detectTOL, the CAD kernel and the app library import.
  5. Writes a launcher to %LOCALAPPDATA%\detectTOL and puts a "detectTOL" shortcut on
     the Desktop and in the Start menu.

Run it with install_detectTOL.bat (double-click). Remove it with uninstall_detectTOL.bat.
Options: -DryRun (show the steps, change nothing), -EnvName <name>, -NoShortcuts.
#>
param(
    [switch]$DryRun,
    [string]$EnvName = "detecttol",
    [switch]$NoShortcuts
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$AppDir = Join-Path $env:LOCALAPPDATA "detectTOL"
$MiniforgeUrl = "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe"

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Run($exe, [string[]]$arguments) {
    Write-Host "    $exe $($arguments -join ' ')" -ForegroundColor DarkGray
    if ($DryRun) { return }
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "failed (exit code $LASTEXITCODE): $exe $($arguments -join ' ')" }
}

function Find-CondaRoot {
    $candidates = @(
        (Join-Path $env:USERPROFILE "miniforge3"), (Join-Path $env:USERPROFILE "miniconda3"),
        (Join-Path $env:USERPROFILE "anaconda3"), (Join-Path $env:LOCALAPPDATA "miniforge3"),
        "C:\ProgramData\miniforge3", "C:\ProgramData\miniconda3", "C:\ProgramData\anaconda3"
    )
    foreach ($c in $candidates) { if (Test-Path (Join-Path $c "Scripts\conda.exe")) { return $c } }
    $onPath = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($onPath) { return (Split-Path -Parent (Split-Path -Parent $onPath.Source)) }
    return $null
}

Write-Host "detectTOL installer" -ForegroundColor White
Write-Host "  source folder: $Repo"
if ($DryRun) { Write-Host "  DRY RUN: nothing will be changed" -ForegroundColor Yellow }

# 1. conda ------------------------------------------------------------------------------
Step "Looking for conda"
$CondaRoot = Find-CondaRoot
if (-not $CondaRoot) {
    Write-Host "    No conda installation found."
    $target = Join-Path $env:USERPROFILE "miniforge3"
    $answer = Read-Host "    Download and install Miniforge (free, conda-forge) into $target ? [y/N]"
    if ($answer -notmatch '^[yY]') { throw "conda is needed. Install Miniforge from https://conda-forge.org/download/ and run this again." }
    $exe = Join-Path $env:TEMP "Miniforge3-Windows-x86_64.exe"
    Write-Host "    downloading $MiniforgeUrl"
    if (-not $DryRun) { Invoke-WebRequest -Uri $MiniforgeUrl -OutFile $exe -UseBasicParsing }
    Run $exe @("/InstallationType=JustMe", "/RegisterPython=0", "/AddToPath=0", "/S", "/D=$target")
    $CondaRoot = $target
}
$Conda = Join-Path $CondaRoot "Scripts\conda.exe"
Write-Host "    conda: $Conda"

# 2. environment ------------------------------------------------------------------------
Step "Preparing the conda environment '$EnvName'"
$envList = & $Conda env list
$exists = $envList | Where-Object { ($_ -split '\s+')[0] -eq $EnvName }
if ($exists) {
    Write-Host "    exists; adding the app's packages if missing"
    Run $Conda @("install", "-y", "--freeze-installed", "-n", $EnvName, "-c", "conda-forge", "nicegui>=4.0", "pywin32", "pillow")
} else {
    Run $Conda @("env", "create", "-n", $EnvName, "-f", (Join-Path $PSScriptRoot "environment-app.yml"))
}

# 3. detectTOL itself -------------------------------------------------------------------
Step "Installing detectTOL from $Repo"
$pipArgs = @("run", "-n", $EnvName, "python", "-m", "pip", "install", "--no-deps")
if (Test-Path (Join-Path $Repo ".git")) { $pipArgs += @("-e", $Repo) } else { $pipArgs += @($Repo) }
Run $Conda $pipArgs

# 4. check ------------------------------------------------------------------------------
Step "Checking the installation"
Run $Conda @("run", "-n", $EnvName, "python", "-c",
    "import detecttol, OCC, nicegui, win32com; print('detecttol', detecttol.__version__, '| nicegui', nicegui.__version__, '| OK')")

# 5. launcher and shortcuts -------------------------------------------------------------
if ($NoShortcuts) { Write-Host ""; Write-Host "Done (no shortcuts)."; exit 0 }
Step "Creating the launcher and shortcuts"
$launcher = Join-Path $AppDir "detectTOL.bat"
$icon = Join-Path $AppDir "detectTOL.ico"
$batch = @"
@echo off
rem detectTOL launcher (written by installer\install.ps1). Starts the app in your browser.
title detectTOL
call "$CondaRoot\Scripts\activate.bat" $EnvName
python -m detecttol app
"@
Write-Host "    $launcher"
if (-not $DryRun) {
    New-Item -ItemType Directory -Force $AppDir | Out-Null
    Set-Content -Path $launcher -Value $batch -Encoding ASCII
    & $Conda run -n $EnvName python (Join-Path $PSScriptRoot "make_icon.py") $icon
}
$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "detectTOL.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "detectTOL.lnk")
)
foreach ($lnk in $targets) {
    Write-Host "    $lnk"
    if ($DryRun) { continue }
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $launcher
    $s.WorkingDirectory = $AppDir
    $s.WindowStyle = 7          # minimised: the console only shows the app's log
    $s.Description = "detectTOL - tolerance stack-up from your CAD model"
    if (Test-Path $icon) { $s.IconLocation = $icon }
    $s.Save()
}

Write-Host ""
Write-Host "Done. Double-click 'detectTOL' on your Desktop; the app opens in your browser." -ForegroundColor Green
