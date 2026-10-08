import base64
import hashlib
import hmac
import secrets
import time

from core_system.models import OfficerUser


MFA_EMAIL_RATE_LIMIT_SECONDS = 300  # 5 minutes exactly

# ---- Authenticator-app TOTP (RFC 6238: SHA-1, 30s step, 6 digits) ----
# Separate from the email OTP above (HMAC-SHA256 over a hex secret), which
# authenticator apps cannot reproduce. The authenticator secret is base32 so
# Google/Microsoft Authenticator can enroll via otpauth:// URI or manual key.
AUTH_WINDOW_SECONDS = 30
AUTH_DIGITS = 6
AUTH_DRIFT_STEPS = 1  # accept ±1 step (±30s) for phone/server clock skew
AUTH_ISSUER = "ISUCauFA"

# Single-use recovery codes shown once at authenticator enrollment.
BACKUP_CODE_COUNT = 10


def generate_mfa_secret() -> str:
    return secrets.token_hex(16)


def generate_otp(secret: str) -> str:
    counter = int(time.time() // 30)
    msg = counter.to_bytes(8, "big")
    h = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    offset = h[-1] & 0xF
    code = int.from_bytes(h[offset:offset + 4], "big") & 0x7FFFFFFF
    return f"{code % 1000000:06d}"


def verify_otp(secret: str, otp: str) -> bool:
    if not secret or not otp:
        return False
    now = time.time()
    # Exactly 10 windows × 30s = 300s = 5 minutes
    for offset in range(0, -300, -30):
        counter = int((now + offset) // 30)
        msg = counter.to_bytes(8, "big")
        h = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
        h_offset = h[-1] & 0xF
        code = int.from_bytes(h[h_offset:h_offset + 4], "big") & 0x7FFFFFFF
        if f"{code % 1000000:06d}" == str(otp).strip():
            return True
    return False


def mask_email(email: str) -> str:
    """Mask an address for display, keeping 2 chars on each side at the same
    length, e.g. humanmale050519@gmail.com -> hu***********19@gmail.com."""
    email = (email or "").strip()
    if not email or "@" not in email:
        return email
    local, _, domain = email.rpartition("@")
    if len(local) >= 5:
        masked_local = f"{local[:2]}{'*' * (len(local) - 4)}{local[-2:]}"
    elif len(local) >= 3:
        masked_local = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    elif local:
        masked_local = "*" * len(local)
    else:
        masked_local = "***"
    return f"{masked_local}@{domain}"


def send_mfa_email(
    officer: OfficerUser,
    otp: str,
    subject: str = "CAUFA MFA Verification Code",
    extra_context: dict | None = None,
) -> bool:
    # Queued (not sent inline): SMTP can take 8-15s, which used to block the
    # login/resend/forgot-password response until the OTP email left the box.
    from core_system.services.email_service import send_html_email_async

    html_template = "emails/mfa_challenge.html"
    context = {
        "full_name": officer.full_name,
        "otp_code": otp,
        "expiry_minutes": 5,
    }
    if extra_context:
        context.update(extra_context)
    _log = __import__("logging").getLogger(__name__)
    if not officer.email:
        _log.error("send_mfa_email: officer %s (pk=%s) has no email address", officer.full_name, officer.user_id_PK)
        return False

    result = send_html_email_async(
        subject=subject,
        recipient_list=[officer.email],
        html_template=html_template,
        context=context,
    )
    _log.info("send_mfa_email queued to %s (pk=%s) -> %s", officer.email, officer.user_id_PK, result)
    return result


# ---------------------------------------------------------------------------
# Authenticator-app fallback (true offline: codes are generated on-device,
# no email and no push delivery needed — only the login POST needs internet).
# ---------------------------------------------------------------------------

def generate_authenticator_secret() -> str:
    """160-bit random secret, base32 without padding (otpauth convention)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _b32decode(secret: str) -> bytes:
    cleaned = (secret or "").strip().upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def authenticator_otpauth_uri(secret: str, account_name: str) -> str:
    """otpauth:// URI for QR enrollment in Google/Microsoft Authenticator."""
    from urllib.parse import quote

    return (
        f"otpauth://totp/{quote(AUTH_ISSUER)}:{quote(account_name or 'officer')}"
        f"?secret={secret}&issuer={quote(AUTH_ISSUER)}"
        f"&algorithm=SHA1&digits={AUTH_DIGITS}&period={AUTH_WINDOW_SECONDS}"
    )


def format_manual_key(secret: str) -> str:
    """Grouped lowercase key for manual entry, e.g. 'abcd efgh ...'."""
    raw = (secret or "").strip().upper()
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4)).lower()


