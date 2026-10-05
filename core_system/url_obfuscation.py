"""URL encryption & obfuscation service.

Every query-bearing URL the server emits goes through one of two token
shapes (both HMAC-backed, both with **no expiry** — only tampering fails):

1. Opaque envelope (browser address bar): the whole querystring is
   Fernet-encrypted + authenticated into a single blob, e.g.
   ``/?session_expired=1`` becomes ``/?x=3o5ihtesuhdfw29034u...``.
   Any manual edit breaks authentication -> branded 404 page.
2. HMAC signature param (API / fetch URLs): ``?page=2&_s=<sig>`` where the
   signature covers the path + sorted params. Readable keys stay readable
   for debugging, but edits fail verification -> 404.

Browser fetch calls self-sign transparently (``static/js/shared/url_obf.js``
patches ``window.fetch`` with a per-session HMAC subkey issued at login),
so no call-site rewrites are needed.

Settings (``caufa_portal/settings.py``):
    URL_OBFUSCATION_ENABLED=True      master kill-switch (False = everything
                                      plain, verifier off)
    URL_OBFUSCATION_REQUIRE_SIGNATURE=False
                                      False = requests WITHOUT any token pass
                                      (old bookmarks / unsigned stragglers
                                      keep working); requests WITH a
                                      present-but-invalid token ALWAYS 404.
                                      Flip to True for hard enforcement once
                                      all clients sign.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

# Query keys carrying a token. ``_s`` = HMAC signature, ``x`` = opaque blob.
SIG_PARAM = "_s"
ENVELOPE_PARAM = "x"

# Query keys never covered by the signature (cache-busters, asset versions).
IGNORED_PARAMS = frozenset({"_", "t", "v"})

# Fernet context separation + version, so a future format can coexist.
_FERNET_CONTEXT = b"url-obf-envelope-v1"

# django signing salt for opt-in path-ID tokens.
_ID_SALT = "url-obf-id-v1"

SESSION_KEY_NAME = "url_obf_key"


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    return bool(getattr(settings, "URL_OBFUSCATION_ENABLED", True))


def is_require_signature() -> bool:
    return bool(getattr(settings, "URL_OBFUSCATION_REQUIRE_SIGNATURE", False))


def exempt_prefixes() -> tuple:
    return tuple(getattr(
        settings,
        "URL_OBFUSCATION_EXEMPT_PREFIXES",
        (
            "/admin/",
            "/static/",
            "/media/",
            "/sw.js",
            "/favicon.ico",
            "/__reload__/",
            "/api/url/",  # the obfuscation helper endpoints themselves
            "/api/public/",  # anonymous registration / public docs
            "/api/push/",  # service-worker push (no session key)
            "/register/",
        ),
    ))


def is_exempt_path(path: str) -> bool:
    path = path or "/"
    return any(path.startswith(p) for p in exempt_prefixes())


# ---------------------------------------------------------------------------
# Per-session HMAC subkey (issued at login, flushed at logout with session)
# ---------------------------------------------------------------------------

def get_or_create_session_key(request) -> str | None:
    """Return the session's URL-signing subkey, creating one if needed.

    Returns None when sessions are unavailable (never raises).
    Only call for requests that already carry a session (authenticated
    traffic); anonymous visitors are intentionally left without a key so
    no session rows are created for bots.
    """
    try:
        key = request.session.get(SESSION_KEY_NAME)
        if not key:
            key = secrets.token_urlsafe(32)
            request.session[SESSION_KEY_NAME] = key
        return key
    except Exception:
        return None


def get_session_key(request) -> str | None:
    try:
        return request.session.get(SESSION_KEY_NAME)
    except Exception:
        return None


def rotate_session_key(request) -> str | None:
    """Issue a fresh subkey (call on successful login). Never raises."""
    try:
        key = secrets.token_urlsafe(32)
        request.session[SESSION_KEY_NAME] = key
        return key
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HMAC signature over path + sorted query (``_s`` param)
# ---------------------------------------------------------------------------

def _canonical_query(params: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted(
        ((k, v) for k, v in params if k not in IGNORED_PARAMS and k != SIG_PARAM),
        key=lambda kv: (kv[0], kv[1]),
    )


def compute_sig(path: str, params: list[tuple[str, str]], key: str) -> str:
    canonical = path + "?" + urlencode(_canonical_query(params), doseq=True)
    digest = hmac.new(key.encode(), canonical.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign_url(url: str, key: str) -> str:
    """Append (or refresh) the ``_s`` signature on ``url`` (path + query)."""
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    params = [(k, v) for k, v in params if k != SIG_PARAM]
    params.append((SIG_PARAM, compute_sig(parts.path, params, key)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params, doseq=True), parts.fragment))


def verify_signed_query(path: str, querydict, key: str) -> bool:
    """True when ``_s`` is present and valid for path + remaining params."""
    try:
        provided = querydict.get(SIG_PARAM, "")
        if not provided:
            return False
        flat: list[tuple[str, str]] = []
        for k, vals in querydict.lists():
            for v in vals:
                flat.append((k, v))
        expected = compute_sig(path, flat, key)
        return hmac.compare_digest(str(provided), expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Opaque envelope (``x`` param): encrypted whole-querystring for the URL bar
# ---------------------------------------------------------------------------

def _fernet():
    from cryptography.fernet import Fernet

    secret = getattr(settings, "SECRET_KEY", "") or ""
    raw = hashlib.sha256(_FERNET_CONTEXT + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def opaque_encode(params: dict) -> str:
    """Encrypt ``params`` dict into an opaque URL-safe token (no expiry)."""
    token = _fernet().encrypt(urlencode(params, doseq=True).encode())
    return token.decode()


def opaque_decode(token: str) -> dict | None:
    """Decrypt an envelope token; None when tampered/unreadable."""
    try:
        raw = _fernet().decrypt(str(token).encode()).decode()
        return dict(parse_qsl(raw, keep_blank_values=True))
    except Exception:
        return None


def opaque_url(path: str, params: dict) -> str:
    """Build ``path?x=<blob>`` hiding every key/value from the address bar."""
    return path + "?" + urlencode({ENVELOPE_PARAM: opaque_encode(params)})


def session_expired_url() -> str:
    """Obfuscated landing redirect for dead sessions (was ?session_expired=1)."""
    return opaque_url("/", {"session_expired": "1"})


def decode_envelope_params(request) -> dict:
    """Decoded ``?x=`` params for this request, or {} when absent/invalid."""
    try:
        token = request.GET.get(ENVELOPE_PARAM, "")
        if not token:
            return {}
        return opaque_decode(token) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Opt-in path-ID tokens (for future use on sensitive ``<id>`` segments)
# ---------------------------------------------------------------------------

def sign_id(pk) -> str:
    return signing.dumps(str(pk), salt=_ID_SALT)


def unsign_id(token: str):
    try:
        return signing.loads(str(token), salt=_ID_SALT)
    except signing.BadSignature:
        return None


# ---------------------------------------------------------------------------
# Template context: per-session key for the JS auto-signer
# ---------------------------------------------------------------------------

def url_obf_context(request):
    """Expose the session signing key to templates (meta tag for JS)."""
    try:
        return {"URL_OBF_KEY": request.session.get(SESSION_KEY_NAME) or ""}
    except Exception:
        return {"URL_OBF_KEY": ""}
