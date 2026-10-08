from core_system.models import SystemSetting

SHOW_OTHER_CAMPUS_KEY = "show_other_campus"

_TRUTHY = {"true", "1", "yes", "on"}


def is_other_campus_enabled() -> bool:
    """Whether the President monthly-deduction recipient picker offers Other Campus.

    Default ON: Death Aid / Other rows show the "Other Campus (external
    beneficiary)" option, the per-row Other-campus checkbox, and the
    campus + beneficiary inputs. When OFF, the option is hidden everywhere
    on the President dashboard — existing external rows already saved stay
    visible as history, but no new other-campus aid can be declared.
    """
    row = SystemSetting.objects.filter(setting_key=SHOW_OTHER_CAMPUS_KEY).first()
    if row is None:
        return True
    return (row.setting_value or "").strip().lower() in _TRUTHY


def set_other_campus_enabled(enabled: bool) -> None:
    SystemSetting.objects.update_or_create(
        setting_key=SHOW_OTHER_CAMPUS_KEY,
        defaults={"setting_value": "true" if enabled else "false"},
    )
