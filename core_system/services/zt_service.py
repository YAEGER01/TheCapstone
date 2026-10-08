"""Zero Trust risk engine.

Server-authoritative continuous verification for officer sessions. The client
contributes soft signals (timezone, screen) but only server-observed values
(User-Agent, IP, session, account) can escalate to a hard check, because
anything the client sends can be spoofed by an attacker who holds a stolen
session cookie.

Verification levels (highest wins):
  none   - session matches its baseline
  soft   - harmless drift; rebind silently, log only
  medium - environment changed noticeably; notify the user in-app
  hard   - possible cookie replay / suspicious activity; require email OTP

All state lives in AccessSession.session_policy so no new migration is needed.
"""

import hmac
import hashlib
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from core_system import zt_settings
from core_system.zt_settings import get_zt_timers

# Default values kept as module constants for backward compatibility;
# live values always come from get_zt_timers() (superadmin-editable).
ZT_IDLE_SOFT = zt_settings.ZT_IDLE_SOFT
ZT_IDLE_MEDIUM = zt_settings.ZT_IDLE_MEDIUM
ZT_SEC_WINDOW = zt_settings.ZT_SEC_WINDOW
ZT_SEC_MEDIUM = zt_settings.ZT_SEC_MEDIUM
ZT_SEC_HARD = zt_settings.ZT_SEC_HARD
ZT_CHALLENGE_COOLDOWN = zt_settings.ZT_CHALLENGE_COOLDOWN
ZT_LOCK_IDLE = zt_settings.ZT_LOCK_IDLE
ZT_LOCK_HEARTBEAT_STALE = zt_settings.ZT_LOCK_HEARTBEAT_STALE
ZT_LOCK_OTP_AFTER = zt_settings.ZT_LOCK_OTP_AFTER
ZT_UNLOCK_MAX_FAILURES = zt_settings.ZT_UNLOCK_MAX_FAILURES
ZT_UNLOCK_OTP_AFTER_FAILURES = zt_settings.ZT_UNLOCK_OTP_AFTER_FAILURES
ZT_ALWAYS_VERIFY_ROLES = zt_settings.ZT_ALWAYS_VERIFY_ROLES

LEVEL_ORDER = {"none": 0, "soft": 1, "medium": 2, "hard": 3}


# ---------------------------------------------------------------------------
# Signal extraction (server-observed + client-attested)
# ---------------------------------------------------------------------------

def get_client_ip(request) -> str:
    """Best-effort client IP behind proxies (nginx / Cloudflare / Passenger).

    Why this exists: the old code read only REMOTE_ADDR. Behind nginx
    (deploy/nginx*.conf proxies to Daphne) REMOTE_ADDR is always 127.0.0.1,
    and on local runserver it is 127.0.0.1 too — so a WiFi/hotspot move was
    invisible and the network lock could never fire. Nginx overwrites
    X-Real-IP with $remote_addr and appends to X-Forwarded-For, so prefer
    the headers the proxy controls and fall back to REMOTE_ADDR.
    NOTE: only trustworthy when a proxy you control sets/strips these
    (same caveat as SECURE_PROXY_SSL_HEADER in settings.py). Never expose
    Daphne/runserver directly to clients while trusting these headers.
    """
    try:
        meta = getattr(request, "META", {}) or {}
    except Exception:
        return "0.0.0.0"

    def _clean(value: str) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        v = v.split(",")[0].strip()
        if not v:
            return ""
        v = v.split()[0].strip()
        # strip port ("1.2.3.4:1234", "[::1]:1234") and zone ("fe80::1%eth0")
        if v.startswith("[") and "]" in v:
            v = v[1:v.index("]")]
        elif v.count(":") == 1 and v.count(".") == 3:
            v = v.split(":")[0]
        return v.split("%")[0].strip()

    for header in ("HTTP_CF_CONNECTING_IP", "HTTP_TRUE_CLIENT_IP", "HTTP_X_REAL_IP"):
        cleaned = _clean(meta.get(header, ""))
        if cleaned and cleaned not in ("unknown", "undefined"):
            return cleaned
    xff = meta.get("HTTP_X_FORWARDED_FOR") or ""
    for part in xff.split(","):
        cleaned = _clean(part)
        if cleaned and cleaned not in ("unknown", "undefined"):
            return cleaned
    return _clean(meta.get("REMOTE_ADDR", "")) or "0.0.0.0"

