import os as _os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_value(key, default=None, *, cast=str):
    """Return env value or default without raising if the variable is missing.

    The cast applies to the default as well: a missing variable must behave
    exactly like one explicitly set to the default (previously a default of
    "False" came back as a truthy string, silently enabling whatever flag
    it belonged to).
    """
    value = _os.getenv(key)
    if value is None or value == "":
        value = default

    if value is None:
        return None
    if cast is bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if cast is int:
        return int(value)
    if cast is float:
        return float(value)
    return value


SECRET_KEY = env_value("SECRET_KEY", "django-insecure-change-me-for-production")
DEBUG = env_value("DEBUG", "True", cast=bool)
# Comma-separated in .env (e.g. isucaufa-fms.online,www.isucaufa-fms.online).
# "*" default keeps local/ngrok dev working; prod MUST set real hostnames —
# with ["*"], Host-header attacks and cache poisoning stay possible.
ALLOWED_HOSTS = [
    h.strip() for h in str(env_value("ALLOWED_HOSTS", "*")).split(",") if h.strip()
]

# Absolute base URL used for push-notification payloads and reminder emails.
# Set BASE_URL environment variable to your public URL (e.g., https://your-domain.ngrok-free.app or https://isucaufa.org)
# Default is localhost for local development.
BASE_URL = env_value("BASE_URL", "http://localhost:8000")

