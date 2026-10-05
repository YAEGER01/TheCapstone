param(
  [string]$Hosts = "localhost 127.0.0.1 ::1"
)

# Local HTTPS for CAUFASYSTEM via mkcert (trusted-by-your-browser CA).
# Produces certs/localhost+2.pem + certs/localhost+2-key.pem, which
# deploy/nginx.conf already points at.
#
# Usage:
#   .\scripts\setup_local_tls.ps1
#   # then in .env:  HTTPS_ENABLED=True
#   # then run nginx with deploy/nginx.conf and open https://localhost/
#
# Django runserver itself stays plain HTTP (it cannot do TLS); nginx is the
# local TLS terminator, exactly like production.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$CertDir = Join-Path $ProjectRoot "certs"

function Have-Cmd($name) {
  $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Have-Cmd "mkcert")) {
  Write-Host "[*] mkcert not found — installing..." -ForegroundColor Yellow
  if (Have-Cmd "winget") {
    winget install -e --id FiloSottile.mkcert
  } elseif (Have-Cmd "choco") {
    choco install mkcert -y
  } else {
    Write-Host "  -> Install mkcert manually: https://github.com/FiloSottile/mkcert/releases" -ForegroundColor Red
    Write-Host "     (or: winget install FiloSottile.mkcert)" -ForegroundColor Gray
    exit 1
  }
  # Refresh PATH for this session so mkcert resolves immediately.
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host "[1/3] Installing local CA into system + browser stores..." -ForegroundColor Yellow
mkcert -install

Write-Host "[2/3] Issuing localhost certificate..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $CertDir | Out-Null
Push-Location $CertDir
try {
  $names = $Hosts -split "\s+" | Where-Object { $_ }
  mkcert localhost 127.0.0.1 ::1
} finally {
  Pop-Location
}

Write-Host "[3/3] Verifying..." -ForegroundColor Yellow
$pem = Join-Path $CertDir "localhost+2.pem"
$key = Join-Path $CertDir "localhost+2-key.pem"
if ((Test-Path $pem) -and (Test-Path $key)) {
  Write-Host "  -> $pem" -ForegroundColor Green
  Write-Host "  -> $key" -ForegroundColor Green
  Write-Host ""
  Write-Host "Next steps:" -ForegroundColor Cyan
  Write-Host "  1. In .env set:  HTTPS_ENABLED=True"
  Write-Host "  2. Point nginx at deploy/nginx.conf and reload (nginx -t; nginx -s reload)"
  Write-Host "  3. Open https://localhost/  (green lock, no warnings)"
  Write-Host "  certs/ is gitignored — every dev runs this script once." -ForegroundColor Gray
} else {
  Write-Host "  -> Expected files missing; mkcert output above has details." -ForegroundColor Red
  exit 1
}
