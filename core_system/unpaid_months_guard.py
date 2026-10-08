from core_system.models import SystemSetting

SHOW_UNPAID_MONTHS_KEY = "show_unpaid_months"

_TRUTHY = {"true", "1", "yes", "on"}


def is_show_unpaid_months_enabled() -> bool:
    """Whether the Record Monthly Dues unpaid popup shows the month checkbox list.

    Default ON: the popup shows Total Unpaid Balance + Amount to pay + the
    tickable month breakdown. When OFF, only the amount-based input stays
    visible — typing an amount still auto-settles the oldest months behind
    the scenes, so recording works exactly as before.
    """
    row = SystemSetting.objects.filter(setting_key=SHOW_UNPAID_MONTHS_KEY).first()
    if row is None:
        return True
    return (row.setting_value or "").strip().lower() in _TRUTHY


def set_show_unpaid_months_enabled(enabled: bool) -> None:
    SystemSetting.objects.update_or_create(
        setting_key=SHOW_UNPAID_MONTHS_KEY,
        defaults={"setting_value": "true" if enabled else "false"},
    )