# Production origins are listed by default: without them every POST from the
# real domain fails CSRF (403). Extend via CSRF_TRUSTED_ORIGINS_EXTRA in .env
# (comma-separated, full scheme+host, e.g. https://staging.example.com).
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://*.ngrok-free.app",
    "https://*.ngrok.io",
    "https://isucaufa-fms.online",
    "https://www.isucaufa-fms.online",
] + [
    o.strip()
    for o in str(env_value("CSRF_TRUSTED_ORIGINS_EXTRA", "")).split(",")
    if o.strip()
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# NOTE: the header above is only trustworthy when a proxy you control sets /
# strips it (see deploy/nginx.conf which sets X-Forwarded-Proto). Never
# expose Daphne/runserver directly to clients with this setting active.

# -------------------------
# Transport security (TLS/HTTPS) — core_system hardening
# -------------------------
# Off by default in local dev (plain `runserver` keeps working). Turn on via
#   HTTPS_ENABLED=True            (local HTTPS behind nginx + mkcert certs), or
#   APP_ENV=production            (prod is HTTPS-only, always).
# Without this, passwords, OTP codes, session cookies and device secrets all
# travel as plaintext HTTP on the local leg (ngrok only secures its public
# leg, not 127.0.0.1:5000).
APP_ENV = env_value("APP_ENV", "development")
_IS_PROD = APP_ENV.strip().lower() == "production"
_HTTPS_ON = env_value(
    "HTTPS_ENABLED", "True" if _IS_PROD else "False",
    cast=bool,
)
if _IS_PROD:
    # Fail closed: production is HTTPS-only even if HTTPS_ENABLED=False slips
    # into the environment. Downgrading Secure cookies in prod would leak the
    # session + device-proof secret over plaintext HTTP.
    _HTTPS_ON = True

# Fail-closed secrets in production. Dev keeps convenient defaults so plain
# `runserver` works; prod refuses to boot with placeholder / wildcard values
# instead of silently running with a publicly-known SECRET_KEY or open Host
# header (session/Fernet forgery, cache poisoning).
if _IS_PROD:
    from django.core.exceptions import ImproperlyConfigured as _ProdGuardError
    _PLACEHOLDER_KEYS = ("change-me", "django-insecure", "")
    if not SECRET_KEY or any(p in SECRET_KEY for p in _PLACEHOLDER_KEYS):
        raise _ProdGuardError(
            "APP_ENV=production requires a real SECRET_KEY "
            "(python -c \"import secrets; print(secrets.token_hex(32))\") — "
            "refusing to boot with the dev placeholder."
        )
    if DEBUG:
        raise _ProdGuardError(
            "APP_ENV=production requires DEBUG=False — refusing to boot with "
            "DEBUG=True (tracebacks + static serving leak internals)."
        )
    if "*" in ALLOWED_HOSTS:
        raise _ProdGuardError(
            "APP_ENV=production requires ALLOWED_HOSTS set to real hostnames "
            "(e.g. isucaufa-fms.online,www.isucaufa-fms.online) — refusing to "
            "boot with '*'."
        )

# http -> https redirect + HSTS (sent only on HTTPS responses). HSTS max-age
# default 1 year; preload submits the domain to browsers' baked-in lists.
SECURE_SSL_REDIRECT = _HTTPS_ON
SECURE_HSTS_SECONDS = env_value("SECURE_HSTS_SECONDS", 31536000 if _HTTPS_ON else 0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _HTTPS_ON
SECURE_HSTS_PRELOAD = _HTTPS_ON

# Cookies: Secure (never sent over http) + HttpOnly + SameSite. These only
# take effect when the browser sees HTTPS, so enabling them while _HTTPS_ON
# is False is harmless but useless — gate on _HTTPS_ON for clarity.
# Device-binding cookies (caufa_device_id / caufa_device_proof) are issued
# with secure=request.is_secure() at login (see core_system/auth_views.py)
# and cleared with matching path/samesite on logout (see
# core_system/device_binding.clear_device_cookies). They are security
# controls, never optional tracking: no consent opt-out may disable them.
SESSION_COOKIE_SECURE = _HTTPS_ON
CSRF_COOKIE_SECURE = _HTTPS_ON
SESSION_COOKIE_HTTPONLY = True
# Django defaults CSRF_COOKIE_HTTPONLY=True, which makes the csrftoken cookie
# unreadable to document.cookie. This app reads that cookie in 20+ places
# (static/js/* getCookie("csrftoken")) to populate the X-CSRFToken header on
# every fetch POST — with HttpOnly on, the header is sent empty and Django
# rejects it: "CSRF token from the 'X-Csrftoken' HTTP header has incorrect
# length." The token is also embedded in every rendered form via
# {% csrf_token %}, so HttpOnly adds no XSS protection here. Keep it readable.
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Align the Django session cookie with AccessSession's 8h absolute lifetime
# (see create_access_session). The server still enforces expiry + idle
# timeout, so this only stops a stale `sessionid` lingering for Django's
# 2-week default after the AccessSession is already dead.
SESSION_COOKIE_AGE = 8 * 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Misc response hardening (safe on http too).
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"
# Content-Security-Policy override (empty = built-in baseline in
# core_system.middleware.SecurityHeadersMiddleware, which allowlists the
# pinned CDN/identity hosts). Tighten here without code changes.
CSP_POLICY = env_value("CSP_POLICY", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "core_system",
    "django.contrib.staticfiles",
    "channels",
    "django_browser_reload",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Reject forged cross-site POSTs before any view (backstop for the
    # @csrf_exempt dashboards) + stamp CSP on every response.
    "core_system.middleware.FetchMetadataGuardMiddleware",
    "core_system.middleware.SecurityHeadersMiddleware",
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "core_system.middleware.NoCacheMiddleware",
    "core_system.middleware.EmailQueueKickMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "core_system.middleware.ZeroTrustMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core_system.middleware.UrlObfuscationMiddleware",
]

# -------------------------
# URL encryption & obfuscation (core_system/url_obfuscation.py)
# -------------------------
# Master kill-switch: False restores plain URLs everywhere.
URL_OBFUSCATION_ENABLED = env_value("URL_OBFUSCATION_ENABLED", "True", cast=bool)
# False (default): requests WITHOUT any token pass (old bookmarks and not
# yet migrated clients keep working); requests WITH a present-but-invalid
# token ALWAYS get the branded 404. True: missing tokens on query-bearing
# covered URLs also 404 (flip after all clients sign).
URL_OBFUSCATION_REQUIRE_SIGNATURE = env_value("URL_OBFUSCATION_REQUIRE_SIGNATURE", "False", cast=bool)
URL_OBFUSCATION_EXEMPT_PREFIXES = (
    "/admin/",
    "/static/",
    "/media/",
    "/sw.js",
    "/favicon.ico",
    "/__reload__/",
    "/api/url/",
    "/api/public/",
    "/api/push/",
    "/register/",
)

# (X_FRAME_OPTIONS is set in the transport-security block above.)

# AJAX-aware CSRF failure: fetch callers get JSON {"ok": False,
# "csrf_failed": True, ...} instead of an HTML 403 page that resp.json()
# chokes on (core_system/csrf_views.py). Normal navigations keep Django's
# default HTML page.
CSRF_FAILURE_VIEW = "core_system.csrf_views.csrf_failure"

ROOT_URLCONF = "caufa_portal.urls"
# Inside caufa_portal/settings.py

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core_system.nav_modules.nav_modules_context",
                "core_system.isu_email_guard.isu_email_guard_context",
                "core_system.url_obfuscation.url_obf_context",
            ],
            # ADD THIS BLOCK BELOW TO GLOBALLY ENABLE LOAD STATIC
            "builtins": [
                "django.templatetags.static",
            ],
        },
    },
]

