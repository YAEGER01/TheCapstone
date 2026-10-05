"""Landing-page visibility toggles (Superadmin -> public site).

Homepage cards (Announcements, News & Highlights, Quick Links, Live
Location, Placeholder) and header nav entries (About Us, Officers,
Activities & Events, Resources, News & Highlights) can each be hidden
without touching templates. Stored as SystemSetting rows
``landing_<key>`` = true/false; missing row = visible (default ON).
"""
from core_system.models import SystemSetting

# (key, label, description) — key doubles as the POST field + context suffix.
SECTION_META = [
    ("announcements", "Announcements card", "Homepage announcements column."),
    ("news_highlights", "News & Highlights card", "Homepage featured-news column."),
    ("quick_links", "Quick Links card", "Homepage shortcut tiles column."),
    ("live_location", "Live Location card", "Homepage campus-map column."),
    ("placeholder_card", "Placeholder card", "Homepage upcoming-feature tile (Join-Us CTA always stays)."),
    ("nav_about", "About Us menu", "Header navigation entry."),
    ("nav_officers", "Officers menu", "Header navigation entry."),
    ("nav_activities", "Activities & Events menu", "Header navigation entry."),
    ("nav_resources", "Resources menu", "Header navigation entry."),
    ("nav_news", "News & Highlights menu", "Header navigation entry."),
]

_SETTING_PREFIX = "landing_"
_TRUTHY = {"true", "1", "yes", "on"}


def _flag(key: str) -> bool:
    row = SystemSetting.objects.filter(setting_key=_SETTING_PREFIX + key).first()
    if row is None:
        return True
    return (row.setting_value or "").strip().lower() in _TRUTHY


def get_landing_sections() -> dict:
    """key -> visible bool."""
    return {key: _flag(key) for key, _label, _desc in SECTION_META}


def set_landing_sections(flags: dict) -> None:
    """Persist only the keys present in flags (partial updates safe)."""
    wanted = {key for key, _l, _d in SECTION_META if key in flags}
    for key, _label, _desc in SECTION_META:
        if key not in wanted:
            continue
        SystemSetting.objects.update_or_create(
            setting_key=_SETTING_PREFIX + key,
            defaults={"setting_value": "true" if flags.get(key) else "false"},
        )


def reset_landing_sections() -> None:
    SystemSetting.objects.filter(
        setting_key__in=[_SETTING_PREFIX + key for key, _l, _d in SECTION_META]
    ).delete()


def landing_setting_keys() -> list:
    return [_SETTING_PREFIX + key for key, _l, _d in SECTION_META]


def landing_sections_context(request):
    flags = get_landing_sections()
    return {f"landing_{key}": flags[key] for key, _l, _d in SECTION_META}


def landing_admin_cards() -> list:
    """Meta + live state for the Superadmin toggles card."""
    flags = get_landing_sections()
    return [
        {"key": key, "label": label, "desc": desc, "on": flags[key]}
        for key, label, desc in SECTION_META
    ]
