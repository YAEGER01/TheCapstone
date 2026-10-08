param(
  [int]$Port = 8000,
  [switch]$NoMigrate,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$VenvActivate = Join-Path $ProjectRoot "venv\Scripts\Activate.ps1"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CAUFA Portal - START (live auto-refresh)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Kill any server already bound to the target port (avoids "port in use")
try {
  $procs = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
  if ($procs) {
    Write-Host "[*] Freeing port $Port..." -ForegroundColor Yellow
    $procs.OwningProcess | Sort-Object -Unique | ForEach-Object {
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
  }
}
catch { }

Write-Host "[1/3] Activating virtual environment..." -ForegroundColor Yellow
if (Test-Path $VenvActivate) {
  . $VenvActivate
  Write-Host "  -> Virtual env activated." -ForegroundColor Green
}
else {
  Write-Host "  -> Virtual env not found at $VenvActivate" -ForegroundColor Red
  exit 1
}

if (-not $NoMigrate) {
  Write-Host "[2/3] Applying database migrations..." -ForegroundColor Yellow
  & $VenvPython "$ProjectRoot\manage.py" migrate 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  -> Migrations applied." -ForegroundColor Green
  }
  else {
    Write-Host "  -> Migration failed. Check errors above." -ForegroundColor Red
    exit 1
  }
}
else {
  Write-Host "[2/3] Skipping migrations (-NoMigrate)." -ForegroundColor Gray
}

if (-not $NoBrowser) {
  $Url = "http://127.0.0.1:$Port"
  $BrowserJob = Start-Job -ScriptBlock {
    param($Port, $Url)
    for ($i = 0; $i -lt 60; $i++) {
      try {
        $tcp = New-Object Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect("127.0.0.1", $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(500) -and $tcp.Connected) {
          $tcp.Close()
          Start-Process $Url
          break
        }
        $tcp.Close()
      }
      catch { }
      Start-Sleep -Milliseconds 500
    }
  } -ArgumentList $Port, $Url
  Write-Host "[3/3] Browser will open automatically at $Url" -ForegroundColor Yellow
}
else {
  Write-Host "[3/3] Skipping auto-open browser (-NoBrowser)." -ForegroundColor Gray
}

Write-Host ""
Write-Host "  Live behavior (no restarts / no F5 needed):" -ForegroundColor Cyan
Write-Host "    *.html / *.js / *.css  -> browser tab refreshes by itself" -ForegroundColor Green
Write-Host "    *.py                   -> server auto-restarts, tab refreshes after" -ForegroundColor Green
Write-Host "  -> Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

# CAUFA_DEV_WATCH=1 enables the template/static watcher thread
# (core_system/dev_reload_watcher.py) that feeds django-browser-reload.
# Set for the server process only - migrate above already ran without it.
$env:CAUFA_DEV_WATCH = "1"
& $VenvPython "$ProjectRoot\manage.py" runserver "127.0.0.1:$Port"