WSGI_APPLICATION = "caufa_portal.wsgi.application"
ASGI_APPLICATION = "caufa_portal.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Redis (shared cache + channel layer). The login throttle (cache.incr) and
# WebSocket fan-out are per-process on locmem — a second worker/Daphne makes
# lockouts bypassable and pushes undeliverable. Set REDIS_URL and both flip
# to shared Redis with zero code changes. Production refuses to boot without
# it (fail closed); dev/test stay on locmem/in-memory.
REDIS_URL = env_value("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "TIMEOUT": 300,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        },
    }
elif _IS_PROD:
    raise _ProdGuardError(
        "APP_ENV=production requires REDIS_URL (e.g. "
        "redis://127.0.0.1:6379/1 with requirepass + TLS) — locmem cache "
        "makes login lockouts per-process and channels single-worker. "
        "See SECURITY_MANUAL_STEPS.md §7."
    )

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "caufa-cache",
        "TIMEOUT": 300,
    }
}

# Use MySQL only. The SQLite database option has been removed because it was
# causing Django to connect to the stale local database file instead of the live
# database used by the application.
#
# MySQL TLS: the live driver is PyMySQL (see caufa_portal/__init__.py shim),
# so OPTIONS use its ssl_* parameters (ssl_ca/cert/key + verify flags).
# Off by default locally; on the server set DB_SSL_CA (+ cert/key for X509
# client auth) and the wire is encrypted with the server cert verified.
# DB_SSL_ENFORCE=True fails startup loudly instead of silently going plaintext.
from django.core.exceptions import ImproperlyConfigured as _ImproperlyConfigured

_DB_SSL_CA = env_value("DB_SSL_CA", "")
_DB_SSL_CERT = env_value("DB_SSL_CERT", "")
_DB_SSL_KEY = env_value("DB_SSL_KEY", "")
_DB_SSL_VERIFY_IDENTITY = env_value("DB_SSL_VERIFY_IDENTITY", "True", cast=bool)
_DB_OPTIONS: dict = {"init_command": "SET sql_mode='STRICT_TRANS_TABLES'"}
if _DB_SSL_CA or _DB_SSL_CERT or _DB_SSL_KEY:
    if _DB_SSL_CA:
        _DB_OPTIONS["ssl_ca"] = _DB_SSL_CA
    if _DB_SSL_CERT:
        _DB_OPTIONS["ssl_cert"] = _DB_SSL_CERT
    if _DB_SSL_KEY:
        _DB_OPTIONS["ssl_key"] = _DB_SSL_KEY
    _DB_OPTIONS["ssl_verify_cert"] = True
    _DB_OPTIONS["ssl_verify_identity"] = _DB_SSL_VERIFY_IDENTITY
