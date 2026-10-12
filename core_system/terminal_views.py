"""Break-glass web terminal (/terminal/) for hosts with no SSH.

Triple-gated: TERMINAL_ENABLED flag + Superadmin session + 4-char dev PIN
(TERMINAL_PIN in server .env). There is deliberately NO raw shell here:
every command is matched against a fixed allowlist and executed as an
argument list (never shell=True), so shell metacharacters (;, &&, |, $, ``,
...) are rejected instead of interpreted. `runserver` and `git` are NOT
offered: Passenger already serves the site and deploys are zip uploads.

PIN math: 4 alphanumeric chars = ~1.7M combos, but 5 wrong tries lock the
IP out for 15 minutes (~480 guesses/day/IP), and an attacker first needs a
hijacked Superadmin session. Attempts are logged without the entered value.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from core_system.guards import require_role

logger = logging.getLogger(__name__)

BASE_DIR = settings.BASE_DIR
MANAGE_PY = str(Path(BASE_DIR) / "manage.py")
LOG_DIR = Path(BASE_DIR) / "logs"
TERMINAL_LOG = LOG_DIR / "terminal.log"

_UNLOCK_SESSION_KEY = "terminal_unlocked_at"
_UNLOCK_TTL_SECONDS = 30 * 60
_MAX_PIN_ATTEMPTS = 5
_PIN_LOCKOUT_SECONDS = 15 * 60
_PIN_RE = re.compile(r"^[A-Za-z0-9]{4}$")
_PIP_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,60}$")
_USERNAME_RE = re.compile(r"^[\w.@+\-]{3,150}$")
_OUTPUT_CAP = 100_000
_CMD_TIMEOUT_SECONDS = 240

_RUN_LOCK = threading.Lock()

HELP_TEXT = """Allowed commands (type 'help' anytime):
  status                    python version, DB ping, worker pid
  check                     Django system check
  migrate                   apply pending database migrations
  migrate --check            show only whether migrations are pending
  showmigrations            list applied / pending migrations
  collectstatic             collect static files (automatic --noinput)
  createsuperuser           (use the form below, NOT inline) Django /admin/ account
  pip install               install server requirements.txt
  pip list                  installed packages
  pip show <name>           package details
  logs [passenger|cron|terminal] [lines]   tail a server log (default 50, max 200)
  db tables                 list database tables (read-only)
  db count &lt;table&gt;        row count of one table (read-only)
  db describe &lt;table&gt;     columns of one table (read-only)
  lock                      lock the terminal (PIN needed again)
