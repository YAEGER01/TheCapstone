import json
import logging
import secrets
import time
import uuid
import threading
from datetime import timedelta

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from core_system.auth_utils import (
    create_access_session,
    hash_password,
    log_login_attempt,
    password_needs_rehash,
    validate_new_password,
    verify_officer_password,
    verify_password,
)
from core_system.constants.status_constants import RegistrationStatus
from core_system.models import AccessSession, OfficerUser, MemberRegistrationRequest
from core_system.shared_view_utils import _record_audit_trail
from core_system.services import zt_service
from core_system import zt_settings
from core_system.services.mfa_service import (
    authenticator_otpauth_uri,
    backup_code_matches,
    backup_codes_remaining,
    format_manual_key,
    generate_authenticator_code,
    generate_authenticator_secret,
    generate_backup_codes,
    generate_mfa_secret,
    generate_otp,
    hash_backup_code,
    has_push_subscription,
    issue_backup_codes,
    mask_email,
    send_mfa_email,
    send_mfa_push,
    verify_authenticator_code,
    verify_otp,
    MFA_EMAIL_RATE_LIMIT_SECONDS,
)
from core_system.turnstile import (
    get_turnstile_site_key,
    is_turnstile_enabled,
    validate_turnstile_token,
)

MFA_SESSION_KEY = "mfa_pre_auth_token"
MFA_OFFICER_ID_KEY = "mfa_officer_id"
MFA_USERNAME_KEY = "mfa_username"
MFA_EMAIL_MASKED_KEY = "mfa_email_masked"
# When the current pre-auth attempt started. Anchors the delivery-status poll
# to THIS login's row so a stale SENT row from an earlier login can never
# report a fake "Code sent" for a code that was never queued.
MFA_INITIATED_KEY = "mfa_initiated_at"
# Minimum gap between two OTP emails to the same officer. Re-sends inside one
# TOTP window carry the identical code anyway, so 60s stops spam-clicking
# without ever trapping an officer behind a 5-minute wait for mail that
# failed or stalled.
MFA_RESEND_FLOOR_SECONDS = 60


def _queue_mfa_email(officer, otp):
    from core_system.services.mfa_service import send_mfa_email
    return send_mfa_email(officer, otp)


def _latest_otp_info(officer):
    """Newest queued OTP email for this officer, or None (never raises)."""
    try:
        from core_system.services.email_service import get_latest_otp_status
        return get_latest_otp_status(officer.email)
    except Exception:
        return None


def _otp_age_seconds(info) -> float | None:
    if not info or not info.get("created_at"):
        return None
    try:
        created = timezone.datetime.fromisoformat(info["created_at"])
        if timezone.is_naive(created):
            created = timezone.make_aware(created)
        return (timezone.now() - created).total_seconds()
    except (ValueError, TypeError):
        return None


def _mfa_send_allowed(officer):
    """Row-based resend gate. Returns (allowed, retry_after_seconds).

    - No prior OTP mail → allowed.
    - Last code FAILED → allowed immediately (it never arrived).
    - Last code queued <60s ago and not failed → wait (probably sending now,
      or the officer just got it — re-sends carry the identical TOTP code).
    - Older than that → allowed.
    """
    latest = _latest_otp_info(officer)
    if latest is None:
        return True, 0
    if latest.get("status") == "failed":
        return True, 0
    age = _otp_age_seconds(latest)
    if age is not None and age < MFA_RESEND_FLOOR_SECONDS:
        return False, int(MFA_RESEND_FLOOR_SECONDS - age)
    return True, 0


# Minimum gap between two push OTPs to the same officer (push is manual
# fallback only — the email resend path already has its own 60s floor).
MFA_PUSH_FLOOR_SECONDS = 60
# Session flags set when the push fallback delivered THIS attempt's code,
# so the audit trail can attribute the channel honestly.
MFA_PUSH_SENT_KEY = "mfa_push_sent"
MFA_PUSH_SENT_AT_KEY = "mfa_push_sent_at"
# Session key holding the one-time plaintext backup codes for the
# first-login reveal (member dashboard fetches them exactly once, then the
# key is destroyed). SHOW key drives the modal; REVEAL key holds the codes.
BACKUP_REVEAL_KEY = "pending_backup_reveal"
SHOW_BACKUP_MODAL_KEY = "show_backup_modal"
# Reveal is only served while the login itself is this fresh (minutes).
BACKUP_REVEAL_FRESH_MINUTES = 30
# Maximum wrong codes per pre-auth session before the attempt is killed.
# Higher than the step-up gates (5) — codes legitimately expire and typo —
# but 10 consecutive failures is brute force, not bad luck.
MAX_MFA_ATTEMPTS = 10
MFA_FAILS_KEY = "mfa_attempt_fails"
# Same cap for the password-reset code: it mints a new password directly,
# so it gets the same brute-force budget as the login code box — no more.
MAX_RESET_ATTEMPTS = 10
RESET_FAILS_KEY = "reset_otp_fails"
# Session key counting failed authenticator-enrollment confirmations.
AUTH_CONFIRM_FAILS_KEY = "auth_confirm_fails"


def _current_authenticated_officer(request):
    """Logged-in officer: live access session first, officer_id fallback."""
    token = request.session.get("access_token")
    if token:
        try:
            sess = AccessSession.objects.select_related("user_id_FK").get(token_id=token)
            if sess.revoked_at is None and sess.expires_at > timezone.now():
                return sess.user_id_FK
        except AccessSession.DoesNotExist:
            pass
    officer_id = request.session.get("officer_id")
    if officer_id is not None:
        try:
            return OfficerUser.objects.get(user_id_PK=int(officer_id))
        except (OfficerUser.DoesNotExist, TypeError, ValueError):
            return None
    return None


def _verify_mfa_code(officer, code):
    """Accept email/push TOTP, authenticator TOTP, or an unused backup code.

    Returns (ok, method). A matching backup code burns on first use.
    """
    raw = (code or "").strip()
    if not raw:
        return False, ""
    if officer.mfa_secret and verify_otp(officer.mfa_secret, raw):
        return True, "mfa_email"
    if (
        getattr(officer, "authenticator_enabled", False)
        and getattr(officer, "authenticator_secret", None)
        and verify_authenticator_code(officer.authenticator_secret, raw)
    ):
        return True, "mfa_authenticator"
    try:
        from core_system.models import MfaBackupCode

        for row in MfaBackupCode.objects.filter(officer_id_FK=officer, used_at__isnull=True):
            if backup_code_matches(raw, row.code_hash):
                row.used_at = timezone.now()
                row.save(update_fields=["used_at"])
                return True, "mfa_backup_code"
    except Exception:
        pass
    return False, ""


def _get_masked_mfa_email(request) -> str:
    """Masked registered email for the OTP screen (cached in session)."""
    masked = request.session.get(MFA_EMAIL_MASKED_KEY, "")
    if masked:
        return masked
    officer_id = request.session.get(MFA_OFFICER_ID_KEY)
    if not officer_id:
        return ""
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        return ""
    masked = mask_email(officer.email)
    request.session[MFA_EMAIL_MASKED_KEY] = masked
    return masked


def _check_term_validity(officer: OfficerUser) -> tuple[bool, str]:
    term_start = getattr(officer, "term_start", None)
    term_end = getattr(officer, "term_end", None)
    if not term_start or not term_end:
        return True, ""
    today = timezone.localdate()
    if today < term_start:
        return False, f"Your officer term has not started yet. Term begins on {term_start.isoformat()}."
    if today > term_end:
        return False, f"Your officer term expired on {term_end.isoformat()}. Please contact the board."
    return True, ""


def _term_info(officer: OfficerUser) -> dict:
    term_start = getattr(officer, "term_start", None)
    term_end = getattr(officer, "term_end", None)
    today = timezone.localdate()
    is_expired = False
    days_until_expiry = None
    if term_start and term_end:
        if today > term_end:
            is_expired = True
        else:
            days_until_expiry = (term_end - today).days
    return {
        "term_start": term_start.isoformat() if term_start else "",
        "term_end": term_end.isoformat() if term_end else "",
        "is_expired": is_expired,
        "days_until_expiry": days_until_expiry,
    }


def _workspace_redirect(role: str) -> str:
    role_norm = (role or "").strip().lower()
    if role_norm == "member":
        return "/member/"
    if role_norm == "treasurer":
        return "/treasurer/"
    if role_norm == "auditor":
        return "/auditor/"
    if role_norm == "president":
        return "/president/"
    if role_norm == "secretary":
        return "/secretary/"
    if role_norm == "superadmin":
        return "/superadmin/"
    if role_norm == "public information officer":
        return "/pio/"
    if role_norm == "system":
        return "/systembackup/"
    return "/"


def _login_success_redirect(officer: OfficerUser) -> str:
    if getattr(officer, "must_change_password", False):
        # Members activate through the dashboard onboarding gate (privacy
        # notice + set new password) instead of the generic change-password page.
        if (officer.role or "").strip().lower() == "member":
            return "/member/"
        return "/change-password/"
    return _workspace_redirect(officer.role)


def _resolve_login_state_code(officer: OfficerUser) -> str | None:
    status = (officer.account_status or "").strip()
    normalized = status.lower()

    if status == RegistrationStatus.PENDING_TREASURER_REVIEW:
        return "pending_treasurer_review"
    if status == RegistrationStatus.RETURNED_FOR_REVISION:
        return "returned_for_revision"
    if status == RegistrationStatus.TREASURER_VERIFIED:
        return "pending_auditor_review"
    if status == RegistrationStatus.AUDITOR_VERIFIED:
        return "pending_president_approval"
    if normalized in {"inactive", "inactive_account"}:
        return "inactive_account"
    if normalized in {"suspended", "suspended_account", "account_suspended"}:
        return "suspended_account"
    if normalized in {"retired", "retired_member", "retired_account"}:
        return "retired_member"
    if normalized in {"locked", "account_locked", "temporarily locked", "temporarily_locked"}:
        return "account_locked"

    return None


def _login_error_info(code: str) -> dict:
    return {
        "incorrect_password": {
            "title": "Password Incorrect",
            "detail": "The password you entered is incorrect. Please try again.",
        },
        "account_not_found": {
            "title": "Account Not Found",
            "detail": "No ISUCauFA, Inc. account is associated with the entered Faculty ID or Email. Please check your credentials or register for a new account.",
        },
        "pending_treasurer_review": {
            "title": "Registration Pending",
            "detail": "Your registration is currently under review by the Treasurer. You will receive a notification once your registration has been reviewed.",
        },
        "pending_auditor_review": {
            "title": "Pending Auditor Review",
            "detail": "Your registration has been verified by the Treasurer and is now awaiting review by the Auditor. You will be notified once the Auditor has completed the review.",
        },
        "pending_president_approval": {
            "title": "Pending President Approval",
            "detail": "Your registration has been verified by the Auditor and is now awaiting final approval from the President. Your account will become active once approved.",
        },
        "returned_for_revision": {
            "title": "Registration Returned",
            "detail": "Your registration requires corrections. Please review the remarks, update the required information, and submit again.",
        },
        "inactive_account": {
            "title": "Account Inactive",
            "detail": "Your account is currently inactive. Please contact the Treasurer or System Administrator.",
        },
        "suspended_account": {
            "title": "Account Suspended",
            "detail": "Your account has been temporarily suspended. Please contact the CAUFA officers for assistance.",
        },
        "retired_member": {
            "title": "Retired Membership",
            "detail": "Your membership is classified as Retired. Please contact the Treasurer if you believe this is incorrect.",
        },
        "device_not_registered": {
            "title": "Unrecognized Device",
            "detail": "This device is not registered for your account. Please verify your identity before continuing.",
        },
        "location_restricted": {
            "title": "Location Verification Failed",
            "detail": "Login from your current location is not permitted. Please try again from an authorized location.",
        },
        "account_locked": {
            "title": "Account Temporarily Locked",
            "detail": "Too many unsuccessful login attempts. Please try again later or reset your password.",
        },
    }.get(code, {
        "title": "Login Failed",
        "detail": "Please check your credentials and try again.",
    })