elif env_value("DB_SSL_ENFORCE", "False", cast=bool):
    raise _ImproperlyConfigured(
        "DB_SSL_ENFORCE=True but no DB_SSL_CA/CERT/KEY is configured — "
        "refusing to connect to MySQL over plaintext. See deploy/mysql_tls_server.sql."
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env_value("DB_NAME", "capstone_project_db"),
        "USER": env_value("DB_USER", "root"),
        # No live password default: dev reads it from .env, prod must set
        # DB_PASSWORD or boot fails closed below. A committed default makes
        # every password rotation ineffective for anyone with a repo copy.
        "PASSWORD": env_value("DB_PASSWORD", ""),
        "HOST": env_value("DB_HOST", "127.0.0.1"),
        "PORT": env_value("DB_PORT", "3306"),
        "OPTIONS": _DB_OPTIONS,
        # Never hold a handle past the request: background threads (scheduler,
        # channels, mail workers) have no request cycle to trigger cleanup,
        # and idle handles otherwise linger until MySQL's wait_timeout kills
        # them (1040 Too many connections). Health checks recycle stale ones.
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media upload configuration (receipts / supporting proofs)
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication Redirect routing boundaries
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# -------------------------
# Django Email Settings (uses env vars when available, else safe defaults)
# Primary = EMAIL_* (Gmail App Password); fallback = FALLBACK_SMTP_* (cPanel mailbox).
# core_system.email_backends.FallbackSMTPBackend tries primary first and
# automatically retries with the fallback — whichever connects wins.
# -------------------------
EMAIL_BACKEND = "core_system.email_backends.FallbackSMTPBackend"
EMAIL_HOST = env_value("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = env_value("EMAIL_PORT", "465", cast=int)
EMAIL_USE_TLS = env_value("EMAIL_USE_TLS", "False", cast=bool)
EMAIL_USE_SSL = env_value("EMAIL_USE_SSL", "True", cast=bool)
EMAIL_HOST_USER = env_value("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = "".join(env_value("EMAIL_HOST_PASSWORD", "").split())
EMAIL_TIMEOUT = env_value("EMAIL_TIMEOUT", 30, cast=int)
# Fail-closed SMTP: refuse plaintext relays (both use_tls and use_ssl off).
# Only disable for a local test relay: EMAIL_REQUIRE_TLS=False.
EMAIL_REQUIRE_TLS = env_value("EMAIL_REQUIRE_TLS", "True", cast=bool)
DEFAULT_FROM_EMAIL = env_value("DEFAULT_FROM_EMAIL", "CAUFASYSTEM <noreply@localhost>")
SERVER_EMAIL = env_value("SERVER_EMAIL", "root@localhost")

# Daily email limit (default 450, below Gmail's 500/day limit for regular accounts)
EMAIL_DAILY_LIMIT = env_value("EMAIL_DAILY_LIMIT", 450, cast=int)

# -------------------------
# Fallback SMTP (cPanel mailbox, used automatically when the primary Gmail SMTP fails)
# -------------------------
FALLBACK_SMTP_HOST = env_value("FALLBACK_SMTP_HOST", "mail.isucaufa-fms.online")
FALLBACK_SMTP_PORT = env_value("FALLBACK_SMTP_PORT", "465", cast=int)
FALLBACK_SMTP_USER = env_value("FALLBACK_SMTP_USER", "isucaufa@isucaufa-fms.online")
# Credentials must exist only in the deployment environment.  In particular,
# never keep a mailbox password as a source-code default: it is exposed to
# anyone with a copy of the project and makes a password rotation ineffective.
FALLBACK_SMTP_PASSWORD = env_value("FALLBACK_SMTP_PASSWORD", "")
FALLBACK_SMTP_USE_TLS = env_value("FALLBACK_SMTP_USE_TLS", "False", cast=bool)
FALLBACK_SMTP_USE_SSL = env_value("FALLBACK_SMTP_USE_SSL", "True", cast=bool)

SMTP_RETRY_DELAY_SECONDS = env_value("SMTP_RETRY_DELAY_SECONDS", "1", cast=float)
SMTP_BULK_BATCH_SIZE = env_value("SMTP_BULK_BATCH_SIZE", "25", cast=int)
# OTP messages use the Gmail-only mailer and make one fresh-connection retry.
OTP_SMTP_RETRY_DELAY_SECONDS = env_value("OTP_SMTP_RETRY_DELAY_SECONDS", "1.5", cast=float)

# -------------------------
# Web Push (VAPID) Settings
# -------------------------
# No committed key defaults: generate per deployment
# (python -c "from pywebpush import Vapid; ...") and keep the private key in
# .env only. Committed defaults leak to every repo copy.
VAPID_PUBLIC_KEY = env_value("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env_value("VAPID_PRIVATE_KEY", "")

# -------------------------
# Secure uploads (core_system/secure_upload.py)
# -------------------------
# New uploads are stored under secure_uploads/ with random names and are
# validated by magic bytes + Pillow (never by client content_type).
SECURE_UPLOAD_MAX_BYTES = env_value("SECURE_UPLOAD_MAX_BYTES", 10 * 1024 * 1024, cast=int)
# Legacy media/backups/*.sql must never be web-served (see media/.htaccess +
# media/web.config). Future dumps belong OUTSIDE MEDIA_ROOT.
SECURE_BACKUP_ROOT = env_value("SECURE_BACKUP_ROOT", str(BASE_DIR / "CAUFA-backups"))
# Fernet key (urlsafe-base64, 44 chars) for at-rest field encryption
# (see core_system/fields.py). MUST differ from BACKUP_ENCRYPTION_KEY.
# Empty = derive from SECRET_KEY (works, dedicated key preferred).
DATA_ENCRYPTION_KEY = env_value("DATA_ENCRYPTION_KEY", "")
# Fernet key (urlsafe-base64, 44 chars) for DB-dump + config-snapshot
# encryption at rest (see core_system/services/backup_service.py). Empty =
# derive from SECRET_KEY (works, but a dedicated key survives SECRET_KEY
# rotation — generate one: Fernet.generate_key()).
BACKUP_ENCRYPTION_KEY = env_value("BACKUP_ENCRYPTION_KEY", "")

# -------------------------
# Login throttling (core_system/login_throttle.py)
# -------------------------
LOGIN_THROTTLE_MAX_ATTEMPTS = env_value("LOGIN_THROTTLE_MAX_ATTEMPTS", 5, cast=int)
LOGIN_THROTTLE_WINDOW_SECONDS = env_value("LOGIN_THROTTLE_WINDOW_SECONDS", 900, cast=int)
LOGIN_THROTTLE_LOCKOUT_SECONDS = env_value("LOGIN_THROTTLE_LOCKOUT_SECONDS", 900, cast=int)

# -------------------------
# Device binding / proof-of-possession (core_system/device_binding.py)
# Short proof window layered over the 8h absolute session expiry.
# -------------------------
DEVICE_PROOF_WINDOW_SECONDS = env_value("DEVICE_PROOF_WINDOW_SECONDS", 900, cast=int)

TURNSTILE_SITE_KEY = env_value("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = env_value("TURNSTILE_SECRET_KEY", "")
# Captcha is enforced on localhost too (siteverify is a ~1-2s call).
# Public domains always enforce Turnstile regardless of this flag.
TURNSTILE_REQUIRE_ON_LOCALHOST = env_value("TURNSTILE_REQUIRE_ON_LOCALHOST", "true", cast=bool)

if _IS_PROD and (not TURNSTILE_SITE_KEY or not TURNSTILE_SECRET_KEY):
    raise _ImproperlyConfigured(
        "APP_ENV=production requires real TURNSTILE_SITE_KEY/SECRET_KEY — "
        "empty defaults would silently disable bot protection (see "
        "core_system/turnstile.is_turnstile_enabled)."
    )


