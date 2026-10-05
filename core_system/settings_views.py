import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core_system.guards import require_officer_session, require_role
from core_system.models import SystemSetting


BANNER_DURATION_KEY = "banner_duration_seconds"
BANNER_DURATION_DEFAULT = 6
BANNER_DURATION_MIN = 2
BANNER_DURATION_MAX = 60


def get_banner_duration_seconds() -> int:
    """Top-center banner display time in seconds (admin-configurable, default 6)."""
    try:
        row = SystemSetting.objects.filter(setting_key=BANNER_DURATION_KEY).first()
        if row is None:
            return BANNER_DURATION_DEFAULT
        value = int(float(row.setting_value))
        if value < BANNER_DURATION_MIN or value > BANNER_DURATION_MAX:
            return BANNER_DURATION_DEFAULT
        return value
    except (TypeError, ValueError):
        return BANNER_DURATION_DEFAULT


@require_http_methods(["GET", "PUT"])
def banner_duration_setting(request: HttpRequest):
    # Read: any logged-in officer (dashboards fetch this on load).
    # Write: Superadmin only (System Admin panel).
    if request.method == "GET":
        guard = require_officer_session(request)
        if guard:
            return guard
        setting, _ = SystemSetting.objects.get_or_create(
            setting_key=BANNER_DURATION_KEY,
            defaults={"setting_value": str(BANNER_DURATION_DEFAULT)},
        )
        return JsonResponse({
            "key": setting.setting_key,
            "value": get_banner_duration_seconds(),
        })

    guard = require_role(request, role="Superadmin")
    if guard:
        return guard

    try:
        body = json.loads(request.body)
        value = body.get("value")
        if value is None:
            return JsonResponse({"error": "value is required"}, status=400)
        int_value = int(value)
        if int_value < BANNER_DURATION_MIN or int_value > BANNER_DURATION_MAX:
            return JsonResponse(
                {"error": f"value must be between {BANNER_DURATION_MIN} and {BANNER_DURATION_MAX} seconds"},
                status=400,
            )
    except (ValueError, TypeError):
        return JsonResponse(
            {"error": f"value must be an integer between {BANNER_DURATION_MIN} and {BANNER_DURATION_MAX}"},
            status=400,
        )

    setting, _ = SystemSetting.objects.update_or_create(
        setting_key=BANNER_DURATION_KEY,
        defaults={"setting_value": str(int_value)},
    )
    return JsonResponse({
        "key": setting.setting_key,
        "value": int(setting.setting_value),
        "message": "Banner display time updated",
    })


@require_http_methods(["GET", "PUT"])
def grace_period_setting(request: HttpRequest):
    guard = require_role(request, role="president")
    if guard:
        return guard

    if request.method == "GET":
        setting, _ = SystemSetting.objects.get_or_create(
            setting_key="grace_period_days",
            defaults={"setting_value": "15"},
        )
        return JsonResponse({
            "key": setting.setting_key,
            "value": int(setting.setting_value),
        })

    try:
        body = json.loads(request.body)
        value = body.get("value")
        if value is None:
            return JsonResponse({"error": "value is required"}, status=400)
        int_value = int(value)
        if int_value < 1 or int_value > 60:
            return JsonResponse({"error": "value must be between 1 and 60"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"error": "value must be an integer between 1 and 60"}, status=400)

    setting, _ = SystemSetting.objects.update_or_create(
        setting_key="grace_period_days",
        defaults={"setting_value": str(int_value)},
    )
    return JsonResponse({
        "key": setting.setting_key,
        "value": int(setting.setting_value),
        "message": "Grace period updated",
    })


@require_http_methods(["GET", "PUT"])
def notification_settings(request: HttpRequest):
    guard = require_role(request, role="president")
    if guard:
        return guard

    if request.method == "GET":
        keys = ["reminder_intervals", "reminder_channels", "reminder_message_templates"]
        result = {}
        for key in keys:
            setting, _ = SystemSetting.objects.get_or_create(
                setting_key=key,
                defaults={"setting_value": "{}" if "template" in key else "[]" if "intervals" in key else "{}"},
            )
            try:
                result[key] = json.loads(setting.setting_value)
            except (json.JSONDecodeError, TypeError):
                result[key] = setting.setting_value
        return JsonResponse(result)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    allowed_keys = {"reminder_intervals", "reminder_channels", "reminder_message_templates"}
    for key, value in body.items():
        if key not in allowed_keys:
            continue
        serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        SystemSetting.objects.update_or_create(
            setting_key=key,
            defaults={"setting_value": serialized},
        )

    return JsonResponse({"message": "Notification settings updated"})