def generate_authenticator_code(secret: str, for_time: float | None = None) -> str:
    """Current RFC 6238 TOTP code for `secret` (server-side reference)."""
    counter = int((for_time if for_time is not None else time.time()) // AUTH_WINDOW_SECONDS)
    msg = counter.to_bytes(8, "big")
    digest = hmac.new(_b32decode(secret), msg, hashlib.sha1).digest()
    offset = digest[-1] & 0xF
    code = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return f"{code % (10 ** AUTH_DIGITS):0{AUTH_DIGITS}d}"


def verify_authenticator_code(secret: str, code: str) -> bool:
    """Accept the current step plus ±1 step of clock skew. Never raises."""
    if not secret or not code:
        return False
    candidate = (str(code).strip().replace(" ", "").replace("-", ""))
    if len(candidate) != AUTH_DIGITS or not candidate.isdigit():
        return False
    try:
        now = time.time()
        for step in range(-AUTH_DRIFT_STEPS, AUTH_DRIFT_STEPS + 1):
            if generate_authenticator_code(secret, for_time=now + step * AUTH_WINDOW_SECONDS) == candidate:
                return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Single-use recovery backup codes (lost phone / reinstall safety net).
# Only sha256 hashes are stored; plaintext is shown exactly once.
# ---------------------------------------------------------------------------

def _backup_pepper() -> str:
    try:
        from django.conf import settings
        return str(getattr(settings, "SECRET_KEY", "") or "")
    except Exception:
        return ""


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    """Human-typable codes like 'K7Q2-9M4X' (ambiguous chars excluded)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_backup_code(code: str) -> str:
    normalized = (code or "").strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256((_backup_pepper() + "|" + normalized).encode()).hexdigest()


def backup_code_matches(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_backup_code(code), code_hash or "")


def issue_backup_codes(officer: OfficerUser) -> list[str]:
    """Replace all of the officer's backup codes; return plaintext ONCE.

    Old codes (used or not) die immediately. Only sha256 hashes hit the DB.
    Stamp ``backup_codes_issued_at`` so first-login/nudge logic stays honest.
    """
    from django.utils import timezone as _tz

    from core_system.models import MfaBackupCode

    MfaBackupCode.objects.filter(officer_id_FK=officer).delete()
    plaintext = generate_backup_codes()
    MfaBackupCode.objects.bulk_create([
        MfaBackupCode(officer_id_FK=officer, code_hash=hash_backup_code(c)) for c in plaintext
    ])
    officer.backup_codes_issued_at = _tz.now()
    officer.save(update_fields=["backup_codes_issued_at"])
    return plaintext


def backup_codes_remaining(officer: OfficerUser) -> int:
    try:
        from core_system.models import MfaBackupCode
        return MfaBackupCode.objects.filter(officer_id_FK=officer, used_at__isnull=True).count()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Push-delivered OTP fallback (survives a Gmail outage; still needs internet
# on both ends — Web Push is relayed via the browser vendor's push service).
# Delivers the SAME email-TOTP code, so verification is unchanged.
# ---------------------------------------------------------------------------

def has_push_subscription(officer: OfficerUser) -> bool:
    try:
        from core_system.models import PushSubscription
        return PushSubscription.objects.filter(officer_id_FK=officer).exists()
    except Exception:
        return False


def send_mfa_push(officer: OfficerUser, otp: str) -> bool:
    """Push the current login code to all of the officer's devices.

    Returns True when at least one device accepted the push. Never raises —
    push is best-effort fallback, a push outage must never break login.
    """
    import json as _json

    _log = __import__("logging").getLogger(__name__)
    try:
        from django.conf import settings

        from core_system.models import PushSubscription

        subs = list(PushSubscription.objects.filter(officer_id_FK=officer))
        if not subs:
            return False
        if not getattr(settings, "VAPID_PRIVATE_KEY", ""):
            _log.warning("send_mfa_push: VAPID key missing, skipping push OTP")
            return False
        from pywebpush import webpush

        try:
            from core_system.services.notifications import _abs_url
        except Exception:
            _abs_url = None  # type: ignore[assignment]

        delivered = False
        for sub in subs:
            try:
                url = "/login/"
                if _abs_url is not None:
                    try:
                        url = _abs_url("/login/", getattr(sub, "origin", None))
                    except Exception:
                        url = "/login/"
                payload = _json.dumps({
                    "title": "ISUCauFA Login Code",
                    "body": (
                        f"Your verification code is {otp}. "
                        "Enter it on the login screen — it expires in 5 minutes."
                    ),
                    "url": url,
                })
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
                    },
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": "mailto:isucaufa@isucaufa-fms.online"},
                    timeout=10,
                    ttl=300,  # login code lifetime: don't queue stale codes
                    headers={"Urgency": "high"},
                )
                delivered = True
            except Exception as exc:
                _log.warning("send_mfa_push failed for sub %s: %s", getattr(sub, "pk", "?"), exc)
        return delivered
    except Exception as exc:
        _log.warning("send_mfa_push setup failed: %s", exc)
        return False
