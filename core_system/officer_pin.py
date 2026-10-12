"""Offline personal action-PIN for officers.

Separate from the login password. The officer chooses their own PIN (4-digit
numeric per product decision); only a salted PBKDF2 hash is stored via
``auth_utils.hash_pin`` / ``verify_pin`` — fully offline, no email/OTP.

Lockout: every 3 consecutive wrong attempts locks the PIN for
``action_pin_lock_minutes`` minutes, starting at 1 and doubling each cycle
(1 -> 2 -> 4 -> 8 ...). A successful verification resets fail count and the
lock duration back to 1 minute.
"""

from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from functools import wraps

from core_system.auth_utils import hash_pin, verify_pin, verify_password
from core_system.models import AccessSession, OfficerUser

ACTION_PIN_LENGTH = 4
ACTION_PIN_FAILS_PER_LOCK = 3
ACTION_PIN_BASE_LOCK_MINUTES = 1
ACTION_PIN_MAX_LOCK_MINUTES = 60 * 8  # cap doubling at 8h to avoid permanent lock


def validate_action_pin(pin: str) -> list[str]:
    errors: list[str] = []
    p = (pin or "").strip()
    if len(p) != ACTION_PIN_LENGTH or not p.isdigit():
        errors.append(f"PIN must be exactly {ACTION_PIN_LENGTH} digits.")
        return errors
    # Reject trivial PINs (0000, 1111, 1234, 4321, ...).
    if len(set(p)) == 1:
        errors.append("PIN is too easy to guess. Avoid repeating digits.")
    elif p in {"1234", "4321", "0123", "3210"}:
        errors.append("PIN is too easy to guess. Choose a less predictable PIN.")
    return errors


def has_action_pin(officer: OfficerUser) -> bool:
    return bool(getattr(officer, "action_pin_hash", None))


def is_action_pin_locked(officer: OfficerUser) -> tuple[bool, int]:
    """Return (locked, retry_after_seconds)."""
    locked_until = getattr(officer, "action_pin_locked_until", None)
    if locked_until is None:
        return False, 0
    now = timezone.now()
    if locked_until <= now:
        return False, 0
    return True, int((locked_until - now).total_seconds())


def _audit(action: str, officer: OfficerUser, request=None, *, result="Success", notes=None):
    try:
        from core_system.shared_view_utils import _record_audit_trail

        ip = None
        device = None
        if request is not None:
            ip = request.META.get("REMOTE_ADDR")
            device = request.META.get("HTTP_USER_AGENT", "")[:255]
        _record_audit_trail(
            "officer_user",
            getattr(officer, "user_id_PK", 0) or 0,
            action,
            officer,
            ip=ip,
            device_info=device,
            notes=notes,
            result=result,
        )
    except Exception:
        pass


def setup_action_pin(*, officer: OfficerUser, pin: str, password: str = "", request=None) -> tuple[bool, str]:
    """First-time setup. The session already proves login; when a password is
    supplied it must also match (extra proof for sensitive first setup)."""
    if has_action_pin(officer):
        return False, "Action PIN is already set. Use change instead."
    errs = validate_action_pin(pin)
    if errs:
        return False, errs[0]
    if password:
        if not verify_password(password, officer.password_hash):
            _audit("ACTION_PIN_SETUP_FAILED", officer, request, result="Failed",
                   notes="Setup rejected: password mismatch.")
            return False, "Login password is incorrect."
    officer.action_pin_hash = hash_pin(pin.strip())
    officer.action_pin_set_at = timezone.now()
    officer.action_pin_fail_count = 0
    officer.action_pin_locked_until = None
    officer.action_pin_lock_minutes = ACTION_PIN_BASE_LOCK_MINUTES
    officer.save(update_fields=[
        "action_pin_hash", "action_pin_set_at", "action_pin_fail_count",
        "action_pin_locked_until", "action_pin_lock_minutes",
    ])
    _audit("ACTION_PIN_SETUP", officer, request, notes="Action PIN set.")
    return True, "Action PIN set successfully."


