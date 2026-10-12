# CAUFASYSTEM — Setup TODO (the ONLY guide, read top to bottom)

> Words used below: **cPanel** = your hosting control panel (clicks only, no commands).
> **PC** = your home Windows computer (this is where you type commands).
> Replace `USER` = cPanel username, `DOMAIN` = `isucaufa-fms.online`,
> `APPDIR` = app folder name you choose (example: `caufasystem`).

---

## PART A — Local PC setup (do once)

- Install MySQL 8 and remember if it runs on port `3306` or `3307`
  (`netstat -ano | findstr 330` shows you).
- Copy `.env.example` to `.env`, then fill the blanks:
  `SECRET_KEY` (run `python -c "import secrets; print(secrets.token_hex(32))"` and paste),
  `DB_PASSWORD` (your local MySQL password), `DB_PORT` (the port above).
- Open PowerShell in the project folder and run:
  - `python -m venv venv`
  - `.\venv\Scripts\Activate.ps1`
  - `pip install -r requirements.txt`
  - `python manage.py migrate`
  - `python manage.py createsuperuser` (type admin login when asked)
  - `python manage.py create_position_rank_table`
  - `python manage.py seed_position_ranks`
- Start the site: `.\start-dev.ps1`, open `http://127.0.0.1:8000/`.
- Rotate the leaked passwords in `.env` (Gmail App Passwords + cPanel mailbox
  `Loleris1234!`): Google Account → 2-Step → App Passwords for Gmail;
  cPanel → Email Accounts → Change Password for the mailbox. Never commit `.env`.

---

## PART B — Put the site on cPanel (no SSH needed)

**B1. cPanel → Databases → MySQL Database Wizard (clicks)**

- Create database `caufadb` (full name becomes `USER_caufadb` — write it down).
- Create user `caufauser` with a generated strong password (save it).
- Tick ALL PRIVILEGES.

**B2. cPanel → Databases → Remote MySQL (clicks)**

- Add your home IP (see it at `https://whatismyip.host`).
- If PC commands later say "Can't connect", your home IP changed — re-add it here.

**B3. PC → zip the code (clicks)**

- Zip the project folder WITHOUT: `venv/`, `.git/`, `certs/`, `CAUFA-backups/`,
  `_archive/`, `staticfiles/`, `db.sqlite3`, `__pycache__/`.

**B4. cPanel → Files → File Manager (clicks)**

- Go to `/home/USER` (NOT inside `public_html`), Upload the zip, Extract it,
  rename the folder to `APPDIR`.
- Inside `APPDIR`, rename `requirements.txt` → `requirements-local.txt`,
  then rename `requirements-cpanel.txt` → `requirements.txt`.
- Create folder `APPDIR/logs/`.
- Create file `APPDIR/.env` and paste the template from `.env.example`, filled in:
  `APP_ENV=production`, `DEBUG=False`, `CPANEL_MODE=True`,
  fresh `SECRET_KEY`, `ALLOWED_HOSTS=DOMAIN,www.DOMAIN`,
  `BASE_URL=https://DOMAIN`, `DB_HOST=localhost`, `DB_PORT=3306`,
  `DB_NAME=USER_caufadb`, `DB_USER=USER_caufauser`, `DB_PASSWORD=(B1 password)`,
  both email blocks, Turnstile prod keys, VAPID keys, two different
  `DATA/BACKUP_ENCRYPTION_KEY` values,
  `SECURE_BACKUP_ROOT=/home/USER/caufa-backups`.

**B5. cPanel → Software → Setup Python App → Create Application (clicks)**

- Python version: `3.10` or newer. Application root: `APPDIR`.
- Application URL: `DOMAIN` + `/`. Startup file: `passenger_wsgi.py`
  (do NOT edit it). Entry point: `application`.
- Passenger log file: `/home/USER/APPDIR/logs/passenger.log`.
- Click Create → click **Run Pip Install** → wait → click **RESTART**.

**B6. cPanel → Security → SSL/TLS Status (clicks)**

- Select `DOMAIN` + `www.DOMAIN` → Run AutoSSL until green.

**B7. cPanel → Files → File Manager → `public_html/.htaccess` (clicks)**

- Paste the contents of this repo's `deploy/cpanel.htaccess` into it.

**B8. cPanel → Advanced → Cron Jobs (clicks, paste these 8 lines)**

