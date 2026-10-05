from urllib.parse import quote

from django.conf import settings
import logging
from datetime import timedelta
from django.http import JsonResponse, HttpResponseRedirect
from django.utils import timezone
from core_system.models import AccessSession
from core_system.services import zt_service
from core_system import zt_settings

logger = logging.getLogger(__name__)

# Fallback default; the live value is superadmin-editable (zt_settings).
SESSION_IDLE_TIMEOUT = timedelta(minutes=30)

# Paths that must never be hard-blocked (escape hatches + the challenge flow
# itself). Everything else gets evaluated for officers.
ZT_SKIP_PREFIXES = ("/api/auth/", "/mfa", "/zt-challenge", "/logout")
ZT_SKIP_EXACT = ("/login/", "/")

# While a session is screen-locked, ONLY these keep answering (plus /logout
# and the unlock page). Everything else - including other /api/auth/*
# endpoints like MFA settings - is frozen until the officer unlocks.
ZT_LOCK_EXEMPT = (
    "/api/auth/zt/lock/",
    "/api/auth/zt/heartbeat/",
    "/api/auth/zt/status/",
    "/api/auth/zt/unlock/",
    "/api/auth/zero-trust/challenge/",
    "/api/auth/zero-trust/verify/",
    "/api/auth/zero-trust/status/",
)
ZT_LOCK_EXEMPT_PREFIXES = ("/zt-unlock", "/logout")


class NoCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG:
            if request.path.startswith(("/static/", "/media/")):
                response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
                response["Pragma"] = "no-cache"
                response["Expires"] = "0"
            elif isinstance(response, HttpResponseRedirect):
                return response
            elif response.get("Content-Type", "").startswith("text/html"):
                response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
                response["Pragma"] = "no-cache"
                response["Expires"] = "0"
        return response