def change_action_pin(*, officer: OfficerUser, current_pin: str, new_pin: str, password: str, request=None) -> tuple[bool, str]:
    """Change an existing PIN. Requires current PIN + login password."""
    if not has_action_pin(officer):
        return False, "No action PIN set yet. Use setup instead."
    if not password or not verify_password(password, officer.password_hash):
        _audit("ACTION_PIN_CHANGE_FAILED", officer, request, result="Failed",
               notes="Change rejected: password mismatch.")
        return False, "Login password is incorrect."
    ok, _, _ = verify_action_pin(officer, current_pin or "", request=request, audit=False)
    if not ok:
        _audit("ACTION_PIN_CHANGE_FAILED", officer, request, result="Failed",
               notes="Change rejected: current PIN incorrect.")
        return False, "Current PIN is incorrect."
    errs = validate_action_pin(new_pin)
    if errs:
        return False, errs[0]
    if (current_pin or "").strip() == (new_pin or "").strip():
        return False, "New PIN must be different from the current PIN."
    officer.action_pin_hash = hash_pin(new_pin.strip())
    officer.action_pin_set_at = timezone.now()
    officer.action_pin_fail_count = 0
    officer.action_pin_locked_until = None
    officer.action_pin_lock_minutes = ACTION_PIN_BASE_LOCK_MINUTES
    officer.save(update_fields=[
        "action_pin_hash", "action_pin_set_at", "action_pin_fail_count",
        "action_pin_locked_until", "action_pin_lock_minutes",
    ])
    _audit("ACTION_PIN_CHANGED", officer, request, notes="Action PIN changed.")
    return True, "Action PIN changed successfully."


def _store_new_pin(*, officer: OfficerUser, new_pin: str) -> None:
    officer.action_pin_hash = hash_pin(new_pin.strip())
    officer.action_pin_set_at = timezone.now()
    officer.action_pin_fail_count = 0
    officer.action_pin_locked_until = None
    officer.action_pin_lock_minutes = ACTION_PIN_BASE_LOCK_MINUTES
    officer.save(update_fields=[
        "action_pin_hash", "action_pin_set_at", "action_pin_fail_count",
        "action_pin_locked_until", "action_pin_lock_minutes",
    ])


def reset_action_pin(*, officer: OfficerUser, new_pin: str, password: str = "",
                     request=None, grant_validated: bool = False) -> tuple[bool, str]:
    """Forgot-PIN recovery (step 2). Requires a fresh MFA grant from step 1.

    Fallback: when the officer has NO MFA options at all (no email on file,
    no authenticator, zero unused backup codes), the login password alone is
    accepted so recovery is never impossible. Audit-logged either way.
    """
    errs = validate_action_pin(new_pin)
    if errs:
        return False, errs[0]
    if not grant_validated:
        if mfa_options_available(officer)["any"]:
            _audit("ACTION_PIN_RESET_FAILED", officer, request, result="Failed",
                   notes="Reset rejected: no verified MFA code.")
            return False, "Verify a login code first."
        if not password or not verify_password(password, officer.password_hash):
            _audit("ACTION_PIN_RESET_FAILED", officer, request, result="Failed",
                   notes="Reset rejected: password mismatch (no-MFA fallback).")
            return False, "Login password is incorrect."
    _store_new_pin(officer=officer, new_pin=new_pin)
    _audit("ACTION_PIN_RESET", officer, request,
           notes="Action PIN reset (forgot-PIN flow).")
    return True, "Action PIN reset successfully."


# ---------------------------------------------------------------------------
# Forgot-PIN step 1: prove identity with a sign-in fallback code
# (email OTP, authenticator-app TOTP, or one-time backup code — same box as
# login). Success issues a short-lived single-use session grant for step 2.
# ---------------------------------------------------------------------------

RESET_GRANT_SESSION_KEY = "officer_pin_reset_grant"
RESET_FAILS_SESSION_KEY = "officer_pin_reset_fails"
RESET_CODE_SENT_AT_KEY = "officer_pin_reset_code_at"
RESET_GRANT_MINUTES = 10
RESET_CODE_RESEND_SECONDS = 60
RESET_MAX_ATTEMPTS = 10


def mfa_options_available(officer: OfficerUser) -> dict:
    """Which step-1 code sources this officer can use."""
    from core_system.services.mfa_service import backup_codes_remaining

    has_email = bool((getattr(officer, "email", None) or "").strip())
    has_auth = bool(getattr(officer, "authenticator_enabled", False)
                    and getattr(officer, "authenticator_secret", None))
    backups = backup_codes_remaining(officer)
    return {
        "email": has_email,
        "authenticator": has_auth,
        "backup_codes": backups,
        "any": bool(has_email or has_auth or backups > 0),
    }