- Get `VENVPY` from the Setup Python App page (the *"Enter to the virtual
  environment"* line, ends with `/bin/python`).
- Add one cron job per line (replace `USER`/`APPDIR`/`VENVPY`):

```text
* * * * *    cd /home/USER/APPDIR && VENVPY manage.py process_emails --otp-only >> /home/USER/APPDIR/logs/cron.log 2>&1
*/2 * * * *  cd /home/USER/APPDIR && VENVPY manage.py process_emails >> /home/USER/APPDIR/logs/cron.log 2>&1
0 8 * * *    cd /home/USER/APPDIR && VENVPY manage.py send_dues_reminders >> /home/USER/APPDIR/logs/cron.log 2>&1
0 0 * * *    cd /home/USER/APPDIR && VENVPY manage.py run_backup_scheduler --once >> /home/USER/APPDIR/logs/cron.log 2>&1
0 1 * * *    cd /home/USER/APPDIR && VENVPY manage.py deactivate_overdue_members >> /home/USER/APPDIR/logs/cron.log 2>&1
30 2 * * *   cd /home/USER/APPDIR && VENVPY manage.py purge_expired_rows >> /home/USER/APPDIR/logs/cron.log 2>&1
0 3 * * 0    cd /home/USER/APPDIR && VENVPY manage.py purge_stale_push_subscriptions >> /home/USER/APPDIR/logs/cron.log 2>&1
30 3 * * *   cd /home/USER/APPDIR && VENVPY manage.py reconcile_aid_setasides >> /home/USER/APPDIR/logs/cron.log 2>&1
```

**B9. PC → build the server database (commands, PowerShell in project folder)**

- Point this shell at the server DB (temporary, this window only):
  - `$env:DB_HOST="DOMAIN"` (or the server hostname if DOMAIN fails)
  - `$env:DB_PORT="3306"`
  - `$env:DB_NAME="USER_caufadb"`
  - `$env:DB_USER="USER_caufauser"`
  - `$env:DB_PASSWORD="(B1 password)"`
- `.\venv\Scripts\python.exe manage.py check` (must say "no issues";
  if "Can't connect", redo B2).
- `.\venv\Scripts\python.exe manage.py migrate`
- `.\venv\Scripts\python.exe manage.py createsuperuser` (server admin login)
- `.\venv\Scripts\python.exe manage.py create_position_rank_table`
- `.\venv\Scripts\python.exe manage.py seed_position_ranks`
- `.\venv\Scripts\python.exe manage.py collectstatic --noinput`
- `Remove-Item Env:\DB_HOST, Env:\DB_PORT, Env:\DB_NAME, Env:\DB_USER, Env:\DB_PASSWORD`
- Upload the generated `staticfiles/` folder to `/home/USER/APPDIR/staticfiles/`
  via File Manager.

**B10. cPanel → Setup Python App → RESTART, open `https://DOMAIN/login/`**

- Log in with the B9 admin, turn on MFA, done.
- RESTART the app again after every `.env` or file change.

**B11. Server terminal page (no SSH needed ever again)**

- In server `.env`, add `TERMINAL_ENABLED=True` and `TERMINAL_PIN=K7Q2`
  (your own 4 letters/digits) → Setup Python App → RESTART.
- Open `https://DOMAIN/terminal/` → log in as Superadmin → type the 4-char code.
- Type `help` inside. Useful commands: `migrate`, `collectstatic`, `check`,
  `status`, `pip install`, `logs passenger`, `logs cron`,
  `db tables`, `db count officer_user`, `db describe officer_user`.
- New Django `/admin/` account: use the form under the terminal
  (never type the password into the command line).
- Press **Lock** (or type `lock`) when done. 5 wrong codes = 15-minute lockout.
- NOT here on purpose: `runserver` (Passenger already serves the site),
  `git` (deploys are zip uploads — git stays on your PC).

---

## PART C — Later updates and quick fixes

- **New code:** re-zip changed files on PC → File Manager overwrite →
  Setup Python App → RESTART. (Run Pip Install again only if `requirements.txt` changed.)
- **Changed `.env`:** edit `APPDIR/.env` in File Manager → RESTART.
- **Site shows error:** File Manager → `APPDIR/logs/passenger.log` (top lines say why).
  Usual causes: typo in `.env`, wrong `DB_*`, Python older than 3.10.
  (Or open `/terminal/` → `logs passenger` — same file, no File Manager needed.)
- **CSS/images broken:** redo B9 `collectstatic` + upload `staticfiles/`, check
  `CPANEL_MODE=True` in server `.env`, RESTART.
- **Emails not sending:** check `APPDIR/logs/cron.log`, verify Gmail App Password
  and cPanel mailbox password in server `.env`.
- **Backups:** download `/home/USER/caufa-backups/` via File Manager regularly and
  keep a copy off the server. Test-restore once a month.
- **Terminal says "disabled":** set `TERMINAL_ENABLED=True` + a 4-char
  `TERMINAL_PIN` in server `.env` → RESTART.
- **Terminal says "incorrect code" / locked out:** wait 15 minutes (auto-resets),
  then type the exact `TERMINAL_PIN` from server `.env`.
- **Every terminal command is logged** to `APPDIR/logs/terminal.log` — check who
  ran what, anytime.
- **Host is missing something** (no Python 3.10+, no Remote MySQL, pip blocked):
  send support this: *"Hi, my account (USER) has no SSH. For my Django 5.1 app I
  need: (1) Python 3.10+ in Setup Python App, (2) Remote MySQL for my IP, (3) pip
  installs via the Run Pip Install button. Please advise or enable. Thanks."*

---

## Helper files (you don't read these, the steps above use them)

- `requirements-cpanel.txt` — slim package list the server installs (becomes
  `requirements.txt` on the server via the B4 rename).
- `deploy/cpanel.htaccess` — paste into `public_html/.htaccess` (step B7).
- `deploy/cpanel-cron.txt` — same 8 cron lines as B8 with explanations.
- `BACKUP_RESTORE.md` — Windows Task Scheduler backups for the local PC only.
- `REPORTS.MD` — report tracker, not setup.
- `deploy/nginx.conf`, `deploy/nginx.prod.conf`, `deploy/enable_prod_tls.sh`,
  `deploy/mysql_tls.*` — VPS-only (needs root). Ignore on shared cPanel.
