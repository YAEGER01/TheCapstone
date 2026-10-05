from core_system.models import SystemSetting

NAV_MODULE_KEYS = {
    "sidebar": "nav_sidebar_enabled",
    "header_strip": "nav_header_strip_enabled",
}

_TRUTHY = {"true", "1", "yes", "on"}


def _nav_flag(key: str, default: bool = True) -> bool:
    row = SystemSetting.objects.filter(setting_key=key).first()
    if row is None:
        return default
    return (row.setting_value or "").strip().lower() in _TRUTHY


def get_nav_modules() -> dict[str, bool]:
    return {
        "sidebar": _nav_flag(NAV_MODULE_KEYS["sidebar"], True),
        "header_strip": _nav_flag(NAV_MODULE_KEYS["header_strip"], True),
    }


def set_nav_modules(sidebar: bool, header_strip: bool) -> None:
    if not sidebar and not header_strip:
        sidebar = True
    SystemSetting.objects.update_or_create(
        setting_key=NAV_MODULE_KEYS["sidebar"],
        defaults={"setting_value": "true" if sidebar else "false"},
    )
    SystemSetting.objects.update_or_create(
        setting_key=NAV_MODULE_KEYS["header_strip"],
        defaults={"setting_value": "true" if header_strip else "false"},
    )


def nav_modules_context(request):
    flags = get_nav_modules()
    ctx = {
        "nav_sidebar_enabled": flags["sidebar"],
        "nav_header_strip_enabled": flags["header_strip"],
    }
    try:
        from core_system.landing_sections import landing_sections_context as _landing_ctx
        ctx.update(_landing_ctx(request))
    except Exception:
        pass
    return ctx
