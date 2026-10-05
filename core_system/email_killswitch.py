"""Master kill switch for ALL outbound email.

Single SystemSetting row (``email_sending_enabled``) gates every SMTP path:

- ``email_service.send_html_email`` / ``send_html_email_async``
- ``email_service.queue_email`` / ``queue_and_process_email``
- ``email_service.send_html_emails_bulk``
- ``email_service.process_email_queue`` / ``flush_email_queue_async`` /
  ``kick_email_worker`` (queue drains)
- ``gmail_otp_emailer.send_gmail_otp_email`` (MFA / Zero Trust codes)

Default is ON (``True``): email flows normally. When a Superadmin flips it
OFF, every entry point above refuses to queue or send and logs a warning
instead — one switch stops the Gmail SMTP burn even if a monthly-deduction
fan-out, dues-reminder cron, or announcement blast is mid-loop.

In-app dashboard notifications and Web Push are intentionally NOT gated:
members still see notices inside the portal; only SMTP stops.
"""

EMAIL_SENDING_ENABLED_KEY = "email_sending_enabled"

_TRUTHY = {"true", "1", "yes", "on"}
_FALSY = {"false", "0", "no", "off"}


def _read_raw_setting() -> str | None:
    from core_system.models import SystemSetting

    row = SystemSetting.objects.filter(setting_key=EMAIL_SENDING_ENABLED_KEY).first()
    if row is None:
        return None
    return (row.setting_value or "").strip().lower()


def is_email_sending_enabled() -> bool:
    """True when outbound email may be queued/sent (default ON).

    Fail-open when the table/row is missing (fresh migrate, tests without
    DB): callers behave exactly as before until a Superadmin explicitly
    flips the switch OFF.
    """
    try:
        raw = _read_raw_setting()
    except Exception:
        return True
    if raw is None or raw == "":
        return True
    if raw in _FALSY:
        return False
    return True


def is_email_killed() -> bool:
    """Convenience alias: True when the kill switch is engaged."""
    return not is_email_sending_enabled()


def set_email_sending_enabled(enabled: bool) -> None:
    from core_system.models import SystemSetting

    SystemSetting.objects.update_or_create(
        setting_key=EMAIL_SENDING_ENABLED_KEY,
        defaults={"setting_value": "true" if enabled else "false"},
    )


LAST_STOP_AT_KEY = "email_last_stop_at"
LAST_STOP_CANCELLED_KEY = "email_last_stop_cancelled"


def get_last_stop_info() -> dict:
    """When the momentary STOP was last pressed and how much it cancelled."""
    from core_system.models import SystemSetting

    try:
        at = SystemSetting.objects.filter(setting_key=LAST_STOP_AT_KEY).first()
        cancelled = SystemSetting.objects.filter(setting_key=LAST_STOP_CANCELLED_KEY).first()
        return {
            "at": at.setting_value if at else "",
            "cancelled": cancelled.setting_value if cancelled else "0",
        }
    except Exception:
        return {"at": "", "cancelled": "0"}


def get_queue_counts() -> dict:
    """Live PENDING / stuck-SENDING counts for the admin status line."""
    from core_system.models import OutgoingEmail

    try:
        return {
            "pending": OutgoingEmail.objects.filter(status=OutgoingEmail.PENDING).count(),
            "sending": OutgoingEmail.objects.filter(status="sending").count(),
        }
    except Exception:
        return {"pending": 0, "sending": 0}


def momentary_email_stop() -> dict:
    """Momentary STOP: block everything, wipe the queue, auto-turn back ON.

    Sequence: switch OFF (every SMTP path refuses instantly, even mid-loop)
    -> cancel every PENDING / stuck-SENDING row as FAILED so nothing resumes
    -> switch back ON. The ``finally`` guarantees email is re-enabled even
    if the purge itself errors, so this can never wedge the system OFF.

    Returns ``{"cancelled": int}`` — rows wiped, i.e. how much spam died.
    In-app dashboard notifications and Web Push are never touched.
    """
    from django.utils import timezone

    from core_system.models import OutgoingEmail, SystemSetting

    set_email_sending_enabled(False)
    try:
        now = timezone.now()
        cancelled = OutgoingEmail.objects.filter(
            status__in=[OutgoingEmail.PENDING, "sending"]
        ).update(
            status=OutgoingEmail.FAILED,
            error_message="Cancelled by operator via momentary email STOP",
            claimed_at=None,
            sent_at=now,
        )
        SystemSetting.objects.update_or_create(
            setting_key=LAST_STOP_AT_KEY,
            defaults={"setting_value": now.isoformat()},
        )
        SystemSetting.objects.update_or_create(
            setting_key=LAST_STOP_CANCELLED_KEY,
            defaults={"setting_value": str(cancelled)},
        )
        return {"cancelled": cancelled}
    finally:
        # Always come back ON fresh — a STOP is momentary, never a wedge.
        set_email_sending_enabled(True)
