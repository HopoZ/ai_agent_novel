#Requires -Version 5.1
<#
.SYNOPSIS
  Build release from repo root: frontend dist -> PyInstaller backend -> Electron NSIS installer.

.DESCRIPTION
  Output: *-Setup.exe under electron/release/ (name follows electron/package.json version/productName).

.PARAMETER SkipPyInstaller
  Skip PyInstaller; requires electron/resources/backend/novel-backend.exe to already exist.

.PARAMETER SkipFrontendBuild
  Skip webapp/frontend npm run build; requires webapp/frontend/dist to already exist.

.EXAMPLE
  .\scripts\build-windows-release.ps1

.EXAMPLE
  .\scripts\build-windows-release.ps1 -SkipPyInstaller
#>

[CmdletBinding()]
param(
    [switch] $SkipPyInstaller,
    [switch] $SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Test-Command([string] $Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "npm")) {
    throw "npm not found. Install Node.js 18+ first."
}
if (-not $SkipPyInstaller -and -not (Test-Command "py") -and -not (Test-Command "python")) {
    throw "py/python not found. If you want to skip backend build, pass -SkipPyInstaller."
}

# --- 1) Build frontend dist ---
$frontendDir = Join-Path $RepoRoot "webapp/frontend"
$distDir = Join-Path $frontendDir "dist"
if (-not $SkipFrontendBuild) {
    Write-Host "[1/4] webapp/frontend: npm install and npm run build" -ForegroundColor Cyan
    Push-Location $frontendDir
    try {
        npm install
        npm run build
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path (Join-Path $distDir "index.html"))) {
    throw "Missing webapp/frontend/dist/index.html. Build frontend first or remove -SkipFrontendBuild."
}

# --- 2) PyInstaller ---
$backendDest = Join-Path $RepoRoot "electron/resources/backend/novel-backend.exe"
if (-not $SkipPyInstaller) {
    Write-Host "[2/4] PyInstaller: novel-backend.exe" -ForegroundColor Cyan
    $py = if (Test-Command "py") { "py" } else { "python" }
    & $py -m pip install -q pyinstaller
    $pyArgs = @(
        "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", "novel-backend",
        "packaging/pyinstaller/run_uvicorn.py",
        "--paths", ".",
        "--add-data", "webapp/frontend/dist;webapp/frontend/dist",
        "--add-data", "webapp/static;webapp/static",
        "--add-data", "webapp/templates;webapp/templates",
        "--collect-all", "uvicorn",
        "--collect-all", "fastapi",
        "--collect-all", "starlette",
        "--collect-all", "pydantic",
        "--collect-submodules", "agents",
        "--collect-submodules", "webapp"
    )
    & $py @pyArgs
    $built = Join-Path $RepoRoot "dist/novel-backend.exe"
    if (-not (Test-Path $built)) {
        throw "dist/novel-backend.exe was not generated. Add required --hidden-import/--collect-all entries."
    }
    $destDir = Split-Path $backendDest -Parent
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -Force $built $backendDest
    Write-Host "Copied to $backendDest" -ForegroundColor Green
} else {
    Write-Host "[2/4] Skip PyInstaller" -ForegroundColor Yellow
    if (-not (Test-Path $backendDest)) {
        throw "$backendDest not found, cannot use -SkipPyInstaller."
    }
}

# --- 3) Electron ---
Write-Host "[3/4] electron: npm install and npm run dist" -ForegroundColor Cyan
$electronDir = Join-Path $RepoRoot "electron"
Push-Location $electronDir
try {
    npm install
    npm run dist
} finally {
    Pop-Location
}

Write-Host "[4/4] Done. Installer output: electron/release/" -ForegroundColor Green
$releaseDir = Join-Path $RepoRoot "electron/release"
if (Test-Path $releaseDir) {
    Get-ChildItem $releaseDir -Filter "*.exe" | ForEach-Object { Write-Host "  $($_.FullName)" }
}