_UA_BROWSERS = [
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Chrome/", "Chrome"),
    ("Firefox/", "Firefox"),
    ("Safari/", "Safari"),
]


def parse_ua_family(ua: str) -> dict:
    """Reduce a User-Agent string to the stable parts worth comparing.

    The full UA string changes when a browser auto-updates mid-session, so we
    compare browser family + OS platform only (e.g. Chrome / Windows).
    """
    ua = (ua or "").strip()
    family = "Other"
    for token, name in _UA_BROWSERS:
        if token in ua:
            family = name
            break
    platform = "Unknown"
    m = re.search(r"\(([^)]*)\)", ua)
    if m:
        platform = m.group(1).split(";")[0].strip()[:60] or "Unknown"
    return {"family": family, "platform": platform}


def ip_network_key(ip: str) -> str:
    """Coarse network identity for an IP.

    IPv4 -> first 3 octets (the /24, typically one site/ISP POP).
    IPv6 -> first 4 hextacts. Comparing prefixes instead of exact addresses
    avoids lockouts from CGNAT/mobile rotation while still catching a device
    that moves to a wholly different network.
    """
    ip = (ip or "").strip()
    if ":" in ip:
        return ":".join(ip.split(":")[:4])
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3])
    return ip


def baseline_fingerprint(request) -> dict:
    """Snapshot of server-observed signals, taken at login (and re-taken on
    successful hard verification or after a notified medium event)."""
    ua = parse_ua_family(request.META.get("HTTP_USER_AGENT", ""))
    ip = get_client_ip(request)
    lang = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").split(",")[0][:35]
    return {
        "ua_family": ua["family"],
        "ua_platform": ua["platform"],
        "lang": lang,
        "ip": ip,
        "ip_net": ip_network_key(ip),
        "ts": timezone.now().isoformat(),
    }


_CLIENT_ENV_KEYS = {"tz": 40, "screen": 20, "plat": 60, "cores": 3, "mem": 3}


def capture_client_env(params: dict) -> dict:
    """Validate the client-attested environment the badge JS reports."""
    env = {}
    for key, max_len in _CLIENT_ENV_KEYS.items():
        val = str(params.get(key, "") or "").strip()[:max_len]
        if val:
            env[key] = val
    return env


# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------

def _policy(session) -> dict:
    return session.session_policy if isinstance(session.session_policy, dict) else {}


def _sec_events(policy) -> list:
    events = policy.get("zt_sec_events")
    return events if isinstance(events, list) else []


def ensure_snapshot(session, request) -> bool:
    """Bootstrap a fingerprint snapshot for sessions created before ZT
    hardening (or by tests). Returns True if the policy changed."""
    policy = _policy(session)
    if policy.get("zt_snapshot"):
        return False
    policy["zt_snapshot"] = baseline_fingerprint(request)
    policy["zt_ip_baseline"] = policy["zt_snapshot"]["ip_net"]
    session.session_policy = policy
    return True


def merge_client_env(session, params: dict) -> bool:
    """Merge client-attested environment into the policy. Returns True if it
    changed. Soft signals only - never used for hard escalation by itself."""
    env = capture_client_env(params)
    if not env:
        return False
    policy = _policy(session)
    if policy.get("zt_client_env") == env:
        return False
    policy["zt_client_env"] = env
    session.session_policy = policy
    return True


