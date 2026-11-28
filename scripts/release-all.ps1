<#
  AI Clipper Pro — Windows one-command release (PowerShell).
    powershell -ExecutionPolicy Bypass -File scripts\release-all.ps1
    powershell -ExecutionPolicy Bypass -File scripts\release-all.ps1 -All -Publish
#>
param(
  [string]$Version = (node -p "require('./package.json').version"),
  [switch]$All,
  [switch]$Publish,
  [switch]$SkipBackend
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$CurrentBranch = (git branch --show-current).Trim()
Write-Host "== AI Clipper Pro release v$Version =="
if ($All) {
  if (-not $CurrentBranch) { throw 'Cannot dispatch a release from a detached HEAD' }
  if (git status --porcelain) {
    throw 'Commit the current changes before dispatching; GitHub Actions builds the pushed branch, not this working tree.'
  }
  $LocalSha = (git rev-parse HEAD).Trim()
  $RemoteLine = git ls-remote --heads origin "refs/heads/$CurrentBranch"
  $RemoteSha = if ($RemoteLine) { ($RemoteLine -split '\s+')[0] } else { '' }
  if (-not $RemoteSha -or $LocalSha -ne $RemoteSha) {
    throw "Push $CurrentBranch at $LocalSha to origin before dispatching the all-target build."
  }
}

function Invoke-Checked([string]$Command) {
  Write-Host "> $Command"
  Invoke-Expression $Command
  if ($LASTEXITCODE -ne 0) { throw "Failed: $Command" }
}

Invoke-Checked 'npm run typecheck'
if (Test-Path '.venv\Scripts\python.exe') { $Python = '.venv\Scripts\python.exe' } else { $Python = 'python' }
& $Python -m pytest backend/tests -q
Invoke-Checked "$Python scripts/generate-icons.py"
Invoke-Checked 'npm run build'
if ($All) {
  Write-Host 'Skipping local Python-engine packaging; each GitHub Actions matrix job builds its engine bundle.'
} elseif ($SkipBackend) {
  Invoke-Checked "$Python scripts/package-backend.py --skip-pyinstaller"
} else {
  Invoke-Checked "$Python scripts/package-backend.py"
}

if ($All) {
  if (-not $CurrentBranch) { throw 'Cannot dispatch a release from a detached HEAD' }
  $BuildOnly = 'true'
  if ($Publish) { $BuildOnly = 'false' }
  Invoke-Checked "gh workflow run release.yml --ref $CurrentBranch -f version=$Version -f build_only=$BuildOnly"
  Start-Sleep -Seconds 8
  $runId = (gh run list --workflow release.yml --branch $CurrentBranch --limit 1 --json databaseId --jq '.[0].databaseId')
  if (-not $runId) { throw 'Could not find the dispatched GitHub Actions run' }
  Invoke-Checked "gh run watch $runId --exit-status"
  if (Test-Path release) { Remove-Item -Recurse -Force release }
  New-Item -ItemType Directory -Force release | Out-Null
  Invoke-Checked "gh run download $runId -D release\.download"
  Get-ChildItem release\.download -Recurse -File | ForEach-Object { Copy-Item $_.FullName -Destination release -Force }
  Remove-Item -Recurse -Force release\.download
  $Expected = @(
    "AI-Clipper-Pro-$Version-Windows-x64.exe",
    "AI-Clipper-Pro-$Version-Windows-arm64.exe",
    "AI-Clipper-Pro-$Version-macOS-x64.dmg",
    "AI-Clipper-Pro-$Version-macOS-x64.zip",
    "AI-Clipper-Pro-$Version-macOS-arm64.dmg",
    "AI-Clipper-Pro-$Version-macOS-arm64.zip",
    "AI-Clipper-Pro-$Version-Linux-x86_64.AppImage",
    "AI-Clipper-Pro-$Version-Linux-amd64.deb"
  )
  foreach ($Name in $Expected) {
    if (-not (Test-Path "release\$Name")) { throw "Missing all-target artifact: $Name" }
  }
  $Actual = @(Get-ChildItem release -File | Where-Object { $_.Extension -in '.exe', '.dmg', '.zip', '.AppImage', '.deb' }).Count
  if ($Actual -ne $Expected.Count) { throw "Expected $($Expected.Count) installers, found $Actual" }
} else {
  Invoke-Checked 'npx electron-builder --win --x64 --arm64 --publish never'
}

if (-not (Test-Path release)) { New-Item -ItemType Directory -Force release | Out-Null }
$installers = Get-ChildItem release -Recurse -File | Where-Object { $_.Extension -in '.exe', '.dmg', '.AppImage', '.deb', '.zip' }
$lines = $installers | ForEach-Object { "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)" }
$lines | Set-Content release\SHA256SUMS.txt
@{
  product = 'AI Clipper Pro'; author = 'analoggeek'; version = $Version
  builtAt = (Get-Date).ToUniversalTime().ToString('o'); buildMode = $(if ($All) { 'ci' } else { 'local' })
  installers = @($installers.Name)
} | ConvertTo-Json -Depth 4 | Set-Content release\manifest.json

if ($Publish -and $All) {
  Invoke-Checked "gh release view v$Version --json tagName,url"
} elseif ($Publish) {
  try { Invoke-Checked "gh release create v$Version release/* --target HEAD --generate-notes --title 'AI Clipper Pro v$Version'" }
  catch { Invoke-Checked "gh release upload v$Version release/* --clobber" }
}
Write-Host 'Done. Installers and checksums are in .\release'
Get-ChildItem release | Select-Object Name, Length
