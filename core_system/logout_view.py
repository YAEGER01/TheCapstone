from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

from core_system.models import AccessSession
from core_system.shared_view_utils import _record_audit_trail


def logout_view(request: HttpRequest) -> HttpResponse:
    """Logout for custom session-token auth (revokes AccessSession + clears Django session keys)."""

    token = request.session.get("access_token")
    officer = None
    if token:
        try:
            sess = AccessSession.objects.select_related("user_id_FK").get(token_id=token)
            officer = sess.user_id_FK
            sess.revoked_at = timezone.now()
            sess.session_status = "Revoked"
            sess.save(update_fields=["revoked_at", "session_status"])
        except AccessSession.DoesNotExist:
            # Token not found; continue with client-side logout
            pass

    if officer is not None:
        try:
            _record_audit_trail(
                table="officer_user",
                record_id=officer.user_id_PK,
                action="LOGOUT",
                actor=officer,
                ip=request.META.get("REMOTE_ADDR"),
                device_info=request.META.get("HTTP_USER_AGENT"),
                notes="Session revoked via logout.",
            )
        except Exception:
            # Never block logout because auditing failed
            pass

    request.session.pop("access_token", None)
    request.session.pop("officer_id", None)
    request.session.pop("role", None)
    request.session.pop("_mfa_initiated", None)
    request.session.pop("mfa_pre_auth_token", None)
    request.session.pop("mfa_officer_id", None)
    request.session.pop("mfa_username", None)
    request.session.pop("mfa_initiated_at", None)
    request.session.pop("mfa_email_warning", None)
    request.session.flush()

    response = redirect("login")
    # Zero-trust teardown: the device-binding cookie pair is a security
    # control and must not survive logout (shared PCs, session fixation).
    # Django's session flush rotates `sessionid`; we explicitly clear the
    # device cookies with matching path/samesite.
    try:
        from core_system.device_binding import clear_device_cookies
        clear_device_cookies(response)
    except Exception:
        pass
    return response