def record_security_event(session, kind: str) -> int:
    """Count a security-relevant denial against this session (permission
    denied, failed OTP, blocked action). Returns the current count in the
    window; the evaluator escalates when thresholds are crossed."""
    timers = get_zt_timers()
    policy = _policy(session)
    now = timezone.now()
    cutoff = now - timers["sec_window"]
    events = [
        e for e in _sec_events(policy)
        if isinstance(e, list) and len(e) == 2
        and _parse_iso(e[0]) is not None and _parse_iso(e[0]) > cutoff
    ]
    events.append([now.isoformat(), str(kind)[:40]])
    policy["zt_sec_events"] = events[-50:]
    session.session_policy = policy
    session.save(update_fields=["session_policy"])
    return len(policy["zt_sec_events"])


def _parse_iso(value):
    try:
        dt = datetime.fromisoformat(str(value))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_zero_trust(session, request) -> dict:
    """Compare the live request against the session's baseline.

    Returns {"level": str, "reasons": [str], "changed": bool, "rebaseline": dict|None}.
    Never persists anything itself except via the returned rebaseline hint;
    the caller decides what to save (keeps DB writes under middleware control).
    """
    timers = get_zt_timers()
    policy = _policy(session)
    reasons = []
    level = "none"

    def raise_to(new_level, reason):
        nonlocal level
        if LEVEL_ORDER.get(new_level, 0) > LEVEL_ORDER.get(level, 0):
            level = new_level
        if reason not in reasons:
            reasons.append(reason)

    snapshot = policy.get("zt_snapshot") or baseline_fingerprint(request)
    ua_now = parse_ua_family(request.META.get("HTTP_USER_AGENT", ""))

    # 1. Device binding (server-observed UA) - cookie replayed on another
    #    device/browser shows up here. Hard.
    if snapshot.get("ua_family") and ua_now["family"] != snapshot["ua_family"]:
        raise_to("hard", f"Browser changed from {snapshot['ua_family']} to {ua_now['family']}")
    elif snapshot.get("ua_platform") and ua_now["platform"] != snapshot["ua_platform"]:
        raise_to("hard", f"Device platform changed from {snapshot['ua_platform']}")

    # 2. Network drift (server-observed IP prefix)
    ip_now = get_client_ip(request)
    ip_net_now = ip_network_key(ip_now)
    ip_baseline = policy.get("zt_ip_baseline") or snapshot.get("ip_net")
    network_changed = bool(ip_baseline and ip_net_now and ip_net_now != ip_baseline)

    # 3. Client-attested environment drift (soft signals)
    env = policy.get("zt_client_env") or {}
    env_baseline = policy.get("zt_env_baseline") or {}
    tz_changed = bool(env.get("tz") and env_baseline.get("tz") and env["tz"] != env_baseline["tz"])
    screen_changed = bool(
        env.get("screen") and env_baseline.get("screen") and env["screen"] != env_baseline["screen"]
    )

    # 4. Suspicious-activity counter (fed by guards/verify failures)
    now = timezone.now()
    cutoff = now - timers["sec_window"]
    recent = [
        e for e in _sec_events(policy)
        if isinstance(e, list) and len(e) == 2 and (_parse_iso(e[0]) or now - timers["sec_window"]) > cutoff
    ]
    if len(recent) >= timers["sec_hard"]:
        raise_to("hard", f"{len(recent)} suspicious events in {int(timers['sec_window'].total_seconds() // 60)} min")
    elif len(recent) >= timers["sec_medium"]:
        raise_to("medium", f"{len(recent)} suspicious events recently")

    # 5. Idle tiering - within the existing hard-logout idle window
    last_active = session.last_activity_at
    if last_active is not None:
        idle = now - last_active
        if idle >= timers["idle_medium"]:
            raise_to("medium", f"Inactive for {int(idle.total_seconds() // 60)} minutes")
        elif idle >= timers["idle_soft"]:
            raise_to("soft", "Rechecked after inactivity")

    # 6. Timezone change usually means travel / new network -> medium once
    if tz_changed:
        raise_to("medium", f"Timezone changed to {env.get('tz')}")
    elif screen_changed:
        raise_to("soft", "Display changed")

    # Network change ranks above soft idle/screen drift but below hard.
    if network_changed:
        raise_to("medium", "Network changed since last check")

    # After notifying a medium event we rebaseline so a stable new normal
    # (e.g. DHCP gave out a new IP) does not nag on every request.
    rebaseline = None
    if level in ("medium", "soft") and (
        network_changed or tz_changed or screen_changed or "Rechecked after inactivity" in reasons
    ):
        rebaseline = {"ip_net": ip_net_now, "env": dict(env)}

    return {"level": level, "reasons": reasons, "changed": False, "rebaseline": rebaseline}