NOT available here (PC-only): runserver (Passenger serves the site), git (deploys are zip uploads).
Full SQL stays in phpMyAdmin — the 'mysql' client itself can shell out, so it is never allowed here."""


def _terminal_configured() -> bool:
    """Master switch + well-formed PIN. Anything else = locked, fail closed."""
    if not getattr(settings, "TERMINAL_ENABLED", False):
        return False
    return bool(_PIN_RE.match((getattr(settings, "TERMINAL_PIN", "") or "")))


def _client_ip(request: HttpRequest) -> str:
    try:
        from core_system.services.zt_service import get_client_ip

        return get_client_ip(request) or "0.0.0.0"
    except Exception:
        return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _fail_key(ip: str) -> str:
    return f"terminal:pinlock:{ip}"


def _pin_fails(ip: str) -> int:
    try:
        return int(cache.get(_fail_key(ip)) or 0)
    except Exception:
        return 0


def _bump_pin_fails(ip: str) -> None:
    try:
        cache.set(_fail_key(ip), _pin_fails(ip) + 1, _PIN_LOCKOUT_SECONDS)
    except Exception:
        logger.exception("terminal pin-fail counter failed")


def _clear_pin_fails(ip: str) -> None:
    try:
        cache.delete(_fail_key(ip))
    except Exception:
        pass


def _is_unlocked(request: HttpRequest) -> bool:
    try:
        ts = float(request.session.get(_UNLOCK_SESSION_KEY) or 0)
    except (TypeError, ValueError):
        return False
    return (time.time() - ts) < _UNLOCK_TTL_SECONDS


def _superadmin_guard(request: HttpRequest):
    """Superadmin session first — the PIN is the second factor, not a login."""
    return require_role(request, role="Superadmin")


def _json_body(request: HttpRequest) -> dict:
    try:
        return json.loads((request.body or b"").decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def _audit(request: HttpRequest, cmd_display: str, ok: bool, ms: int) -> None:
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "actor": request.session.get("username") or request.session.get("officer_id"),
        "role": request.session.get("role"),
        "ip": _client_ip(request),
        "cmd": cmd_display[:200],
        "ok": bool(ok),
        "ms": int(ms),
    }
    logger.info("terminal cmd actor=%s ip=%s ok=%s ms=%d cmd=%s",
                entry["actor"], entry["ip"], entry["ok"], entry["ms"], entry["cmd"])
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TERMINAL_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        logger.exception("terminal audit append failed")


@require_GET
def terminal_page(request: HttpRequest) -> HttpResponse:
    guard = _superadmin_guard(request)
    if guard is not None:
        return guard
    if not _terminal_configured():
        return render(request, "website/Superadmin/terminal.html", {
            "terminal_state": "disabled",
        })
    if not _is_unlocked(request):
        return render(request, "website/Superadmin/terminal.html", {
            "terminal_state": "locked",
        })
    return render(request, "website/Superadmin/terminal.html", {
        "terminal_state": "open",
        "terminal_help": HELP_TEXT,
    })


@require_POST
def terminal_unlock(request: HttpRequest) -> HttpResponse:
    guard = _superadmin_guard(request)
    if guard is not None:
        return guard
    if not _terminal_configured():
        return JsonResponse({"ok": False, "error": "Terminal is disabled."}, status=403)
    ip = _client_ip(request)
    if _pin_fails(ip) >= _MAX_PIN_ATTEMPTS:
        logger.warning("terminal unlock locked-out ip=%s", ip)
        return JsonResponse(
            {"ok": False, "error": "Too many wrong tries. Wait 15 minutes."}, status=429)
    pin = str((_json_body(request).get("pin") or "")).strip()
    # Same generic message for bad format and wrong value: never tell an
    # attacker which half of the secret they got right.
    expected = getattr(settings, "TERMINAL_PIN", "") or ""
    if not _PIN_RE.match(pin) or not secrets.compare_digest(pin, expected):
        _bump_pin_fails(ip)
        remaining = max(0, _MAX_PIN_ATTEMPTS - _pin_fails(ip))
        logger.warning("terminal unlock failed ip=%s remaining=%d", ip, remaining)
        return JsonResponse(
            {"ok": False, "error": f"Incorrect code. {remaining} tries left."}, status=403)
    _clear_pin_fails(ip)
    request.session[_UNLOCK_SESSION_KEY] = time.time()
    logger.info("terminal unlocked ip=%s", ip)
    return JsonResponse({"ok": True})


@require_POST
def terminal_lock(request: HttpRequest) -> HttpResponse:
    guard = _superadmin_guard(request)
    if guard is not None:
        return guard
    request.session.pop(_UNLOCK_SESSION_KEY, None)
    return JsonResponse({"ok": True})


def _server_status() -> str:
    lines = [f"python {sys.version.split()[0]}  pid={os.getpid()}"]
    try:
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        lines.append(f"database OK ({connection.vendor})")
    except Exception as exc:
        lines.append(f"database FAILED: {exc.__class__.__name__}: {exc}")
    try:
        from django.core.cache import caches

        lines.append(f"cache backend: {settings.CACHES['default']['BACKEND']}")
        caches["default"].set("terminal:ping", "pong", 10)
        lines.append("cache write/read OK")
    except Exception as exc:
        lines.append(f"cache FAILED: {exc.__class__.__name__}: {exc}")
    lines.append(f"debug={'ON (dev)' if settings.DEBUG else 'off (prod)'}")
    lines.append(f"cpanel_mode={'on' if getattr(settings, 'CPANEL_MODE', False) else 'off'}")
    return "\n".join(lines)


def _tail_log(name: str, count: int) -> tuple[bool, str]:
    allowed = {"passenger": "passenger.log", "cron": "cron.log", "terminal": "terminal.log"}
    if name not in allowed:
        return False, "Usage: logs [passenger|cron|terminal] [lines]"
    count = max(1, min(int(count or 50), 200))
    path = LOG_DIR / allowed[name]
    if not path.exists():
        return True, f"(no {allowed[name]} yet)"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-count:]
        return True, "".join(tail) or "(empty)"
    except Exception as exc:
        return False, f"Cannot read log: {exc.__class__.__name__}: {exc}"


def _db_tables() -> tuple[bool, str]:
    """Read-only table list. Never executes user-supplied SQL."""
    try:
        from django.db import connection

        names = sorted(connection.introspection.table_names())
        return True, "\n".join(names) or "(no tables)"
    except Exception as exc:
        return False, f"Database FAILED: {exc.__class__.__name__}: {exc}"


def _db_validated_table(name: str) -> str | None:
    """Return the table name only if it is a real table (safe to quote)."""
    if not re.match(r"^[A-Za-z0-9_]{1,64}$", name or ""):
        return None
    try:
        from django.db import connection

        if name in connection.introspection.table_names():
            return name
    except Exception:
        return None
    return None


def _db_count(name: str) -> tuple[bool, str]:
    table = _db_validated_table(name)
    if table is None:
        return False, "Unknown table. Use 'db tables' to list real ones."
    try:
        from django.db import connection

        quoted = connection.ops.quote_name(table)
        with connection.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {quoted}")
            (count,) = cur.fetchone()
        return True, f"{table}: {count} row(s)"
    except Exception as exc:
        return False, f"Database FAILED: {exc.__class__.__name__}: {exc}"


def _db_describe(name: str) -> tuple[bool, str]:
    table = _db_validated_table(name)
    if table is None:
        return False, "Unknown table. Use 'db tables' to list real ones."
    try:
        from django.db import connection

        cols = connection.introspection.get_table_description(
            connection.cursor(), table)
        lines = [f"{c.name}  {c.type_code}" + ("" if c.null_ok else "  NOT NULL")
                 for c in cols]
        return True, f"{table}:\n" + "\n".join(lines)
    except Exception as exc:
        return False, f"Database FAILED: {exc.__class__.__name__}: {exc}"
    """Execute a fixed argument list. NEVER shell=True — no metacharacters run."""
    started = time.time()
    try:
        with _RUN_LOCK:
            proc = subprocess.run(
                args,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=_CMD_TIMEOUT_SECONDS,
                env={**os.environ, **(extra_env or {})},
            )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out[:_OUTPUT_CAP]
    except subprocess.TimeoutExpired:
        ms = int((time.time() - started) * 1000)
        return 124, f"(timed out after {_CMD_TIMEOUT_SECONDS}s, {ms}ms elapsed)"
    except Exception as exc:
        return 1, f"Cannot start process: {exc.__class__.__name__}: {exc}"


def _dispatch(raw: str, payload: dict) -> tuple[str, bool, str]:
    """Map raw input to one allowlisted action.

    Returns (audit_label, ok, output). Passwords never appear in the label.
    """
    text = (raw or "").strip()
    if not text:
        return "(empty)", False, "Type 'help' for allowed commands."
    if len(text) > 500:
        return "(too long)", False, "Command too long (max 500 chars)."
    try:
        parts = shlex.split(text, posix=True)
    except ValueError:
        return "(unparseable)", False, "Could not parse that. Type 'help'."
    if not parts:
        return "(empty)", False, "Type 'help' for allowed commands."
    head = parts[0]

    if head == "help":
        return "help", True, HELP_TEXT

    if head == "status":
        if len(parts) != 1:
            return "status (bad args)", False, "Usage: status"
        return "status", True, _server_status()

    if head == "lock":
        if len(parts) != 1:
            return "lock (bad args)", False, "Usage: lock"
        return "lock", True, "__LOCK__"

    if head == "logs":
        name = (parts[1] if len(parts) > 1 else "passenger").lower()
        try:
            count = int(parts[2]) if len(parts) > 2 else 50
        except (ValueError, IndexError):
            return "logs (bad args)", False, "Usage: logs [passenger|cron|terminal] [lines]"
        if len(parts) > 3:
            return "logs (bad args)", False, "Usage: logs [passenger|cron|terminal] [lines]"
        ok, out = _tail_log(name, count)
        return f"logs {name}", ok, out

    if head == "db":
        if len(parts) == 2 and parts[1] == "tables":
            ok, out = _db_tables()
            return "db tables", ok, out
        if len(parts) == 3 and parts[1] in ("count", "describe"):
            fn = _db_count if parts[1] == "count" else _db_describe
            ok, out = fn(parts[2])
            return f"db {parts[1]} {parts[2]}", ok, out
        return "db (bad args)", False, (
            "Usage: db tables  |  db count <table>  |  db describe <table>")

    if head in ("migrate", "showmigrations", "check", "collectstatic"):
        rest = parts[1:]
        if head == "migrate" and rest not in ([], ["--check"]):
            return "migrate (bad args)", False, "Usage: migrate  OR  migrate --check"
        if head in ("showmigrations", "check", "collectstatic") and rest:
            return f"{head} (bad args)", False, f"Usage: {head}  (no extra words)"
        args = [sys.executable, MANAGE_PY, head, *rest]
        if head == "collectstatic":
            args.append("--noinput")
        rc, out = _run_subprocess(args)
        label = " ".join([head, *rest]).strip()
        return label, rc == 0, out or "(no output)"

    if head == "createsuperuser":
        # Passwords must never travel inside the typed line (it stays in
        # scrollback history and the audit log) — the page sends them as
        # separate fields and they are redacted everywhere below.
        username = str(payload.get("username") or "").strip()
        email = str(payload.get("email") or "").strip()
        password = str(payload.get("password") or "")
        if parts[1:]:
            return "createsuperuser (bad args)", False, (
                "Use the account form under the terminal (username + email + "
                "password fields) — never type the password into the command line.")
        if not _USERNAME_RE.match(username):
            return "createsuperuser (bad username)", False, (
                "Username: 3-150 chars, letters/digits plus . @ + - _")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return "createsuperuser (bad email)", False, "Enter a valid email address."
        try:
            from core_system.auth_utils import validate_new_password
        except Exception:
            return "createsuperuser (unavailable)", False, "Password checker unavailable."
        problems = validate_new_password(password)
        if problems:
            return "createsuperuser (weak password)", False, " ".join(problems)
        args = [sys.executable, MANAGE_PY, "createsuperuser",
                "--noinput", "--username", username, "--email", email]
        rc, out = _run_subprocess(args, {"DJANGO_SUPERUSER_PASSWORD": password})
        # NOTE: this makes a Django /admin/ account, NOT a dashboard login.
        # Dashboard logins are OfficerUser rows (the President creates those).
        note = "\n(Django /admin/ account — dashboard logins are separate OfficerUser rows.)"
        return f"createsuperuser {username} (password redacted)", rc == 0, (out or "(no output)") + note

    if head == "pip":
        rest = parts[1:]
        if rest == ["list"]:
            rc, out = _run_subprocess([sys.executable, "-m", "pip", "list"])
            return "pip list", rc == 0, out or "(no output)"
        if len(rest) == 2 and rest[0] == "show" and _PIP_NAME_RE.match(rest[1]):
            rc, out = _run_subprocess([sys.executable, "-m", "pip", "show", rest[1]])
            return f"pip show {rest[1]}", rc == 0, out or "(not installed)"
        if rest == ["install"]:
            rc, out = _run_subprocess(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            return "pip install -r requirements.txt", rc == 0, out or "(no output)"
        return "pip (bad args)", False, (
            "Allowed: pip install  |  pip list  |  pip show <name>")

    return f"({head} rejected)", False, (
        f"'{head}' is not allowed here. Type 'help' for allowed commands.\n"
        "PC-only: runserver (Passenger serves the site), git (deploys are zip uploads).")


@require_POST
def terminal_run(request: HttpRequest) -> HttpResponse:
    guard = _superadmin_guard(request)
    if guard is not None:
        return guard
    if not _terminal_configured():
        return JsonResponse({"ok": False, "error": "Terminal is disabled."}, status=403)
    if not _is_unlocked(request):
        return JsonResponse({"ok": False, "error": "Locked. Enter the dev code again."}, status=403)
    payload = _json_body(request)
    started = time.time()
    label, ok, output = _dispatch(str(payload.get("cmd") or ""), payload)
    ms = int((time.time() - started) * 1000)
    _audit(request, label, ok, ms)
    if output == "__LOCK__":
        request.session.pop(_UNLOCK_SESSION_KEY, None)
        return JsonResponse({"ok": True, "output": "Locked. PIN needed again.", "locked": True})
    status = 200 if ok else 400
    # Shell-style exit code for the terminal look (0 = fine).
    return JsonResponse({"ok": ok, "output": output, "ms": ms}, status=status)
