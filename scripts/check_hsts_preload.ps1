param(
  [string]$Domain = "isucaufa-fms.online"
)

# HSTS preload eligibility check (hstspreload.org requirements).
# Submission itself is a one-way, owner-clicked action in a browser and is
# IRREVERSIBLE for the domain (+ subdomains) — so this script proves every
# requirement first and stops with NO-GO on any failure.
#
# Usage:  .\scripts\check_hsts_preload.ps1 -Domain isucaufa-fms.online
#
# Requirements checked:
#   1. valid (trusted, unexpired) cert on https://domain/
#   2. http://  -> 301 to https:// (same host)
#   3. Strict-Transport-Security: max-age >= 31536000, includeSubDomains, preload
#   4. header present on the apex AND www (preload covers subdomains)

$ErrorActionPreference = "Stop"
$failures = @()

function Fail($msg) {
  Write-Host "  [FAIL] $msg" -ForegroundColor Red
  $script:failures += $msg
}
function Pass($msg) {
  Write-Host "  [PASS] $msg" -ForegroundColor Green
}

Write-Host "HSTS preload eligibility: $Domain" -ForegroundColor Cyan

# --- 1. trusted cert (Invoke-WebRequest fails on untrusted/expired) ---
Write-Host "[1/4] Certificate trust + expiry..." -ForegroundColor Yellow
try {
  $resp = Invoke-WebRequest -Uri "https://$Domain/" -MaximumRedirection 0 -TimeoutSec 20 -UseBasicParsing
  Pass "https://$Domain/ served with a trusted certificate."
} catch {
  # A redirect (301) surfaces as an exception with MaximumRedirection 0 — fine.
  if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -in @(301, 302, 303, 307, 308)) {
    Pass "https://$Domain/ reachable (redirects onward)."
  } else {
    Fail "https://$Domain/ unreachable or cert untrusted/expired: $($_.Exception.Message)"
  }
}

# --- 2. http -> https redirect ---
Write-Host "[2/4] http -> https redirect..." -ForegroundColor Yellow
try {
  $r = Invoke-WebRequest -Uri "http://$Domain/" -MaximumRedirection 0 -TimeoutSec 20 -UseBasicParsing -ErrorAction Stop
  Fail "http:// did not redirect (status $($r.StatusCode))."
} catch {
  $res = $_.Exception.Response
  if ($res -and [int]$res.StatusCode -in @(301, 308)) {
    $loc = $res.Headers["Location"]
    if ($loc -like "https://$Domain*") { Pass "http://$Domain/ -> 301 $loc" }
    else { Fail "http redirect target wrong: $loc" }
  } else {
    Fail "http:// did not 301 to https (got: $($_.Exception.Message))."
  }
}

# --- 3+4. HSTS header on apex and www ---
foreach ($host_ in @($Domain, "www.$Domain")) {
  Write-Host "[3/4] HSTS header on https://$host_ ..." -ForegroundColor Yellow
  try {
    $h = (Invoke-WebRequest -Uri "https://$host_/" -TimeoutSec 20 -UseBasicParsing).Headers["Strict-Transport-Security"]
    if (-not $h) { Fail "no Strict-Transport-Security header on $host_."; continue }
    Write-Host "       value: $h" -ForegroundColor Gray
    $ok = $true
    if ($h -notmatch "max-age=\s*(\d+)") { Fail "max-age missing on $host_."; $ok = $false }
    elseif ([int64]$Matches[1] -lt 31536000) { Fail "max-age $($Matches[1]) < 31536000 on $host_."; $ok = $false }
    if ($h -notmatch "(?i)includesubdomains") { Fail "includeSubDomains missing on $host_."; $ok = $false }
    if ($h -notmatch "(?i)\bpreload\b") { Fail "preload token missing on $host_."; $ok = $false }
    if ($ok) { Pass "HSTS preload-ready on $host_." }
  } catch {
    Fail "could not fetch https://$host_/ : $($_.Exception.Message)"
  }
}

Write-Host ""
if ($failures.Count -eq 0) {
  Write-Host "GO — eligible. Submit at https://hstspreload.org/?domain=$Domain" -ForegroundColor Green
  Write-Host "Reminder: removal from the preload list takes months to reach all" -ForegroundColor Gray
  Write-Host "browsers. Only submit when HTTPS + redirect are permanent." -ForegroundColor Gray
  exit 0
} else {
  Write-Host "NO-GO — $($failures.Count) failing check(s). Fix, redeploy, re-run." -ForegroundColor Red
  exit 1
}