def apply_hard_check(session, request, reasons: list) -> None:
    """Make a hard check sticky: the session stays challenged until
    zero_trust_verify succeeds (which calls clear_hard_check)."""
    policy = _policy(session)
    policy["zt_level"] = "hard"
    policy["zt_reasons"] = reasons[:5]
    policy["zt_hard_since"] = timezone.now().isoformat()
    policy["zt_verify_failures"] = 0
    session.session_policy = policy
    session.save(update_fields=["session_policy"])


def clear_hard_check(session, request) -> None:
    """Called after a successful OTP hard check: rebaseline everything to the
    current environment so the session continues cleanly."""
    policy = _policy(session)
    policy["zt_snapshot"] = baseline_fingerprint(request)
    policy["zt_ip_baseline"] = policy["zt_snapshot"]["ip_net"]
    policy["zt_env_baseline"] = dict(policy.get("zt_client_env") or {})
    policy["zt_level"] = "none"
    policy["zt_reasons"] = []
    policy["zt_verified_at"] = timezone.now().isoformat()
    policy["zt_confirm_count"] = (policy.get("zt_confirm_count", 0) or 0) + 1
    policy["zt_sec_events"] = []
    session.session_policy = policy
    session.save(update_fields=["session_policy"])


def current_level(session) -> tuple:
    """Read the sticky level without evaluating (for the status endpoint)."""
    policy = _policy(session)
    return policy.get("zt_level", "none"), policy.get("zt_reasons", [])


# ---------------------------------------------------------------------------
# Screen lock (bathroom-break protection)
#
# The overlay is just the visual; the authoritative lock is the zt_locked
# flag: while it is set, the middleware 403s everything except the unlock
# endpoints, so stripping the overlay from the DOM unlocks nothing.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Network-change lockout ("Is this you?" — dedicated, debounced)
#
# A WiFi/hotspot move shows up as a new /24 prefix. Locking on the very first
# sighting would punish proxy failovers and captive-portal blips, so a new
# prefix only ARMS a candidate; the screen locks once the SAME new prefix is
# still there on a later request (>= NETLOCK_CONFIRM_REQUESTS sightings,
# >= NETLOCK_CONFIRM_SECONDS apart). Flapping back to the old network disarms
# silently. "Role" cannot change mid-session (it is bound at login), so the
# lock reports network + device/browser/timezone signals only.
# ---------------------------------------------------------------------------
NETWORK_LOCK_REASON = "network_change"
NETLOCK_CONFIRM_REQUESTS = 2
NETLOCK_CONFIRM_SECONDS = 20


def _mask_net(ip_net: str) -> str:
    """Prefix shape without the full address (192.168.1 -> 192.168.1.xxx)."""
    ip_net = (ip_net or "").strip()
    if not ip_net:
        return "unknown network"
    sep = ":" if ":" in ip_net else "."
    return f"{ip_net}{sep}xxx"


def netlock_changes_text(details: dict) -> str:
    """Human $whatChanged list for the lock popup and the email."""
    d = details or {}
    bits = []
    if d.get("from_net") and d.get("to_net"):
        bits.append(
            f"network (from {_mask_net(d['from_net'])} to {_mask_net(d['to_net'])})"
        )
    for extra in d.get("extra") or []:
        if str(extra) not in bits:
            bits.append(str(extra))
    return ", ".join(bits) or "network"