def send_reset_code(*, officer: OfficerUser, request=None) -> tuple[bool, str]:
    """Email the step-1 code (same rotating OTP as login). Rate-limited."""
    from core_system.services.mfa_service import (
        generate_mfa_secret, generate_otp, mask_email, send_mfa_email, send_mfa_push,
    )

    if not (getattr(officer, "email", None) or "").strip():
        return False, "No email on file — use your authenticator app code or a backup code."
    if request is not None:
        last = request.session.get(RESET_CODE_SENT_AT_KEY, 0) or 0
        try:
            waiting = RESET_CODE_RESEND_SECONDS - (timezone.now().timestamp() - float(last))
        except (TypeError, ValueError):
            waiting = 0
        if waiting > 0:
            return False, f"Code already sent. Wait {int(waiting)}s before resending."
    if not getattr(officer, "mfa_secret", None):
        officer.mfa_secret = generate_mfa_secret()
        officer.save(update_fields=["mfa_secret"])
    otp = generate_otp(officer.mfa_secret)
    send_mfa_email(officer, otp, subject="CAUFA Action PIN Reset Code")
    try:
        send_mfa_push(officer, otp)
    except Exception:
        pass
    if request is not None:
        request.session[RESET_CODE_SENT_AT_KEY] = timezone.now().timestamp()
        request.session.pop(RESET_FAILS_SESSION_KEY, None)
    _audit("ACTION_PIN_RESET_CODE_SENT", officer, request,
           notes=f"Reset code sent to {mask_email(officer.email)}.")
    return True, f"Code sent to {mask_email(officer.email)}. Valid 5 minutes."


def verify_reset_code(*, officer: OfficerUser, code: str, request=None) -> tuple[bool, str, str]:
    """Check the step-1 code; on success issue the step-2 grant.

    Returns (ok, message, method). A matching backup code burns on first use.
    """
    from core_system.auth_views import _verify_mfa_code

    fails = 0
    if request is not None:
        fails = int(request.session.get(RESET_FAILS_SESSION_KEY, 0) or 0)
        if fails >= RESET_MAX_ATTEMPTS:
            return False, "Too many wrong codes. Request a new code and try again.", ""
    ok, method = _verify_mfa_code(officer, code or "")
    if not ok:
        if request is not None:
            request.session[RESET_FAILS_SESSION_KEY] = fails + 1
        left = RESET_MAX_ATTEMPTS - fails - 1
        _audit("ACTION_PIN_RESET_CODE_FAILED", officer, request, result="Failed",
               notes="Wrong reset code.")
        return False, f"Invalid code. {max(0, left)} attempt(s) left.", ""
    if request is not None:
        request.session.pop(RESET_FAILS_SESSION_KEY, None)
        request.session[RESET_GRANT_SESSION_KEY] = {
            "officer_id": getattr(officer, "user_id_PK", None),
            "exp": (timezone.now() + timezone.timedelta(minutes=RESET_GRANT_MINUTES)).isoformat(),
        }
    _audit("ACTION_PIN_RESET_CODE_VERIFIED", officer, request,
           notes=f"Reset identity check passed via {method}.")
    return True, "Code verified. Set your new PIN.", method


def consume_reset_grant(*, officer: OfficerUser, request) -> bool:
    """Single-use step-2 grant check. Returns True once per verified code."""
    try:
        grant = (request.session.get(RESET_GRANT_SESSION_KEY) or {}) if request else {}
        if not grant or grant.get("officer_id") != getattr(officer, "user_id_PK", None):
            return False
        exp = timezone.datetime.fromisoformat(grant.get("exp", ""))
        if timezone.is_naive(exp):
            exp = timezone.make_aware(exp)
        if exp <= timezone.now():
            return False
    except (ValueError, TypeError):
        return False
    request.session.pop(RESET_GRANT_SESSION_KEY, None)
    return True


def verify_action_pin(officer: OfficerUser, pin: str, *, request=None, audit=True) -> tuple[bool, str, int]:
    """Verify a PIN with doubling lockout. Returns (ok, message, retry_after_s)."""
    officer.refresh_from_db(fields=[
        "action_pin_hash", "action_pin_fail_count",
        "action_pin_locked_until", "action_pin_lock_minutes",
    ]) if officer.pk else None
    if not has_action_pin(officer):
        return False, "No action PIN set. Please set one first.", 0
    locked, retry_after = is_action_pin_locked(officer)
    if locked:
        return False, f"Too many wrong attempts. Try again in {max(1, retry_after // 60)} minute(s).", retry_after
    # Expired lock: clear timestamp but keep escalated duration for next cycle.
    if officer.action_pin_locked_until is not None:
        officer.action_pin_locked_until = None
        officer.save(update_fields=["action_pin_locked_until"])
    p = (pin or "").strip()
    if not p:
        return False, "Action PIN is required.", 0
    if verify_pin(p, officer.action_pin_hash or ""):
        officer.action_pin_fail_count = 0
        officer.action_pin_locked_until = None
        officer.action_pin_lock_minutes = ACTION_PIN_BASE_LOCK_MINUTES
        officer.save(update_fields=[
            "action_pin_fail_count", "action_pin_locked_until", "action_pin_lock_minutes",
        ])
        return True, "PIN verified.", 0
    # Wrong PIN.
    officer.action_pin_fail_count = int(officer.action_pin_fail_count or 0) + 1
    fails = officer.action_pin_fail_count
    if fails % ACTION_PIN_FAILS_PER_LOCK == 0:
        minutes = int(officer.action_pin_lock_minutes or ACTION_PIN_BASE_LOCK_MINUTES)
        officer.action_pin_locked_until = timezone.now() + timezone.timedelta(minutes=minutes)
        officer.action_pin_lock_minutes = min(minutes * 2, ACTION_PIN_MAX_LOCK_MINUTES)
        officer.save(update_fields=[
            "action_pin_fail_count", "action_pin_locked_until", "action_pin_lock_minutes",
        ])
        if audit:
            _audit("ACTION_PIN_LOCKED", officer, request, result="Failed",
                   notes=f"Locked for {minutes} min after {fails} wrong attempts.")
        return False, f"Too many wrong attempts. Locked for {minutes} minute(s).", minutes * 60
    officer.save(update_fields=["action_pin_fail_count"])
    if audit:
        _audit("ACTION_PIN_FAILED", officer, request, result="Failed",
               notes=f"Wrong PIN attempt {fails}.")
    remaining = ACTION_PIN_FAILS_PER_LOCK - (fails % ACTION_PIN_FAILS_PER_LOCK)
    return False, f"Incorrect PIN. {remaining} attempt(s) left before lock.", 0


