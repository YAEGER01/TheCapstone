# CAUFASYSTEM — ISU Cauayan Faculty Association Fund Management System

<p>
  <img src="https://img.shields.io/badge/Django-5.1-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django 5.1" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/MySQL-8-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL 8" />
  <img src="https://img.shields.io/badge/Redis-prod-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Channels_4-Daphne-512BD4?style=for-the-badge&logo=django&logoColor=white" alt="Channels + Daphne" />
</p>

<p>
  <img src="https://img.shields.io/badge/HTTPS-Enforced-2EA043?style=for-the-badge&logo=letsencrypt&logoColor=white" alt="HTTPS enforced" />
  <img src="https://img.shields.io/badge/HSTS-1yr_preload-1F6FEB?style=for-the-badge&logo=cloudflare&logoColor=white" alt="HSTS preload" />
  <img src="https://img.shields.io/badge/Auth-Argon2id_MFA-6E40C9?style=for-the-badge&logo=1password&logoColor=white" alt="Argon2id + MFA" />
  <img src="https://img.shields.io/badge/Zero_Trust-enabled-A371F7?style=for-the-badge&logo=auth0&logoColor=white" alt="Zero-Trust" />
  <img src="https://img.shields.io/badge/Turnstile-protected-F68212?style=for-the-badge&logo=cloudflare&logoColor=white" alt="Turnstile" />
  <img src="https://img.shields.io/badge/URL-Fernet_HMAC-8250DF?style=for-the-badge&logo=lock&logoColor=white" alt="URL encryption" />
</p>

<p>
  <img src="https://img.shields.io/badge/Roles-8_portals-blueviolet?style=for-the-badge&logo=keycloak&logoColor=white" alt="8 role portals" />
  <img src="https://img.shields.io/badge/Reports-49_types-FA6310?style=for-the-badge&logo=libreofficecalc&logoColor=white" alt="49 reports" />
  <img src="https://img.shields.io/badge/Realtime-WS_polling-0A7EA4?style=for-the-badge&logo=socketdotio&logoColor=white" alt="Realtime" />
  <img src="https://img.shields.io/badge/PWA-ready-5FD0B5?style=for-the-badge&logo=pwa&logoColor=white" alt="PWA" />
  <img src="https://img.shields.io/badge/Tests-70_passing-238636?style=for-the-badge&logo=pytest&logoColor=white" alt="70 tests" />
  <img src="https://img.shields.io/badge/Deploys-VPS_cPanel-8957E5?style=for-the-badge&logo=cpanel&logoColor=white" alt="VPS + cPanel" />
</p>

> Public website + multi-role officer/member portals for dues, aids & claims, payroll deductions, fund ledger, audit/approval workflow, reports, and realtime dashboards.

