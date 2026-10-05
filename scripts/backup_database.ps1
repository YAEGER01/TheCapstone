param(
 [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
 [string]$BackupRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "..\CAUFA-backups"),
 [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Get-DotEnvValue([string]$Name) {
 $line = Get-Content (Join-Path $ProjectRoot ".env") | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
 if (-not $line) { throw "Missing $Name in .env" }
 return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

$dbHost = Get-DotEnvValue "DB_HOST"
$dbName = Get-DotEnvValue "DB_NAME"
$dbUser = Get-DotEnvValue "DB_USER"
$dbPassword = Get-DotEnvValue "DB_PASSWORD"
$dbPort = Get-DotEnvValue "DB_PORT"
$dbDirectory = Join-Path $BackupRoot "database"
$cloudRemote = if ($env:BACKUP_RCLONE_REMOTE) { $env:BACKUP_RCLONE_REMOTE } else { "" }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$sqlFile = Join-Path $dbDirectory ("{0}_{1}.sql" -f $dbName, $stamp)
$backupFile = Join-Path $dbDirectory ("{0}_{1}.sql.zip" -f $dbName, $stamp)

New-Item -ItemType Directory -Force -Path $dbDirectory | Out-Null
$env:MYSQL_PWD = $dbPassword

try {
 & mysqldump --single-transaction --routines --events --triggers --hex-blob --result-file=$sqlFile --host=$dbHost --port=$dbPort --user=$dbUser --databases $dbName
 if ($LASTEXITCODE -ne 0 -or -not (Test-Path $sqlFile) -or (Get-Item $sqlFile).Length -lt 100) {
  throw "mysqldump failed or produced an empty backup."
 }

 Compress-Archive -Path $sqlFile -DestinationPath $backupFile -CompressionLevel Optimal
 Expand-Archive -Path $backupFile -DestinationPath (Join-Path $dbDirectory "verify_$stamp") -Force
 $verifiedSql = Join-Path $dbDirectory "verify_$stamp\$(Split-Path $sqlFile -Leaf)"
 if (-not (Test-Path $verifiedSql) -or (Get-Item $verifiedSql).Length -ne (Get-Item $sqlFile).Length) {
  throw "Backup compression verification failed."
 }

 if ($cloudRemote) {
    & rclone copy $backupFile "${cloudRemote}:database" --immutable
  if ($LASTEXITCODE -ne 0) { throw "rclone upload failed." }
 }
}
finally {
 Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
 Remove-Item $sqlFile -Force -ErrorAction SilentlyContinue
 Remove-Item (Join-Path $dbDirectory "verify_$stamp") -Recurse -Force -ErrorAction SilentlyContinue
}

Get-ChildItem $dbDirectory -File -Filter "*.sql.gz" |
Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
Remove-Item -Force

Get-ChildItem $dbDirectory -File -Filter "*.sql.zip" |
Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
Remove-Item -Force

Write-Host "Database backup created: $backupFile"