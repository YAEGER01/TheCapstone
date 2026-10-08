# =========================================================================
# MIGRATION STATUS — All views moved to dedicated files:
#   - President views   → president_views.py
#   - Treasurer views   → treasurer_views.py
#   - Auditor views     → auditor_views.py
# This file now only re-exports logout_view + shared fund ledger views.
# =========================================================================
from __future__ import annotations

from __future__ import annotations

import secrets
from datetime import date, datetime, time as dtime, timedelta
from typing import Any

from django.conf import settings
from django.db.models import Q, Sum, Prefetch
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import ensure_csrf_cookie

from django.shortcuts import render
from core_system.auth_utils import hash_password
from core_system.auth_views import _workspace_redirect
from core_system.constants.policy_constants import get_membership_fee_amount, get_monthly_dues_amount, is_retired_member
from core_system.constants.status_constants import Status
from core_system.guards import require_officer_session, require_role
from core_system.ledger_utils import member_deduction_overview, member_unpaid_months
from core_system.models import (
    Claimant,
    Contribution,
    DeathAid,
    FundTransaction,
    MedicalAid,
    Member,
    MembershipFee,
    MonthlyDues,
    Notification,
    OfficerUser,
    PayrollBatch,
    PayrollDeduction,
    SystemSetting,
)
from core_system.logout_view import logout_view

MEMBERSHIP_FEE_SUBMITTED_STATUSES = {"Paid", "Full Payment", "Partial", "Pending"}

logout_view = logout_view


def _ensure_default_superadmin_accounts():
    # Bootstrap ONLY: create the canonical accounts when missing. Existing
    # rows are NEVER touched here — the old code reset every Superadmin's
    # username/password to hardcoded defaults on each dashboard load, which
    # reverted password changes and kept unsalted SHA-256 hashes alive.
    from core_system.auth_utils import hash_password

    superadmin_defaults = {
        "full_name": "Superadmin Admin Von",
        "username": "systemadmin",
        "password_hash": hash_password(secrets.token_urlsafe(24)),
        "role": "Superadmin",
        "account_status": "Active",
        "mfa_enabled": False,
        "mfa_secret": None,
        "email": "fredcantcorner@gmail.com",
        "must_change_password": True,
    }

    president_defaults = {
        "full_name": "President Account",
        "password_hash": hash_password(secrets.token_urlsafe(24)),
        "role": "President",
        "account_status": "Active",
        "mfa_enabled": False,
        "mfa_secret": None,
        "email": "president@caufa.local",
        "must_change_password": True,
    }

    system_backfill_defaults = {
        "full_name": "System Backfill",
        "password_hash": hash_password(secrets.token_urlsafe(24)),
        "role": "System",
        "account_status": "Inactive",
        "mfa_enabled": False,
        "mfa_secret": None,
        "email": "",
        "must_change_password": True,
    }

    def _resolve(role, username, defaults):
        # Prefer the canonical username account.
        account = OfficerUser.objects.filter(username=username).first()
        if account is not None:
            return account
        # Fall back to any existing account of the same role so that renaming
        # an account's username never spawns a duplicate default on the next load.
        account = OfficerUser.objects.filter(role__iexact=role).order_by("user_id_PK").first()
        if account is not None:
            return account
        return OfficerUser.objects.create(**defaults)

    superadmin = _resolve("Superadmin", "systemadmin", superadmin_defaults)
    president = _resolve("President", "president", president_defaults)
    system_backfill = _resolve("System", "system_backfill", system_backfill_defaults)

    return superadmin, president, system_backfill


ZT_LOCK_FIELD_KEYS = {
    "zt_lock_idle_minutes",
    "zt_lock_heartbeat_stale_minutes",
    "zt_lock_otp_after_minutes",
    "zt_lock_auto_signout_minutes",
    "zt_unlock_max_failures",
    "zt_unlock_otp_after_failures",
}
ZT_SESSION_FIELD_KEYS = {"zt_session_idle_timeout_minutes"}


def _zt_timer_panel_context() -> dict:
    """Describe the ZT/lockout timer fields for the admin panel, with their
    current saved values (or defaults)."""
    from core_system import zt_settings

    rows = {
        row.setting_key: row.setting_value
        for row in SystemSetting.objects.filter(setting_key__startswith="zt_")
    }

    def _current(field, default):
        raw = rows.get(field)
        if raw is None:
            return default
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default

    lock_fields, check_fields, session_fields = [], [], []
    for f in zt_settings.timer_fields():
        unit = {"minutes": "minutes", "seconds": "seconds", "count": "attempts"}[f["kind"]]
        item = {
            "key": f["key"],
            "label": f["label"],
            "value": _current(f["key"], f["default"]),
            "min": f["min"],
            "max": f["max"],
            "unit": unit,
            "help": f["help"],
        }
        if f["key"] in ZT_LOCK_FIELD_KEYS:
            lock_fields.append(item)
        elif f["key"] in ZT_SESSION_FIELD_KEYS:
            session_fields.append(item)
        else:
            check_fields.append(item)

    roles_value = rows.get(zt_settings.ROLES_FIELD, zt_settings.ROLES_DEFAULT)
    zt_is_default = all(
        _current(f["key"], f["default"]) == f["default"]
        for f in zt_settings.timer_fields()
    ) and (roles_value or "").strip() == (zt_settings.ROLES_DEFAULT or "").strip()

    return {
        "zt_lock_fields": lock_fields,
        "zt_check_fields": check_fields,
        "zt_session_fields": session_fields,
        "zt_roles_field": {
            "key": zt_settings.ROLES_FIELD,
            "label": zt_settings.ROLES_LABEL,
            "value": roles_value,
            "help": zt_settings.ROLES_HELP,
        },
        "zt_is_default": zt_is_default,
    }