**Live stack:** Django 5.1 + Channels/Daphne + MySQL 8 + Redis (prod) · **Deploys the same codebase two ways:** VPS (Nginx + Daphne + Let's Encrypt) and shared cPanel Passenger · **Timezone:** Asia/Manila

---

## Table of Contents

- [What this site does](#what-this-site-does)
- [Capabilities by portal](#capabilities-by-portal)
- [Financial core & workflows](#financial-core--workflows)
- [Reports (49 built-in types)](#reports-49-built-in-types)
- [Realtime, PWA & notifications](#realtime-pwa--notifications)
- [Security measures](#security-measures)
- [Tech stack](#tech-stack)
- [Deployment modes](#deployment-modes)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Testing & operations](#testing--operations)

---

## What this site does

CAUFASYSTEM is a fund-management portal for the ISU-Cauayan Faculty Association (CauFA):

- **Public site** — home, about, officers, activities, gallery, news, resources, announcements, public bylaws/docs, public member registration + registration-status check, PIO-managed content (officer profiles, hero slides, news articles, announcements).
- **Member & officer portals** — role-scoped dashboards for Members, Treasurer, Auditor, President, Secretary, PIO, Superadmin, and SystemBackup.
- **Money in / money out** — monthly dues (OTC / salary deduction / bulk), membership fees, contributions, payroll batches, medical & death aids, claims queue, releases, fund ledger/timeline/overview, budgets.
- **Governance** — Treasurer files → Auditor verifies → President approves → Treasurer releases, with returns/revisions, audit trails, compliance heatmaps, and 49 report types (preview / XLSX / PDF).
- **Always-live feel** — WebSockets with polling fallback, fund-balance tickers, live tables, Web Push (VAPID), in-app bell, email queue (OTP-first), scheduled jobs.

---

## Capabilities by portal

| Portal | What it can do |
|--------|----------------|
| **Public** | Landing + about/officers/activities/gallery/news/resources/announcements, public registration (`/register/`), registration-status lookup, certificate verification surface |
| **Member** | Dashboard + transparency view, personal ledger, unpaid-months matrix, dues breakdown/payments, fund summary/trend/movements, contributions, aid claims (file/list/detail/proof-upload), attendance & events, profile + email-OTP change + picture + 4-digit action PIN + onboarding + family/rep info, session revoke, certificates view/download, salary-deduction exemption requests |
| **Treasurer** | Members (add/create/batch-upload, retire, position ranks, categories, departments), membership fees, monthly dues (OTC/salary/bulk-preview/process), payroll batches & deductions, other transactions, medical/death aid filing, claims queue, releases & payments, fund timeline/ledger/overview, documents repository, returned/revision resubmits |
| **Auditor** | Verify payments/aids/fees (single + batch), reject/return with findings, payroll verify/reject, registration verify, aid-tracking posts + compliance heatmap, audited logs, audit-trail verify, auditor & fund reports |
| **President** | Presidential queue/decision (payments + aids, single + batch), auditor-approved queues, payroll & monthly-dues approve/reject, registration approve, officers CRUD + self-enroll, documents/activity management, overview KPIs (8 chart endpoints), backups & codebase snapshot, audit logs |
| **Secretary** | Attendance (today/summary/check-in/bulk-time-in/live-monitoring/export PDF/Excel), events CRUD + open/close attendance, documents/minutes/announcements/categories/event-types, member directory, certificates (settings/history/resend + ReportLab PDF) |
| **PIO** | News / announcements / gallery / officers content publishing |
| **Superadmin** | Settings (grace periods, notifications, banner, nav modules, Zero-Trust timers), feedback forms (forms/questions/responses), security & system audit views |
| **SystemBackup** (president-owned) | DB / media / config backups, scheduler control, restore drills |

Cross-cutting: officer directory, event calendar, notice cards, announcements list, past activities, cookie notice, officer PIN modal, security modal, audit-trail panel, per-module nav visibility.

---

## Financial core & workflows

**Ledger chain:**

```text
MonthlyAssessment → AssessmentItem → MemberAssessment → Allocation
  → CatchupDue → AidSetAside → MonthlyDues / MembershipFee
  → MemberLedger → FundTransaction → BudgetLine
```

- **Dues collection:** OTC cash, salary-deduction (with exemptions, auto-allocation by priority, dues reminders), bulk-preview/process, catch-up dues, backfill guards, unpaid-months guard.
- **Payroll flow:** Treasurer builds batch → Auditor verifies → President approves → Treasurer posts deductions (`PayrollBatch` / `PayrollDeduction` + deduction-sheet PDF).
- **Aid flow:** Treasurer files `MedicalAid` / `DeathAid` + `Claimant` + `SupportingProof` → Auditor verifies → President approves → Treasurer releases/pays → tracking posts with per-member contributions, expedite notices, external-aid co-funding.
- **Controls:** set-asides per aid, budget lines, fund timeline, balance reconciliation, cleanup/reconcile/backfill management commands, revision logs.

---

## Reports (49 built-in types)

Unified + association + oversight + auditor + fund builders with **preview / XLSX (openpyxl) / PDF (ReportLab + safe-PDF + WeasyPrint fallback)** and weekly-Excel + deduction-sheet PDF shortcuts. Every new type ships with a `tests_sample_<code>.py` fixture test.

| Group | Codes | Examples |
|-------|-------|----------|
| Membership / Collection | A1–A5 | Member roster, collection summary, delinquency, assessment vs collection |
| Aid | AID1–AID11 | Medical/death filings, approvals, releases, tracking, aging |
| Donation / Disbursement | D1–D4 | Contributions in, disbursements out, donor summary |
| Control / Exception | F1–F7 | Variances, missing proofs, unverified items, duplicate guards |
| Bank / Cash | G1–G5 | Cash position, bank recon, cash-flow |
| Ledgers / Summaries | H1–H10 | Member ledger, fund ledger, trial summaries |
| Recommended | N1–N5 | Oversight-recommended views |
| Panel-added | X1–X2 | Defense-panel requested additions |

> Full builder matrix lives in `REPORTS.MD` (49 DONE, layouts LP1–LP5).

---

## Realtime, PWA & notifications

- **WebSockets (Django Channels):** 4 groups — `auditor_dashboard`, `treasurer_dashboard`, `president_dashboard`, `member_{id}` + `fund_watchers`. Events: `fund_updated`, `dashboard_refresh`, `data_changed`, `notification_created`, `aid_post_*`. Auth via short-lived `access_token`.
- **Graceful degradation:** `static/js/shared/realtime.js` tries WS, falls back to polling automatically (required for cPanel shared hosting with no ASGI/Redis). Per-role `websocket.js`, `live_tables` / `realtime_tables`, `fund_balance_live` tickers.
- **Web Push (VAPID via `pywebpush`):** `push_views.py` + `push-init.js` + `sw.js`, stale-subscription purger.
- **PWA:** `manifest.json` + service worker, offline-vendored assets (no CDN runtime dependency — htmx 2.0.4, Tailwind-play, SweetAlert2, Flatpickr, FA 6.5.2, Turbo, Chart.js, Poppins/Inter), installable + app icons generator.
- **Comms & scheduler:** `OutgoingEmail` queue + `process_emails [--otp-only]`, `EmailQueueKickMiddleware` piggyback flush, APScheduler in-process (dev/VPS) or 8 cPanel cron jobs (shared), dues reminders, overdue deactivation, backup scheduler, in-app bell + push fan-out.

---

## Security measures

Defense-in-depth across transport, session, auth, Zero-Trust, bot/abuse, URL, headers, input, data, email, and backups. Key files in parentheses.

### 1. Transport security (TLS/HTTPS/HSTS)

- `APP_ENV=production` **forces** `SECURE_SSL_REDIRECT`, HSTS 1 year + `preload` + `includeSubDomains`, `SECURE_PROXY_SSL_HEADER` (Nginx sets `X-Forwarded-Proto`). (`caufa_portal/settings.py`, `.env.example`)
- **VPS Nginx (`deploy/nginx.prod.conf`):** 443 only, TLS 1.2/1.3 + strong ciphers, OCSP stapling, `http → https` (ACME exception), HSTS/CSP/`X-Content-Type-Options`/Referrer at edge, `/media/backups` hard-404, WS proxy to Daphne `:5000`. Provisioned by `deploy/enable_prod_tls.sh` (Certbot + renew cron).
- **Shared cPanel (`deploy/cpanel.htaccess`):** HTTPS force + deny `*.sql|*.db|*.zip|.env`, static cache headers. AutoSSL on host.
- **Local dev:** `deploy/nginx.conf` + `scripts/setup_local_tls.ps1` (mkcert) or plain `runserver`; `HTTPS_ENABLED` flag distinguishes the two.
- **Fail-closed prod:** placeholder `SECRET_KEY` refused, `DEBUG=False` enforced, no `*` hosts, `REDIS_URL` required unless `SINGLE_WORKER_MODE`, Turnstile keys required. HSTS-preload checker: `scripts/check_hsts_preload.ps1`.

### 2. Cookies, sessions & single-login

- `Secure + HttpOnly (session) + SameSite=Lax`, CSRF cookie readable for `fetch` + `Lax`. 8 h absolute expiry (`SESSION_EXPIRE_HOURS`) + idle timeout (Zero-Trust-editable, default 30 min) + per-minute activity touch.
- **Single-login:** new officer login revokes old `AccessSession` + push notice. Screen-lock + auto-signout, `NoCacheMiddleware` sends `no-store` on HTML (dev), per-device session list with remote revoke. (`core_system/middleware.py`, `auth_utils.py`)

### 3. Authentication & password policy

- **Hashing:** Argon2id (OWASP) primary, legacy PBKDF2-SHA256 260k auto-upgrades on login, unsalted-SHA rejected outright.
- **Action PIN:** 4-digit, PBKDF2-200k salted, trivial-PIN reject (`0000`/`1234`/…), 3 fails → doubling lockout 1 min → 8 h. Required (`X-Action-PIN` header) on final approvals; MFA-grant reset flow. (`officer_pin.py`, `officer_pin_views.py`)
- **Password rules:** 8+ chars with upper/lower/digit/special, server-enforced with strength meter.
- **Login throttle:** 5 attempts per user+IP / 15 min + 10 per IP / 15 min (cache + DB fallback). (`login_throttle.py`)
- **MFA:** email OTP (HMAC-SHA256, 30 s × 10 steps = 5 min window) + authenticator TOTP (RFC 6238) + 10 single-use hashed backup codes + push OTP; 5-min rate limit; `otp_killswitch.py` / `email_killswitch.py` break-glass. (`services/mfa_service.py`, `gmail_otp_emailer.py`)

### 4. Zero-Trust (per-request risk engine)

- `ZeroTrustMiddleware` checks expiry/revoke/idle **every request**, then officer-only risk eval via `services/zt_service.py`: IP/network drift (2-sighting confirm → password lock), User-Agent/environment baseline, heartbeat-loss auto-lock, `device_binding.py` DPoP-lite HMAC (`X-Device-Id/Proof` + HttpOnly cookie-pair fallback, `mtls_fp` ready).
- Sticky verdicts: `hard → OTP challenge (/zt-challenge)`, `medium → notify + audit`, response headers `X-ZT-*`. Route guards in `guards.py` (`require_officer_session`, `require_role`, `require_zero_trust`), tunable timers in `zt_settings.py`. (`middleware.py`, `zt_service.py`, `turnstile.py`)

### 5. Bot, CSRF & abuse protection

- **Cloudflare Turnstile** server-verified (3 s timeout, localhost/LAN bypass, enforced on public + login), plus `offline_botcheck` + `botcheck_views` fallback. (`turnstile.py`)
- **CSRF:** `CSRF_TRUSTED_ORIGINS` + AJAX-aware `csrf_failure` (JSON for `fetch`); `FetchMetadataGuard` returns 403 on cross-site POST as backstop for the 58 `csrf_exempt` realtime/dashboard endpoints. (`middleware.py`, `csrf_views.py`)

### 6. URL encryption & signing (anti-enumeration / anti-tamper)

- `url_obfuscation.py`: Fernet envelope `?x=` (hides IDs in address bar) + HMAC `?_s=` (signs API calls, auto-attached by `url_obf.js` via per-login subkey). Tampered/unsigned → branded 404 (`handler404`), never a stack trace.
- `UrlObfuscationMiddleware` + kill-switch `URL_OBFUSCATION_ENABLED` + strict mode `URL_OBFUSCATION_REQUIRE_SIGNATURE` (keeps old bookmarks working until all clients sign). Public/push/registration exempt. (`url_obfuscation_views.py`, `templatetags/url_obf.py`)

### 7. Headers & XSS

- `SecurityHeadersMiddleware`: Content-Security-Policy (`self` + `unsafe-inline` + pinned `cdnjs/tailwind/jsdelivr/challenges.cloudflare`, `object-src 'none'`, `base-uri/form-action/frame-ancestors 'self'`, `upgrade-insecure-requests`), `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`. Uploads never served by MIME sniffing.

### 8. Input validation & secure uploads

- `secure_upload.py`: 10 MiB cap, allow/deny extension lists, magic-byte + Pillow re-encode verify, `uuid + slug` filenames under `secure_uploads/%Y%m%d`, SHA-256 + normalized-image dedup (409 on duplicate). ISU-email-only guard (`isu.edu.ph`), other-campus / dues-backfill / unpaid-months guards. (`isu_email_guard.py`, `other_campus_guard.py`, …)

### 9. Data, database & audit

- **DB:** MySQL-only, `STRICT_TRANS_TABLES`, `CONN_MAX_AGE=0` + health checks. Optional **MySQL TLS** (`DB_SSL_CA/CERT/KEY` + `VERIFY_IDENTITY` + `ENFORCE` fail-closed; `deploy/mysql_tls.cnf` + `mysql_tls_server.sql` `REQUIRE X509`); `check_db_tls` command proves it. (`caufa_portal/settings.py`)
- **At-rest encryption:** Fernet `EncryptedChar/TextField` (`mfa_secret`, `contact_number`, …) via `DATA_ENCRYPTION_KEY`; backups via `BACKUP_ENCRYPTION_KEY` (both derived from `SECRET_KEY` when empty). (`fields.py`)
- **Audit:** `GlobalAuditTrail` / `RevisionLog` / `LoginAttemptLog` / `SensitiveReadLog` with role-scoped views + audit-trail verify queue + `audit_trail_utils.py`. ~70 `tests_*.py` cover aid, dues, auth, ZT, headers, URL-obfuscation, backup/restore.

### 10. Email safety

- `FallbackSMTPBackend` (primary Gmail → fallback cPanel), `EMAIL_REQUIRE_TLS=True` **fail-closed** (refuses plaintext SMTP — OTP codes + app passwords cross this wire), 30 s timeout, 450/day cap, kill-switch enforced at the backend. (`email_backends.py`, `services/email_service.py`)

### 11. Backups & recovery

- Encrypted dumps **outside webroot** (`SECURE_BACKUP_ROOT`, default `CAUFA-backups/`); legacy `media/backups` never served (Nginx 404 + `.htaccess`/`web.config` deny). In-app President → Backups UI + `run_backup_scheduler [--once]`, local `scripts/backup_*.ps1` + rclone-to-Drive + Task Scheduler (`install_backup_tasks.ps1` daily 00:00/00:30). Monthly restore drill per `BACKUP_RESTORE.md`; `tests_backup_access/restore` prove the deny + round-trip. (`services/backup_service.py`)

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Framework | Django 5.1, Django REST + django-filter + django-cors (installed), Channels 4 / Daphne (WS) |
| DB / cache | MySQL 8 (PyMySQL + mysqlclient local), `STRICT_TRANS_TABLES`; django-redis + channels-redis (VPS prod) / locmem (dev, cPanel) |
| Auth/crypto | Argon2id + PBKDF2, PyJWT (installed; sessions use custom `AccessSession` tokens), Fernet field + URL encryption, HMAC device binding |
| Jobs / mail | APScheduler (in-process) or cPanel cron, queued `OutgoingEmail`, Gmail + cPanel SMTP failover |
| Docs / media | ReportLab + WeasyPrint + openpyxl (PDF/XLSX), Pillow + qrcode, pywebpush (VAPID) |
| Frontend | Vendored-offline htmx 2.0.4 + Turbo + Tailwind-play + SweetAlert2 + Flatpickr + Chart.js + FA 6.5.2, PWA manifest + service worker |
| Human checks | Cloudflare Turnstile + offline botcheck |
| Tests | pytest-django, ~70 test modules |

---

## Deployment modes

| Mode | How it runs | Notes |
|------|-------------|-------|
| **Local dev** | `start-dev.ps1` / `start.ps1` → runserver / Daphne `127.0.0.1:8000/5000`, MySQL `3306/3307`, locmem, in-process scheduler | `DEBUG=True`, `HTTPS_ENABLED=False` (or True behind mkcert Nginx) |
| **VPS prod** | `deploy/nginx.prod.conf` → Daphne, Let's Encrypt via `enable_prod_tls.sh`, `APP_ENV=production` + `REDIS_URL`, MySQL TLS, `collectstatic → staticfiles/` | Full WS + Redis + scheduler, HSTS preload-ready |
| **cPanel shared** | `passenger_wsgi.py` (WSGI), `requirements-cpanel.txt` (no daphne/gunicorn/mysqlclient/weasyprint/redis/browser-reload), `CPANEL_MODE=True` ⇒ `SINGLE_WORKER_MODE` + scheduler off | Static via host mapping, 8 cron jobs (`deploy/cpanel-cron.txt`), AutoSSL + `.htaccess`, WS degrades to polling, backups outside `public_html` |

Env template: `.env.example` (safe to commit) → copy to `.env` (never commit). Production needs fresh `SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`), `ALLOWED_HOSTS`, `BASE_URL`, `REDIS_URL`, DB + mail credentials.

---

## Project structure

```text
caufa_portal/        Django project (settings, urls, asgi/wsgi, tests)
core_system/         Single monolithic app — models (~60), role views,
                     middleware/guards/auth, services, templatetags,
                     management commands (24), migrations, ~70 tests
templates/website/   Public + Member/Treasurer/Auditor/President/
                     Secretary/PIO/Superadmin/SystemBackup + partials
templates/emails/    ~50 transactional templates (OTP, claims, aids,
                     dues, payroll, registration, ZT…)
static/              css/js/img/audio/vendor (pinned offline) + PWA
deploy/              nginx[.prod].conf, cpanel.htaccess, cpanel-cron.txt,
                     mysql_tls.*, enable_prod_tls.sh
scripts/             backup/restore, TLS setup, HSTS check, PWA icons…
CAUFA-backups/       Encrypted dumps (outside webroot in prod)
BACKUP_RESTORE.md · REPORTS.MD · MANUAL_SETUP_TODO.md
```

---

## Getting started

```powershell
# 1. Env + deps
copy .env.example .env
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. DB (MySQL 8) + migrate + run
python manage.py migrate
python manage.py runserver        # or .\start-dev.ps1 (Daphne + scheduler)
```

cPanel: `pip install -r requirements-cpanel.txt`, set `CPANEL_MODE=True`, wire the 8 cron lines from `deploy/cpanel-cron.txt`, map `/static/` per host docs.

---

## Testing & operations

```powershell
pytest -q
python manage.py check_db_tls
python manage.py process_emails --otp-only
python manage.py run_backup_scheduler --once
.\scripts\check_hsts_preload.ps1
```

- **Backups:** see `BACKUP_RESTORE.md` (monthly restore test required).
- **Reports:** see `REPORTS.MD` (builder matrix + layouts LP1–LP5).
- **Manual setup:** see `MANUAL_SETUP_TODO.md`.
- **Cron (cPanel):** see `deploy/cpanel-cron.txt`.

---

*Built as a capstone project for ISU-Cauayan — secure by default, auditable by design, deployable anywhere from a laptop to a VPS to shared cPanel.*
