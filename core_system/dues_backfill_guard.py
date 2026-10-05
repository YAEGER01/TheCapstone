from core_system.models import SystemSetting

BACK_DUES_CHASE_KEY = "dues_require_back_dues_on_join"

_TRUTHY = {"true", "1", "yes", "on"}


def is_back_dues_chase_enabled() -> bool:
    """Whether mid-year joiners must chase back dues (Jan..join-month).

    Default OFF per client: a member who joins midway pays the current and
    future dues only. When ON (panel request), the legacy catch-up flow
    (Jan of join year .. join month + container frontier) applies.
    """
    row = SystemSetting.objects.filter(setting_key=BACK_DUES_CHASE_KEY).first()
    if row is None:
        return False
    return (row.setting_value or "").strip().lower() in _TRUTHY


def set_back_dues_chase_enabled(enabled: bool) -> None:
    SystemSetting.objects.update_or_create(
        setting_key=BACK_DUES_CHASE_KEY,
        defaults={"setting_value": "true" if enabled else "false"},
    )


def should_flag_backfill(joined, classification: str = "Teaching") -> bool:
    """Whether a newly enrolled member gets dues_backfill_pending=True.

    Default OFF: mid-year joiners pay current->future only, so never flag.
    When the chase switch is ON, flag non-Retired members joining after
    January (legacy behavior).
    """
    if joined is None or getattr(joined, "month", 1) <= 1:
        return False
    if (classification or "Teaching") == "Retired":
        return False
    return is_back_dues_chase_enabled()