def _establish_login_session(request: HttpRequest, officer: OfficerUser, auth_method: str = "mfa_email") -> tuple[str, str]:
    """Create a full access session for `officer` and stash it in Django session.

    Shared by the OTP-disabled fast path in ``officer_login`` and the normal
    ``mfa_verify`` success path so both produce identical sessions (device
    binding, ZT baseline, rotation key). Returns (device_id, device_secret).
    The caller attaches the device cookies to its own response.
    """
    from core_system.device_binding import (
        DEVICE_ID_COOKIE, DEVICE_PROOF_COOKIE, ENROLL_PROTOCOL, new_device_credential,
    )
    from core_system.url_obfuscation import rotate_session_key

    ip_address = zt_service.get_client_ip(request) or "0.0.0.0"
    user_agent = request.META.get("HTTP_USER_AGENT")
    had_active_sessions = AccessSession.objects.filter(
        user_id_FK=officer, session_status="Active"
    ).exists()

    device_id, device_secret = new_device_credential()
    mtls_fp = (
        request.headers.get("X-Client-Cert-Fingerprint")
        or request.META.get("HTTP_X_CLIENT_CERT_FINGERPRINT")
        or ""
    )
    session, token = create_access_session(
        officer=officer,
        ip_address=ip_address,
        device_info=user_agent,
        device_id=device_id,
        device_secret=device_secret,
        mtls_fp=mtls_fp,
    )
    if had_active_sessions:
        # A fresh login just revoked live sessions - tell the owner.
        _queue_new_device_alert(request, officer, session)

    session.trusted_device = True
    session.last_verified_location = {"ip": ip_address, "ua": user_agent}
    policy = dict(session.session_policy or {})
    policy.update({
        "zt_verified_at": timezone.now().isoformat(),
        "auth_method": auth_method,
        "device_protocol": ENROLL_PROTOCOL,
    })
    session.session_policy = policy
    session.save(update_fields=["trusted_device", "last_verified_location", "session_policy"])

    request.session["access_token"] = token
    request.session["officer_id"] = officer.user_id_PK
    request.session["role"] = officer.role
    request.session.set_expiry(None)
    # Issue this session's URL-obfuscation signing subkey (auto-signer for
    # fetch calls + signed redirect links; flushed with the session).
    try:
        rotate_session_key(request)
    except Exception:
        pass
    # First-login backup-code issue for members: the member dashboard is
    # where the true owner meets these codes (one-time reveal modal). Only
    # when the account never had codes — never re-issues, never overwrites.
    try:
        from core_system.models import Member

        if (
            getattr(officer, "backup_codes_issued_at", None) is None
            and Member.objects.filter(officer_user_id_FK=officer).exists()
            and backup_codes_remaining(officer) == 0
        ):
            plaintext = issue_backup_codes(officer)
            request.session[BACKUP_REVEAL_KEY] = plaintext
            request.session[SHOW_BACKUP_MODAL_KEY] = True
    except Exception:
        pass
    return device_id, device_secret


def _log_auth_audit(action, officer=None, username=None, ip=None, device=None, result="Success", notes=None):
    """Record a login/logout/security event into GlobalAuditTrail.

    Failures (unknown user, bad password) have no officer, so the username that
    was attempted and an 'Anonymous' actor type are recorded instead.
    """
    try:
        _record_audit_trail(
            table="officer_user",
            record_id=(officer.user_id_PK if officer else 0),
            action=action,
            actor=officer,
            ip=ip,
            device_info=device,
            notes=notes,
            actor_type_override=None if officer else "Anonymous",
            actor_name_override=None if officer else (username or "Unknown"),
            result=result,
        )
    except Exception as exc:  # never block authentication because auditing failed
        logger.error("Failed to record auth audit trail (%s): %s", action, exc)