def track_network_drift(session, request) -> dict:
    """Debounced drift tracker. Returns state none|pending|confirmed + details.

    Saves the candidate into session_policy itself. Callers lock on
    "confirmed" and otherwise leave the session running.
    """
    policy = _policy(session)
    snapshot = policy.get("zt_snapshot") or {}
    baseline = policy.get("zt_ip_baseline") or snapshot.get("ip_net")
    ip_now = get_client_ip(request)
    ip_net_now = ip_network_key(ip_now)
    out = {"state": "none", "from_net": baseline or "", "to_net": ip_net_now, "changes": []}
    if not baseline or not ip_net_now or ip_net_now == baseline:
        if policy.pop("zt_net_candidate", None) is not None:
            session.session_policy = policy
            session.save(update_fields=["session_policy"])
        return out
    out["changes"].append(f"network (from {_mask_net(baseline)} to {_mask_net(ip_net_now)})")
    env = policy.get("zt_client_env") or {}
    env_baseline = policy.get("zt_env_baseline") or {}
    if env.get("tz") and env_baseline.get("tz") and env["tz"] != env_baseline["tz"]:
        out["changes"].append(f"timezone (now {env['tz']})")
    ua_now = parse_ua_family(request.META.get("HTTP_USER_AGENT", ""))
    if snapshot.get("ua_family") and ua_now["family"] != snapshot["ua_family"]:
        out["changes"].append(f"browser (now {ua_now['family']})")
    now = timezone.now()
    cand = policy.get("zt_net_candidate") or {}
    if cand.get("to_net") != ip_net_now or cand.get("from_net") != baseline:
        cand = {"from_net": baseline, "to_net": ip_net_now,
                "first_seen": now.isoformat(), "confirms": 1}
        out["state"] = "pending"
    else:
        cand["confirms"] = int(cand.get("confirms") or 1) + 1
        first = _parse_iso(cand.get("first_seen")) or now
        age = (now - first).total_seconds()
        out["state"] = (
            "confirmed"
            if (cand["confirms"] >= NETLOCK_CONFIRM_REQUESTS and age >= NETLOCK_CONFIRM_SECONDS)
            else "pending"
        )
    policy["zt_net_candidate"] = cand
    session.session_policy = policy
    session.save(update_fields=["session_policy"])
    return out


def apply_network_lock(session, request, track: dict) -> dict:
    """Freeze details + engage the lock. Caller audits, emails, responds."""
    policy = _policy(session)
    details = {
        "from_net": track.get("from_net", ""),
        "to_net": track.get("to_net", ""),
        "extra": [c for c in track.get("changes", []) if not c.startswith("network (")],
        "when": timezone.now().isoformat(),
        "mailed": False,
    }
    policy["zt_netlock_details"] = details
    policy.pop("zt_net_candidate", None)
    session.session_policy = policy
    session.save(update_fields=["session_policy"])
    lock_session(session, NETWORK_LOCK_REASON)
    return details


def mark_netlock_mailed(session) -> None:
    policy = _policy(session)
    details = policy.get("zt_netlock_details") or {}
    details["mailed"] = True
    policy["zt_netlock_details"] = details
    session.session_policy = policy
    session.save(update_fields=["session_policy"])


def is_locked(session) -> bool:
    return bool(_policy(session).get("zt_locked"))