class EmailQueueKickMiddleware:
    """Piggyback OTP/email delivery on ANY traffic.

    The queue worker spawned at queue time is fire-and-forget: it can die
    with a page close, dev-reload, or Passenger recycle while SMTP is still
    handshaking, leaving the row PENDING with nobody to retry it. This
    middleware kicks a bounded background drain (at most once per
    KICK_COOLDOWN_SECONDS, OTP-first ordering) after any non-static
    response that MIGHT have pending mail — so delivery never waits for
    the same page to be refreshed. Never blocks the response, never raises.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            path = request.path or ""
            static_url = getattr(settings, "STATIC_URL", "/static/")
            media_url = getattr(settings, "MEDIA_URL", "/media/")
            if path.startswith((static_url, media_url, "/__reload__/")):
                return response
            from core_system.models import OutgoingEmail
            from core_system.services.email_service import kick_email_worker
            if OutgoingEmail.objects.filter(status=OutgoingEmail.PENDING).exists():
                kick_email_worker(batch_size=10)
        except Exception:
            logger.exception("EmailQueueKickMiddleware piggyback failed")
        return response


def _wants_json(request) -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )


def _obf_sign_next(url: str, request) -> str:
    """Append the tamper-proof signature to a redirect URL when possible."""
    try:
        from core_system import url_obfuscation as obf
        if obf.is_enabled():
            key = obf.get_session_key(request)
            if key:
                return obf.sign_url(url, key)
    except Exception:
        pass
    return url


def _obf_session_expired() -> str:
    """Obfuscated landing URL for dead sessions (was ?session_expired=1)."""
    try:
        from core_system import url_obfuscation as obf
        if obf.is_enabled():
            return obf.session_expired_url()
    except Exception:
        pass
    return "/?session_expired=1"


def _zt_challenge_response(request, reasons: list):
    """Hard-check block: JSON challenge for API callers, redirect to the
    full-page challenge for normal navigation."""
    if _wants_json(request):
        response = JsonResponse({
            "ok": False,
            "zero_trust_challenge": True,
            "level": "hard",
            "reasons": reasons,
            "error": "Additional verification required. Please confirm the code sent to your email.",
        }, status=403)
        response["X-Zero-Trust-Challenge"] = "true"
        return response
    return HttpResponseRedirect(_obf_sign_next(f"/zt-challenge/?next={quote(request.path)}", request))


def _zt_locked_response(request, session):
    """Screen-locked block: JSON flag for API callers, redirect to the
    full-page unlock for normal navigation."""
    if _wants_json(request):
        response = JsonResponse({
            "ok": False,
            "session_locked": True,
            "error": "This session is locked. Unlock it to continue.",
            "unlock_url": _obf_sign_next(f"/zt-unlock/?next={quote(request.path)}", request),
        }, status=403)
        response["X-ZT-Session-Locked"] = "true"
        return response
    return HttpResponseRedirect(_obf_sign_next(f"/zt-unlock/?next={quote(request.path)}", request))


def _zt_expired_response(request):
    """Auto sign-out answer: the locked screen sat past its timer, so the
    session is gone - same shape as every other session-death path."""
    if _wants_json(request):
        return JsonResponse({
            "ok": False,
            "session_expired": True,
            "session_revoked": True,
            "error": "Your session was signed out automatically because the locked screen was not unlocked in time. Please log in again.",
        }, status=401)
    return HttpResponseRedirect(_obf_session_expired())


def _revoke_expired_lock(session, request) -> None:
    """Sign out a lock that outlived its auto sign-out timer. Runs once:
    afterwards the session reads Revoked and every later request takes the
    normal session-death path."""
    try:
        zt_service.revoke_session(session)
    except Exception:
        logger.exception("ZT auto sign-out revoke failed")
        return
    try:
        from core_system.shared_view_utils import _record_audit_trail
        _record_audit_trail(
            table="access_session",
            record_id=0,
            action="ZT_AUTO_SIGNOUT",
            actor=session.user_id_FK,
            old=None,
            new=None,
            ip=request.META.get("REMOTE_ADDR"),
            device_info=request.META.get("HTTP_USER_AGENT"),
            notes="Locked screen not unlocked in time - session signed out automatically.",
        )
    except Exception:
        logger.exception("ZT auto sign-out audit write failed")


class ZeroTrustMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        static_url = getattr(settings, 'STATIC_URL', '/static/')
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        if path.startswith(static_url) or path.startswith(media_url):
            return self.get_response(request)

        token = request.session.get("access_token")

        # Screen lock freezes even the other /api/auth/* endpoints (e.g. MFA
        # settings) - only the lock/unlock/heartbeat/status + OTP endpoints
        # answer while locked.
        if token and path.startswith("/api/auth/"):
            locked_session = (
                AccessSession.objects.select_related("user_id_FK")
                .filter(token_id=token).first()
            )
            if locked_session is not None and zt_service.is_locked(locked_session):
                # Locked past the auto sign-out timer: sign out, don't re-lock.
                if zt_service.lock_auto_signout_expired(locked_session):
                    _revoke_expired_lock(locked_session, request)
                    request.session.flush()
                    return _zt_expired_response(request)
                if path not in ZT_LOCK_EXEMPT:
                    return _zt_locked_response(request, locked_session)
            return self.get_response(request)

        if (
            any(path.startswith(p) for p in ZT_SKIP_PREFIXES)
            or path in ZT_SKIP_EXACT
        ):
            return self.get_response(request)

        if token:
            try:
                session = AccessSession.objects.select_related("user_id_FK").get(token_id=token)

                # Check if session is revoked or expired
                if (
                    session.session_status != "Active"
                    or session.expires_at <= timezone.now()
                ):
                    # Session is no longer valid - clear it and redirect to login
                    request.session.flush()
                    if _wants_json(request):
                        return JsonResponse({
                            "ok": False,
                            "session_expired": True,
                            "error": "Your session has been revoked due to a new login on another device. Please login again."
                        }, status=401)
                    return HttpResponseRedirect(_obf_session_expired())

                now = timezone.now()

                # Idle timeout: no activity for the configured hard-logout
                # window -> expire session (superadmin-editable timer)
                session_idle_timeout = zt_settings.get_zt_timers()["session_idle_timeout"]
                if session.last_activity_at is not None:
                    if now - session.last_activity_at > session_idle_timeout:
                        request.session.flush()
                        if _wants_json(request):
                            return JsonResponse({
                                "ok": False,
                                "session_expired": True,
                                "error": "Your session has expired due to inactivity. Please login again."
                            }, status=401)
                        return HttpResponseRedirect(_obf_session_expired())

                # Zero Trust only applies to officers - members just get activity tracking
                user_role = (session.user_id_FK.role or "").strip().lower()
                if user_role != "member":
                    # Screen lock first: nothing else matters until unlocked.
                    if zt_service.is_locked(session):
                        # Locked past the auto sign-out timer: sign out, don't re-lock.
                        if zt_service.lock_auto_signout_expired(session):
                            _revoke_expired_lock(session, request)
                            request.session.flush()
                            return _zt_expired_response(request)
                        if path not in ZT_LOCK_EXEMPT and not any(
                            path.startswith(p) for p in ZT_LOCK_EXEMPT_PREFIXES
                        ):
                            return _zt_locked_response(request, session)
                        # Exempt path while locked (heartbeat/status/unlock):
                        # skip evaluation, the lock is the only state that counts.
                    else:
                        # Proof-of-possession: bound sessions must present a
                        # fresh device proof (DPoP-lite). A stolen bearer
                        # cookie alone fails here -> hard challenge.
                        try:
                            from core_system.device_binding import verify_request_binding

                            bound_ok, bound_reason = verify_request_binding(
                                request, session.session_policy
                            )
                        except Exception:
                            bound_ok, bound_reason = True, "binding-check-error"
                        if not bound_ok:
                            zt_service.record_security_event(session, "device_binding_failed")
                            # Persist the hard level BEFORE redirecting. The
                            # challenge page bounces back to ?next= when the
                            # sticky level is not "hard" - redirecting without
                            # persisting is an infinite 302 loop
                            # (ERR_TOO_MANY_REDIRECTS). Fail closed with a
                            # solvable OTP form instead.
                            zt_service.apply_hard_check(
                                session, request,
                                [f"Device binding failed: {bound_reason}"],
                            )
                            self._audit_level(
                                "ZT_HARD", session, request,
                                [f"Device binding failed: {bound_reason}"],
                            )
                            return _zt_challenge_response(
                                request, [f"Device binding failed: {bound_reason}"]
                            )
                        # Backstop: requests flowing but the page heartbeat went
                        # quiet means the lock UI was stripped or JS died -
                        # lock server-side and demand an unlock.
                        if zt_service.heartbeat_lost(session, now):
                            zt_service.lock_session(session, "heartbeat_lost")
                            self._audit_level("ZT_AUTO_LOCK", session, request, ["Page heartbeat lost"])
                            return _zt_locked_response(request, session)

                        block = self._evaluate_officer(request, session, now)
                        if block is not None:
                            return block

                # Continuous activity tracking (throttled to once per minute)
                if session.last_activity_at is None or now - session.last_activity_at > timedelta(minutes=1):
                    session.last_activity_at = now
                    session.save(update_fields=["last_activity_at"])

                response = self.get_response(request)
                zt_level = getattr(request, "_zt_level", None)
                if zt_level:
                    response["X-Zero-Trust-Level"] = zt_level
                    reasons = getattr(request, "_zt_reasons", [])
                    if reasons:
                        response["X-Zero-Trust-Reasons"] = quote("; ".join(reasons))
                return response

            except AccessSession.DoesNotExist:
                # Session doesn't exist - clear session data
                request.session.flush()
                if _wants_json(request):
                    return JsonResponse({
                        "ok": False,
                        "session_expired": True,
                        "error": "Your session has been revoked. Please login again."
                    }, status=401)
                return HttpResponseRedirect(_obf_session_expired())

        return self.get_response(request)

    # ------------------------------------------------------------------
    # Officer per-request Zero Trust evaluation
    # ------------------------------------------------------------------

    def _evaluate_officer(self, request, session, now):
        try:
            result = zt_service.evaluate_zero_trust(session, request)
        except Exception:
            # The risk engine must never take the whole dashboard down.
            logger.exception("ZT evaluation failed for session %s", session.token_id[:12])
            return None

        policy_changed = False
        policy = session.session_policy if isinstance(session.session_policy, dict) else {}
        original = dict(policy)

        # First request of an older session: bootstrap its baseline instead of
        # challenging it for having no snapshot.
        if zt_service.ensure_snapshot(session, request):
            policy = session.session_policy
            policy.setdefault("zt_env_baseline", dict(policy.get("zt_client_env") or {}))
            policy_changed = True
        else:
            policy = session.session_policy

        # A previously-raised hard check stays sticky until the OTP verifies.
        sticky_level = policy.get("zt_level") or "none"
        if sticky_level == "hard":
            return _zt_challenge_response(request, policy.get("zt_reasons") or result["reasons"])

        level = result["level"]
        reasons = result["reasons"]
        prev_level = sticky_level if sticky_level in zt_service.LEVEL_ORDER else "none"

        # Dedicated network-change lockout: a moved laptop must confirm with
        # its password. The drift candidate needs a second sighting before it
        # counts, so while it is still pending we hush the generic
        # "Network changed" medium noise and keep the OLD baseline (the
        # result rebaseline below would otherwise adopt the new network and
        # the confirmation could never complete).
        net_hold_ip_rebaseline = False
        try:
            if "Network changed since last check" in reasons:
                net = zt_service.track_network_drift(session, request)
                if net["state"] == "confirmed":
                    details = zt_service.apply_network_lock(session, request, net)
                    self._audit_level(
                        "ZT_NETLOCK", session, request,
                        [f"Network changed ({net['from_net']} -> {net['to_net']}); screen locked pending password confirm"],
                    )
                    try:
                        if not details.get("mailed"):
                            from core_system.auth_views import _queue_network_change_alert
                            _queue_network_change_alert(request, session.user_id_FK, details)
                            zt_service.mark_netlock_mailed(session)
                    except Exception:
                        logger.exception("ZT netlock email failed")
                    return _zt_locked_response(request, session)
                if net["state"] == "pending":
                    reasons = [r for r in reasons if r != "Network changed since last check"]
                    if not reasons:
                        level = "none"
                    net_hold_ip_rebaseline = True
        except Exception:
            logger.exception("ZT network-drift tracking failed")

        if level == "hard":
            zt_service.apply_hard_check(session, request, reasons)
            self._audit_level("ZT_HARD", session, request, reasons)
            return _zt_challenge_response(request, reasons)

        if zt_service.LEVEL_ORDER.get(level, 0) > zt_service.LEVEL_ORDER.get(prev_level, 0):
            policy["zt_level"] = level
            policy["zt_reasons"] = reasons
            policy_changed = True
            if level == "medium":
                self._notify_medium(session, request, reasons)
                self._audit_level("ZT_MEDIUM", session, request, reasons)
            elif prev_level == "hard":
                # Downgraded below hard without a verify (e.g. events aged out)
                policy["zt_level"] = level
        elif level != prev_level and level == "none":
            policy["zt_level"] = "none"
            policy["zt_reasons"] = []
            policy_changed = True

        if result.get("rebaseline"):
            rb = result["rebaseline"]
            if not net_hold_ip_rebaseline:
                policy["zt_ip_baseline"] = rb["ip_net"]
            policy["zt_env_baseline"] = rb["env"]
            policy_changed = True

        if policy_changed:
            session.session_policy = policy
            session.save(update_fields=["session_policy"])

        if level in ("soft", "medium"):
            request._zt_level = level
            request._zt_reasons = reasons

        return None

    def _notify_medium(self, session, request, reasons):
        """Notify the officer once per occurrence (in-app bell + push)."""
        try:
            from core_system.services.notifications import notify_officer

            officer = session.user_id_FK
            notify_officer(
                officer,
                notification_type="zt_medium",
                message="Security check: " + "; ".join(reasons) + ". If this wasn't you, change your password and review your sessions.",
                category="general",
                url=request.path,
            )
        except Exception:
            logger.exception("ZT medium notification failed")

    def _audit_level(self, action, session, request, reasons):
        try:
            from core_system.shared_view_utils import _record_audit_trail

            _record_audit_trail(
                table="access_session",
                record_id=0,
                action=action,
                actor=session.user_id_FK,
                old=None,
                new={"reasons": reasons},
                ip=request.META.get("REMOTE_ADDR"),
                device_info=request.META.get("HTTP_USER_AGENT"),
                notes=f"ZT level change: {', '.join(reasons)}",
            )
        except Exception:
            logger.exception("ZT audit trail write failed")


class UrlObfuscationMiddleware:
    """Enforce URL encryption/obfuscation tokens (service: url_obfuscation).

    Rules (only when URL_OBFUSCATION_ENABLED):
      - Exempt prefixes, static/media: always pass.
      - ``?x=`` present: must decrypt; tampered blob -> branded 404.
        Decoded params are stashed on ``request.obf_envelope``.
      - ``?_s=`` present: must verify against the session subkey;
        mismatch -> branded 404. Requests without a session subkey
        (anonymous/public traffic) cannot be verified -> pass.
      - Neither present but a covered query IS present: 404 only when
        URL_OBFUSCATION_REQUIRE_SIGNATURE is True (hard-enforcement
        mode); otherwise pass (compat for old bookmarks / clients
        still migrating to signed URLs).

    The 404 is rendered directly (not raised) so the branded page shows
    in every DEBUG mode.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from core_system import url_obfuscation as obf

        if obf.is_enabled() and self._should_inspect(request):
            denial = self._inspect(request, obf)
            if denial is not None:
                return denial
        return self.get_response(request)

    def _should_inspect(self, request) -> bool:
        from core_system import url_obfuscation as obf

        path = request.path or "/"
        if obf.is_exempt_path(path):
            return False
        static_url = getattr(settings, "STATIC_URL", "/static/")
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        if path.startswith((static_url, media_url)):
            return False
        return True

    def _inspect(self, request, obf):
        query = request.GET
        # Bootstrap the per-session subkey for already-authenticated
        # sessions created before rollout (their session row exists, so
        # this creates no new rows for anonymous visitors).
        try:
            if request.session.get("access_token") and not request.session.get(obf.SESSION_KEY_NAME):
                obf.get_or_create_session_key(request)
        except Exception:
            pass

        if obf.ENVELOPE_PARAM in query:
            decoded = obf.opaque_decode(query.get(obf.ENVELOPE_PARAM, ""))
            if decoded is None:
                return self._tampered(request, "envelope")
            request.obf_envelope = decoded
            return None

        if obf.SIG_PARAM in query:
            key = obf.get_session_key(request)
            if key is not None and obf.verify_signed_query(request.path, query, key):
                return None
            if key is None:
                # No subkey (anonymous/public) -> nothing to verify against.
                logger.info("URL-OBF unsigned (no session key): %s", request.path)
                return None
            return self._tampered(request, "signature")

        if obf.is_require_signature() and self._has_covered_query(query):
            key = obf.get_session_key(request)
            if key is not None:
                try:
                    if request.session.get("access_token"):
                        return self._tampered(request, "missing")
                except Exception:
                    pass
        return None

    @staticmethod
    def _has_covered_query(query) -> bool:
        from core_system import url_obfuscation as obf

        for k in query.keys():
            if k not in obf.IGNORED_PARAMS:
                return True
        return False

    @staticmethod
    def _tampered(request, reason: str):
        logger.warning("URL-OBF tampered URL blocked (%s): %s", reason, request.get_full_path())
        try:
            from django.shortcuts import render

            return render(request, "404.html", status=404)
        except Exception:
            from django.http import HttpResponseNotFound

            return HttpResponseNotFound("<h1>404 — Page not found</h1>")


