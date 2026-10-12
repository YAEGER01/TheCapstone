"""Self-service endpoints for the offline personal action-PIN.

All roles (president / treasurer / auditor / others) use the same endpoints:

  GET  /api/officer/pin/status/  -> {has_pin, locked, retry_after_seconds, set_at}
  POST /api/officer/pin/setup/   -> {pin, password}            (first time)
  POST /api/officer/pin/change/  -> {current_pin, new_pin, password}
  POST /api/officer/pin/verify/  -> {pin}                       (explicit check)
  POST /api/officer/pin/reset/   -> {new_pin} + step-1 grant    (forgot-PIN step 2)
  POST /api/officer/pin/reset/code/   -> {}                     (forgot-PIN step 1a: email code)
  POST /api/officer/pin/reset/verify/ -> {code}                 (forgot-PIN step 1b: email/auth/backup)

Setup/change/reset never return the PIN or its hash. Verification is fully
offline (salted PBKDF2 via auth_utils) — no email or OTP involved.
"""

from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core_system import officer_pin as pin_service
from core_system.guards import require_officer_session


def _parse_json(request: HttpRequest) -> dict:
    try:
        if request.body:
            body = json.loads(request.body.decode("utf-8") or "{}")
            return body if isinstance(body, dict) else {}
    except Exception:
        pass
    return {}


def _merge(request: HttpRequest) -> dict:
    data = _parse_json(request)
    for k, v in request.POST.items():
        data.setdefault(k, v)
    return data


@require_GET
def officer_pin_status(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer = pin_service.get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)
    locked, retry_after = pin_service.is_action_pin_locked(officer)
    return JsonResponse({
        "ok": True,
        "has_pin": pin_service.has_action_pin(officer),
        "locked": locked,
        "retry_after_seconds": retry_after,
        "lock_minutes_next": int(getattr(officer, "action_pin_lock_minutes", 1) or 1),
        "fails_in_cycle": int(getattr(officer, "action_pin_fail_count", 0) or 0) % pin_service.ACTION_PIN_FAILS_PER_LOCK,
        "set_at": officer.action_pin_set_at.isoformat() if getattr(officer, "action_pin_set_at", None) else None,
        "pin_length": pin_service.ACTION_PIN_LENGTH,
    })


@require_POST
def officer_pin_setup(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer = pin_service.get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)
    data = _merge(request)
    pin = str(data.get("pin") or data.get("new_pin") or "").strip()
    confirm = str(data.get("confirm_pin") or data.get("pin_confirm") or "").strip()
    password = str(data.get("password") or "")
    if confirm and pin != confirm:
        return JsonResponse({"ok": False, "error": "PIN and confirmation do not match."}, status=400)
    ok, msg = pin_service.setup_action_pin(officer=officer, pin=pin, password=password, request=request)
    return JsonResponse({"ok": ok, **({"message": msg} if ok else {"error": msg})},
                        status=200 if ok else 400)


@require_POST
def officer_pin_change(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer = pin_service.get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)
    data = _merge(request)
    current_pin = str(data.get("current_pin") or data.get("pin") or "").strip()
    new_pin = str(data.get("new_pin") or "").strip()
    confirm = str(data.get("confirm_pin") or data.get("new_pin_confirm") or "").strip()
    password = str(data.get("password") or "")
    if confirm and new_pin != confirm:
        return JsonResponse({"ok": False, "error": "New PIN and confirmation do not match."}, status=400)
    ok, msg = pin_service.change_action_pin(
        officer=officer, current_pin=current_pin, new_pin=new_pin, password=password, request=request)
    return JsonResponse({"ok": ok, **({"message": msg} if ok else {"error": msg})},
                        status=200 if ok else 400)


@require_POST
def officer_pin_verify(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer = pin_service.get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)
    data = _merge(request)
    pin = pin_service.extract_action_pin(request, data)
    ok, msg, retry = pin_service.verify_action_pin(officer, pin, request=request)
    if ok:
        return JsonResponse({"ok": True, "message": msg})
    status = 423 if retry and "Locked" in msg else (403 if "Incorrect" in msg or "attempt" in msg else 400)
    payload: dict = {"ok": False, "error": msg}
    if retry:
        payload["retry_after_seconds"] = retry
    locked, ra = pin_service.is_action_pin_locked(officer)
    payload["locked"] = locked
    if locked:
        payload["retry_after_seconds"] = ra
    return JsonResponse(payload, status=status)


@require_POST
def officer_pin_reset(request: HttpRequest):
    """Forgot-PIN recovery step 2: set the new PIN.

    Requires the single-use grant from step 1 (verified login code), or —
    only when the officer has no MFA options at all — the login password.
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer = pin_service.get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)
    data = _merge(request)
    new_pin = str(data.get("new_pin") or data.get("pin") or "").strip()
    confirm = str(data.get("confirm_pin") or data.get("new_pin_confirm") or "").strip()
    password = str(data.get("password") or "")
    if confirm and new_pin != confirm:
        return JsonResponse({"ok": False, "error": "New PIN and confirmation do not match."}, status=400)
    granted = pin_service.consume_reset_grant(officer=officer, request=request)
    ok, msg = pin_service.reset_action_pin(
        officer=officer, new_pin=new_pin, password=password,
        request=request, grant_validated=granted)
    if not ok and not granted:
        return JsonResponse({"ok": False, "error": msg, "code": "RESET_UNAUTHORIZED"}, status=403)
    return JsonResponse({"ok": ok, **({"message": msg} if ok else {"error": msg})},
                        status=200 if ok else 400)


@require_POST
def officer_pin_reset_code(request: HttpRequest):
    """Forgot-PIN step 1a: email the rotating code (same OTP as login)."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer = pin_service.get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)
    ok, msg = pin_service.send_reset_code(officer=officer, request=request)
    return JsonResponse({"ok": ok, **({"message": msg} if ok else {"error": msg})},
                        status=200 if ok else 400)


@require_POST
def officer_pin_reset_verify(request: HttpRequest):
    """Forgot-PIN step 1b: check the email/authenticator/backup code.

    One input accepts all three (same box as login). Success unlocks step 2.
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer = pin_service.get_officer_from_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)
    data = _merge(request)
    code = str(data.get("code") or data.get("otp") or "").strip()
    if not code:
        return JsonResponse({"ok": False, "error": "Enter the verification code."}, status=400)
    ok, msg, method = pin_service.verify_reset_code(officer=officer, code=code, request=request)
    if not ok:
        return JsonResponse({"ok": False, "error": msg}, status=429 if "Too many" in msg else 401)
    return JsonResponse({"ok": True, "message": msg, "method": method,
                         "grant_minutes": pin_service.RESET_GRANT_MINUTES})
