param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$BackupRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "..\CAUFA-backups")
)

$ErrorActionPreference = "Stop"
$powerShell = (Get-Command powershell.exe).Source
$databaseScript = Join-Path $ProjectRoot "scripts\backup_database.ps1"
$systemScript = Join-Path $ProjectRoot "scripts\backup_system.ps1"
$common = "-NoProfile -ExecutionPolicy Bypass -File"

$dbAction = New-ScheduledTaskAction -Execute $powerShell -Argument "$common `"$databaseScript`" -ProjectRoot `"$ProjectRoot`" -BackupRoot `"$BackupRoot`""
$systemAction = New-ScheduledTaskAction -Execute $powerShell -Argument "$common `"$systemScript`" -ProjectRoot `"$ProjectRoot`" -BackupRoot `"$BackupRoot`""
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At "12:00AM"
$systemTrigger = New-ScheduledTaskTrigger -Daily -At "12:30AM"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "CAUFA Database Backup" -Action $dbAction -Trigger $dailyTrigger -Settings $settings -Description "Daily CAUFA MariaDB backup at midnight." -Force | Out-Null
Register-ScheduledTask -TaskName "CAUFA System Backup" -Action $systemAction -Trigger $systemTrigger -Settings $settings -Description "CAUFA project archive; script creates one every 15 days." -Force | Out-Null
Write-Host "Scheduled tasks installed. Run Get-ScheduledTask -TaskName 'CAUFA*' to inspect them."