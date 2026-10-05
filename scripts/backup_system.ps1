param(
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$BackupRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "..\CAUFA-backups"),
  [int]$IntervalDays = 15,
  [int]$RetentionCount = 8
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$archiveDirectory = Join-Path $BackupRoot "system"
$cloudRemote = if ($env:BACKUP_RCLONE_REMOTE) { $env:BACKUP_RCLONE_REMOTE } else { "" }

New-Item -ItemType Directory -Force -Path $archiveDirectory | Out-Null
$latest = Get-ChildItem $archiveDirectory -File -Filter "CAUFASYSTEM_*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest -and $latest.LastWriteTime -gt (Get-Date).AddDays(-$IntervalDays)) {
  if ($cloudRemote) {
    & rclone mkdir "$cloudRemote`:system" --log-level ERROR 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Could not access the system backup folder." }
    $cloudArchive = @(& rclone lsf "$cloudRemote`:system" --files-only --log-level ERROR 2>$null) |
    Where-Object { $_ -eq $latest.Name }
    if (-not $cloudArchive) {
      & rclone copy $latest.FullName "${cloudRemote}:system" --immutable
      $latestManifest = Join-Path $archiveDirectory ($latest.BaseName + ".manifest.txt")
      if (Test-Path $latestManifest) { & rclone copy $latestManifest "${cloudRemote}:system" --immutable }
      if ($LASTEXITCODE -ne 0) { throw "rclone upload failed." }
      Write-Host "Existing system backup uploaded: $($latest.FullName)"
    }
  }
  Write-Host "System backup is not due yet. Latest: $($latest.FullName)"
  exit 0
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archivePath = Join-Path $archiveDirectory "CAUFASYSTEM_$stamp.zip"
$manifestPath = Join-Path $archiveDirectory "CAUFASYSTEM_$stamp.manifest.txt"
$excludedNames = @(".git", ".venv", "venv", "__pycache__", "node_modules", "media", "caufa-gdrive", "*.zip", "*.pyc")

$items = Get-ChildItem $ProjectRoot -Force | Where-Object {
  $relative = $_.FullName.Substring($ProjectRoot.Length).TrimStart("\")
  -not ($excludedNames | Where-Object { $relative -like $_ -or $relative.StartsWith("$_\") })
}
Compress-Archive -Path $items.FullName -DestinationPath $archivePath -CompressionLevel Optimal

Get-FileHash $archivePath -Algorithm SHA256 | ForEach-Object {
  "SHA256  $($_.Hash)  $archivePath"
} | Set-Content $manifestPath -Encoding UTF8

if ($cloudRemote) {
  & rclone copy $archivePath "${cloudRemote}:system" --immutable
  & rclone copy $manifestPath "${cloudRemote}:system" --immutable
  if ($LASTEXITCODE -ne 0) { throw "rclone upload failed." }
}

Get-ChildItem $archiveDirectory -File -Filter "CAUFASYSTEM_*.zip" |
Sort-Object LastWriteTime -Descending |
Select-Object -Skip $RetentionCount |
Remove-Item -Force
Get-ChildItem $archiveDirectory -File -Filter "CAUFASYSTEM_*.manifest.txt" |
Where-Object { -not (Test-Path ($_.FullName -replace '\.manifest\.txt$', '.zip')) } |
Remove-Item -Force

Write-Host "System backup created: $archivePath"