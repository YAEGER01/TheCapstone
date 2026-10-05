# CAUFA Backup and Restore

The backup jobs run outside Django so they continue to work when the web application is down.

## Backup layout

Backups are stored outside the project by default:

```text
..\CAUFA-backups\database\   Daily MariaDB .sql.zip files
..\CAUFA-backups\system\     Project ZIP files (at most one every 15 days)
```

The project archive includes the source, templates, static files, media, and `.env`. The archive excludes virtual environments, Git metadata, caches, and generated backups. Treat the archive as sensitive because it contains secrets.

## Google Drive

Install and configure `rclone` once:

```powershell
rclone config
```

Create a Google Drive remote, then set the remote in the current Windows user environment:

```powershell
[Environment]::SetEnvironmentVariable("BACKUP_RCLONE_REMOTE", "gdrive:caufa-backups", "User")
```

The scripts upload to `gdrive:caufa-backups/database` and `gdrive:caufa-backups/system`. Without this variable, they still create and verify local external backups.

## Install the schedules

Run PowerShell as the account that owns the project:

```powershell
cd C:\Users\maday\PROJECTS\CAUFASYSTEM
.\scripts\install_backup_tasks.ps1
```

This creates:

- `CAUFA Database Backup`: every day at 12:00 AM
- `CAUFA System Backup`: checked every day at 12:30 AM; it creates an archive only when the previous one is at least 15 days old

Test both jobs immediately:

```powershell
Start-ScheduledTask -TaskName "CAUFA Database Backup"
Start-ScheduledTask -TaskName "CAUFA System Backup"
Get-ScheduledTaskInfo -TaskName "CAUFA Database Backup","CAUFA System Backup"
```

## Manual backups

```powershell
.\scripts\backup_database.ps1
.\scripts\backup_system.ps1
```

## Restore a database

Stop Django/Daphne first. Use a local or downloaded `.sql.zip` file:

```powershell
.\scripts\restore_database.ps1 -BackupFile "..\CAUFA-backups\database\isucaufafms_capstone_project_db_YYYYMMDD_HHMMSS.sql.zip"
```

The script requires typing `RESTORE` before replacing the live database. After restoring, start the application and verify login, member records, and critical workflows.

## Restore the project files

Restore into a separate directory first:

```powershell
.\scripts\restore_system.ps1 -BackupFile "..\CAUFA-backups\system\CAUFASYSTEM_YYYYMMDD_HHMMSS.zip"
```

Review `..\CAUFASYSTEM-restored`, copy any needed files into the live project after stopping the application, and restore the matching database backup if the incident involved data loss.

## Recovery practice

Once per month, test one database restore and one project archive extraction on a separate directory or machine. A backup is only considered healthy when the archive opens, the SQL dump imports, and the application starts against the restored copy.