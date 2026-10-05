@echo off
REM ============================================================
REM  CAUFASYSTEM - System (codebase) backup
REM  Usage: backup_system.bat <source_dir> <dest_zip>
REM
REM  Zips the project's CODE into DEST_ZIP using the bsdtar that ships
REM  with Windows 10/11 (-a picks zip from the file extension). Excluded:
REM  the virtualenv, .git, node_modules, staticfiles, media/ (uploads have
REM  their own dedicated backup job), previous *.zip / *.log files, and
REM  Python caches - so the archive stays small and cannot recurse.
REM ============================================================
setlocal

set "SRC=%~1"
set "DEST=%~2"

if "%SRC%"=="" set /p SRC=Source directory:
if "%DEST%"=="" set /p DEST=Destination zip path:

if not exist "%SRC%\" (
    echo [ERROR] Source directory not found: %SRC%
    exit /b 2
)

for %%F in ("%DEST%") do set "DEST_NAME=%%~nxF"
for %%D in ("%DEST%") do set "DEST_DIR=%%~dpD"
if not exist "%DEST_DIR%" mkdir "%DEST_DIR%"
if exist "%DEST%" del /q "%DEST%"

REM Run tar from inside the destination folder so -f gets a bare filename:
REM bsdtar parses "C:\..." in -f as a remote host ("Cannot connect to C:").
pushd "%DEST_DIR%"
tar -a -c -f "%DEST_NAME%" ^
    --exclude "./venv" --exclude "./venv/*" ^
    --exclude "./.git" --exclude "./.git/*" ^
    --exclude "./node_modules" --exclude "./node_modules/*" ^
    --exclude "./staticfiles" --exclude "./staticfiles/*" ^
    --exclude "./media" --exclude "./media/*" ^
    --exclude "./media/backups" --exclude "./media/backups/*" ^
    --exclude "*.zip" ^
    --exclude "*.log" ^
    --exclude "*__pycache__*" ^
    --exclude "*.pyc" ^
    -C "%SRC%" .
set "TAR_RC=%errorlevel%"
popd

if not exist "%DEST%" (
    echo [ERROR] Backup zip was not created. tar output:
    echo %CD%
    exit /b 1
)

if errorlevel 1 (
    echo [WARN] tar reported problems but the zip exists - inspect it before relying on it.
)

echo [OK] Codebase backup written to %DEST%
endlocal
exit /b 0
