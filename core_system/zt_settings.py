"""Superadmin-editable Zero Trust & lockout timers.

Backing store is the existing SystemSetting key-value table; values are
cached for a few seconds because the middleware reads them on every request.
All defaults live here so zt_service, the middleware, and the admin panel
share one source of truth.
"""

from datetime import timedelta

from django.core.cache import cache

from core_system.models import OfficerUser, SystemSetting

CACHE_KEY = "zt_timers_v1"
CACHE_TTL = 15  # seconds - keeps per-request reads cheap without feeling stale

# (field, default, label, kind, min, max, help)
# kind: "minutes" -> edited in minutes, used as timedelta
#       "seconds" -> edited in seconds, used as int seconds
#       "count"   -> plain integer threshold
_TIMER_FIELDS = [
    ("zt_lock_idle_minutes", 2, "Lock screen after idle", "minutes", 1, 30,
     "How long an officer can be inactive before the dashboard locks itself."),
    ("zt_lock_heartbeat_stale_minutes", 5, "Heartbeat stale auto-lock", "minutes", 2, 30,
     "If requests keep flowing but the page heartbeat is silent this long, the session is locked server-side."),
    ("zt_lock_otp_after_minutes", 10, "OTP required after locked for", "minutes", 1, 120,
     "A lock longer than this escalates the unlock from password to email OTP. "
     "Only applies when shorter than the auto sign-out below."),
    ("zt_lock_auto_signout_minutes", 5, "Auto sign-out after locked for", "minutes", 1, 120,
     "A locked screen that is not unlocked within this time is signed out entirely."),
    ("zt_unlock_max_failures", 5, "Unlock attempts before revoking session", "count", 3, 10,
     "Total failed unlock attempts (password + OTP combined) that revoke the session."),
    ("zt_unlock_otp_after_failures", 2, "Failed attempts before OTP required", "count", 1, 4,
     "Wrong unlock attempts after which even the correct password no longer unlocks."),
    ("zt_idle_soft_minutes", 5, "Soft check after idle", "minutes", 1, 25,
     "Quiet background recheck once the officer resumes after this idle time."),
    ("zt_idle_medium_minutes", 15, "Medium check after idle", "minutes", 2, 29,
     "Visible security notice once the officer resumes after this idle time."),
    ("zt_sec_window_minutes", 15, "Suspicious-activity window", "minutes", 5, 60,
     "Sliding window in which security events are counted."),
    ("zt_sec_medium", 3, "Events for medium check", "count", 2, 20,
     "Security events in the window that trigger a visible notice."),
    ("zt_sec_hard", 6, "Events for hard check", "count", 3, 30,
     "Security events in the window that force email OTP verification."),
    ("zt_challenge_cooldown_seconds", 60, "OTP email cooldown", "seconds", 30, 600,
     "Minimum seconds between two Zero Trust OTP emails."),
    ("zt_session_idle_timeout_minutes", 30, "Hard logout after idle", "minutes", 10, 240,
     "Sessions are killed entirely after this much inactivity (existing behavior, now adjustable)."),
]

ROLES_FIELD = "zt_lock_always_verify_roles"
# Empty by default: NO role is forced through email OTP on every unlock.
# OTP still escalates by lock age (lock_otp_after), elevated risk level, and
# failed attempts. A superadmin can opt roles back in from the panel.
ROLES_DEFAULT = ""
ROLES_LABEL = "Roles that always unlock with OTP"
ROLES_HELP = "Comma-separated officer roles (lowercase) that must verify an email OTP on every unlock. Leave empty for no role-based OTP (lock age, risk level, and failed attempts can still escalate to OTP)."

DEFAULT_TIMERS = {
    "lock_idle": timedelta(minutes=2),
    "heartbeat_stale": timedelta(minutes=5),
    "lock_otp_after": timedelta(minutes=10),
    "lock_auto_signout": timedelta(minutes=5),
    "unlock_max_failures": 5,
    "unlock_otp_after_failures": 2,
    "idle_soft": timedelta(minutes=5),
    "idle_medium": timedelta(minutes=15),
    "sec_window": timedelta(minutes=15),
    "sec_medium": 3,
    "sec_hard": 6,
    "challenge_cooldown": 60,
    "session_idle_timeout": timedelta(minutes=30),
    "always_verify_roles": set(),
}

# Backward-compatible aliases used by zt_service (and older references)
ZT_IDLE_SOFT = DEFAULT_TIMERS["idle_soft"]
ZT_IDLE_MEDIUM = DEFAULT_TIMERS["idle_medium"]
ZT_SEC_WINDOW = DEFAULT_TIMERS["sec_window"]
ZT_SEC_MEDIUM = DEFAULT_TIMERS["sec_medium"]
ZT_SEC_HARD = DEFAULT_TIMERS["sec_hard"]
ZT_CHALLENGE_COOLDOWN = DEFAULT_TIMERS["challenge_cooldown"]
ZT_LOCK_IDLE = DEFAULT_TIMERS["lock_idle"]
ZT_LOCK_HEARTBEAT_STALE = DEFAULT_TIMERS["heartbeat_stale"]
ZT_LOCK_OTP_AFTER = DEFAULT_TIMERS["lock_otp_after"]
ZT_LOCK_AUTO_SIGNOUT = DEFAULT_TIMERS["lock_auto_signout"]
ZT_UNLOCK_MAX_FAILURES = DEFAULT_TIMERS["unlock_max_failures"]
ZT_UNLOCK_OTP_AFTER_FAILURES = DEFAULT_TIMERS["unlock_otp_after_failures"]
ZT_ALWAYS_VERIFY_ROLES = DEFAULT_TIMERS["always_verify_roles"]