class SecurityHeadersMiddleware:
    """Emit Content-Security-Policy (+ friends) on every response.

    Inline scripts/styles are pervasive (dashboards), so the policy allows
    'unsafe-inline' + the pinned CDN/identity hosts and instead bans the
    high-impact vectors: plugins, foreign frames (except Turnstile),
    form exfiltration, and clickjacking. Tighten via the CSP_POLICY setting
    (no code change) once inline code is hashed/nonces.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            policy = getattr(settings, "CSP_POLICY", "") or self._default_policy()
            response["Content-Security-Policy"] = policy
        except Exception:
            pass
        return response

    @staticmethod
    def _default_policy() -> str:
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
            "https://cdn.tailwindcss.com https://cdn.jsdelivr.net "
            "https://challenges.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
            "https://fonts.googleapis.com https://cdn.tailwindcss.com "
            "https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' https: wss:; "
            "frame-src https://challenges.cloudflare.com https://maps.google.com https://www.google.com; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'self'; upgrade-insecure-requests"
        )


class FetchMetadataGuardMiddleware:
    """Same-origin POST guard for the ~58 @csrf_exempt endpoints.

    Those views skip Django's CSRF token check (dashboards post without
    tokens), so this enforces the next-best thing at the edge: state-changing
    requests that a modern browser labels cross-site (or carry a foreign
    Origin) are rejected before any view runs. Same-origin fetch, navigations,
    and non-browser clients pass untouched — nothing to rewire in 58 views.
    Long-term fix remains per-view CSRF tokens; this is the backstop.
    """

    _METHODS = ("POST", "PUT", "PATCH", "DELETE")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self._METHODS and self._is_forged(request):
            logger.warning(
                "FETCH-META cross-site %s blocked: %s origin=%s sfs=%s",
                request.method, request.path,
                request.META.get("HTTP_ORIGIN", "-"),
                request.META.get("HTTP_SEC_FETCH_SITE", "-"),
            )
            return JsonResponse(
                {"ok": False, "error": "Cross-site request refused."}, status=403
            )
        return self.get_response(request)

    @classmethod
    def _is_forged(cls, request) -> bool:
        try:
            site = (request.META.get("HTTP_SEC_FETCH_SITE") or "").lower()
            if site == "cross-site":
                return True
            if site in ("same-origin", "same-site", "none"):
                return False
            origin = (request.META.get("HTTP_ORIGIN") or "").strip()
            if not origin:
                return False  # old browser / curl: nothing to check
            return not cls._origin_trusted(request, origin)
        except Exception:
            return False

    @staticmethod
    def _origin_trusted(request, origin: str) -> bool:
        from urllib.parse import urlparse

        try:
            host = (urlparse(origin).hostname or "").lower()
            if not host:
                return False
            own = (request.get_host().split(":")[0] or "").lower()
            if host == own:
                return True
            trusted = []
            for o in list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []):
                h = (urlparse(o).hostname or "").lower()
                if h:
                    trusted.append(h)
            for t in trusted:
                if t.startswith("*."):
                    if host == t[2:] or host.endswith("." + t[2:]):
                        return True
                elif host == t:
                    return True
            return False
        except Exception:
            return False
