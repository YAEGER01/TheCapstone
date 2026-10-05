param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
if (-not $Force) {
    $confirmation = Read-Host "This replaces the live database. Type RESTORE to continue"
    if ($confirmation -cne "RESTORE") { throw "Restore cancelled." }
}

function Get-DotEnvValue([string]$Name) {
    $line = Get-Content (Join-Path $ProjectRoot ".env") | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
    if (-not $line) { throw "Missing $Name in .env" }
    return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

if (-not (Test-Path $BackupFile)) { throw "Backup file not found: $BackupFile" }
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("caufa_restore_" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
$env:MYSQL_PWD = Get-DotEnvValue "DB_PASSWORD"
try {
    Expand-Archive -Path $BackupFile -DestinationPath $tempRoot -Force
    $sqlFile = Get-ChildItem $tempRoot -File -Filter "*.sql" | Select-Object -First 1
    if (-not $sqlFile) { throw "No SQL file found in backup archive." }
    & mysql --host=(Get-DotEnvValue "DB_HOST") --port=(Get-DotEnvValue "DB_PORT") --user=(Get-DotEnvValue "DB_USER") --execute="source $($sqlFile.FullName.Replace('\', '/'))"
    if ($LASTEXITCODE -ne 0) { throw "mysql restore failed." }
    Write-Host "Database restored from $BackupFile"
}
finally {
    Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}