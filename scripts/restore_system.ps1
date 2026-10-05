param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$RestoreRoot = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "CAUFASYSTEM-restored"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $BackupFile)) { throw "Backup file not found: $BackupFile" }
if ((Test-Path $RestoreRoot) -and -not $Force) {
    $confirmation = Read-Host "Restore directory exists and will be replaced. Type RESTORE to continue"
    if ($confirmation -cne "RESTORE") { throw "Restore cancelled." }
}

if (Test-Path $RestoreRoot) { Remove-Item $RestoreRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $RestoreRoot | Out-Null
Expand-Archive -Path $BackupFile -DestinationPath $RestoreRoot -Force
Write-Host "System files restored to $RestoreRoot"
Write-Host "Stop the application before replacing the live project directory."