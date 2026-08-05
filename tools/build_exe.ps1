<#
.SYNOPSIS
    Builds the onefile/windowed "MVR Enhancer.exe" via PyInstaller.

.DESCRIPTION
    Invokes the project venv's pyinstaller.exe directly (no venv activation)
    against build/pyinstaller.spec, always run from the repository root so
    the spec's SPECPATH-relative paths resolve correctly. PyInstaller's
    working directory (build/pyinstaller-out) and dist directory (dist) are
    both gitignored.

.EXAMPLE
    powershell -File tools\build_exe.ps1
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Pyinstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $Pyinstaller)) {
    throw "pyinstaller.exe not found at $Pyinstaller - install dev extras into .venv first."
}

$SpecPath = Join-Path $RepoRoot "build\pyinstaller.spec"

& $Pyinstaller $SpecPath `
    --noconfirm `
    --distpath dist `
    --workpath build\pyinstaller-out

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$ExePath = Join-Path $RepoRoot "dist\MVR Enhancer.exe"
if (-not (Test-Path $ExePath)) {
    throw "Build reported success but exe not found at $ExePath"
}

$ExeItem = Get-Item $ExePath
$SizeMb = [math]::Round($ExeItem.Length / 1MB, 2)
Write-Output "Built: $($ExeItem.FullName)"
Write-Output "Size: $($ExeItem.Length) bytes ($SizeMb MB)"