def get_officer_from_request(request: HttpRequest) -> OfficerUser | None:
    officer_id = request.session.get("officer_id")
    if officer_id is not None:
        try:
            return OfficerUser.objects.get(user_id_PK=int(officer_id))
        except (OfficerUser.DoesNotExist, ValueError, TypeError):
            pass
    token = request.session.get("access_token")
    if token:
        sess = AccessSession.objects.select_related("user_id_FK").filter(token_id=token).first()
        if sess is not None:
            return sess.user_id_FK
    return None


def extract_action_pin(request: HttpRequest, data: dict | None = None) -> str:
    """PIN may arrive as JSON `action_pin`, POST `action_pin`, or `X-Action-PIN` header."""
    header_pin = (request.headers.get("X-Action-PIN") or request.META.get("HTTP_X_ACTION_PIN") or "").strip()
    if header_pin:
        return header_pin
    if data is not None and isinstance(data, dict):
        for key in ("action_pin", "actionPin", "pin"):
            val = data.get(key)
            if val not in (None, ""):
                return str(val).strip()
    # POST form fallback (auditor/treasurer use form posts).
    post_pin = (request.POST.get("action_pin") or request.POST.get("actionPin") or "").strip()
    if post_pin:
        return post_pin
    # Last resort: try JSON body.
    if data is None:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}") if request.body else {}
            if isinstance(body, dict):
                for key in ("action_pin", "actionPin", "pin"):
                    val = body.get(key)
                    if val not in (None, ""):
                        return str(val).strip()
        except Exception:
            pass
    return ""


def require_action_pin(request: HttpRequest, officer: OfficerUser | None = None, data: dict | None = None):
    """Enforce action-PIN for a final approval. Returns None if OK, else JsonResponse."""
    if officer is None:
        officer = get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "success": False, "error": "Officer session missing.", "code": "NO_SESSION"}, status=401)
    if not has_action_pin(officer):
        return JsonResponse({
            "ok": False, "success": False,
            "error": "Action PIN not set. Please set your 4-digit action PIN first.",
            "code": "PIN_NOT_SET",
        }, status=403)
    locked, retry_after = is_action_pin_locked(officer)
    if locked:
        return JsonResponse({
            "ok": False, "success": False,
            "error": f"Action PIN locked. Try again in {max(1, retry_after // 60)} minute(s).",
            "code": "PIN_LOCKED", "retry_after_seconds": retry_after,
        }, status=423)
    pin = extract_action_pin(request, data)
    if not pin:
        return JsonResponse({
            "ok": False, "success": False,
            "error": "Action PIN is required to confirm this action.",
            "code": "PIN_REQUIRED",
        }, status=403)
    ok, msg, retry = verify_action_pin(officer, pin, request=request)
    if not ok:
        code = "PIN_LOCKED" if retry and "Locked" in msg else "PIN_INVALID"
        status = 423 if code == "PIN_LOCKED" else 403
        payload = {"ok": False, "success": False, "error": msg, "code": code}
        if retry:
            payload["retry_after_seconds"] = retry
        return JsonResponse(payload, status=status)
    return None


def require_action_pin_view(view_func):
    """Decorator for final-approval views. Enforces the offline action-PIN.

    The client must send the 4-digit PIN as JSON ``action_pin``, form field
    ``action_pin``, or ``X-Action-PIN`` header on the SAME request that
    performs the approval (single-step, no TOCTOU gap).
    """
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        guard = require_action_pin(request)
        if guard is not None:
            return guard
        return view_func(request, *args, **kwargs)
    return _wrapped
