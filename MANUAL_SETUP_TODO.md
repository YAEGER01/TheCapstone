# CAUFASYSTEM — Manual Setup TODO (what YOU must do by hand)

Auto-scan of `settings.py`, `.env` vs `.env.example`, `deploy/`, `scripts/`, `passenger_wsgi.py`, `manage.py`.
Generated 2026-10-12. Code is done — everything below needs a human with passwords / server access.

> ⚠️ **`.env` currently contains LIVE secrets** (2 Gmail App Passwords + cPanel mailbox password `Loleris1234!`). It is gitignored (good) but anyone with a copy of this folder has them. **Rotate all three now** (see §1), never commit `.env`, never zip it into a public backup.

---

## 0. Quick start (local dev, happy path)

```powershell
copy .env.example .env   # then fill §1 below
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# MySQL must exist first (§2). Then:
python manage.py migrate
python manage.py createsuperuser
.\start-dev.ps1          # or .\start.ps1  (live reload)
```

Nothing else is automatic. Work through §1–§9 once per machine, §10 once on the server.

---

## 1. REPLACE — secrets / placeholder values in `.env`

Your `.env` is **missing ~15 vars** that `caufa_portal/settings.py` reads, and several values are placeholders. Fix each line:

| # | Variable | Current value (bad) | What to put | How |
|---|----------|---------------------|-------------|-----|
| 1.1 | `SECRET_KEY` | `a_new_long_random_Django_secret` (placeholder — prod refuses to boot with it) | Fresh 64-hex | `python -c "import secrets; print(secrets.token_hex(32))"` |
| 1.2 | `DB_PASSWORD` | `new_password` | Real MySQL password for `DB_USER` | `ALTER USER 'root'@'localhost' IDENTIFIED BY '...'` |
| 1.3 | `DB_PORT` | `3307` in `.env` vs `3306` in `.env.example` | Confirm which port MySQL actually listens on | `netstat -ano \| findstr 330` → set to match |
| 1.4 | `EMAIL_HOST_PASSWORD` (primary Gmail) | `bigk tenv qxzj buul` — **live, rotate now** | New Gmail **App Password** for `humanmale050519@gmail.com` | Google Account → 2-Step ON → App Passwords → Mail → paste 16-char (spaces stripped automatically) |
| 1.5 | Old primary account `manchoco69@gmail.com` / `jvrp tuir bpgf trqx` | Commented out but still in file — **rotate or delete** | Delete block if unused, else rotate same as 1.4 | Remove lines 13–21 if `humanmale…` is canonical |
| 1.6 | `FALLBACK_SMTP_PASSWORD` | `Loleris1234!` — **live cPanel password, rotate now** | New password for `isucaufa@isucaufa-fms.online` | cPanel → Email Accounts → Change Password → update `.env` on every host |
| 1.7 | `DEFAULT_FROM_EMAIL` | `CAUFASYSTEM <manchoco69@gmail.com>` (personal Gmail) | `CAUFASYSTEM <isucaufa@isucaufa-fms.online>` or `noreply@isucaufa-fms.online` | Must match an authenticated mailbox or Gmail rewrites/spam-filters it |
| 1.8 | `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Present — verify they belong to YOUR Cloudflare widget | Per-domain widget keys from `dash.cloudflare.com → Turnstile` | Create one widget for `localhost` (test) + one for `isucaufa-fms.online`; paste server `.env` = prod widget |
| 1.9 | `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | Present but shared with every repo copy | Regenerate **per deployment**, keep private key server-only | `python -c "from pywebpush import Vapid; v=Vapid(); v.generate_keys(); print(v.private_key, v.public_key)"` (or `generate_caufa_pwa_icons.py`-adjacent keygen) |
| 1.10 | **Missing — add:** `APP_ENV`, `ALLOWED_HOSTS`, `BASE_URL` | Absent (defaults to dev/`*`/`localhost:8000`) | Dev: `APP_ENV=development`; Prod **must** have `APP_ENV=production`, `ALLOWED_HOSTS=isucaufa-fms.online,www.isucaufa-fms.online`, `BASE_URL=https://isucaufa-fms.online` or prod **refuses to boot** | Copy from `.env.example` lines 10–15 |
| 1.11 | **Missing — add:** `REDIS_URL` | Absent → dev uses locmem (fine), **prod crashes on boot without it** | e.g. `redis://:STRONGPASS@127.0.0.1:6379/1` | Install Redis + `requirepass` first (§5) |
| 1.12 | **Missing — add:** `DATA_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY` | Absent → derived from `SECRET_KEY` (works, fragile) | Two **different** Fernet keys | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` ×2; store offline; rotating `SECRET_KEY` later orphans derived-key data |
| 1.13 | **Missing — add:** `EMAIL_REQUIRE_TLS=True`, `HTTPS_ENABLED`, `SECURE_HSTS_SECONDS`, `DB_SSL_*`, `URL_OBFUSCATION_*`, `JWT_SECRET_KEY`/`ACCESS_TOKEN_EXPIRE_MINUTES`/`SESSION_EXPIRE_HOURS` | Absent → insecure/plaintext defaults | Copy whole blocks from `.env.example` (§33–61) | Prod: `HTTPS_ENABLED=True`, `DB_SSL_ENFORCE=True` + `DB_SSL_CA` path, `EMAIL_REQUIRE_TLS=True` |
| 1.14 | `DATABASE_URL` | In `.env.example` but **ignored by `settings.py`** (it reads `DB_HOST/NAME/USER/PASSWORD/PORT` only) | Delete it or ignore it | Don't rely on it — set the `DB_*` vars |
| 1.15 | `DEBUG` | `True` (correct for dev) | Prod server `.env` **must** be `DEBUG=False` (`APP_ENV=production` + `DEBUG=True` = boot error) | Set on server only |

After editing: `python manage.py check --deploy` must pass with prod values.

---

## 2. REPLACE — hardcoded machine paths in repo

| File:line | Bad value | Fix |
|-----------|-----------|-----|
| `deploy/nginx.conf:54-55` | `ssl_certificate C:/Users/maday/PROJECTS/CAUFASYSTEM/certs/...` | Point at YOUR `certs/` dir, or on server **don't use this file at all — use `deploy/nginx.prod.conf`** |
| `deploy/nginx.conf:89,101` (commented examples) | Same `C:/Users/maday/...` static/media aliases | Update if you ever uncomment static-serving |
| `core_system/test_htmx.py:81` | `r"C:\Users\maday\PROJECTS\CAPSTONE_PROJECT"` (stale, wrong folder name) | Update to your path or delete the test |
| `BACKUP_RESTORE.md:37` | `cd C:\Users\maday\PROJECTS\CAUFASYSTEM` | Replace with target machine path |
| `scripts/install_backup_tasks.ps1` default `-BackupRoot ..\CAUFA-backups` | Relative — resolves differently per host | Pass explicit `-BackupRoot D:\CAUFA-backups` (outside webroot, outside repo) |
| `caufa_portal/settings.py:56-58,398,400` + `deploy/*.conf`, `scripts/check_hsts_preload.ps1`, `guards.py`, `notifications.py`, `mfa_service.py` | `isucaufa-fms.online` / `mailto:isucaufa@isucaufa-fms.online` baked in | Correct for this project — only change if domain changes (then update all + Cloudflare + certbot + `.env`) |

---

## 3. MANUAL — MySQL / MariaDB (once per machine)

- [ ] Install MySQL 8 / MariaDB, note port (3306 vs your 3307). Create DB + user: `CREATE DATABASE isucaufafms_capstone_project_db CHARACTER SET utf8mb4; CREATE USER 'caufa_app'@'%' IDENTIFIED BY '...'; GRANT ALL ON <db>.* TO ...;`
- [ ] Dev: `python manage.py migrate` then `createsuperuser`, then seed: `python manage.py create_position_rank_table`, `python manage.py seed_position_ranks`.
- [ ] Prod TLS (Django refuses plaintext when `DB_SSL_ENFORCE=True`): on DB host `sudo mysql_ssl_rsa_setup --datadir=/var/lib/mysql --uid=mysql`, append `deploy/mysql_tls.cnf` to my.cnf, restart, run `deploy/mysql_tls_server.sql` as root (change `'caufa_app'@'%'` to your user, `REQUIRE SSL` → `REQUIRE X509` once client certs exist), set `.env` `DB_SSL_CA/CERT/KEY`, verify `python manage.py check_db_tls --require` shows a cipher.
- [ ] `mysqlclient` needs MSVC C++ Build Tools on Windows; `weasyprint>=61` needs GTK/Pango (`winget install GNOME.gtk3` or use WSL) — `pip install -r requirements.txt` fails without them.

## 4. MANUAL — TLS / HTTPS

- [ ] **Local dev (optional, for Secure cookies + HSTS testing):** `.\scripts\setup_local_tls.ps1` (installs mkcert, writes gitignored `certs/`), set `.env` `HTTPS_ENABLED=True`, install nginx, replace `C:\nginx\conf\nginx.conf` with `deploy/nginx.conf` (fix §2 paths), `nginx -t; nginx -s reload`, open `https://localhost/`. `manage.py runserver` itself stays plain HTTP — nginx is the terminator.
- [ ] **Production (on the Linux server as root, once):** point DNS `isucaufa-fms.online` + `www` at server, open 80/443, then `sudo bash deploy/enable_prod_tls.sh admin@isucaufa-fms.online` (installs certbot, issues certs, installs `nginx.prod.conf`, adds weekly renewal cron, verifies chain + redirect + HSTS). Then `.\scripts\check_hsts_preload.ps1 -Domain isucaufa-fms.online` from dev; only submit to `hstspreload.org` when it passes.

## 5. MANUAL — Redis (required for prod, recommended for dev with 2+ workers)

- [ ] Install Redis, set `requirepass <strong>` (+ TLS in prod), put `REDIS_URL=redis://:PASS@127.0.0.1:6379/1` in `.env`. Without it, login lockouts are per-process and WebSockets only work on one worker — prod fails closed on purpose (`settings.py` raises without `REDIS_URL`).

## 6. MANUAL — Email + Turnstile + Push (per deployment)

- [ ] Gmail: enable 2-Step on the sender account, mint an **App Password**, paste into `EMAIL_HOST_PASSWORD`. Send a test OTP; check fallback by breaking primary temporarily.
- [ ] cPanel: create/verify `isucaufa@isucaufa-fms.online`, set strong password (§1.6), confirm port 465 SSL connects from server.
- [ ] Cloudflare Turnstile: create widgets (localhost + prod domain), paste keys; keep `TURNSTILE_REQUIRE_ON_LOCALHOST=true` in dev so login is tested realistically.
- [ ] Web Push: generate VAPID pair (§1.9), set both in `.env`, open a dashboard → allow notifications → confirm `/api/push/` registers and test push arrives. `mailto:isucaufa@isucaufa-fms.online` (VAPID `sub`) only changes if the contact address changes.

## 7. MANUAL — Backups (Windows Task Scheduler + Google Drive)

- [ ] `rclone config` → create `gdrive` remote; then `[Environment]::SetEnvironmentVariable("BACKUP_RCLONE_REMOTE","gdrive:caufa-backups","User")` (restart shell). Without it, scripts only keep local copies.
- [ ] As the project owner: `.\scripts\install_backup_tasks.ps1 -BackupRoot D:\CAUFA-backups`, then `Start-ScheduledTask -TaskName "CAUFA Database Backup"` + `"CAUFA System Backup"` and `Get-ScheduledTaskInfo` to confirm success.
- [ ] Monthly drill: `.\scripts\restore_database.ps1 -BackupFile ...` (type `RESTORE` to confirm) into a **separate** directory + `restore_system.ps1` extraction; verify login works. A backup that was never restored doesn't count.

## 8. MANUAL — cPanel / Passenger production deploy

- [ ] Upload project (excluding `venv/`, `.git/`, `certs/`, `CAUFA-backups/`, `_archive/`), create Python app, set `passenger_wsgi.py` as startup file (it already points at `caufa_portal.settings` — no edit needed unless module path changes).
- [ ] Create **server** `.env` from scratch (never copy dev): `APP_ENV=production`, `DEBUG=False`, fresh `SECRET_KEY`, real `ALLOWED_HOSTS`/`BASE_URL`, `DB_*`, both SMTP blocks, Turnstile prod keys, VAPID, `REDIS_URL`, `DB_SSL_CA`+`DB_SSL_ENFORCE=True`, `DATA/BACKUP_ENCRYPTION_KEY`, `EMAIL_REQUIRE_TLS=True`. `pip install -r requirements.txt`, `python manage.py migrate`, `collectstatic` — **note: `settings.py` currently defines no `STATIC_ROOT`, so add `STATIC_ROOT = BASE_DIR / "staticfiles"` before `collectstatic` and point nginx at it.**
- [ ] Cron/scheduler: run `run_backup_scheduler`, `process_emails`, `send_dues_reminders`, `deactivate_overdue_members`, `purge_expired_rows`, `purge_stale_push_subscriptions`, `reconcile_aid_setasides`, `archive_fiscal_term` on their schedules; one-off backfills (`backfill_*`) once after first migrate.
- [ ] First login: `createsuperuser` via SSH, sign in, enable MFA (`activate_mfa`), define position ranks, upload bylaws, set `SECURE_BACKUP_ROOT` outside webroot.

## 9. MANUAL — files that DON'T exist yet / need your decision

- [ ] **`SECURITY_MANUAL_STEPS.md` is referenced twice (`settings.py:282`, `auth_utils.py:51`) but missing.** It should document: Redis setup (§7 in that numbering), legacy unsalted PIN neutralization (step 5), and HSTS-preload steps. Create it or remove the references.
- [ ] `README.md` is just `# CAPSTONE_PROJECT` — replace with real run instructions (or keep this file as the manual and link it).
- [ ] `STATIC_ROOT` missing (§8) — add it.
- [ ] `media/backups/` still exists locally (legacy dumps). Move any `.sql/.zip/.enc` out to `SECURE_BACKUP_ROOT`; `.htaccess` + `web.config` + nginx `location ~* ^/media/(backups/...` are backstops, not a storage plan. Never serve `media/` directly from nginx without replicating those deny rules.
- [ ] `db.sqlite3` in repo root is dead (settings are MySQL-only) — delete it to avoid confusion.

## 10. Pre-launch verify (run, don't skip)

```powershell
python manage.py check --deploy
python manage.py check_db_tls --require   # prod only
.\scripts\check_hsts_preload.ps1 -Domain isucaufa-fms.online
pytest -q
```

All green + §1 rotated + monthly restore drill done = shippable.

---

### What was scanned

`caufa_portal/settings.py` (all `env_value` + prod guards), `.env` vs `.env.example` (diffed key-by-key), `passenger_wsgi.py`, `manage.py` (uvicorn wrapper), `deploy/nginx.conf` + `nginx.prod.conf` + `enable_prod_tls.sh` + `mysql_tls.*`, `scripts/setup_local_tls.ps1` + `install_backup_tasks.ps1` + `check_hsts_preload.ps1`, `BACKUP_RESTORE.md`, `media/.htaccess`, `core_system/management/commands/` (25 commands), VAPID/Turnstile/Fernet usages.
