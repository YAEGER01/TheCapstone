"""Global kill switch for login OTP (all roles).

Single SystemSetting row (``login_otp_enabled``) gates the email-OTP step of
every role login in ``auth_views.officer_login``:

- ON (default): password success -> email OTP queued -> ``mfa_verify``.
- OFF: password success -> full session immediately, no OTP queued, no
  ``mfa_verify`` needed. Applies to every role (Superadmin, President,
  Treasurer, Auditor, Secretary, PIO, Member, System Backfill) because they
  all sign in through the same ``officer_login`` view.

Fail-open: when the table/row is missing (fresh migrate, tests without DB),
login behaves exactly as before (OTP required) until a Superadmin explicitly
flips the switch OFF.

Scope notes (deliberate):
- Zero Trust step-up codes (``zero_trust_challenge``) and forgot-password
  reset codes are NOT gated — this switch is login OTP only.
- The master email kill switch (``email_killswitch``) is independent: it
  blocks SMTP delivery, while this switch skips the OTP requirement itself.
"""

LOGIN_OTP_ENABLED_KEY = "login_otp_enabled"

_TRUTHY = {"true", "1", "yes", "on"}
_FALSY = {"false", "0", "no", "off"}


def _read_raw_setting() -> str | None:
    from core_system.models import SystemSetting

    row = SystemSetting.objects.filter(setting_key=LOGIN_OTP_ENABLED_KEY).first()
    if row is None:
        return None
    return (row.setting_value or "").strip().lower()


def is_login_otp_enabled() -> bool:
    """True when login OTP is required (default ON).

    Fail-open when the table/row is missing: callers behave exactly as
    before until a Superadmin explicitly flips the switch OFF.
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


def is_login_otp_disabled() -> bool:
    """Convenience alias: True when the OTP switch is turned OFF."""
    return not is_login_otp_enabled()


def set_login_otp_enabled(enabled: bool) -> None:
    from core_system.models import SystemSetting

    SystemSetting.objects.update_or_create(
        setting_key=LOGIN_OTP_ENABLED_KEY,
        defaults={"setting_value": "true" if enabled else "false"},
    )
