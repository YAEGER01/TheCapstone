from core_system.models import SystemSetting

ISU_EMAIL_GUARD_KEY = "isu_email_guard_enabled"
MEMBERSHIP_ALLOW_DUPLICATE_EMAIL_KEY = "membership_allow_duplicate_email"

_TRUTHY = {"true", "1", "yes", "on"}


def is_isu_email_guard_enabled() -> bool:
    row = SystemSetting.objects.filter(setting_key=ISU_EMAIL_GUARD_KEY).first()
    if row is None:
        return True
    return (row.setting_value or "").strip().lower() in _TRUTHY


def set_isu_email_guard_enabled(enabled: bool) -> None:
    SystemSetting.objects.update_or_create(
        setting_key=ISU_EMAIL_GUARD_KEY,
        defaults={"setting_value": "true" if enabled else "false"},
    )


def is_membership_duplicate_email_allowed() -> bool:
    """Whether member enrollment may reuse an email already present on another
    member / officer account (controlled by the Superadmin toggle)."""
    row = SystemSetting.objects.filter(
        setting_key=MEMBERSHIP_ALLOW_DUPLICATE_EMAIL_KEY
    ).first()
    if row is None:
        return False
    return (row.setting_value or "").strip().lower() in _TRUTHY


def set_membership_duplicate_email_allowed(enabled: bool) -> None:
    SystemSetting.objects.update_or_create(
        setting_key=MEMBERSHIP_ALLOW_DUPLICATE_EMAIL_KEY,
        defaults={"setting_value": "true" if enabled else "false"},
    )


def isu_email_guard_context(request):
    return {
        "isu_email_guard_enabled": is_isu_email_guard_enabled(),
        "membership_allow_duplicate_email": is_membership_duplicate_email_allowed(),
    }