def lock_note(session) -> str:
    """Plain-language answer to 'why am I locked out?', for the lock UI."""
    policy = _policy(session)
    if not policy.get("zt_locked"):
        return ""
    reason = (policy.get("zt_lock_reason") or "idle").strip()
    if reason == "heartbeat_lost":
        return ("The system locked this session automatically because the page "
                "stopped responding.")
    if reason == "idle":
        minutes = int(get_zt_timers()["lock_idle"].total_seconds() // 60)
        minutes_text = f"{minutes} minute{'s' if minutes != 1 else ''}"
        return (f"The system locked this session automatically because it idled "
                f"for {minutes_text} after your last activity.")
    if reason == NETWORK_LOCK_REASON:
        details = policy.get("zt_netlock_details") or {}
        what = netlock_changes_text(details)
        return (f"We detected a change in {what} while you were signed in. "
                "Is this you? Type your password below to confirm your "
                "identity and continue. If this wasn't you, sign out and "
                "change your password immediately.")
    return "The system locked this session automatically for security."


def lock_session(session, reason: str = "idle") -> None:
    policy = _policy(session)
    if policy.get("zt_locked"):
        return
    policy["zt_locked"] = True
    policy["zt_locked_at"] = timezone.now().isoformat()
    policy["zt_lock_reason"] = str(reason)[:40]
    policy["zt_unlock_failures"] = 0
    session.session_policy = policy
    session.save(update_fields=["session_policy"])


def lock_age(session, now=None):
    """How long the session has been screen-locked, or None when it is not
    locked (or the lock predates lock timestamps)."""
    policy = _policy(session)
    if not policy.get("zt_locked"):
        return None
    locked_at = _parse_iso(policy.get("zt_locked_at"))
    if locked_at is None:
        return None
    return (now or timezone.now()) - locked_at


def lock_auto_signout_expired(session, now=None) -> bool:
    """True once a locked screen has sat unlocked past the auto sign-out
    timer - the session must be signed out, not just kept locked."""
    age = lock_age(session, now)
    if age is None:
        return False
    return age >= get_zt_timers()["lock_auto_signout"]


def lock_expires_in(session, now=None):
    """Seconds left before a locked session auto-signs-out (0 when expired,
    None when not locked)."""
    age = lock_age(session, now)
    if age is None:
        return None
    remaining = get_zt_timers()["lock_auto_signout"] - age
    return max(0, int(remaining.total_seconds()))


def revoke_session(session) -> None:
    """Kill an access session entirely (lock flag included - a revoked
    session is dead, not locked). Mirrors the revoke pattern in auth_views."""
    policy = _policy(session)
    policy["zt_locked"] = False
    policy["zt_lock_reason"] = ""
    session.session_policy = policy
    session.session_status = "Revoked"
    session.revoked_at = timezone.now()
    session.expires_at = timezone.now()
    session.save(update_fields=["session_policy", "session_status", "revoked_at", "expires_at"])


def unlock_requirements(session, officer) -> dict:
    """What does this locked session need to unlock?

    Password is the normal path; OTP escalates when the lock lasted long
    enough that the officer may have left the building, the ZT level is
    elevated, unlock attempts already failed, or the role handles money.
    """
    timers = get_zt_timers()
    policy = _policy(session)
    locked_at = _parse_iso(policy.get("zt_locked_at"))
    level, _ = current_level(session)
    reasons = []
    otp_required = False

    if (officer.role or "").strip().lower() in timers["always_verify_roles"]:
        otp_required = True
        reasons.append("role policy")
    if locked_at is not None and (timezone.now() - locked_at) >= timers["lock_otp_after"]:
        otp_required = True
        reasons.append(f"locked for {int((timezone.now() - locked_at).total_seconds() // 60)} minutes")
    if LEVEL_ORDER.get(level, 0) >= LEVEL_ORDER["medium"]:
        otp_required = True
        reasons.append("session risk level elevated")
    if (policy.get("zt_unlock_failures") or 0) >= timers["unlock_otp_after_failures"]:
        otp_required = True
        reasons.append("multiple failed attempts")

    return {
        "otp_required": otp_required,
        "reasons": reasons,
        "failures": policy.get("zt_unlock_failures", 0),
    }


def record_unlock_failure(session) -> int:
    policy = _policy(session)
    failures = (policy.get("zt_unlock_failures") or 0) + 1
    policy["zt_unlock_failures"] = failures
    policy["zt_last_unlock_failure_at"] = timezone.now().isoformat()
    session.session_policy = policy
    session.save(update_fields=["session_policy"])
    return failures


def clear_lock(session, request, method: str) -> None:
    """Successful unlock: lift the lock, restart the heartbeat window, and if
    the session was ALSO hard-challenged, the just-proven OTP clears that too
    (one code, both doors) - except for password unlocks, where a sticky hard
    check stays (a password proves less than an OTP)."""
    policy = _policy(session)
    was_netlock = (policy.get("zt_lock_reason") or "") == NETWORK_LOCK_REASON
    policy["zt_locked"] = False
    policy["zt_unlocked_at"] = timezone.now().isoformat()
    policy["zt_lock_reason"] = ""
    policy["zt_unlock_failures"] = 0
    policy["zt_last_heartbeat"] = timezone.now().isoformat()
    if was_netlock:
        # The officer just proved identity on the NEW network: adopt it as
        # the baseline or the next request would lock the screen again.
        try:
            ip_now = (get_client_ip(request) if request else None) or "0.0.0.0"
        except Exception:
            ip_now = "0.0.0.0"
        policy["zt_ip_baseline"] = ip_network_key(ip_now)
        policy.pop("zt_net_candidate", None)
        policy.pop("zt_netlock_details", None)
    session.session_policy = policy
    session.save(update_fields=["session_policy"])

    if method == "otp":
        level, _ = current_level(session)
        if level == "hard":
            clear_hard_check(session, request)


def lock_heartbeat(session) -> bool:
    """Page heartbeat while unlocked. Returns False if the session is locked
    (the caller treats that as the page needing to re-engage the overlay)."""
    policy = _policy(session)
    if policy.get("zt_locked"):
        return False
    policy["zt_last_heartbeat"] = timezone.now().isoformat()
    session.session_policy = policy
    session.save(update_fields=["session_policy"])
    return True


def heartbeat_lost(session, now) -> bool:
    """True when requests are still flowing but the page heartbeat has gone
    quiet - the signature of a tab where the lock UI was stripped or JS died.
    Never judges sessions that never had a heartbeat (no JS yet)."""
    timers = get_zt_timers()
    policy = _policy(session)
    if policy.get("zt_locked"):
        return False
    hb = _parse_iso(policy.get("zt_last_heartbeat"))
    if hb is None:
        return False
    last_active = session.last_activity_at
    if last_active is None or (now - last_active) > timedelta(minutes=2):
        return False  # no traffic either - just idle; the page locks itself
    return (now - hb) >= timers["heartbeat_stale"]


# ---------------------------------------------------------------------------
# Session Integrity Token (kept - used by zero_trust_confirm)
# ---------------------------------------------------------------------------

def generate_sit(session_id: str, action: str, action_id: str, timestamp: str) -> str:
    """Generate a Session Integrity Token (SIT) for a specific action.

    The SIT is a cryptographic signature binding the action to the current session,
    preventing replay attacks and ensuring per-action confirmation.
    """
    payload = f"{session_id}:{action}:{action_id}:{timestamp}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_sit(sit: str, session_id: str, action: str, action_id: str, timestamp: str) -> bool:
    """Verify a Session Integrity Token (SIT).

    Uses constant-time comparison to prevent timing attacks.
    """
    expected = generate_sit(session_id, action, action_id, timestamp)
    return hmac.compare_digest(expected, sit)


def get_session_fingerprint(request, session) -> dict:
    """Extract session fingerprint information for display in the confirmation modal.

    This allows officers to visually verify they are on their own session by checking
    IP address, device, and session duration.
    """
    return {
        "ip": get_client_ip(request),
        "device": request.META.get("HTTP_USER_AGENT", "Unknown")[:255],
        "logged_in_since": session.issued_at.isoformat(),
        "session_id": session.token_id[:12] + "...",
        "trusted_device": session.trusted_device,
    }


def build_action_descriptor(action: str, record_id, details: dict = None) -> str:
    """Build a human-readable action descriptor for the confirmation modal.

    Example: "Approve Disbursement #7291 — Amount: ₱45,000.00 · Payee: Juan Dela Cruz"
    """
    desc = action.replace("_", " ").title()
    if details:
        extras = " · ".join(f"{k}: {v}" for k, v in details.items())
        return f"{desc} #{record_id} — {extras}"
    return f"{desc} #{record_id}"