def _sa_float_or_zero(raw) -> float:
    try:
        return float(str(raw or "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _build_superadmin_dashboard_context(superadmin: OfficerUser, president: OfficerUser, system_backfill: OfficerUser, form_feedback: dict | None = None, threshold_feedback: dict | None = None):
    # Get safety threshold settings
    safety_threshold = SystemSetting.objects.filter(setting_key="safety_threshold_amount").first()
    safety_threshold_enabled = SystemSetting.objects.filter(setting_key="safety_threshold_enabled").first()
    banner_duration = SystemSetting.objects.filter(setting_key="banner_duration_seconds").first()

    from core_system.nav_modules import get_nav_modules
    from core_system.landing_sections import get_landing_sections, landing_admin_cards
    from core_system.isu_email_guard import is_isu_email_guard_enabled, is_membership_duplicate_email_allowed
    from core_system.dues_backfill_guard import is_back_dues_chase_enabled
    from core_system.email_killswitch import is_email_sending_enabled
    from core_system.otp_killswitch import is_login_otp_enabled
    from core_system.unpaid_months_guard import is_show_unpaid_months_enabled
    from core_system.other_campus_guard import is_other_campus_enabled
    nav_flags = get_nav_modules()
    landing_flags = get_landing_sections()
    isu_email_guard_enabled = is_isu_email_guard_enabled()
    membership_allow_duplicate_email = is_membership_duplicate_email_allowed()
    dues_require_back_dues_on_join = is_back_dues_chase_enabled()
    email_sending_enabled = is_email_sending_enabled()
    login_otp_enabled = is_login_otp_enabled()
    show_unpaid_months = is_show_unpaid_months_enabled()
    show_other_campus = is_other_campus_enabled()
    try:
        from core_system.email_killswitch import get_last_stop_info, get_queue_counts

        _email_queue = get_queue_counts()
        _email_last_stop = get_last_stop_info()
    except Exception:
        _email_queue = {"pending": 0, "sending": 0}
        _email_last_stop = {"at": "", "cancelled": "0"}
    zt_timers = _zt_timer_panel_context()

    def _account_payload(account: OfficerUser):
        return {
            "full_name": account.full_name,
            "username": account.username,
            "role": account.role,
            "status": account.account_status,
            "email": account.email or "",
        }

    return {
        "superadmin_account": _account_payload(superadmin),
        "president_account": _account_payload(president),
        "system_backfill_account": _account_payload(system_backfill),
        "superadmin_id": superadmin.pk,
        "president_id": president.pk,
        "system_backfill_id": system_backfill.pk,
        "president_exists": president.pk is not None,
        "president_dashboard_url": "/president/",
        "form_feedback": form_feedback,
        "threshold_feedback": threshold_feedback,
        "safety_threshold": safety_threshold.setting_value if safety_threshold else "0.00",
        "safety_threshold_enabled": safety_threshold_enabled.setting_value if safety_threshold_enabled else "false",
        "banner_duration_seconds": banner_duration.setting_value if banner_duration else "6",
        "nav_sidebar_enabled": nav_flags["sidebar"],
        "nav_header_strip_enabled": nav_flags["header_strip"],
        "landing_admin_cards": landing_admin_cards(),
        "landing_is_default": all(landing_flags.values()),
        "isu_email_guard_enabled": isu_email_guard_enabled,
        "membership_allow_duplicate_email": membership_allow_duplicate_email,
        "dues_require_back_dues_on_join": dues_require_back_dues_on_join,
        "login_otp_enabled": login_otp_enabled,
        "login_otp_is_default": login_otp_enabled,
        "show_unpaid_months": show_unpaid_months,
        "show_unpaid_months_is_default": show_unpaid_months,
        "show_other_campus": show_other_campus,
        "show_other_campus_is_default": show_other_campus,
        "email_sending_enabled": email_sending_enabled,
        "email_is_default": email_sending_enabled,
        "email_queue_pending": _email_queue["pending"],
        "email_queue_sending": _email_queue["sending"],
        "email_last_stop_at": _email_last_stop["at"],
        "email_last_stop_cancelled": _email_last_stop["cancelled"],
        "nav_is_default": bool(nav_flags["sidebar"] and nav_flags["header_strip"]),
        "threshold_is_default": (
            _sa_float_or_zero(safety_threshold.setting_value if safety_threshold else None) == 0
            and (safety_threshold_enabled.setting_value if safety_threshold_enabled else "false") != "true"
        ),
        "banner_is_default": (banner_duration.setting_value if banner_duration else "6") == "6",
        **zt_timers,
    }


def _handle_superadmin_account_form(request: HttpRequest, account: OfficerUser, label: str) -> tuple[OfficerUser, dict]:
    full_name = request.POST.get("account_full_name", "").strip()
    username = request.POST.get("account_username", "").strip()
    password = request.POST.get("account_password", "").strip()
    email = request.POST.get("account_email", "").strip()
    account_status = request.POST.get("account_status", "Active").strip() or "Active"

    feedback = {"ok": False, "message": "", "level": "error"}

    if not full_name:
        feedback["message"] = f"{label} full name is required."
        return account, feedback
    if not username:
        feedback["message"] = f"{label} username is required."
        return account, feedback

    existing_username = OfficerUser.objects.filter(username=username).exclude(pk=account.pk).first()
    if existing_username is not None:
        feedback["message"] = "That username is already taken. Choose a different one."
        return account, feedback

    update_fields = ["full_name", "username", "email", "account_status", "updated_at"]

    account.full_name = full_name
    account.username = username
    account.email = email or None
    account.account_status = account_status
    account.updated_at = timezone.now()
    if password:
        account.password_hash = hash_password(password)
        update_fields.append("password_hash")

    account.save(update_fields=update_fields)

    feedback["ok"] = True
    feedback["message"] = f"{label} account has been saved successfully."
    feedback["level"] = "success"
    return account, feedback


def _handle_superadmin_safety_threshold_form(request: HttpRequest) -> dict:
    form_type = request.POST.get("form_type", "").strip()
    threshold_amount = request.POST.get("safety_threshold_amount", "0").strip()
    threshold_enabled = request.POST.get("safety_threshold_enabled", "false").strip()

    feedback = {"ok": False, "message": "", "level": "error"}

    if form_type != "safety_threshold":
        feedback["message"] = "Invalid form type."
        return feedback

    try:
        threshold_float = float(threshold_amount)
        if threshold_float < 0:
            feedback["message"] = "Safety threshold amount must be non-negative."
            return feedback
    except ValueError:
        feedback["message"] = "Invalid safety threshold amount."
        return feedback

    # Update or create safety threshold setting
    SystemSetting.objects.update_or_create(
        setting_key="safety_threshold_amount",
        defaults={"setting_value": str(threshold_float)}
    )
    SystemSetting.objects.update_or_create(
        setting_key="safety_threshold_enabled",
        defaults={"setting_value": threshold_enabled}
    )

    feedback["ok"] = True
    feedback["message"] = "Safety threshold settings have been saved successfully."
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_banner_settings_form(request: HttpRequest) -> dict:
    from core_system.settings_views import (
        BANNER_DURATION_DEFAULT,
        BANNER_DURATION_MAX,
        BANNER_DURATION_MIN,
    )

    form_type = request.POST.get("form_type", "").strip()
    raw_value = request.POST.get("banner_duration_seconds", "").strip()

    feedback = {"ok": False, "message": "", "level": "error"}

    if form_type != "banner_settings":
        feedback["message"] = "Invalid form type."
        return feedback

    try:
        seconds = int(raw_value)
        if seconds < BANNER_DURATION_MIN or seconds > BANNER_DURATION_MAX:
            feedback["message"] = (
                f"Banner display time must be between {BANNER_DURATION_MIN} "
                f"and {BANNER_DURATION_MAX} seconds."
            )
            return feedback
    except (TypeError, ValueError):
        feedback["message"] = "Enter a valid banner display time in seconds."
        return feedback

    SystemSetting.objects.update_or_create(
        setting_key="banner_duration_seconds",
        defaults={"setting_value": str(seconds)},
    )

    feedback["ok"] = True
    feedback["message"] = (
        f"Notification banner display time set to {seconds} seconds "
        f"(default {BANNER_DURATION_DEFAULT})."
    )
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_toggle_account_status(request: HttpRequest, account: OfficerUser, label: str) -> tuple[OfficerUser, dict]:
    feedback = {"ok": False, "message": "", "level": "error"}

    new_status = "Inactive" if (account.account_status or "").lower() == "active" else "Active"
    account.account_status = new_status
    account.updated_at = timezone.now()
    account.save(update_fields=["account_status", "updated_at"])

    feedback["ok"] = True
    feedback["message"] = f"{label} account has been {new_status.lower()}d successfully."
    feedback["level"] = "success"
    return account, feedback


def _handle_superadmin_nav_modules_form(request: HttpRequest) -> dict:
    from core_system.nav_modules import set_nav_modules

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "nav_modules":
        feedback["message"] = "Invalid form type."
        return feedback

    sidebar = request.POST.get("nav_sidebar") == "on"
    header_strip = request.POST.get("nav_header_strip") == "on"
    if not sidebar and not header_strip:
        feedback["message"] = "Keep at least one navigation visible (Sidebar or Header Strip)."
        return feedback

    set_nav_modules(sidebar=sidebar, header_strip=header_strip)
    feedback["ok"] = True
    feedback["message"] = "Navigation module visibility has been saved."
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_zt_timers_form(request: HttpRequest, updated_by: OfficerUser) -> dict:
    from core_system import zt_settings
    from core_system.shared_view_utils import _record_audit_trail

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "zt_timers":
        feedback["message"] = "Invalid form type."
        return feedback

    clean, errors = zt_settings.validate_timer_values(request.POST)
    if errors:
        feedback["message"] = " ".join(errors)
        return feedback

    stored = {
        row.setting_key: (row.setting_value or "").strip()
        for row in SystemSetting.objects.filter(setting_key__in=list(clean.keys()))
    }
    changed = [
        field for field, value in clean.items()
        if stored.get(field) != str(value)
    ]
    zt_settings.save_zt_timers(clean, updated_by=updated_by)

    _record_audit_trail(
        table="system_setting",
        record_id=0,
        action="ZT_TIMERS_UPDATED",
        actor=updated_by,
        old=None,
        new=clean,
        ip=request.META.get("REMOTE_ADDR"),
        device_info=request.META.get("HTTP_USER_AGENT"),
        notes="Zero Trust / lockout timers updated" + (f": {', '.join(changed)}" if changed else ""),
    )

    feedback["ok"] = True
    feedback["message"] = "Zero Trust & lockout timers saved. New values apply within a few seconds."
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_isu_email_guard_form(request: HttpRequest) -> dict:
    from core_system.isu_email_guard import set_isu_email_guard_enabled

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "isu_email_guard":
        feedback["message"] = "Invalid form type."
        return feedback

    enabled = request.POST.get("isu_email_guard") == "on"
    set_isu_email_guard_enabled(enabled)
    feedback["ok"] = True
    feedback["message"] = (
        "ISU email guard is now enabled (membership emails must be @isu.edu.ph)."
        if enabled
        else "ISU email guard is now disabled (any valid email is accepted for members)."
    )
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_duplicate_email_form(request: HttpRequest) -> dict:
    from core_system.isu_email_guard import set_membership_duplicate_email_allowed

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "membership_duplicate_email":
        feedback["message"] = "Invalid form type."
        return feedback

    enabled = request.POST.get("membership_duplicate_email") == "on"
    set_membership_duplicate_email_allowed(enabled)
    feedback["ok"] = True
    feedback["message"] = (
        "Duplicate member emails are now allowed during enrollment."
        if enabled
        else "Duplicate member emails are now rejected during enrollment."
    )
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_back_dues_chase_form(request: HttpRequest) -> dict:
    from core_system.dues_backfill_guard import set_back_dues_chase_enabled

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "dues_back_dues_chase":
        feedback["message"] = "Invalid form type."
        return feedback

    enabled = request.POST.get("dues_require_back_dues_on_join") == "on"
    set_back_dues_chase_enabled(enabled)
    feedback["ok"] = True
    feedback["message"] = (
        "Back-dues chase is now ON: mid-year joiners will be asked for Jan-to-join-month dues."
        if enabled
        else "Back-dues chase is now OFF: mid-year joiners pay current and future dues only."
    )
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_email_stop_form(request: HttpRequest) -> dict:
    """Momentary STOP: block all SMTP, wipe the queue, auto-turn back ON.

    Separate form (not part of Update All) with its own confirm dialog.
    """
    from core_system.email_killswitch import momentary_email_stop
    from core_system.shared_view_utils import _record_audit_trail

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "email_stop_now":
        feedback["message"] = "Invalid form type."
        return feedback

    result = momentary_email_stop()

    try:
        officer = OfficerUser.objects.filter(username="systemadmin").first()
        _record_audit_trail(
            table="system_setting",
            record_id=0,
            action="EMAIL_STOP",
            actor=officer,
            old=None,
            new={"cancelled": result["cancelled"]},
            ip=request.META.get("REMOTE_ADDR"),
            device_info=request.META.get("HTTP_USER_AGENT"),
            notes=f"Momentary email STOP: {result['cancelled']} queued row(s) wiped, email auto re-enabled",
        )
    except Exception:
        pass

    feedback["ok"] = True
    feedback["level"] = "success"
    feedback["message"] = (
        f"STOPPED — {result['cancelled']} queued email(s) wiped and all sending blocked. "
        "Email is back ON fresh: nothing pending, nothing stuck, nothing will resume. "
        "In-app notices and Web Push were never affected."
    )
    return feedback


def _handle_superadmin_email_kill_switch_form(request: HttpRequest) -> dict:
    """Master kill switch for ALL outbound SMTP (Superadmin only)."""
    from core_system.email_killswitch import set_email_sending_enabled

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "email_kill_switch":
        feedback["message"] = "Invalid form type."
        return feedback

    enabled = request.POST.get("email_sending_enabled") == "on"
    set_email_sending_enabled(enabled)
    if enabled:
        feedback["ok"] = True
        feedback["message"] = (
            "Outgoing email is now ON: queued PENDING mail will drain normally. "
            "In-app notifications and Web Push were never affected."
        )
    else:
        feedback["ok"] = True
        feedback["message"] = (
            "Outgoing email is now OFF: every SMTP path (deduction notices, reminders, "
            "announcements, OTP codes, certificates, fund reports) is blocked and the "
            "queue is frozen. PENDING rows are kept so they resume when you switch back ON. "
            "In-app dashboard notices and Web Push still work."
        )
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_login_otp_form(request: HttpRequest) -> dict:
    """Global login-OTP switch (Superadmin only): OFF skips the email code step."""
    from core_system.otp_killswitch import set_login_otp_enabled

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "login_otp_switch":
        feedback["message"] = "Invalid form type."
        return feedback

    enabled = request.POST.get("login_otp_enabled") == "on"
    set_login_otp_enabled(enabled)
    if enabled:
        feedback["ok"] = True
        feedback["message"] = (
            "Login OTP is now ON: every role signs in with password + email "
            "verification code, as before."
        )
    else:
        feedback["ok"] = True
        feedback["message"] = (
            "Login OTP is now OFF: every role signs in with password only — "
            "no verification code is queued or asked for. Turn it back ON to "
            "restore the email code step."
        )
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_unpaid_months_form(request: HttpRequest) -> dict:
    """Unpaid month list switch (Superadmin only): OFF hides the month cards."""
    from core_system.unpaid_months_guard import set_show_unpaid_months_enabled

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "show_unpaid_months":
        feedback["message"] = "Invalid form type."
        return feedback

    enabled = request.POST.get("show_unpaid_months") == "on"
    set_show_unpaid_months_enabled(enabled)
    if enabled:
        feedback["ok"] = True
        feedback["message"] = (
            "Unpaid month list is now SHOWN: the Record Monthly Dues popup "
            "shows the month checkbox cards alongside the Amount to pay input."
        )
    else:
        feedback["ok"] = True
        feedback["message"] = (
            "Unpaid month list is now HIDDEN: the Record Monthly Dues popup "
            "shows only the Amount to pay input — typing an amount still "
            "settles the oldest months automatically."
        )
    feedback["level"] = "success"
    return feedback


def _handle_superadmin_other_campus_form(request: HttpRequest) -> dict:
    """Other Campus option switch (Superadmin only): OFF hides the picker option."""
    from core_system.other_campus_guard import set_other_campus_enabled

    form_type = request.POST.get("form_type", "").strip()
    feedback = {"ok": False, "message": "", "level": "error"}
    if form_type != "show_other_campus":
        feedback["message"] = "Invalid form type."
        return feedback

    enabled = request.POST.get("show_other_campus") == "on"
    set_other_campus_enabled(enabled)
    if enabled:
        feedback["ok"] = True
        feedback["message"] = (
            "Other Campus option is now SHOWN: the President monthly deduction "
            "recipient picker offers Other Campus (external beneficiary) again."
        )
    else:
        feedback["ok"] = True
        feedback["message"] = (
            "Other Campus option is now HIDDEN: the President monthly deduction "
            "recipient picker no longer offers Other Campus — saved external "
            "rows stay visible as history but no new ones can be declared."
        )
    feedback["level"] = "success"
    return feedback


# Groups for the consolidated System Settings view: card -> SystemSetting keys.
# Reset deletes these rows so every getter falls back to its code default.
SA_RESET_GROUPS: dict[str, dict] = {
    "navigation": {
        "label": "Navigation Modules",
        "keys": ["nav_sidebar_enabled", "nav_header_strip_enabled"],
    },
    "landing_page": {
        "label": "Landing Page Sections",
        "keys": [
            "landing_announcements", "landing_news_highlights", "landing_quick_links",
            "landing_live_location", "landing_placeholder_card", "landing_nav_about",
            "landing_nav_officers", "landing_nav_activities", "landing_nav_resources",
            "landing_nav_news",
        ],
    },
    "email_guard": {
        "label": "ISU Email Guard",
        "keys": ["isu_email_guard_enabled"],
    },
    "duplicate_email": {
        "label": "Member Duplicate Emails",
        "keys": ["membership_allow_duplicate_email"],
    },
    "back_dues": {
        "label": "Mid-Year Back-Dues Chase",
        "keys": ["dues_require_back_dues_on_join"],
    },
    "email_kill": {
        "label": "Outgoing Email Kill Switch",
        "keys": ["email_sending_enabled"],
    },
    "login_otp": {
        "label": "Login OTP Switch",
        "keys": ["login_otp_enabled"],
    },
    "unpaid_months": {
        "label": "Unpaid Month List",
        "keys": ["show_unpaid_months"],
    },
    "other_campus": {
        "label": "Other Campus Option",
        "keys": ["show_other_campus"],
    },
    "safety_threshold": {
        "label": "Fund Safety Threshold",
        "keys": ["safety_threshold_amount", "safety_threshold_enabled"],
    },
    "banner": {
        "label": "Notification Banner Timer",
        "keys": ["banner_duration_seconds"],
    },
}


def _handle_system_settings_save_all(request: HttpRequest, updated_by: OfficerUser) -> dict:
    """Save every card of the consolidated System Settings view in one POST.

    Unchecked pill toggles are absent from POST and read as OFF. A card with
    invalid input is skipped (its old values kept) while the other cards
    still save; all outcomes are reported in one summary message.
    """
    from core_system import zt_settings
    from core_system.dues_backfill_guard import set_back_dues_chase_enabled
    from core_system.isu_email_guard import (
        set_isu_email_guard_enabled,
        set_membership_duplicate_email_allowed,
    )
    from core_system.nav_modules import set_nav_modules
    from core_system.landing_sections import SECTION_META, set_landing_sections
    from core_system.settings_views import (
        BANNER_DURATION_DEFAULT,
        BANNER_DURATION_MAX,
        BANNER_DURATION_MIN,
    )
    from core_system.shared_view_utils import _record_audit_trail

    saved: list[str] = []
    failed: list[str] = []

    # 1. Navigation Modules (pill toggles; at least one must stay on).
    sidebar = request.POST.get("nav_sidebar") == "on"
    header_strip = request.POST.get("nav_header_strip") == "on"
    forced = False
    if not sidebar and not header_strip:
        sidebar = True
        forced = True
    set_nav_modules(sidebar=sidebar, header_strip=header_strip)
    saved.append(
        "Navigation Modules saved"
        + (" (Sidebar forced on — at least one navigation is required)" if forced else "")
    )

    # 1b. Landing Page Sections (pill toggles; all-off allowed).
    set_landing_sections({
        key: request.POST.get(f"landing_{key}") == "on"
        for key, _label, _desc in SECTION_META
    })
    saved.append("Landing Page Sections saved")

    # 2. Boolean rule cards (pill toggles).
    set_isu_email_guard_enabled(request.POST.get("isu_email_guard") == "on")
    saved.append("ISU Email Guard saved")
    set_membership_duplicate_email_allowed(request.POST.get("membership_duplicate_email") == "on")
    saved.append("Member Duplicate Emails saved")
    set_back_dues_chase_enabled(request.POST.get("dues_require_back_dues_on_join") == "on")
    saved.append("Back-Dues Chase saved")
    from core_system.otp_killswitch import set_login_otp_enabled
    set_login_otp_enabled(request.POST.get("login_otp_enabled") == "on")
    saved.append("Login OTP Switch saved")
    from core_system.unpaid_months_guard import set_show_unpaid_months_enabled
    set_show_unpaid_months_enabled(request.POST.get("show_unpaid_months") == "on")
    saved.append("Unpaid Month List saved")
    from core_system.other_campus_guard import set_other_campus_enabled
    set_other_campus_enabled(request.POST.get("show_other_campus") == "on")
    saved.append("Other Campus Option saved")
    # NOTE: the email STOP is momentary (own button + confirm) and is
    # deliberately NOT part of Update All — an absent checkbox must never
    # force email OFF on a bulk save.

    # 3. Zero Trust & lockout timers (validated as a set).
    clean, errors = zt_settings.validate_timer_values(request.POST)
    if errors:
        failed.append("Zero Trust timers: " + " ".join(errors))
    else:
        zt_settings.save_zt_timers(clean, updated_by=updated_by)
        _record_audit_trail(
            table="system_setting",
            record_id=0,
            action="ZT_TIMERS_UPDATED",
            actor=updated_by,
            old=None,
            new=clean,
            ip=request.META.get("REMOTE_ADDR"),
            device_info=request.META.get("HTTP_USER_AGENT"),
            notes="Zero Trust / lockout timers updated (consolidated settings save)",
        )
        saved.append("Zero Trust timers saved")

    # 4. Fund Safety Threshold (amount + pill toggle).
    raw_amount = (request.POST.get("safety_threshold_amount") or "").strip()
    try:
        amount_value = float(raw_amount)
        if amount_value < 0:
            raise ValueError
    except (TypeError, ValueError):
        failed.append("Fund Safety Threshold: amount must be a non-negative number.")
    else:
        threshold_on = request.POST.get("safety_threshold_enabled") == "on"
        SystemSetting.objects.update_or_create(
            setting_key="safety_threshold_amount",
            defaults={"setting_value": str(amount_value)},
        )
        SystemSetting.objects.update_or_create(
            setting_key="safety_threshold_enabled",
            defaults={"setting_value": "true" if threshold_on else "false"},
        )
        saved.append("Fund Safety Threshold saved")

    # 5. Notification Banner Timer (seconds, 2–60).
    raw_banner = (request.POST.get("banner_duration_seconds") or "").strip()
    try:
        banner_seconds = int(raw_banner)
        if banner_seconds < BANNER_DURATION_MIN or banner_seconds > BANNER_DURATION_MAX:
            raise ValueError
    except (TypeError, ValueError):
        failed.append(
            f"Notification Banner Timer: enter {BANNER_DURATION_MIN}–{BANNER_DURATION_MAX} seconds."
        )
    else:
        SystemSetting.objects.update_or_create(
            setting_key="banner_duration_seconds",
            defaults={"setting_value": str(banner_seconds)},
        )
        saved.append(f"Notification Banner Timer saved ({banner_seconds}s, default {BANNER_DURATION_DEFAULT}s)")

    ok = not failed
    parts = [f"Saved {len(saved)} setting card(s)."]
    if failed:
        parts.append("Not saved: " + " | ".join(failed))
    return {"ok": ok, "message": " ".join(parts), "level": "success" if ok else "error"}


def _handle_system_settings_reset(request: HttpRequest) -> dict:
    """Reset one settings card to its code defaults (delete its rows)."""
    from core_system import zt_settings

    feedback = {"ok": False, "message": "", "level": "error"}
    if request.POST.get("form_type", "").strip() != "system_settings_reset":
        feedback["message"] = "Invalid form type."
        return feedback

    group = (request.POST.get("reset_group") or "").strip()
    if group == "zt_timers":
        keys = [f["key"] for f in zt_settings.timer_fields()] + [zt_settings.ROLES_FIELD]
        label = "Zero Trust & Lockout Timers"
    else:
        spec = SA_RESET_GROUPS.get(group)
        if spec is None:
            feedback["message"] = "Unknown settings group."
            return feedback
        keys = spec["keys"]
        label = spec["label"]

    SystemSetting.objects.filter(setting_key__in=keys).delete()
    if group == "zt_timers":
        from django.core.cache import cache

        cache.delete(zt_settings.CACHE_KEY)

    feedback["ok"] = True
    feedback["message"] = f"{label} reset to default."
    feedback["level"] = "success"
    return feedback


def _backup_scheduler_status_context() -> dict:
    """Live status of the in-process backup scheduler for admin pages."""
    scheduler_running = False
    next_db_backup = None
    try:
        from core_system.management.commands.run_backup_scheduler import scheduler_state

        sched = scheduler_state.get("scheduler")
        scheduler_running = bool(scheduler_state.get("running")) and sched is not None
        if scheduler_running:
            scheduled = sched.get_job("backup_db_daily_0000")
            if scheduled is not None and scheduled.next_run_time is not None:
                next_db_backup = scheduled.next_run_time.isoformat()
    except Exception:
        pass
    return {
        "scheduler_running": scheduler_running,
        "next_db_backup": next_db_backup,
    }


@ensure_csrf_cookie
def superadmin_dashboard(request: HttpRequest):
    guard = require_role(request, role="Superadmin")
    if guard is not None:
        return guard

    superadmin, president, system_backfill = _ensure_default_superadmin_accounts()
    form_feedback = None
    threshold_feedback = None

    if request.method == "POST":
        form_type = request.POST.get("form_type", "").strip()
        account_key = request.POST.get("account_key", "").strip()
        label_by_key = {
            "superadmin": "Superadmin",
            "president": "President",
            "system_backfill": "System Backfill",
        }
        account_by_key = {
            "superadmin": superadmin,
            "president": president,
            "system_backfill": system_backfill,
        }

        if form_type == "safety_threshold":
            threshold_feedback = _handle_superadmin_safety_threshold_form(request)
        elif form_type == "banner_settings":
            form_feedback = _handle_superadmin_banner_settings_form(request)
        elif form_type == "nav_modules":
            form_feedback = _handle_superadmin_nav_modules_form(request)
        elif form_type == "isu_email_guard":
            form_feedback = _handle_superadmin_isu_email_guard_form(request)
        elif form_type == "membership_duplicate_email":
            form_feedback = _handle_superadmin_duplicate_email_form(request)
        elif form_type == "dues_back_dues_chase":
            form_feedback = _handle_superadmin_back_dues_chase_form(request)
        elif form_type == "email_kill_switch":
            form_feedback = _handle_superadmin_email_kill_switch_form(request)
        elif form_type == "login_otp_switch":
            form_feedback = _handle_superadmin_login_otp_form(request)
        elif form_type == "show_unpaid_months":
            form_feedback = _handle_superadmin_unpaid_months_form(request)
        elif form_type == "show_other_campus":
            form_feedback = _handle_superadmin_other_campus_form(request)
        elif form_type == "email_stop_now":
            form_feedback = _handle_superadmin_email_stop_form(request)
        elif form_type == "system_settings_save_all":
            form_feedback = _handle_system_settings_save_all(request, superadmin)
        elif form_type == "system_settings_reset":
            form_feedback = _handle_system_settings_reset(request)
        elif form_type == "zt_timers":
            form_feedback = _handle_superadmin_zt_timers_form(request, superadmin)
        elif form_type == "toggle_account_status" and account_key in account_by_key:
            updated, form_feedback = _handle_superadmin_toggle_account_status(request, account_by_key[account_key], label_by_key[account_key])
            account_by_key[account_key] = updated
        elif form_type == "account_update" and account_key in account_by_key:
            updated, form_feedback = _handle_superadmin_account_form(request, account_by_key[account_key], label_by_key[account_key])
            account_by_key[account_key] = updated
        else:
            form_feedback = {"ok": False, "message": "Unknown form submission.", "level": "error"}

        superadmin, president, system_backfill = (
            account_by_key["superadmin"],
            account_by_key["president"],
            account_by_key["system_backfill"],
        )

    context = _build_superadmin_dashboard_context(superadmin, president, system_backfill, form_feedback, threshold_feedback)
    context.update(_backup_scheduler_status_context())
    return render(request, "website/Superadmin/superadmin_dashboard.html", context)


@require_GET
def fund_ledger_list(request: HttpRequest):
    """Return paginated FundTransaction entries — visible to all roles."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard

    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 50))
    direction = request.GET.get("direction", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    opening_before = request.GET.get("opening_before", "")

    qs = FundTransaction.objects.select_related("recorded_by_user_id_FK").all()

    def _as_bare_date(value: str):
        """YYYY-MM-DD or None."""
        try:
            return date.fromisoformat((value or "").strip())
        except (ValueError, TypeError):
            return None

    def _day_start(day: date):
        """Aware start-of-day in the project timezone (Asia/Manila).

        Bare-date params must compare as aware datetimes: the __date lookup
        relies on MySQL named timezones (often unloaded -> matches nothing),
        and day boundaries belong to the user's locale, not UTC.
        """
        return timezone.make_aware(
            datetime.combine(day, dtime.min), timezone.get_current_timezone()
        )

    def _day_end(day: date):
        return timezone.make_aware(
            datetime.combine(day, dtime.max), timezone.get_current_timezone()
        )

    if direction in ("inflow", "outflow"):
        qs = qs.filter(direction=direction)
    if date_from:
        bare = _as_bare_date(date_from)
        qs = qs.filter(recorded_at__gte=_day_start(bare)) if bare else qs.filter(recorded_at__gte=date_from)
    if date_to:
        bare = _as_bare_date(date_to)
        qs = qs.filter(recorded_at__lte=_day_end(bare)) if bare else qs.filter(recorded_at__lte=date_to)

    total = qs.count()
    qs = qs.order_by("-recorded_at")

    offset = (page - 1) * per_page
    entries = qs[offset:offset + per_page]

    totals = FundTransaction.objects.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    total_in = float(totals["total_in"] or 0)
    total_out = float(totals["total_out"] or 0)
    balance = total_in - total_out

    summary: dict[str, Any] = {
        "total_in": total_in,
        "total_out": total_out,
        "balance": balance,
    }

    # Opening balance for journals: net of every movement strictly before
    # the period start, so a period running balance can start truthfully
    # instead of at zero. Only included when requested.
    opening_day = _as_bare_date(opening_before)
    if opening_day:
        oagg = FundTransaction.objects.filter(
            recorded_at__lt=_day_start(opening_day)
        ).aggregate(
            total_in=Sum("amount", filter=Q(direction="inflow")),
            total_out=Sum("amount", filter=Q(direction="outflow")),
        )
        summary["opening"] = float(oagg["total_in"] or 0) - float(oagg["total_out"] or 0)

    items = []
    for e in entries:
        items.append({
            "id": e.transaction_id_PK,
            "direction": e.direction,
            "amount": float(e.amount),
            "source_type": e.source_type,
            "description": e.description,
            "reference_number": e.reference_number or "",
            "recorded_by": e.recorded_by_user_id_FK.full_name if e.recorded_by_user_id_FK else "",
            "recorded_at": e.recorded_at.isoformat() if e.recorded_at else "",
        })

    return JsonResponse({
        "ok": True,
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if per_page else 1,
        "summary": summary,
    })


@require_GET
def fund_balance_summary(request: HttpRequest):
    """Return current fund balance + safety threshold — visible to all roles.

    Returns BOTH the lifetime totals (``total_in`` / ``total_out``) and the
    month-to-date movement (``month_in`` / ``month_out``). The lifetime keys are
    what the dashboard's "Total Cash Inflows" / "Total Cash Outflows" cards
    read; they were missing here, and because the client coerced ``undefined``
    to zero the cards silently rendered ₱0.00 instead of erroring.
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard

    totals = FundTransaction.objects.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    total_in = float(totals["total_in"] or 0)
    total_out = float(totals["total_out"] or 0)
    balance = total_in - total_out

    threshold, _ = SystemSetting.objects.get_or_create(
        setting_key="safety_threshold",
        defaults={"setting_value": "20000"},
    )
    safety_threshold = float(threshold.setting_value)

    # Monthly totals
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_in = FundTransaction.objects.filter(
        direction="inflow", recorded_at__gte=month_start
    ).aggregate(total=Sum("amount"))["total"] or 0
    month_out = FundTransaction.objects.filter(
        direction="outflow", recorded_at__gte=month_start
    ).aggregate(total=Sum("amount"))["total"] or 0

    return JsonResponse({
        "ok": True,
        "balance": balance,
        "total_in": total_in,
        "total_out": total_out,
        "safety_threshold": safety_threshold,
        "available": balance - safety_threshold,
        "month_in": float(month_in),
        "month_out": float(month_out),
    })


@require_GET
def member_deductions_list(request: HttpRequest, member_id: int | None = None):
    """Return deduction history for a specific member — visible to all roles."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard

    if member_id is None:
        member_id = request.GET.get("member_id", "")
        if not member_id:
            return JsonResponse({"ok": False, "error": "member_id required."}, status=400)

    try:
        member_id = int(member_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "member_id must be an integer."}, status=400)

    officer_role = (request.session.get("role") or "").strip().lower()
    is_member_role = officer_role in ("member", "member_user")
    if is_member_role:
        # Members may only read their own deduction history (IDOR guard).
        officer_id = request.session.get("officer_id")
        own_member = None
        if officer_id:
            own_member = Member.objects.filter(
                officer_user_id_FK=officer_id,
            ).first()
        if not own_member or own_member.member_id_PK != member_id:
            return JsonResponse({"ok": False, "error": "Forbidden: you can only view your own deductions."}, status=403)
        member = own_member
    else:
        member = get_object_or_404(Member, pk=member_id)

    deductions = PayrollDeduction.objects.filter(
        member_id_FK=member,
        batch_id_FK__status="Approved",
    ).select_related("batch_id_FK", "aid_tracking_post_id_FK").order_by("-batch_id_FK__created_at")

    items = []
    for d in deductions:
        batch = d.batch_id_FK
        aid_ref = ""
        if d.aid_tracking_post_id_FK:
            post = d.aid_tracking_post_id_FK
            aid_ref = f"{post.aid_type}#{post.source_id}" if post.source_id else post.aid_type
        items.append({
            "date": batch.president_approved_at.isoformat() if batch.president_approved_at else "",
            "payroll_period": batch.payroll_period,
            "category": d.category,
            "amount": float(d.amount),
            "fund_impact": d.fund_impact,
            "aid_reference": aid_ref,
            "month_covered": d.month_covered or "",
            "batch_id": batch.batch_id_PK,
            "description": _build_member_deduction_desc(d, batch),
        })

    total_deducted = sum(i["amount"] for i in items)

    return JsonResponse({
        "ok": True,
        "member_id": member.member_id_PK,
        "member_name": member.full_name,
        "deductions": items,
        "total_deducted": total_deducted,
        "count": len(items),
    })


def _build_member_deduction_desc(deduction: PayrollDeduction, batch: PayrollBatch) -> str:
    label = dict(PayrollDeduction.CATEGORY_CHOICES).get(deduction.category, deduction.category)
    period = f" ({deduction.month_covered})" if deduction.month_covered else ""
    return f"{label}{period} — {batch.payroll_period}"


@require_GET
@ensure_csrf_cookie
def member_dashboard(request: HttpRequest):
    """Member dashboard page - visible when Member role logs in."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard

    officer_id = request.session.get("officer_id")
    officer_full_name = ""
    officer_email = ""
    member_data = None
    member = None
    onboarding_pending = False

    if officer_id:
        try:
            officer = OfficerUser.objects.get(user_id_PK=officer_id)
            officer_full_name = officer.full_name or ""
            officer_email = officer.email or ""
            member = Member.objects.filter(officer_user_id_FK=officer).first()
            # First-login onboarding gate (Data Privacy Notice + account
            # activation): pending until the member completes it once, or
            # while a password change is still forced on the account.
            onboarding_pending = bool(officer.must_change_password) or bool(
                member is not None and not member.setup_complete
            )
            if member:
                # MANDATORY PUSH: force the account flag on so every device
                # auto-subscribes; delivery itself no longer checks the flag.
                if not member.push_enabled:
                    member.push_enabled = True
                    member.save(update_fields=["push_enabled"])
                member_data = {
                    "member_id": member.member_id_PK,
                    "full_name": member.full_name,
                    "username": (member.officer_user_id_FK.username if member.officer_user_id_FK else "") or member.employee_id or "",
                    "employee_id": member.employee_id or "",
                    "email": member.email or "",
                    "contact_number": member.contact_number or "",
                    "department": member.department or "",
                    "position": member.position or "",
                    "employment_status": member.employment_status,
                    "membership_status": member.membership_status,
                    "member_classification": member.member_classification,
                    "member_type": member.member_type,
                    "date_joined": member.date_joined.isoformat() if member.date_joined else "",
                    "profile_picture": member.profile_picture.url if member.profile_picture else "",
                    "has_pin": bool(member.pin_code),
                    "qr_code": member.qr_code.url if member.qr_code else "",
                    "emergency_contact": member.emergency_contact or "",
                    "emergency_number": member.emergency_number or "",
                    "address": member.address or "",
                    "civil_status": member.civil_status or "",
                    "sex": member.sex or "",
                    "date_of_birth": member.date_of_birth.isoformat() if member.date_of_birth else "",
                    "age": member.age,
                }
        except OfficerUser.DoesNotExist:
            pass
    
    # --- Real data queries ---

    # Membership Fee status
    membership_fee_status = "Unpaid"
    membership_fee_amount = 0
    membership_fee_paid = False
    has_membership_fee = False
    membership_fee_submitted = False
    membership_fee_reference = ""
    membership_fee_payment_date = ""
    membership_fee_method = ""
    if member:
        fee = MembershipFee.objects.filter(member_id_FK=member).order_by("-payment_date").first()
        if fee:
            has_membership_fee = True
            membership_fee_status = fee.payment_status
            membership_fee_amount = float(fee.amount)
            membership_fee_paid = fee.payment_status in ("Paid", "Full Payment")
            membership_fee_submitted = fee.payment_status in MEMBERSHIP_FEE_SUBMITTED_STATUSES
            membership_fee_reference = fee.receipt_number or fee.deposit_reference or ""
            membership_fee_payment_date = fee.payment_date.strftime("%b %d, %Y") if fee.payment_date else ""
            membership_fee_method = fee.payment_method or ""
    if membership_fee_amount == 0:
        membership_fee_amount = get_membership_fee_amount()

    monthly_dues_amount = get_monthly_dues_amount()

    # Monthly Dues
    total_dues_paid = 0
    total_dues_pending = 0
    total_dues_unpaid = 0
    outstanding_balance = 0
    dues_records = []
    unpaid_months = []
    if member:
        all_dues = MonthlyDues.objects.filter(member_id_FK=member).order_by("-month_covered")
        total_dues_paid = float(all_dues.filter(payment_status__in=Status.ALL_AUDITOR_VERIFIED).aggregate(t=Sum("amount"))["t"] or 0)
        total_dues_pending = float(all_dues.filter(payment_status="Pending").aggregate(t=Sum("amount"))["t"] or 0)
        total_dues_unpaid = float(all_dues.filter(payment_status="Unpaid").aggregate(t=Sum("amount"))["t"] or 0)
        covered = set(
            all_dues.filter(
                payment_status__in=["Pending", "Paid", "Full Payment"],
            ).values_list("month_covered", flat=True)
        )
        joined = member.date_joined or (timezone.now().date() - timedelta(days=365))
        unpaid_count = 0
        year, month = joined.year, joined.month + 1
        if month > 12:
            year += 1
            month = 1
        today = timezone.now().date()
        while (year < today.year) or (year == today.year and month <= today.month):
            if f"{year}-{month:02d}" not in covered:
                unpaid_count += 1
            month += 1
            if month > 12:
                month = 1
                year += 1
        outstanding_balance = round(float(get_monthly_dues_amount()) * unpaid_count, 2)
        deduction_overview = member_deduction_overview(member)
        if deduction_overview is not None:
            # Use final-approved salary-deduction months when they exist, so
            # the Overview agrees with History and the member notices.
            total_dues_paid = deduction_overview["total_paid"]
            outstanding_balance = deduction_overview["outstanding_balance"]
        retired_member = is_retired_member(member)
        if retired_member:
            # Retirement ends the current obligation while preserving history.
            outstanding_balance = 0.0
        # Unpaid Balance with months context: the pooled carry-over broken into
        # the actual months it is made of, oldest first — what the member still
        # owes rolls forward month to month until it is collected.
        unpaid_months = [] if retired_member else member_unpaid_months(member)
        for d in all_dues:
            dues_records.append({
                "dues_id": d.dues_id_PK,
                "month_covered": d.month_covered,
                "amount": float(d.amount),
                "payment_status": d.payment_status,
                "payment_method": d.payment_method,
                "payment_date": d.payment_date.isoformat() if d.payment_date else "",
            })

    # Contributions
    total_contributions = 0
    contribution_records = []
    if member:
        medical_claim_ids = MedicalAid.objects.filter(member_id_FK=member).values_list("medical_aid_id_PK", flat=True)
        death_claim_ids = DeathAid.objects.filter(member_id_FK=member).values_list("death_aid_id_PK", flat=True)
        contribs = Contribution.objects.filter(member_id_FK=member).exclude(
            Q(aid_tracking_post_id_FK__source_type="medical_aid", aid_tracking_post_id_FK__source_id__in=medical_claim_ids)
            | Q(aid_tracking_post_id_FK__source_type="death_aid", aid_tracking_post_id_FK__source_id__in=death_claim_ids)
        ).select_related("aid_tracking_post_id_FK").order_by("-aid_tracking_post_id_FK__created_at")
        total_contributions = float(contribs.aggregate(t=Sum("paid_amount"))["t"] or 0)
        for c in contribs:
            post = c.aid_tracking_post_id_FK
            contribution_records.append({
                "contribution_id": c.contribution_id_PK,
                "aid_type": post.aid_type if post else "",
                "target_month": post.target_month if post else "",
                "expected_amount": float(c.expected_amount),
                "paid_amount": float(c.paid_amount),
                "payment_date": c.payment_date.isoformat() if c.payment_date else "",
                "status": c.status,
            })

    # Claims and Notifications
    claim_items = []
    medical_aid_records = []
    death_aid_records = []
    notifications = []
    medical_aid_count = 0
    death_aid_count = 0
    medical_aid_pending = 0
    medical_aid_approved = 0
    medical_aid_released = 0
    death_aid_pending = 0
    death_aid_approved = 0
    death_aid_released = 0

    if member:
        medical_aids = MedicalAid.objects.filter(member_id_FK=member).order_by("-request_date")
        for ma in medical_aids:
            record = {
                "claim_id": ma.medical_aid_id_PK,
                "claim_type": "Medical Aid",
                "status": ma.status,
                "description": f"{ma.hospital_name or 'Medical'} - ₱{ma.requested_amount or 0}",
                "date": ma.request_date.isoformat() if ma.request_date else "",
                "is_medical": True,
            }
            medical_aid_records.append(record)
            claim_items.append(record)
            medical_aid_count += 1
            if ma.status == 'Pending':
                medical_aid_pending += 1
            elif ma.status == 'Approved':
                medical_aid_approved += 1
            elif ma.status == 'Released':
                medical_aid_released += 1

        death_aids = DeathAid.objects.filter(member_id_FK=member).order_by("-claim_date")
        for da in death_aids:
            record = {
                "claim_id": da.death_aid_id_PK,
                "claim_type": "Death Aid",
                "status": da.status,
                "description": f"{da.deceased_name or 'Death'} - ₱{da.benefit_amount or 0}",
                "date": da.claim_date.isoformat() if da.claim_date else "",
                "is_medical": False,
            }
            death_aid_records.append(record)
            claim_items.append(record)
            death_aid_count += 1
            if da.status == 'Pending':
                death_aid_pending += 1
            elif da.status == 'Approved':
                death_aid_approved += 1
            elif da.status == 'Released':
                death_aid_released += 1
        
        notifications_qs = Notification.objects.filter(
            recipient_type='member',
            recipient_id=member.member_id_PK
        ).order_by("-sent_at")[:10]
        for n in notifications_qs:
            notifications.append({
                "notification_id_PK": n.notification_id_PK,
                "notification_type": n.notification_type,
                "message": n.message,
                "category": n.category,
                "sent_at": n.sent_at,
                "is_read": n.is_read,
                "sender_name": n.sender_name or "",
                "sender_role": n.sender_role or "",
                "receipt_number": n.receipt_number or "",
            })

    claim_items.sort(key=lambda x: x["date"], reverse=True)
    total_claims = medical_aid_count + death_aid_count

    # Finance summary
    total_financial_contributions = (membership_fee_amount if membership_fee_paid else 0) + total_dues_paid + total_contributions
    total_paid = (membership_fee_amount if membership_fee_paid else 0) + total_dues_paid
    pending_amount = total_dues_pending

    # Latest payment dates & method
    latest_payment_date = ""
    next_due_date = ""
    next_due_month = ""
    next_due_month_label = "Up to date"
    first_payment_method = ""
    if member:
        last_pmt = MonthlyDues.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("-payment_date").first()
        if last_pmt:
            first_payment_method = last_pmt.payment_method or ""
        if not first_payment_method:
            last_fee = MembershipFee.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("-payment_date").first()
            if last_fee:
                first_payment_method = last_fee.payment_method or ""
    if member:
        last_dues = MonthlyDues.objects.filter(
            member_id_FK=member, payment_date__isnull=False
        ).order_by("-payment_date").first()
        if last_dues and last_dues.payment_date:
            latest_payment_date = last_dues.payment_date.isoformat()
        
        today = date.today()
        next_m = today.replace(day=1) + timedelta(days=32)
        next_m = next_m.replace(day=1)
        next_month_str = next_m.strftime("%Y-%m")
        
        has_next_due = not MonthlyDues.objects.filter(
            member_id_FK=member, month_covered=next_month_str
        ).exists()
        
        if has_next_due:
            # Assuming dues are for the first of the month.
            next_due_date = next_m.strftime("%b %d, %Y")
            next_due_month = next_month_str
            next_due_month_label = next_m.strftime("%B %Y")


    # Payment history (combined)
    payment_history = []
    if member:
        fees = MembershipFee.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("-payment_date")[:10]
        for f in fees:
            payment_history.append({
                "type": "Membership Fee",
                "amount": float(f.amount),
                "method": f.payment_method,
                "status": f.payment_status,
                "date": f.payment_date.isoformat() if f.payment_date else "",
                "reference": f.receipt_number or "",
            })
        dues = MonthlyDues.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("-payment_date")[:10]
        for d in dues:
            payment_history.append({
                "type": f"Dues ({d.month_covered})",
                "amount": float(d.amount),
                "method": d.payment_method,
                "status": d.payment_status,
                "date": d.payment_date.isoformat() if d.payment_date else "",
                "reference": d.receipt_number or "",
                "treasurer_status": d.treasurer_status,
                "auditor_status": d.auditor_status,
                "president_status": d.president_status,
            })
        payment_history.sort(key=lambda x: x["date"], reverse=True)

    # Compute member_since_date (fallback chain)
    member_since_date = ""
    member_since_label = ""
    if member:
        if member.date_joined:
            member_since_date = member.date_joined.isoformat()
            member_since_label = member.date_joined.strftime("%b %Y")
        else:
            earliest = None
            first_fee = MembershipFee.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("payment_date").first()
            if first_fee and first_fee.payment_date:
                earliest = first_fee.payment_date
            
            first_dues = MonthlyDues.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("payment_date").first()
            if first_dues and first_dues.payment_date:
                if earliest is None or first_dues.payment_date < earliest:
                    earliest = first_dues.payment_date
            
            if earliest:
                member_since_date = earliest.isoformat()
                member_since_label = earliest.strftime("%b %Y")
            else:
                member_since_label = "N/A"

    # Authorized representative
    rep_data = None
    if member:
        rep = Claimant.objects.filter(member_id_FK=member).first()
        if rep:
            rep_data = {
                "full_name": rep.full_name,
                "contact_number": rep.contact_number or "",
                "relationship": rep.relationship_to_member,
            }

    context = {
        "officer_full_name": officer_full_name,
        "officer_email": officer_email,
        "member_data": member_data,
        "access_token": request.session.get("access_token", ""),
        "membership_fee_status": membership_fee_status,
        "membership_fee_amount": membership_fee_amount,
        "membership_fee_paid": membership_fee_paid,
        "has_membership_fee": has_membership_fee,
        "membership_fee_submitted": membership_fee_submitted,
        "membership_fee_reference": membership_fee_reference,
        "membership_fee_payment_date": membership_fee_payment_date,
        "membership_fee_method": membership_fee_method,
        "monthly_dues_amount": monthly_dues_amount,
        "next_due_month": next_due_month,
        "next_due_month_label": next_due_month_label,
        "total_dues_paid": total_dues_paid,
        "total_dues_pending": total_dues_pending,
        "total_dues_unpaid": total_dues_unpaid,
        "outstanding_balance": outstanding_balance,
        "unpaid_months": unpaid_months,
        "unpaid_months_label": ", ".join(m["label"] for m in unpaid_months),
        "total_contributions": total_contributions,
        "total_financial_contributions": total_financial_contributions,
        "total_paid": total_paid,
        "pending_amount": pending_amount,
        "next_due_date": next_due_date,
        "latest_payment_date": latest_payment_date,
        "first_payment_method": first_payment_method,
        "total_claims": total_claims,
        "dues_records": dues_records,
        "contribution_records": contribution_records,
        "medical_aid_records": medical_aid_records,
        "death_aid_records": death_aid_records,
        "notifications": notifications,
        "payment_history": payment_history,
        "rep_data": rep_data,
        "member_since_date": member_since_date,
        "member_since_label": member_since_label,
        "medical_aid_pending": medical_aid_pending,
        "medical_aid_approved": medical_aid_approved,
        "medical_aid_released": medical_aid_released,
        "death_aid_pending": death_aid_pending,
        "death_aid_approved": death_aid_approved,
        "death_aid_released": death_aid_released,
        "claim_items": claim_items,
        "total_claims": total_claims,
        "medical_aid_count": medical_aid_count,
        "death_aid_count": death_aid_count,
        "membership_fee_paid": membership_fee_paid,
        "is_member": member is not None,
        # Web Push (device notifications) — MANDATORY for members: the
        # dashboard auto-registers each device against these VAPID keys and
        # every email notification also force-pushes. Always True here.
        "vapid_public_key": getattr(settings, "VAPID_PUBLIC_KEY", ""),
        # Mandatory: members always receive push alongside email.
        "member_push_enabled": True,
        # Onboarding gate (from FROMGROUP/isucaufa-onboarding-demo.html): the
        # Data Privacy Notice + account activation card shown over the
        # dashboard until the member completes it once.
        "onboarding_pending": onboarding_pending,
        "onboarding_email": (member.email if member and member.email else officer_email),
        # First-login backup-code reveal: one-time modal. Plaintext codes are
        # NEVER embedded here — the modal fetches them once via the reveal
        # endpoint, which destroys them server-side on first serve.
        "show_backup_modal": bool(request.session.get("show_backup_modal")),
    }

    return render(request, "website/Member/member_dashboard.html", context)