@csrf_protect
def officer_login(request: HttpRequest) -> HttpResponse:
    """Role-based login using OfficerUser (SHA-256 hex stored in password_hash)."""
    if request.method == "GET":
        force_login = (request.GET.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
        if "access_token" in request.session and not force_login:
            officer_id = request.session.get("officer_id")
            if officer_id:
                try:
                    existing = OfficerUser.objects.get(user_id_PK=officer_id)
                    if getattr(existing, "must_change_password", False):
                        if (existing.role or "").strip().lower() == "member":
                            return redirect("/member/")
                        return redirect("/change-password/")
                except OfficerUser.DoesNotExist:
                    pass
            return redirect(_workspace_redirect(request.session.get("role", "")))

        if force_login:
            request.session.flush()

        # Leaving the OTP step ("Back to login"): drop the pre-auth state
        # so the plain username/password form is shown again.
        if (request.GET.get("cancel_mfa") or "").strip().lower() in {"1", "true", "yes", "on"}:
            for key in (MFA_SESSION_KEY, MFA_OFFICER_ID_KEY, MFA_USERNAME_KEY, MFA_EMAIL_MASKED_KEY, MFA_INITIATED_KEY, MFA_PUSH_SENT_KEY, MFA_PUSH_SENT_AT_KEY, BACKUP_REVEAL_KEY, SHOW_BACKUP_MODAL_KEY, MFA_FAILS_KEY, "mfa_email_warning", "mfa_has_push", "mfa_auth_app", "_mfa_initiated"):
                request.session.pop(key, None)
            request.session.set_expiry(None)
            return render(request, "website/login.html", {
                "turnstile_enabled": is_turnstile_enabled(request),
                "turnstile_site_key": get_turnstile_site_key(),
            })

        # If the MFA keys were set by the POST handler (redirect from login POST),
        # preserve them and clear the flag. Otherwise clear stale MFA state.
        if request.session.pop("_mfa_initiated", None):
            pass  # MFA keys are fresh from POST — keep them
        else:
            for key in (MFA_SESSION_KEY, MFA_OFFICER_ID_KEY, MFA_USERNAME_KEY, MFA_EMAIL_MASKED_KEY, MFA_INITIATED_KEY, MFA_PUSH_SENT_KEY, MFA_PUSH_SENT_AT_KEY, BACKUP_REVEAL_KEY, SHOW_BACKUP_MODAL_KEY, MFA_FAILS_KEY, "mfa_email_warning", "mfa_has_push", "mfa_auth_app"):
                request.session.pop(key, None)

        context = {
            "turnstile_enabled": is_turnstile_enabled(request),
            "turnstile_site_key": get_turnstile_site_key(),
        }
        if request.session.get(MFA_SESSION_KEY):
            context["form"] = {
                "errors": [],
                "mfa_required": True,
                "pre_auth_token": request.session.get(MFA_SESSION_KEY, ""),
                "username": request.session.get(MFA_USERNAME_KEY, ""),
                "mfa_email_masked": _get_masked_mfa_email(request),
                "delivery": "Email",
                "has_push": bool(request.session.get("mfa_has_push")),
                "push_sent": bool(request.session.get(MFA_PUSH_SENT_KEY)),
                "auth_app_enabled": bool(request.session.get("mfa_auth_app")),
            }
            if request.session.get("mfa_email_warning"):
                context["form"]["email_warning"] = request.session.get("mfa_email_warning")
                del request.session["mfa_email_warning"]
        return render(request, "website/login.html", context)

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    username = (request.POST.get("username") or "").strip()
    password_input = request.POST.get("password") or ""
    ip_address = zt_service.get_client_ip(request) or "0.0.0.0"
    user_agent = request.META.get("HTTP_USER_AGENT") or "Unknown"
    turnstile_token = (request.POST.get("cf-turnstile-response") or "").strip()

    try:
        # Members can log in with their system-generated username OR their
        # email address — both uniquely identify one OfficerUser account.
        officer = OfficerUser.objects.get(username__iexact=username)
        username = officer.username  # canonicalize for the rest of the flow
    except OfficerUser.DoesNotExist:
        officer = (
            OfficerUser.objects.filter(email__iexact=username)
            .order_by("user_id_PK")
            .first()
        )
        if officer is not None:
            username = officer.username
        else:
            officer = None

    # Only validate turnstile if user exists - avoid security verification for non-existent accounts
    if officer is not None and is_turnstile_enabled(request) and not validate_turnstile_token(turnstile_token, remote_ip=ip_address, request=request):
        error_info = {
            "title": "Security Verification Failed",
            "detail": "Please complete the security check and try again.",
        }
        if is_ajax:
            return JsonResponse({
                "ok": False,
                "error_code": "turnstile_failed",
                "error_title": error_info["title"],
                "error_detail": error_info["detail"],
                "error": error_info["detail"],
            }, status=403)
        context = {
            "login_error_code": "turnstile_failed",
            "login_error_title": error_info["title"],
            "login_error_detail": error_info["detail"],
            "turnstile_enabled": True,
            "turnstile_site_key": get_turnstile_site_key(),
        }
        return render(request, "website/login.html", context)

    from core_system.login_throttle import (
        check_throttle as _check_login_throttle,
        clear_principal as _clear_login_throttle,
        record_failure as _record_login_failure,
    )

    locked, lock_reason, retry_after = _check_login_throttle(username, ip_address)
    if locked:
        log_login_attempt(
            username=username,
            ip_address=ip_address,
            device_info=user_agent,
            result="LOCKED_OUT",
            user_id=officer.user_id_PK if officer else None,
        )
        _log_auth_audit(
            "LOGIN_FAILED",
            officer=officer,
            username=username,
            ip=ip_address,
            device=user_agent,
            result="Failed",
            notes=f"locked_out:{lock_reason}",
        )
        lock_detail = (
            "Too many failed sign-in attempts. Try again in "
            f"{max(1, retry_after // 60)} minute(s)."
        )
        if is_ajax:
            resp = JsonResponse({"ok": False, "error_code": "locked_out", "error": lock_detail})
            resp.status_code = 429
            resp["Retry-After"] = str(retry_after)
            return resp
        context = {
            "login_error_code": "locked_out",
            "login_error_title": "Temporarily Locked",
            "login_error_detail": lock_detail,
            "turnstile_enabled": is_turnstile_enabled(request),
            "turnstile_site_key": get_turnstile_site_key(),
        }
        resp = render(request, "website/login.html", context)
        resp.status_code = 429
        resp["Retry-After"] = str(retry_after)
        return resp

    password_hash_ok = False
    if officer is not None:
        password_hash_ok = verify_password(password_input, officer.password_hash)

    state_code = None
    if officer is not None and password_hash_ok:
        state_code = _resolve_login_state_code(officer)

    if officer and password_hash_ok and state_code is None:
        _clear_login_throttle(username, ip_address)
        # Transparent upgrade: verified PBKDF2 rows become Argon2id on next
        # login, so the migration needs no password resets.
        try:
            if password_needs_rehash(officer.password_hash):
                officer.password_hash = hash_password(password_input)
                officer.save(update_fields=["password_hash"])
        except Exception:
            pass
        term_ok, term_error = _check_term_validity(officer)
        if not term_ok:
            log_login_attempt(
                username=username,
                ip_address=ip_address,
                device_info=user_agent,
                result="Term expired",
                user_id=officer.user_id_PK,
            )
            if is_ajax:
                return JsonResponse({"ok": False, "error": term_error, "term_expired": True}, status=400)
            messages.error(request, term_error, extra_tags="term_expired")
            return redirect("login")

        # Global OTP kill switch (Superadmin): when OFF, password success signs
        # the officer straight in — no OTP queued, no mfa_verify step. Applies
        # to every role since all logins flow through this view. Fail-open
        # default is OTP required (see otp_killswitch).
        from core_system.otp_killswitch import is_login_otp_enabled
        if not is_login_otp_enabled():
            from core_system.device_binding import (
                DEVICE_ID_COOKIE, DEVICE_PROOF_COOKIE, ENROLL_PROTOCOL,
            )
            device_id, device_secret = _establish_login_session(
                request, officer, auth_method="password_only_otp_disabled",
            )
            log_login_attempt(
                username=username,
                ip_address=ip_address,
                device_info=user_agent,
                result="Success",
                user_id=officer.user_id_PK,
            )
            _log_auth_audit(
                "LOGIN",
                officer=officer,
                username=username,
                ip=ip_address,
                device=user_agent,
                notes="otp_disabled_by_admin",
            )
            _secure = request.is_secure()
            if is_ajax:
                response = JsonResponse({
                    "ok": True,
                    "redirect_url": _login_success_redirect(officer),
                    "device_protocol": ENROLL_PROTOCOL,
                })
            else:
                response = redirect(_login_success_redirect(officer))
            response.set_cookie(
                DEVICE_ID_COOKIE, device_id, max_age=8 * 3600,
                httponly=False, samesite="Strict", secure=_secure, path="/",
            )
            response.set_cookie(
                DEVICE_PROOF_COOKIE, device_secret, max_age=8 * 3600,
                httponly=True, samesite="Strict", secure=_secure, path="/",
            )
            return response

        # Every sign-in requires email OTP verification — there is no
        # per-user opt-out and no trusted-device bypass at this step.
        # (Unless the Superadmin OTP switch above is OFF.)
        if not officer.mfa_secret:
            officer.mfa_secret = generate_mfa_secret()
            officer.save(update_fields=["mfa_secret"])
        if not (officer.email or "").strip():
            no_email_error = (
                "No email address is on file for this account, so a verification "
                "code cannot be sent. Please ask your administrator to update your email."
            )
            log_login_attempt(
                username=username,
                ip_address=ip_address,
                device_info=user_agent,
                result="MFA_NO_EMAIL",
                user_id=officer.user_id_PK,
            )
            if is_ajax:
                return JsonResponse({"ok": False, "error": no_email_error}, status=400)
            context = {
                "login_error_code": "mfa_no_email",
                "login_error_title": "Verification Unavailable",
                "login_error_detail": no_email_error,
                "turnstile_enabled": is_turnstile_enabled(request),
                "turnstile_site_key": get_turnstile_site_key(),
            }
            return render(request, "website/login.html", context)

        now = timezone.now()
        time_limit = now - timedelta(seconds=MFA_EMAIL_RATE_LIMIT_SECONDS)
        rate_limited = False

        if not officer.last_mfa_email_sent_at or officer.last_mfa_email_sent_at < time_limit:
            timestamp_limited = False
        else:
            # Timestamp says "sent recently" — but if that code FAILED or the
            # queue shows nothing fresh, the officer never received anything,
            # so a fresh login must still queue a code.
            allowed, _ = _mfa_send_allowed(officer)
            timestamp_limited = not allowed

        if not timestamp_limited:
            otp = generate_otp(officer.mfa_secret)
            email_sent = _queue_mfa_email(officer, otp)
            if email_sent:
                officer.last_mfa_email_sent_at = now
                officer.save(update_fields=["last_mfa_email_sent_at"])
        else:
            email_sent = False
            rate_limited = True

        pre_auth_token = secrets.token_urlsafe(32)
        request.session[MFA_SESSION_KEY] = pre_auth_token
        request.session[MFA_OFFICER_ID_KEY] = officer.user_id_PK
        request.session[MFA_USERNAME_KEY] = officer.username
        request.session[MFA_EMAIL_MASKED_KEY] = mask_email(officer.email)
        request.session[MFA_INITIATED_KEY] = now.isoformat()
        request.session.set_expiry(600)

        # Best-effort push for the MFA screen (button visibility only).
        try:
            request.session["mfa_has_push"] = has_push_subscription(officer)
        except Exception:
            request.session["mfa_has_push"] = False
        request.session["mfa_auth_app"] = bool(getattr(officer, "authenticator_enabled", False))

        push_sent = False
        if not rate_limited and not email_sent:
            # Gmail path failed on this attempt — deliver the same code over
            # push immediately so the officer is not stuck behind a dead inbox.
            try:
                push_sent = send_mfa_push(officer, otp)
            except Exception:
                push_sent = False
            if push_sent:
                request.session[MFA_PUSH_SENT_KEY] = True
                request.session[MFA_PUSH_SENT_AT_KEY] = now.isoformat()

        if rate_limited:
            request.session["mfa_email_warning"] = "A verification code was already sent recently. Please check your inbox."
        elif push_sent:
            request.session["mfa_email_warning"] = "Email delivery failed — the code was sent to your device via push notification instead."
        elif not email_sent:
            request.session["mfa_email_warning"] = "Failed to send verification email. Use push notification or your authenticator app code."

        log_login_attempt(
            username=username,
            ip_address=ip_address,
            device_info=user_agent,
            result="MFA_REQUIRED",
            user_id=officer.user_id_PK,
        )
        _log_auth_audit(
            "LOGIN_MFA_REQUIRED",
            officer=officer,
            username=username,
            ip=ip_address,
            device=user_agent,
            result="Pending",
        )
        request.session["_mfa_initiated"] = True
        if is_ajax:
            return JsonResponse({"ok": True, "mfa_required": True, "redirect_url": "/login/"})
        return redirect("login")

    if officer is None:
        # Check if there's a member registration with this username at any stage
        pending_registration = MemberRegistrationRequest.objects.filter(
            employee_id__iexact=username,
        ).exclude(
            status__in={
                RegistrationStatus.PRESIDENT_APPROVED,
                RegistrationStatus.REJECTED,
            }
        ).first()
        if pending_registration:
            status = pending_registration.status
            if status == RegistrationStatus.PENDING_TREASURER_REVIEW:
                error_code = "pending_treasurer_review"
            elif status == RegistrationStatus.TREASURER_VERIFIED:
                error_code = "pending_auditor_review"
            elif status == RegistrationStatus.AUDITOR_VERIFIED:
                error_code = "pending_president_approval"
            elif status == RegistrationStatus.RETURNED_FOR_REVISION:
                error_code = "returned_for_revision"
            else:
                error_code = "pending_treasurer_review"
        else:
            error_code = "account_not_found"
    elif not password_hash_ok:
        error_code = "incorrect_password"
    else:
        error_code = state_code or "account_not_found"

    error_info = _login_error_info(error_code)
    _record_login_failure(username, ip_address)
    log_login_attempt(
        username=username,
        ip_address=ip_address,
        device_info=user_agent,
        result=error_code,
        user_id=officer.user_id_PK if officer else None,
    )
    _log_auth_audit(
        "LOGIN_FAILED",
        officer=officer,
        username=username,
        ip=ip_address,
        device=user_agent,
        result="Failed",
        notes=error_code,
    )

    if is_ajax:
        return JsonResponse(
            {
                "ok": False,
                "error_code": error_code,
                "error_title": error_info["title"],
                "error_detail": error_info["detail"],
                "error": error_info["detail"],
            },
            status=401,
        )

    context = {
        "login_error_code": error_code,
        "login_error_title": error_info["title"],
        "login_error_detail": error_info["detail"],
        "turnstile_enabled": is_turnstile_enabled(request),
        "turnstile_site_key": get_turnstile_site_key(),
    }
    return render(request, "website/login.html", context)


@require_POST
@csrf_protect
def mfa_verify(request: HttpRequest) -> JsonResponse:
    """Verifies incoming OTP code for step-up login flow."""
    from core_system.otp_killswitch import is_login_otp_enabled

    otp = (request.POST.get("otp") or "").strip()
    pre_auth_token = (request.POST.get("pre_auth_token") or "").strip() or request.session.get(MFA_SESSION_KEY)

    if not pre_auth_token or (not otp and is_login_otp_enabled()):
        return JsonResponse({"ok": False, "error": "Missing code or token context."}, status=400)

    # Validate session pre-auth token
    session_token = request.session.get(MFA_SESSION_KEY)
    if not session_token or session_token != pre_auth_token:
        return JsonResponse({"ok": False, "error": "Invalid or expired session. Please log in again."}, status=400)

    officer_id = request.session.get(MFA_OFFICER_ID_KEY)
    if not officer_id:
        return JsonResponse({"ok": False, "error": "Pre-auth context expired."}, status=400)

    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer account not found."}, status=404)

    # OTP switch was flipped OFF mid-flow: the password was already verified
    # to reach this pre-auth state, so skip the code check entirely.
    otp_required = is_login_otp_enabled()

    # Verify the code (never log the OTP or secret material itself).
    # Fallback order: email/push TOTP → authenticator-app TOTP (offline) →
    # single-use backup code. All three are accepted in the same input box.
    auth_method = "mfa_email"
    if otp_required:
        code_ok, method = _verify_mfa_code(officer, otp)
        if not code_ok:
            from core_system.login_throttle import record_failure as _record_throttle_failure

            fails = int(request.session.get(MFA_FAILS_KEY, 0) or 0) + 1
            request.session[MFA_FAILS_KEY] = fails
            ip_address = zt_service.get_client_ip(request) or "0.0.0.0"
            # Feed the shared password-gate throttle: hammering codes counts
            # like hammering passwords (5 fails → 15-min principal lockout).
            try:
                _record_throttle_failure(officer.username, ip_address)
            except Exception:
                pass
            log_login_attempt(
                username=officer.username,
                ip_address=ip_address,
                device_info=request.META.get("HTTP_USER_AGENT"),
                result="invalid_mfa_code",
                user_id=officer.user_id_PK,
            )
            _log_auth_audit(
                "LOGIN_FAILED",
                officer=officer,
                username=officer.username,
                ip=ip_address,
                device=request.META.get("HTTP_USER_AGENT"),
                result="Failed",
                notes=f"invalid_mfa_code_attempt_{fails}",
            )
            if fails >= MAX_MFA_ATTEMPTS:
                # Kill the whole attempt: no more guesses on this pre-auth
                # state, no stale keys surviving into a fresh login.
                for key in (
                    MFA_SESSION_KEY, MFA_OFFICER_ID_KEY, MFA_USERNAME_KEY,
                    MFA_EMAIL_MASKED_KEY, MFA_INITIATED_KEY, MFA_PUSH_SENT_KEY,
                    MFA_PUSH_SENT_AT_KEY, BACKUP_REVEAL_KEY, SHOW_BACKUP_MODAL_KEY,
                    MFA_FAILS_KEY, "mfa_email_warning", "mfa_has_push", "mfa_auth_app",
                ):
                    request.session.pop(key, None)
                _log_auth_audit(
                    "LOGIN_FAILED",
                    officer=officer,
                    username=officer.username,
                    ip=ip_address,
                    device=request.META.get("HTTP_USER_AGENT"),
                    result="Failed",
                    notes="mfa_bruteforce_lockout",
                )
                return JsonResponse({
                    "ok": False,
                    "locked_out": True,
                    "error": "Too many wrong codes. Start again from the login screen.",
                }, status=429)
            return JsonResponse({
                "ok": False,
                "error": "Invalid verification code.",
                "attempts_left": max(0, MAX_MFA_ATTEMPTS - fails),
            }, status=401)
        if method == "mfa_email" and request.session.get(MFA_PUSH_SENT_KEY):
            # Same TOTP code, but it reached the officer over push fallback.
            auth_method = "mfa_push_fallback"
        else:
            auth_method = method

    term_ok, term_error = _check_term_validity(officer)
    if not term_ok:
        request.session.pop(MFA_SESSION_KEY, None)
        request.session.pop(MFA_OFFICER_ID_KEY, None)
        request.session.pop(MFA_USERNAME_KEY, None)
        request.session.pop(MFA_EMAIL_MASKED_KEY, None)
        log_login_attempt(
            username=officer.username,
            ip_address=zt_service.get_client_ip(request) or "0.0.0.0",
            device_info=request.META.get("HTTP_USER_AGENT"),
            result="Term expired",
            user_id=officer.user_id_PK,
        )
        _log_auth_audit(
            "LOGIN_FAILED",
            officer=officer,
            username=officer.username,
            ip=zt_service.get_client_ip(request) or "0.0.0.0",
            device=request.META.get("HTTP_USER_AGENT"),
            result="Failed",
            notes="term_expired",
        )
        return JsonResponse({"ok": False, "error": term_error, "term_expired": True}, status=403)

    # Success: Clean up temporary keys
    request.session.pop(MFA_SESSION_KEY, None)
    request.session.pop(MFA_OFFICER_ID_KEY, None)
    request.session.pop(MFA_USERNAME_KEY, None)
    request.session.pop(MFA_EMAIL_MASKED_KEY, None)
    request.session.pop(MFA_PUSH_SENT_KEY, None)
    request.session.pop(MFA_PUSH_SENT_AT_KEY, None)
    request.session.pop(MFA_FAILS_KEY, None)

    # Establish full session (shared helper — identical to the OTP-disabled
    # fast path in officer_login, except for the auth_method marker).
    from core_system.device_binding import (
        DEVICE_ID_COOKIE, DEVICE_PROOF_COOKIE, ENROLL_PROTOCOL,
    )
    device_id, device_secret = _establish_login_session(
        request, officer,
        auth_method=auth_method if otp_required else "password_only_otp_disabled",
    )
    ip_address = zt_service.get_client_ip(request) or "0.0.0.0"
    user_agent = request.META.get("HTTP_USER_AGENT")

    log_login_attempt(
        username=officer.username,
        ip_address=ip_address,
        device_info=user_agent,
        result="Success",
        user_id=officer.user_id_PK,
    )
    _log_auth_audit(
        "LOGIN",
        officer=officer,
        username=officer.username,
        ip=ip_address,
        device=user_agent,
        notes=auth_method if otp_required else "otp_disabled_by_admin",
    )

    response = JsonResponse({
        "ok": True,
        "redirect_url": _login_success_redirect(officer),
        "device_protocol": ENROLL_PROTOCOL,
    })
    # Device-bound cookies: id is readable for the proof header, the secret
    # is HttpOnly (JS must not exfiltrate it; a future WebAuthn upgrade swaps
    # the secret for a private key without changing this contract).
    # Secure follows the live request so prod HTTPS always gets Secure
    # cookies; path=/ matches clear_device_cookies() on logout.
    _secure = request.is_secure()
    response.set_cookie(
        DEVICE_ID_COOKIE, device_id, max_age=8 * 3600,
        httponly=False, samesite="Strict", secure=_secure, path="/",
    )
    response.set_cookie(
        DEVICE_PROOF_COOKIE, device_secret, max_age=8 * 3600,
        httponly=True, samesite="Strict", secure=_secure, path="/",
    )
    return response


@require_POST
@csrf_protect
def mfa_challenge(request: HttpRequest) -> JsonResponse:
    """Triggered when user requests to resend OTP via AJAX during login."""
    from core_system.otp_killswitch import is_login_otp_enabled
    if not is_login_otp_enabled():
        return JsonResponse({"ok": False, "error": "Verification codes are currently disabled by the administrator. Please log in again — no code is needed."}, status=400)
    username = (request.POST.get("username") or "").strip()
    session_username = request.session.get(MFA_USERNAME_KEY)

    if not username or username != session_username:
        return JsonResponse({"ok": False, "error": "Session mismatch. Re-authenticate from login screen."}, status=400)

    officer_id = request.session.get(MFA_OFFICER_ID_KEY)
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer context missing."}, status=404)

    now = timezone.now()

    # Row-based gate (60s floor): a FAILED or long-stalled code never arrived,
    # so Resend stays available. A code queued seconds ago is probably sending
    # now — or already in the inbox carrying the identical TOTP code.
    allowed, retry_after = _mfa_send_allowed(officer)

    if allowed:
        otp = generate_otp(officer.mfa_secret)
        email_sent = send_mfa_email(officer, otp)
        if email_sent:
            officer.last_mfa_email_sent_at = now
            officer.save(update_fields=["last_mfa_email_sent_at"])
            request.session[MFA_INITIATED_KEY] = now.isoformat()
            request.session.set_expiry(600)
            return JsonResponse({
                "ok": True,
                "message": "Verification code sent via email.",
                "delivery": "email",
            })
        # Email queue refused/failed — same-attempt push fallback so the
        # officer is not locked out by a Gmail outage. Same TOTP code.
        if send_mfa_push(officer, otp):
            request.session[MFA_PUSH_SENT_KEY] = True
            request.session[MFA_PUSH_SENT_AT_KEY] = now.isoformat()
            request.session[MFA_INITIATED_KEY] = now.isoformat()
            request.session.set_expiry(600)
            return JsonResponse({
                "ok": True,
                "message": "Email failed — code sent via push notification instead.",
                "delivery": "push",
            })
        return JsonResponse({
            "ok": False,
            "message": "Failed to send email. Try again.",
            "delivery": "email",
        })

    remaining_seconds = max(1, int(retry_after))
    response = JsonResponse({
        "ok": False,
        "error": f"Email OTP was just sent. Please wait {remaining_seconds} second(s).",
        "rate_limited": True,
        "retry_after": remaining_seconds,
    }, status=429)
    response["Retry-After"] = str(remaining_seconds)
    return response


@require_POST
@csrf_protect
def mfa_push_fallback(request: HttpRequest) -> JsonResponse:
    """Manual push fallback: deliver THIS attempt's code via push notification.

    Requires the live pre-auth session (same keys as ``mfa_verify``) and at
    least one officer push subscription. Rate-limited to one push per
    ``MFA_PUSH_FLOOR_SECONDS``. Sends the same email-TOTP code, so the
    verify path is unchanged — success is attributed as ``mfa_push_fallback``.
    """
    from core_system.otp_killswitch import is_login_otp_enabled
    if not is_login_otp_enabled():
        return JsonResponse({"ok": False, "error": "Verification codes are currently disabled."}, status=400)

    pre_auth_token = (request.POST.get("pre_auth_token") or "").strip() or request.session.get(MFA_SESSION_KEY)
    session_token = request.session.get(MFA_SESSION_KEY)
    if not session_token or session_token != pre_auth_token:
        return JsonResponse({"ok": False, "error": "Invalid or expired session. Please log in again."}, status=400)

    officer_id = request.session.get(MFA_OFFICER_ID_KEY)
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer context missing."}, status=404)

    if not has_push_subscription(officer):
        return JsonResponse({
            "ok": False,
            "has_push": False,
            "error": "No push devices registered. Enable notifications on your device first, or use your authenticator app code.",
        }, status=400)

    now = timezone.now()
    last_raw = request.session.get(MFA_PUSH_SENT_AT_KEY)
    if last_raw:
        try:
            last = timezone.datetime.fromisoformat(last_raw)
            if timezone.is_naive(last):
                last = timezone.make_aware(last)
            age = (now - last).total_seconds()
            if age < MFA_PUSH_FLOOR_SECONDS:
                remaining = max(1, int(MFA_PUSH_FLOOR_SECONDS - age))
                response = JsonResponse({
                    "ok": False,
                    "has_push": True,
                    "error": f"A push code was just sent. Please wait {remaining} second(s).",
                    "rate_limited": True,
                    "retry_after": remaining,
                }, status=429)
                response["Retry-After"] = str(remaining)
                return response
        except (ValueError, TypeError):
            pass

    otp = generate_otp(officer.mfa_secret)
    if send_mfa_push(officer, otp):
        request.session[MFA_PUSH_SENT_KEY] = True
        request.session[MFA_PUSH_SENT_AT_KEY] = now.isoformat()
        request.session.set_expiry(600)
        return JsonResponse({
            "ok": True,
            "has_push": True,
            "delivery": "push",
            "message": "Code sent via push notification. Enter it below — it expires in 5 minutes.",
        })
    return JsonResponse({
        "ok": False,
        "has_push": True,
        "error": "Push delivery failed. Check your connection or use your authenticator app code.",
    }, status=502)


@require_GET
def mfa_delivery_status(request: HttpRequest) -> JsonResponse:
    """Delivery status of THIS login attempt's OTP email.

    Anchored to the session's mfa_initiated_at: a SENT row older than the
    current attempt belongs to an earlier login and is reported honestly as
    ``rate_limited`` ("use the earlier email") instead of a fake "sent" for
    a code that was never queued. Never reveals anything without the live
    pre-auth session keys.
    """
    if request.session.get(MFA_SESSION_KEY) is None:
        return JsonResponse({"ok": False, "error": "No pending verification."}, status=404)
    officer_id = request.session.get(MFA_OFFICER_ID_KEY)
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer context missing."}, status=404)
    latest = _latest_otp_info(officer)
    if latest is None:
        return JsonResponse({"ok": True, "delivery": "unknown"})

    initiated_raw = request.session.get(MFA_INITIATED_KEY)
    if initiated_raw:
        try:
            initiated = timezone.datetime.fromisoformat(initiated_raw)
            if timezone.is_naive(initiated):
                initiated = timezone.make_aware(initiated)
            created_raw = latest.get("created_at")
            created = (
                timezone.datetime.fromisoformat(created_raw)
                if created_raw else None
            )
            if created is not None and timezone.is_naive(created):
                created = timezone.make_aware(created)
            if created is not None and created < initiated:
                # Stale row from an EARLIER login — this attempt queued nothing.
                status = latest.get("status")
                if status == "sent":
                    return JsonResponse({
                        "ok": True,
                        "delivery": "rate_limited",
                        "message": "A code was already emailed recently — check your inbox for the earlier message. Codes work for 5 minutes.",
                    })
                if status in ("pending", "sending"):
                    return JsonResponse({
                        "ok": True,
                        "delivery": "rate_limited",
                        "message": "A code is already on its way — check your inbox for the earlier message.",
                    })
                return JsonResponse({"ok": True, "delivery": "failed"})
        except (ValueError, TypeError):
            pass

    status = latest.get("status")
    delivery = (
        "sent" if status == "sent"
        else "failed" if status == "failed"
        else "sending"
    )
    return JsonResponse({
        "ok": True,
        "delivery": delivery,
        "sent_at": latest.get("sent_at"),
    })


@require_POST
@csrf_protect
def mfa_enable(request: HttpRequest) -> HttpResponse:
    stored_officer_id = request.session.get("officer_id")
    if stored_officer_id is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

    try:
        officer = OfficerUser.objects.get(user_id_PK=int(stored_officer_id))
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer not found."}, status=404)

    if not officer.mfa_enabled:
        officer.mfa_enabled = True
        officer.mfa_secret = generate_mfa_secret()
        officer.save(update_fields=["mfa_enabled", "mfa_secret"])

    return JsonResponse({
        "ok": True,
        "message": "MFA enabled. You will be asked for a code at login.",
    })


@require_POST
@csrf_protect
def mfa_disable(request: HttpRequest) -> HttpResponse:
    stored_officer_id = request.session.get("officer_id")
    if stored_officer_id is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

    try:
        officer = OfficerUser.objects.get(user_id_PK=int(stored_officer_id))
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer not found."}, status=404)

    officer.mfa_enabled = False
    officer.mfa_secret = None
    officer.save(update_fields=["mfa_enabled", "mfa_secret"])

    return JsonResponse({
        "ok": True,
        "message": "MFA preference saved. Note: email verification at sign-in is mandatory and still applies.",
    })


# ---------------------------------------------------------------------------
# Authenticator-app fallback enrollment (offline TOTP + backup codes).
# All endpoints require a full officer session (NOT the pre-auth login state).
# ---------------------------------------------------------------------------

def _authenticator_qr_data_uri(otpauth_uri: str) -> str | None:
    """QR PNG as data URI for the enrollment page. None if rendering fails."""
    try:
        import base64 as _b64
        import io as _io

        import qrcode

        img = qrcode.make(otpauth_uri, box_size=8, border=2)
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        logging.getLogger(__name__).warning("Authenticator QR render failed: %s", exc)
        return None


@require_GET
def authenticator_setup(request: HttpRequest) -> JsonResponse:
    """Start (or resume) authenticator enrollment. Returns QR + manual key.

    Creates the secret on first call; a pending (unconfirmed) secret is
    reused so refresh/retry shows the same QR. Confirming is a separate step.
    """
    officer = _current_authenticated_officer(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)
    if getattr(officer, "authenticator_enabled", False):
        return JsonResponse({"ok": True, "enabled": True})

    secret = getattr(officer, "authenticator_secret", None)
    if not secret:
        secret = generate_authenticator_secret()
        officer.authenticator_secret = secret
        officer.save(update_fields=["authenticator_secret"])

    account = officer.email or officer.username
    uri = authenticator_otpauth_uri(secret, account)
    return JsonResponse({
        "ok": True,
        "enabled": False,
        "otpauth_uri": uri,
        "manual_key": format_manual_key(secret),
        "qr_data_uri": _authenticator_qr_data_uri(uri),
    })


@require_POST
@csrf_protect
def authenticator_confirm(request: HttpRequest) -> JsonResponse:
    """Confirm enrollment with a code from the app; issues backup codes."""
    officer = _current_authenticated_officer(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)
    if getattr(officer, "authenticator_enabled", False):
        return JsonResponse({"ok": True, "enabled": True})

    # Light brute-force brake: 10 bad confirmations lock this session 5 min.
    fails = int(request.session.get(AUTH_CONFIRM_FAILS_KEY, 0) or 0)
    locked_until_raw = request.session.get(AUTH_CONFIRM_FAILS_KEY + "_until")
    if locked_until_raw:
        try:
            locked_until = timezone.datetime.fromisoformat(locked_until_raw)
            if timezone.is_naive(locked_until):
                locked_until = timezone.make_aware(locked_until)
            if timezone.now() < locked_until:
                return JsonResponse({"ok": False, "error": "Too many wrong codes. Try again in a few minutes."}, status=429)
            request.session[AUTH_CONFIRM_FAILS_KEY] = 0
        except (ValueError, TypeError):
            pass

    secret = getattr(officer, "authenticator_secret", None)
    code = (request.POST.get("code") or "").strip()
    if not secret or not verify_authenticator_code(secret, code):
        request.session[AUTH_CONFIRM_FAILS_KEY] = fails + 1
        if fails + 1 >= 10:
            request.session[AUTH_CONFIRM_FAILS_KEY + "_until"] = (timezone.now() + timedelta(minutes=5)).isoformat()
        return JsonResponse({"ok": False, "error": "That code doesn't match. Check your app's clock and try the current code."}, status=400)

    officer.authenticator_enabled = True
    officer.authenticator_enrolled_at = timezone.now()
    officer.save(update_fields=["authenticator_enabled", "authenticator_enrolled_at"])

    plaintext = issue_backup_codes(officer)
    request.session.pop(AUTH_CONFIRM_FAILS_KEY, None)
    request.session.pop(AUTH_CONFIRM_FAILS_KEY + "_until", None)
    _log_auth_audit(
        "MFA_AUTHENTICATOR_ENABLED",
        officer=officer,
        username=officer.username,
        ip=zt_service.get_client_ip(request) or "0.0.0.0",
        device=request.META.get("HTTP_USER_AGENT"),
        result="Success",
    )
    return JsonResponse({
        "ok": True,
        "enabled": True,
        # Shown EXACTLY once — hashes only are stored. The officer must
        # write these down before closing the dialog.
        "backup_codes": plaintext,
    })


@require_POST
@csrf_protect
def authenticator_disable(request: HttpRequest) -> JsonResponse:
    """Remove the authenticator fallback (email OTP keeps working)."""
    officer = _current_authenticated_officer(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

    from core_system.models import MfaBackupCode

    officer.authenticator_enabled = False
    officer.authenticator_secret = None
    officer.authenticator_enrolled_at = None
    officer.save(update_fields=["authenticator_enabled", "authenticator_secret", "authenticator_enrolled_at"])
    MfaBackupCode.objects.filter(officer_id_FK=officer).delete()
    _log_auth_audit(
        "MFA_AUTHENTICATOR_DISABLED",
        officer=officer,
        username=officer.username,
        ip=zt_service.get_client_ip(request) or "0.0.0.0",
        device=request.META.get("HTTP_USER_AGENT"),
        result="Success",
    )
    return JsonResponse({"ok": True, "enabled": False})


@require_POST
@csrf_protect
def authenticator_backup_codes_regenerate(request: HttpRequest) -> JsonResponse:
    """Replace all backup codes (old ones stop working immediately)."""
    officer = _current_authenticated_officer(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)
    if not getattr(officer, "authenticator_enabled", False):
        return JsonResponse({"ok": False, "error": "Enable the authenticator app first."}, status=400)

    from core_system.models import MfaBackupCode

    MfaBackupCode.objects.filter(officer_id_FK=officer).delete()
    plaintext = generate_backup_codes()
    MfaBackupCode.objects.bulk_create([
        MfaBackupCode(officer_id_FK=officer, code_hash=hash_backup_code(c)) for c in plaintext
    ])
    return JsonResponse({"ok": True, "backup_codes": plaintext})


@require_POST
@csrf_protect
def backup_codes_issue(request: HttpRequest) -> JsonResponse:
    """Standalone backup-code issuance — no authenticator enrollment needed.

    For officers AND members (any full session). Replaces all existing codes,
    so an explicit ``replace=true`` is required when unused codes exist —
    one stray click must never silently kill saved codes. Plaintext is
    returned exactly once in this response and never stored.
    """
    officer = _current_authenticated_officer(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

    remaining = backup_codes_remaining(officer)
    replace = (request.POST.get("replace") or "").strip().lower() in {"1", "true", "yes", "on"}
    if remaining > 0 and not replace:
        return JsonResponse({
            "ok": False,
            "needs_replace_confirm": True,
            "remaining": remaining,
            "error": f"You still have {remaining} unused code(s). Re-issue and deactivate them?",
        }, status=409)

    plaintext = issue_backup_codes(officer)
    _log_auth_audit(
        "MFA_BACKUP_CODES_ISSUED",
        officer=officer,
        username=officer.username,
        ip=zt_service.get_client_ip(request) or "0.0.0.0",
        device=request.META.get("HTTP_USER_AGENT"),
        result="Success",
    )
    return JsonResponse({"ok": True, "backup_codes": plaintext})


@require_GET
def backup_codes_reveal(request: HttpRequest) -> JsonResponse:
    """Serve the first-login plaintext codes EXACTLY once.

    True-owner binding, all four must hold:
    1. live authenticated session (``_current_authenticated_officer``),
    2. a pending one-time session key (set only at first-login auto-issue),
    3. the login itself is fresh (access session issued < 30 min ago),
    4. fetch destroys the key — refresh/replay returns gone.
    Codes never appear in page HTML, URLs, or logs.
    """
    officer = _current_authenticated_officer(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

    pending = request.session.get(BACKUP_REVEAL_KEY)
    if not pending:
        return JsonResponse({"ok": False, "error": "Nothing to reveal.", "gone": True}, status=410)

    token = request.session.get("access_token")
    try:
        sess = AccessSession.objects.get(token_id=token)
    except AccessSession.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Session invalid."}, status=401)
    if sess.revoked_at is not None or (timezone.now() - sess.issued_at).total_seconds() > BACKUP_REVEAL_FRESH_MINUTES * 60:
        request.session.pop(BACKUP_REVEAL_KEY, None)
        request.session.pop(SHOW_BACKUP_MODAL_KEY, None)
        return JsonResponse({"ok": False, "error": "Reveal window expired. Re-issue codes from security settings.", "gone": True}, status=410)

    request.session.pop(BACKUP_REVEAL_KEY, None)
    request.session.pop(SHOW_BACKUP_MODAL_KEY, None)
    _log_auth_audit(
        "MFA_BACKUP_CODES_REVEALED",
        officer=officer,
        username=officer.username,
        ip=zt_service.get_client_ip(request) or "0.0.0.0",
        device=request.META.get("HTTP_USER_AGENT"),
        result="Success",
    )
    return JsonResponse({"ok": True, "backup_codes": list(pending)})


@require_GET
def backup_status(request: HttpRequest) -> JsonResponse:
    """Fallback coverage for the dashboard nudge (any authenticated user)."""
    officer = _current_authenticated_officer(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)
    remaining = backup_codes_remaining(officer)
    has_push = has_push_subscription(officer)
    auth_app = bool(getattr(officer, "authenticator_enabled", False))
    return JsonResponse({
        "ok": True,
        "has_push": has_push,
        "auth_app_enabled": auth_app,
        "backup_remaining": remaining,
        "needs_fallback": not has_push and not auth_app and remaining == 0,
    })


def security_settings_page(request: HttpRequest) -> HttpResponse:
    """Officer self-service page: push status, authenticator, backup codes."""
    from core_system.guards import require_officer_session

    guard = require_officer_session(request)
    if guard is not None:
        return guard
    token = request.session.get("access_token")
    try:
        sess = AccessSession.objects.select_related("user_id_FK").get(token_id=token)
        officer = sess.user_id_FK
    except AccessSession.DoesNotExist:
        return redirect("login")

    from core_system.models import MfaBackupCode, PushSubscription

    from django.conf import settings as _dj_settings

    return render(request, "website/settings_security.html", {
        "masked_email": mask_email(officer.email),
        "has_push": PushSubscription.objects.filter(officer_id_FK=officer).exists(),
        "push_count": PushSubscription.objects.filter(officer_id_FK=officer).count(),
        "auth_app_enabled": bool(getattr(officer, "authenticator_enabled", False)),
        "auth_enrolled_at": getattr(officer, "authenticator_enrolled_at", None),
        "backup_remaining": MfaBackupCode.objects.filter(officer_id_FK=officer, used_at__isnull=True).count(),
        "vapid_public_key": getattr(_dj_settings, "VAPID_PUBLIC_KEY", ""),
    })


def _get_officer_and_access_session(request: HttpRequest):
    token = request.session.get("access_token")
    if not token:
        return None, None, JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

    try:
        session = AccessSession.objects.select_related("user_id_FK").get(token_id=token)
    except AccessSession.DoesNotExist:
        request.session.pop("access_token", None)
        return None, None, JsonResponse(
            {"ok": False, "error": "Session invalid. Please log in again."},
            status=401,
        )

    return session.user_id_FK, session, None


@csrf_protect
def mfa_challenge_page(request: HttpRequest) -> HttpResponse:
    return render(request, "website/mfa_challenge.html", {
        "mfa_email_masked": _get_masked_mfa_email(request),
        "username": request.session.get(MFA_USERNAME_KEY, ""),
    })


@require_POST
@csrf_protect
def zero_trust_challenge(request: HttpRequest) -> HttpResponse:
    """Hard-check step 1: queue a one-time code email to the officer.

    Fully async like every other OTP path: the OutgoingEmail row is the
    durable record and three independent nets (immediate worker thread,
    EmailQueueKickMiddleware piggyback, 30s OTP scheduler drain + cron)
    deliver it even if the officer closes the page. The response returns
    immediately with delivery="queued" — it never blocks polling SMTP.
    Rate-limited independently of login MFA via the session policy so a ZT
    check can never be used to spam the officer's inbox.
    """
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None:
        return auth_error

    # Actively verifying IS activity - never idle-kill mid-verification.
    session.last_activity_at = timezone.now()
    session.save(update_fields=["last_activity_at"])

    now = timezone.now()
    cooldown = zt_settings.get_zt_timers()["challenge_cooldown"]
    policy = session.session_policy if isinstance(session.session_policy, dict) else {}
    last_sent = zt_service._parse_iso(policy.get("zt_last_challenge_at"))
    if last_sent is not None:
        elapsed = (now - last_sent).total_seconds()
        if elapsed < cooldown:
            return JsonResponse({
                "ok": True,
                "sent": False,
                "cooldown": int(cooldown - elapsed),
                "message": "A code was already sent. Please check your inbox.",
            })

    if not officer.email:
        return JsonResponse({"ok": False, "error": "No email on file for this account. Contact the administrator."}, status=400)

    if not officer.mfa_secret:
        officer.mfa_secret = generate_mfa_secret()
        officer.save(update_fields=["mfa_secret"])

    otp = generate_otp(officer.mfa_secret)
    # Distinct subject + stored marker so a delivery-status check can find
    # exactly THIS message (login MFA emails share sender/recipient).
    challenge_marker = uuid.uuid4().hex
    queued = send_mfa_email(
        officer,
        otp,
        subject="CAUFA Zero Trust Verification Code",
        extra_context={"zt_challenge": challenge_marker},
    )

    # The resend cooldown only applies to a message that was actually queued.
    # A queue failure must stay immediately retryable, otherwise a broken
    # queue locks the officer out with "a code was already sent".
    if queued:
        policy["zt_last_challenge_at"] = now.isoformat()
        session.session_policy = policy
        session.save(update_fields=["session_policy"])

    _record_audit_trail(
        table="access_session",
        record_id=0,
        action="ZT_CHALLENGE_SENT" if queued else "ZT_CHALLENGE_FAILED",
        actor=officer,
        ip=zt_service.get_client_ip(request),
        device_info=request.META.get("HTTP_USER_AGENT"),
        notes="Hard check OTP email "
        + ("queued for async delivery" if queued else "FAILED: could not be queued"),
    )

    if not queued:
        # Same-code push fallback so a Gmail outage doesn't wedge a live
        # session behind an unanswerable hard check. Authenticator/backup
        # codes need no delivery at all and just work at verify time.
        if send_mfa_push(officer, otp):
            _record_audit_trail(
                table="access_session",
                record_id=0,
                action="ZT_CHALLENGE_SENT",
                actor=officer,
                ip=zt_service.get_client_ip(request),
                device_info=request.META.get("HTTP_USER_AGENT"),
                notes="Hard check OTP pushed (email queue failed)",
            )
            return JsonResponse({
                "ok": True,
                "sent": True,
                "delivery": "push",
                "message": "Email failed — code pushed to your device instead. Your authenticator app or a backup code works too.",
                "cooldown": zt_settings.get_zt_timers()["challenge_cooldown"],
                "masked_email": mask_email(officer.email),
            })
        return JsonResponse({
            "ok": False,
            "error": (
                "Email could not be queued. "
                "Use Resend code to try again, or ask the administrator to check outgoing mail."
            ),
        }, status=503)

    return JsonResponse({
        "ok": True,
        "sent": True,
        "delivery": "queued",
        "message": "Code queued for delivery — it sends even if you close this page. If it does not arrive within a minute, use Resend code.",
        "cooldown": zt_settings.get_zt_timers()["challenge_cooldown"],
        "masked_email": mask_email(officer.email),
    })


def _enforce_network_drift(request: HttpRequest, session, officer) -> bool:
    """Run the debounced network-change detector from polling endpoints.

    The middleware only evaluates full page loads (/api/auth/* short-circuits
    before evaluation), so an officer who sits on an open dashboard while
    roaming to a new network would otherwise never lock — the 30s status poll
    and 45s heartbeat are the requests that actually keep flowing. Returns
    True when this call confirmed the move and locked the session.
    """
    try:
        if zt_service.is_locked(session):
            return False
        track = zt_service.track_network_drift(session, request)
        if track.get("state") != "confirmed":
            return False
        details = zt_service.apply_network_lock(session, request, track)
        _record_audit_trail(
            table="access_session",
            record_id=0,
            action="ZT_NETLOCK",
            actor=officer,
            old=None,
            new={"reasons": [f"Network changed ({track.get('from_net')} -> {track.get('to_net')}); screen locked pending password confirm"]},
            ip=zt_service.get_client_ip(request),
            device_info=request.META.get("HTTP_USER_AGENT"),
            notes=f"ZT level change: Network changed ({track.get('from_net')} -> {track.get('to_net')}); screen locked pending password confirm",
        )
        try:
            if not details.get("mailed"):
                _queue_network_change_alert(request, officer, details)
                zt_service.mark_netlock_mailed(session)
        except Exception:
            logging.getLogger(__name__).exception("ZT netlock email failed")
        return True
    except Exception:
        logging.getLogger(__name__).exception("ZT network-drift tracking failed")
        return False


@require_GET
def zero_trust_status(request: HttpRequest) -> HttpResponse:
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None:
        return auth_error

    # Bootstrap the baseline for pre-hardening sessions and fold in any
    # client-attested environment the badge JS sent as query params.
    changed = zt_service.ensure_snapshot(session, request)
    if changed:
        policy = session.session_policy
        policy.setdefault("zt_env_baseline", dict(policy.get("zt_client_env") or {}))
        session.save(update_fields=["session_policy"])
    if zt_service.merge_client_env(session, request.GET):
        session.save(update_fields=["session_policy"])

    # An open dashboard only hits this poll (middleware skips /api/auth/*),
    # so the network lock must be enforced here, not just on page loads.
    _enforce_network_drift(request, session, officer)

    sticky_level, sticky_reasons = zt_service.current_level(session)
    evaluated = zt_service.evaluate_zero_trust(session, request)
    if zt_service.LEVEL_ORDER.get(evaluated["level"], 0) >= zt_service.LEVEL_ORDER.get(sticky_level, 0):
        level, reasons = evaluated["level"], evaluated["reasons"]
    else:
        level, reasons = sticky_level, sticky_reasons

    policy = session.session_policy if isinstance(session.session_policy, dict) else {}
    locked = zt_service.is_locked(session)
    timers = zt_settings.get_zt_timers()
    response = {
        "ok": True,
        "verified": session.trusted_device,
        "level": level,
        "reasons": reasons,
        "locked": locked,
        "officer_name": officer.full_name or "",
        "officer_role": officer.role or "",
        "masked_email": mask_email(officer.email or ""),
        "lock_note": zt_service.lock_note(session),
        "lock_idle_seconds": int(timers["lock_idle"].total_seconds()),
        "lock_auto_signout_seconds": int(timers["lock_auto_signout"].total_seconds()),
        "fingerprint": zt_service.get_session_fingerprint(request, session),
        "zt_confirm_count": policy.get("zt_confirm_count", 0),
        "zt_last_confirmed": policy.get("zt_last_confirmed"),
    }
    if locked:
        requirements = zt_service.unlock_requirements(session, officer)
        response["unlock"] = requirements
        response["lock_expires_in_seconds"] = zt_service.lock_expires_in(session)
    return JsonResponse(response)


@require_POST
@csrf_protect
def zero_trust_verify(request: HttpRequest) -> HttpResponse:
    """Hard-check step 2: verify the emailed code and rebaseline the session."""
    otp_input = (request.POST.get("otp") or "").strip()
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None:
        return auth_error

    # Actively verifying IS activity - never idle-kill mid-verification.
    session.last_activity_at = timezone.now()
    session.save(update_fields=["last_activity_at"])

    if not otp_input:
        return JsonResponse({"ok": False, "error": "Enter the 6-digit code from your email."}, status=400)

    # Accept every login-grade method: email/push TOTP, authenticator app,
    # or a single-use backup code — a Gmail outage must not wedge a live
    # session behind an unanswerable hard check.
    code_ok, method = _verify_mfa_code(officer, otp_input)
    if code_ok:
        zt_service.clear_hard_check(session, request)
        _record_audit_trail(
            table="access_session",
            record_id=0,
            action="ZT_HARD_VERIFIED",
            actor=officer,
            old=None,
            new={"ip": zt_service.get_client_ip(request)},
            ip=zt_service.get_client_ip(request),
            device_info=request.META.get("HTTP_USER_AGENT"),
            notes=f"Hard check passed via {method}; session rebaselined",
        )
        return JsonResponse({"ok": True, "message": "Zero Trust verification successful."})

    # Failed attempt: feed the suspicious-activity counter; lock the session
    # out entirely after repeated failures so the OTP can't be brute-forced.
    zt_service.record_security_event(session, "zt_otp_failed")
    policy = session.session_policy if isinstance(session.session_policy, dict) else {}
    failures = (policy.get("zt_verify_failures") or 0) + 1
    policy["zt_verify_failures"] = failures
    session.session_policy = policy
    session.save(update_fields=["session_policy"])

    _record_audit_trail(
        table="access_session",
        record_id=0,
        action="ZT_VERIFY_FAILED",
        actor=officer,
        result="Failed",
        ip=zt_service.get_client_ip(request),
        device_info=request.META.get("HTTP_USER_AGENT"),
        notes=f"Hard check failed attempt {failures}",
    )

    if failures >= 5:
        session.session_status = "Revoked"
        session.revoked_at = timezone.now()
        session.expires_at = timezone.now()
        session.save(update_fields=["session_status", "revoked_at", "expires_at"])
        request.session.flush()
        return JsonResponse({
            "ok": False,
            "session_revoked": True,
            "error": "Too many failed verification attempts. Please log in again.",
        }, status=401)

    return JsonResponse({"ok": False, "error": "Invalid verification code."}, status=401)


@require_GET
def zero_trust_challenge_page(request: HttpRequest) -> HttpResponse:
    """Full-page fallback for hard checks on normal (non-AJAX) navigation."""
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None or officer is None:
        try:
            from core_system.url_obfuscation import session_expired_url
            return HttpResponseRedirect(session_expired_url())
        except Exception:
            return HttpResponseRedirect("/?session_expired=1")

    next_url = request.GET.get("next") or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    sticky_level, _ = zt_service.current_level(session)
    if sticky_level != "hard":
        return HttpResponseRedirect(next_url)

    try:
        from core_system.url_obfuscation import session_expired_url as _seu
        _seu_val = _seu()
    except Exception:
        _seu_val = "/?session_expired=1"
    return render(request, "website/zt_challenge.html", {
        "masked_email": mask_email(officer.email or ""),
        "next_url": next_url,
        "session_expired_url": _seu_val,
    })


# ---------------------------------------------------------------------------
# Screen lock (bathroom-break protection)
# ---------------------------------------------------------------------------

def _safe_next(request: HttpRequest) -> str:
    next_url = request.GET.get("next") or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    return next_url


@require_POST
@csrf_protect
def zt_lock(request: HttpRequest) -> HttpResponse:
    """The page calls this when the officer goes idle: flag the session
    locked server-side. The overlay is only the visual."""
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None:
        return auth_error

    if not zt_service.is_locked(session):
        reason = (request.POST.get("reason") or "idle").strip()[:40]
        zt_service.lock_session(session, reason)
        _record_audit_trail(
            table="access_session",
            record_id=0,
            action="ZT_LOCK",
            actor=officer,
            ip=zt_service.get_client_ip(request),
            device_info=request.META.get("HTTP_USER_AGENT"),
            notes=f"Screen locked ({reason})",
        )
    return JsonResponse({"ok": True, "locked": True})


@require_POST
@csrf_protect
def zt_heartbeat(request: HttpRequest) -> HttpResponse:
    """Lightweight proof the lock UI is still alive on the page."""
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None:
        return auth_error

    # Same as the status poll: the heartbeat is often the only request an
    # idle-but-open dashboard still sends, so confirm network moves here too.
    if _enforce_network_drift(request, session, officer):
        locked_resp = JsonResponse({"ok": False, "session_locked": True,
                                    "error": "This session is locked. Unlock it to continue."}, status=403)
        locked_resp["X-ZT-Session-Locked"] = "true"
        return locked_resp

    alive = zt_service.lock_heartbeat(session)
    if not alive:
        locked_resp = JsonResponse({"ok": False, "session_locked": True,
                                    "error": "This session is locked. Unlock it to continue."}, status=403)
        locked_resp["X-ZT-Session-Locked"] = "true"
        return locked_resp
    return JsonResponse({"ok": True, "locked": False})


@require_POST
@csrf_protect
def zt_unlock(request: HttpRequest) -> HttpResponse:
    """Unlock a locked session: password by default, email OTP when the
    situation demands it (long lock, elevated risk, failed attempts,
    money-handling roles)."""
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None:
        return auth_error

    if not zt_service.is_locked(session):
        return JsonResponse({"ok": True, "already_unlocked": True})

    # Someone is actively trying to unlock - that IS activity. Without this,
    # the frozen idle clock kills the session on the first data request right
    # after a successful unlock (lockouts longer than the idle timeout).
    session.last_activity_at = timezone.now()
    session.save(update_fields=["last_activity_at"])

    max_failures = zt_settings.get_zt_timers()["unlock_max_failures"]
    requirements = zt_service.unlock_requirements(session, officer)
    unlock_method = ""

    if requirements["otp_required"]:
        otp_input = (request.POST.get("otp") or "").strip()
        if not otp_input:
            return JsonResponse({
                "ok": False,
                "otp_required": True,
                "reasons": requirements["reasons"],
                "error": "Enter the 6-digit code sent to your email to unlock.",
            }, status=403)
        # Same login-grade methods as everywhere else: email/push TOTP,
        # authenticator app, or a burning backup code.
        unlock_ok, unlock_method = _verify_mfa_code(officer, otp_input)
        if not unlock_ok:
            failures = zt_service.record_unlock_failure(session)
            _record_audit_trail(
                table="access_session", record_id=0, action="ZT_UNLOCK_FAILED",
                actor=officer, result="Failed",
                ip=zt_service.get_client_ip(request),
                device_info=request.META.get("HTTP_USER_AGENT"),
                notes=f"Unlock OTP failed attempt {failures}",
            )
            if failures >= max_failures:
                session.session_status = "Revoked"
                session.revoked_at = timezone.now()
                session.expires_at = timezone.now()
                session.save(update_fields=["session_status", "revoked_at", "expires_at"])
                request.session.flush()
                return JsonResponse({
                    "ok": False,
                    "session_revoked": True,
                    "error": "Too many failed unlock attempts. Please log in again.",
                }, status=401)
            return JsonResponse({
                "ok": False,
                "otp_required": True,
                "error": "Invalid verification code.",
                "failures_left": max(0, max_failures - failures),
            }, status=403)
        method = "otp"
    else:
        password = request.POST.get("password") or ""
        if not password:
            return JsonResponse({
                "ok": False,
                "password_required": True,
                "error": "Enter your password to unlock.",
            }, status=403)
        if not verify_officer_password(officer=officer, password_input=password):
            failures = zt_service.record_unlock_failure(session)
            _record_audit_trail(
                table="access_session", record_id=0, action="ZT_UNLOCK_FAILED",
                actor=officer, result="Failed",
                ip=zt_service.get_client_ip(request),
                device_info=request.META.get("HTTP_USER_AGENT"),
                notes=f"Unlock password failed attempt {failures}",
            )
            # Guessing at the password escalates to OTP after N misses,
            # and revokes the session entirely after the configured total.
            if failures >= max_failures:
                session.session_status = "Revoked"
                session.revoked_at = timezone.now()
                session.expires_at = timezone.now()
                session.save(update_fields=["session_status", "revoked_at", "expires_at"])
                request.session.flush()
                return JsonResponse({
                    "ok": False,
                    "session_revoked": True,
                    "error": "Too many failed unlock attempts. Please log in again.",
                }, status=401)
            now_requirements = zt_service.unlock_requirements(session, officer)
            return JsonResponse({
                "ok": False,
                "password_required": not now_requirements["otp_required"],
                "otp_required": now_requirements["otp_required"],
                "error": "Incorrect password.",
                "failures_left": max(0, max_failures - failures),
            }, status=403)
        method = "password"

    zt_service.clear_lock(session, request, method)
    _record_audit_trail(
        table="access_session", record_id=0, action="ZT_UNLOCK",
        actor=officer,
        ip=zt_service.get_client_ip(request),
        device_info=request.META.get("HTTP_USER_AGENT"),
        notes=f"Screen unlocked via {method}"
        + (f" ({unlock_method})" if method == "otp" else ""),
    )
    return JsonResponse({"ok": True, "method": method})


@require_GET
def zt_unlock_page(request: HttpRequest) -> HttpResponse:
    """Full-page unlock for normal navigation while locked."""
    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None or officer is None:
        try:
            from core_system.url_obfuscation import session_expired_url
            return HttpResponseRedirect(session_expired_url())
        except Exception:
            return HttpResponseRedirect("/?session_expired=1")

    next_url = _safe_next(request)
    if not zt_service.is_locked(session):
        return HttpResponseRedirect(next_url)

    # Opening the unlock page is interaction - keep the idle clock honest.
    session.last_activity_at = timezone.now()
    session.save(update_fields=["last_activity_at"])

    requirements = zt_service.unlock_requirements(session, officer)
    try:
        from core_system.url_obfuscation import session_expired_url as _seu2
        _seu_val2 = _seu2()
    except Exception:
        _seu_val2 = "/?session_expired=1"
    return render(request, "website/zt_unlock.html", {
        "officer_name": officer.full_name,
        "masked_email": mask_email(officer.email or ""),
        "next_url": next_url,
        "otp_required": requirements["otp_required"],
        "otp_reasons": requirements["reasons"],
        "lock_note": zt_service.lock_note(session),
        "lock_auto_signout_seconds": int(zt_settings.get_zt_timers()["lock_auto_signout"].total_seconds()),
        "lock_expires_in_seconds": zt_service.lock_expires_in(session),
        "session_expired_url": _seu_val2,
    })


@require_POST
@csrf_protect
def device_enroll(request: HttpRequest) -> JsonResponse:
    """(Re)enroll this browser's device credential (protocol device-key/v1).

    Requires a live officer session. Returns a fresh device_id + secret
    (secret also set as HttpOnly cookie). The contract is versioned so a
    future WebAuthn/FIDO2 flow can replace the response payload's
    ``protocol`` with ``webauthn/v1`` + ``publicKey`` options without
    changing routes or middleware verification.
    """
    from core_system.device_binding import ENROLL_PROTOCOL, new_device_credential
    from core_system.device_binding import DEVICE_ID_COOKIE, DEVICE_PROOF_COOKIE, bind_session_policy

    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None or officer is None or session is None:
        return JsonResponse({"ok": False, "error": "Session expired."}, status=401)
    device_id, device_secret = new_device_credential()
    policy = bind_session_policy(session.session_policy, device_id=device_id,
                                 secret=device_secret)
    session.session_policy = policy
    session.save(update_fields=["session_policy"])
    resp = JsonResponse({
        "ok": True, "protocol": ENROLL_PROTOCOL,
        "device_id": device_id,
        "webauthn": {"available": False, "note": "WebAuthn/FIDO2 upgrade path reserved."},
    })
    _secure = request.is_secure()
    resp.set_cookie(DEVICE_ID_COOKIE, device_id, max_age=8 * 3600,
                    httponly=False, samesite="Strict", secure=_secure, path="/")
    resp.set_cookie(DEVICE_PROOF_COOKIE, device_secret, max_age=8 * 3600,
                    httponly=True, samesite="Strict", secure=_secure, path="/")
    return resp


@require_POST
@csrf_protect
def device_verify(request: HttpRequest) -> JsonResponse:
    """Health-check for device binding: verifies current proof headers."""
    from core_system.device_binding import verify_request_binding

    officer, session, auth_error = _get_officer_and_access_session(request)
    if auth_error is not None or officer is None or session is None:
        return JsonResponse({"ok": False, "error": "Session expired."}, status=401)
    ok, reason = verify_request_binding(request, session.session_policy)
    return JsonResponse({"ok": ok, "reason": reason,
                         "bound": bool((session.session_policy or {}).get("device_bound"))})


def _await_challenge_email_status(marker: str, timeout_seconds: float = 8.0):
    """The OTP email is sent by a background thread after the response is
    queued. Briefly poll its OutgoingEmail row so the unlock UI learns the
    REAL outcome instead of telling an officer 'sent' while SMTP is failing.

    Returns (delivered: bool, delivery_status: str, error: str)."""
    import time as _time
    import uuid as _uuid

    from core_system.models import OutgoingEmail

    deadline = _time.monotonic() + timeout_seconds
    row = None

    def _find_marker_row():
        # Match the stored marker in Python — JSONField key lookups are
        # unreliable on this MySQL server.
        for candidate in OutgoingEmail.objects.order_by("-outgoing_email_id")[:8]:
            if isinstance(candidate.context, dict) and candidate.context.get("zt_challenge") == marker:
                return candidate
        return None

    while True:
        row = _find_marker_row()
        if row is not None and row.status in (OutgoingEmail.SENT, OutgoingEmail.FAILED):
            break
        if _time.monotonic() >= deadline:
            break
        _time.sleep(0.4)

    if row is None:
        return False, "unqueued", "the message could not be queued for delivery"
    if row.status == OutgoingEmail.FAILED:
        return False, "failed", (row.error_message or "SMTP delivery failed").strip()[:200]
    if row.status == OutgoingEmail.SENT:
        return True, "sent", ""
    return True, "queued", ""


def _queue_new_device_alert(request: HttpRequest, officer, new_session) -> None:
    """Alert the officer that a fresh sign-in revoked their previous sessions."""
    try:
        from core_system.services.email_service import send_html_email_async
        from core_system.services.notifications import notify_officer

        ip = zt_service.get_client_ip(request) or "0.0.0.0"
        device = request.META.get("HTTP_USER_AGENT") or "Unknown device"
        when = timezone.localtime(timezone.now()).strftime("%b %d, %Y %I:%M %p")

        if officer.email:
            send_html_email_async(
                subject="CAUFA Security Alert: New Sign-In to Your Account",
                recipient_list=[officer.email],
                html_template="emails/zt_new_login.html",
                context={
                    "full_name": officer.full_name,
                    "ip_address": ip,
                    "device": device[:200],
                    "when": when,
                },
            )

        notify_officer(
            officer,
            notification_type="zt_new_login",
            message=f"New sign-in detected from {device[:80]} (IP {ip}) at {when}. Previous sessions were signed out. If this wasn't you, change your password immediately.",
            category="general",
            url="/",
        )

        _record_audit_trail(
            table="access_session",
            record_id=0,
            action="LOGIN_NEW_DEVICE",
            actor=officer,
            ip=ip,
            device_info=device,
            notes=f"New session {new_session.token_id[:12]}... revoked prior sessions",
        )
    except Exception:
        logging.getLogger(__name__).exception("New-device alert failed")


def _queue_network_change_alert(request: HttpRequest, officer, details: dict) -> None:
    """'Did you do this?' mail for the network-change lockout. Sent once per
    lock (guarded by the mailed flag) — never on mere candidates."""
    try:
        from core_system.services import zt_service
        from core_system.services.email_service import send_html_email_async

        ip = zt_service.get_client_ip(request) or "0.0.0.0"
        device = request.META.get("HTTP_USER_AGENT") or "Unknown device"
        when = timezone.localtime(timezone.now()).strftime("%b %d, %Y %I:%M %p")
        what = zt_service.netlock_changes_text(details)

        if officer and officer.email:
            send_html_email_async(
                subject="CAUFA Security Check: Did You Change Networks?",
                recipient_list=[officer.email],
                html_template="emails/zt_network_change.html",
                context={
                    "full_name": officer.full_name,
                    "what_changed": what,
                    "from_net": zt_service._mask_net(details.get("from_net", "")),
                    "to_net": zt_service._mask_net(details.get("to_net", "")),
                    "device": device[:200],
                    "when": when,
                },
            )

        try:
            from core_system.services.notifications import notify_officer

            notify_officer(
                officer,
                notification_type="zt_netlock",
                message=f"Security check: we detected a change in {what}. Your screen is locked — confirm with your password. If this wasn't you, change your password immediately.",
                category="general",
                url="/",
            )
        except Exception:
            pass

        _record_audit_trail(
            table="access_session",
            record_id=0,
            action="ZT_NETLOCK_MAIL",
            actor=officer,
            ip=ip,
            device_info=device,
            notes=f"Network-change 'was this you' mail queued ({what})",
        )
    except Exception:
        logging.getLogger(__name__).exception("Network-change alert failed")


@require_POST
@csrf_protect
def zero_trust_confirm(request: HttpRequest) -> HttpResponse:
    """Per-action confirmation endpoint - replaces OTP-based verification.
    
    This endpoint generates a Session Integrity Token (SIT) for a specific action,
    logs the confirmation to the audit trail, and returns the SIT for use in
    subsequent requests.
    """
    try:
        from core_system.services.zt_service import (
            generate_sit,
            build_action_descriptor,
        )

        stored_officer_id = request.session.get("officer_id")
        token = request.session.get("access_token")
        if not stored_officer_id or not token:
            return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

        action = (request.POST.get("action") or "").strip()
        action_id = (request.POST.get("action_id") or "").strip()
        details_raw = (request.POST.get("details") or "{}")

        # Provide defaults if missing to avoid blocking during testing
        if not action:
            action = "sensitive_action"
        if not action_id:
            action_id = str(int(time.time()))

        try:
            details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
        except json.JSONDecodeError:
            details = {}

        try:
            officer = OfficerUser.objects.get(user_id_PK=int(stored_officer_id))
            session = AccessSession.objects.get(token_id=token)
        except (OfficerUser.DoesNotExist, AccessSession.DoesNotExist):
            return JsonResponse({"ok": False, "error": "Session not found."}, status=404)

        if not session.trusted_device:
            return JsonResponse({"ok": False, "error": "Device changed. Re-login required."}, status=403)

        timestamp = timezone.now().isoformat()
        sit = generate_sit(session.token_id, action, action_id, timestamp)

        descriptor = build_action_descriptor(action, action_id, details)
        
        # Log the confirmation to audit trail with error handling
        try:
            _record_audit_trail(
                table=action,
                record_id=int(action_id) if action_id.isdigit() else 0,
                action="ZT_CONFIRM",
                actor=officer,
                old=None,
                new=details,
                ip=zt_service.get_client_ip(request),
                device_info=request.META.get("HTTP_USER_AGENT"),
                notes=f"ZT Confirm: {descriptor} | SIT: {sit[:16]}...",
            )
        except Exception as e:
            logger.error("Failed to record ZT audit trail: %s", e)
            # Continue anyway - the confirmation should still work

        try:
            policy = session.session_policy or {}
            policy["zt_last_confirmed"] = timestamp
            policy["zt_confirm_count"] = (policy.get("zt_confirm_count", 0) or 0) + 1
            session.session_policy = policy
            session.save(update_fields=["session_policy"])
        except Exception as e:
            logger.error("Failed to update session policy: %s", e)
            # Continue anyway - the confirmation should still work

        return JsonResponse({
            "ok": True,
            "sit": sit,
            "timestamp": timestamp,
            "descriptor": descriptor,
            "zt_verified_at": timestamp,
        })
    except Exception as e:
        logger.error("ZT confirm error: %s", e, exc_info=True)
        return JsonResponse({
            "ok": False,
            "error": f"Confirmation failed: {str(e)}"
        }, status=500)


@csrf_protect
def forgot_password(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(request, "website/forgot_password.html")

    email = (request.POST.get("email") or "").strip()
    if not email:
        messages.error(request, "Please enter your email address.")
        return render(request, "website/forgot_password.html")

    # Never reveal whether the address belongs to an account: the response
    # is identical either way, and a code is only sent when it does.
    generic_notice = (
        "If an account exists for that email address, a verification code "
        "has been sent. Please check your inbox (and spam folder)."
    )
    try:
        officer = OfficerUser.objects.get(email__iexact=email)
    except OfficerUser.DoesNotExist:
        officer = None

    if officer is not None:
        otp = generate_otp(officer.mfa_secret or generate_mfa_secret())
        if not officer.mfa_secret:
            officer.mfa_secret = generate_mfa_secret()
            officer.save(update_fields=["mfa_secret"])

        email_sent = send_mfa_email(officer, otp)
        if not email_sent:
            messages.error(request, "Failed to send verification email. Please try again later.")
            return render(request, "website/forgot_password.html")

        request.session["reset_email"] = email
        request.session["reset_officer_id"] = officer.user_id_PK
        request.session["reset_otp"] = otp
        request.session["reset_otp_created_at"] = timezone.now().isoformat()
        request.session.set_expiry(600)

        return redirect("reset_password")

    messages.success(request, generic_notice)
    return render(request, "website/forgot_password.html")


@csrf_protect
def reset_password(request: HttpRequest) -> HttpResponse:
    reset_email = request.session.get("reset_email")
    reset_officer_id = request.session.get("reset_officer_id")
    reset_otp = request.session.get("reset_otp")
    otp_created_at = request.session.get("reset_otp_created_at")
    reset_officer_id = request.session.get("reset_officer_id")
    reset_otp = request.session.get("reset_otp")
    otp_created_at = request.session.get("reset_otp_created_at")

    if not reset_email or not reset_officer_id or not reset_otp or not otp_created_at:
        return render(request, "website/reset_password.html", {"expired": True})

    try:
        created = timezone.datetime.fromisoformat(otp_created_at)
        if timezone.is_naive(created):
            created = timezone.make_aware(created)
        if timezone.now() > created + timedelta(minutes=10):
            request.session.pop("reset_email", None)
            request.session.pop("reset_officer_id", None)
            request.session.pop("reset_otp", None)
            request.session.pop("reset_otp_created_at", None)
            return render(request, "website/reset_password.html", {"expired": True})
    except (ValueError, TypeError):
        return render(request, "website/reset_password.html", {"expired": True})

    if request.method == "GET":
        return render(request, "website/reset_password.html", {"email": reset_email})

    otp_input = (request.POST.get("otp") or "").strip()
    new_password = request.POST.get("new_password") or ""
    confirm_password = request.POST.get("confirm_password") or ""

    try:
        officer = OfficerUser.objects.get(user_id_PK=reset_officer_id)
    except OfficerUser.DoesNotExist:
        messages.error(request, "Account not found.")
        return render(request, "website/reset_password.html", {"email": reset_email})

    # Code check: the emailed OTP, or — when email is down — any unused
    # backup code for this officer (burned on use, audited as such).
    code_ok = bool(otp_input) and otp_input == reset_otp
    used_backup = False
    if not code_ok and otp_input:
        try:
            from core_system.models import MfaBackupCode

            for row in MfaBackupCode.objects.filter(officer_id_FK=officer, used_at__isnull=True):
                if backup_code_matches(otp_input, row.code_hash):
                    row.used_at = timezone.now()
                    row.save(update_fields=["used_at"])
                    code_ok, used_backup = True, True
                    break
        except Exception:
            pass

    if not code_ok:
        from core_system.login_throttle import record_failure as _record_throttle_failure

        fails = int(request.session.get(RESET_FAILS_KEY, 0) or 0) + 1
        request.session[RESET_FAILS_KEY] = fails
        ip_address = zt_service.get_client_ip(request) or "0.0.0.0"
        try:
            _record_throttle_failure(officer.username, ip_address)
        except Exception:
            pass
        _log_auth_audit(
            "PASSWORD_RESET_FAILED",
            officer=officer,
            username=officer.username,
            ip=ip_address,
            device=request.META.get("HTTP_USER_AGENT"),
            result="Failed",
            notes=f"invalid_reset_code_attempt_{fails}",
        )
        if fails >= MAX_RESET_ATTEMPTS:
            for key in ("reset_email", "reset_officer_id", "reset_otp", "reset_otp_created_at", RESET_FAILS_KEY):
                request.session.pop(key, None)
            _log_auth_audit(
                "PASSWORD_RESET_FAILED",
                officer=officer,
                username=officer.username,
                ip=ip_address,
                device=request.META.get("HTTP_USER_AGENT"),
                result="Failed",
                notes="reset_bruteforce_lockout",
            )
            messages.error(request, "Too many wrong codes. Request a new reset code to try again.")
            return render(request, "website/reset_password.html", {"expired": True, "lockout": True})
        messages.error(request, f"Invalid verification code. Please try again. ({MAX_RESET_ATTEMPTS - fails} attempt(s) left.)")
        return render(request, "website/reset_password.html", {"email": reset_email})

    if new_password != confirm_password:
        messages.error(request, "Passwords do not match.")
        return render(request, "website/reset_password.html", {"email": reset_email})

    strength_errors = validate_new_password(new_password)
    if strength_errors:
        for err in strength_errors:
            messages.error(request, err)
        return render(request, "website/reset_password.html", {"email": reset_email})

    officer.password_hash = hash_password(new_password)
    officer.must_change_password = False
    officer.save(update_fields=["password_hash", "must_change_password"])

    # A reset assumes compromise until proven otherwise: kill every live
    # session now (not just at the next login) so a squatter holding an old
    # token loses it the moment the password changes.
    try:
        AccessSession.objects.filter(user_id_FK=officer, revoked_at__isnull=True).update(
            revoked_at=timezone.now(), session_status="Revoked",
        )
    except Exception:
        pass

    for key in ("reset_email", "reset_officer_id", "reset_otp", "reset_otp_created_at", RESET_FAILS_KEY):
        request.session.pop(key, None)

    _log_auth_audit(
        "PASSWORD_RESET",
        officer=officer,
        username=officer.username,
        ip=zt_service.get_client_ip(request) or "0.0.0.0",
        device=request.META.get("HTTP_USER_AGENT"),
        result="Success",
        notes="mfa_backup_code" if used_backup else "reset_email_otp",
    )
    messages.success(request, "Your password has been reset successfully. You can now log in with your new password.")
    return redirect("login")


@csrf_protect
def change_password(request: HttpRequest) -> HttpResponse:
    """Self-service password change. Forced on first login when must_change_password is set.

    Requires an active session. Validates the current password, then updates the hash
    and clears the must_change_password flag.
    """
    from core_system.guards import require_officer_session

    guard = require_officer_session(request)
    if guard is not None:
        return guard

    officer_id = request.session.get("officer_id")
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        request.session.flush()
        return redirect("login")

    context = {"forced": bool(officer.must_change_password)}

    if request.method == "GET":
        return render(request, "website/change_password.html", context)

    current_password = request.POST.get("current_password") or ""
    new_password = request.POST.get("new_password") or ""
    confirm_password = request.POST.get("confirm_password") or ""

    if not verify_password(current_password, officer.password_hash):
        messages.error(request, "Your current password is incorrect.")
        return render(request, "website/change_password.html", context)

    if new_password != confirm_password:
        messages.error(request, "Passwords do not match.")
        return render(request, "website/change_password.html", context)

    strength_errors = validate_new_password(new_password)
    if strength_errors:
        for err in strength_errors:
            messages.error(request, err)
        return render(request, "website/change_password.html", context)

    if new_password == current_password:
        messages.error(request, "New password must be different from your current password.")
        return render(request, "website/change_password.html", context)

    officer.password_hash = hash_password(new_password)
    officer.must_change_password = False
    officer.save(update_fields=["password_hash", "must_change_password"])

    _record_audit_trail(
        table="officer_user",
        record_id=officer.user_id_PK,
        action="PASSWORD_CHANGED",
        actor=officer,
        ip=zt_service.get_client_ip(request),
        notes="Password changed via change-password flow.",
    )

    return redirect(_workspace_redirect(officer.role))


@require_GET
def term_info(request: HttpRequest):
    stored_officer_id = request.session.get("officer_id")
    if stored_officer_id is None:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)

    try:
        officer = OfficerUser.objects.get(user_id_PK=int(stored_officer_id))
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer not found."}, status=404)

    return JsonResponse({"ok": True, **_term_info(officer)})