def timer_fields() -> list:
    """Field descriptors for the admin panel."""
    return [
        {"key": f, "default": d, "label": label, "kind": kind, "min": lo, "max": hi, "help": help_}
        for f, d, label, kind, lo, hi, help_ in _TIMER_FIELDS
    ]


def _clean_db_value(raw, default) -> int:
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def _parse_roles(raw) -> set:
    roles = set()
    for part in str(raw or "").replace(";", ",").split(","):
        part = part.strip().lower()
        if part:
            roles.add(part)
    # An explicitly saved empty value means "no role forced" - do NOT fall
    # back to defaults here; get_zt_timers() already applies DEFAULT_TIMERS
    # when no row is stored at all.
    return roles


def get_zt_timers() -> dict:
    """Current timer values (defaults overlaid with saved overrides).

    Cached briefly - the middleware reads this on every request.
    """
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    rows = {
        row.setting_key: row.setting_value
        for row in SystemSetting.objects.filter(setting_key__startswith="zt_")
    }
    timers = dict(DEFAULT_TIMERS)
    for field, _default, _label, kind, _lo, _hi, _help in _TIMER_FIELDS:
        if field not in rows:
            continue
        raw = _clean_db_value(rows[field], None)
        if raw is None:
            continue  # unparseable stored value: keep the default
        key = _FIELD_TO_TIMER[field]
        timers[key] = timedelta(minutes=raw) if kind == "minutes" else raw
    if ROLES_FIELD in rows:
        timers["always_verify_roles"] = _parse_roles(rows[ROLES_FIELD])

    cache.set(CACHE_KEY, timers, CACHE_TTL)
    return timers


_FIELD_TO_TIMER = {
    "zt_lock_idle_minutes": "lock_idle",
    "zt_lock_heartbeat_stale_minutes": "heartbeat_stale",
    "zt_lock_otp_after_minutes": "lock_otp_after",
    "zt_lock_auto_signout_minutes": "lock_auto_signout",
    "zt_unlock_max_failures": "unlock_max_failures",
    "zt_unlock_otp_after_failures": "unlock_otp_after_failures",
    "zt_idle_soft_minutes": "idle_soft",
    "zt_idle_medium_minutes": "idle_medium",
    "zt_sec_window_minutes": "sec_window",
    "zt_sec_medium": "sec_medium",
    "zt_sec_hard": "sec_hard",
    "zt_challenge_cooldown_seconds": "challenge_cooldown",
    "zt_session_idle_timeout_minutes": "session_idle_timeout",
}


def validate_timer_values(posted: dict) -> tuple:
    """Validate a full set of posted timer values.

    Returns (clean: dict[field->str], errors: [str]). Values are strings in
    the field's own unit, ready for SystemSetting rows.
    """
    clean = {}
    errors = []
    values = {}

    for field, _default, label, kind, lo, hi, _help in _TIMER_FIELDS:
        raw = str(posted.get(field, "") or "").strip()
        if raw == "":
            clean[field] = str(_default)
            values[field] = _default
            continue
        try:
            num = int(float(raw))
        except ValueError:
            errors.append(f"{label}: must be a whole number.")
            continue
        if num < lo or num > hi:
            errors.append(f"{label}: must be between {lo} and {hi} {kind}.")
            continue
        clean[field] = str(num)
        values[field] = num

    roles_raw = str(posted.get(ROLES_FIELD, "") or "").strip().lower()
    clean[ROLES_FIELD] = roles_raw if roles_raw else ROLES_DEFAULT

    # Relationship checks (only when the involved fields parsed cleanly)
    if "zt_idle_soft_minutes" in values and "zt_idle_medium_minutes" in values:
        if values["zt_idle_soft_minutes"] >= values["zt_idle_medium_minutes"]:
            errors.append("Soft check idle time must be shorter than medium check idle time.")
    if "zt_idle_medium_minutes" in values and "zt_session_idle_timeout_minutes" in values:
        if values["zt_idle_medium_minutes"] >= values["zt_session_idle_timeout_minutes"]:
            errors.append("Medium check idle time must be shorter than the hard logout idle time.")
    if "zt_unlock_otp_after_failures" in values and "zt_unlock_max_failures" in values:
        if values["zt_unlock_otp_after_failures"] >= values["zt_unlock_max_failures"]:
            errors.append("OTP-after-failures must be smaller than the revoke threshold.")
    if "zt_sec_medium" in values and "zt_sec_hard" in values:
        if values["zt_sec_medium"] >= values["zt_sec_hard"]:
            errors.append("Medium event threshold must be smaller than the hard event threshold.")

    return clean, errors


def save_zt_timers(clean: dict, updated_by: OfficerUser | None = None) -> None:
    """Persist validated timer values and bust the read cache."""
    for field, value in clean.items():
        SystemSetting.objects.update_or_create(
            setting_key=field,
            defaults={
                "setting_value": value,
                "updated_by_id_FK_id": getattr(updated_by, "pk", None),
            },
        )
    cache.delete(CACHE_KEY)
