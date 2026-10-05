"""Shared helpers for the role-scoped Audit Trail feature.

Everything here works off the existing `GlobalAuditTrail` model. The module
name shown in the UI and used for filtering is derived from `table_name`, and
actions are translated to human-friendly labels. The `result` column stores the
Success/Failed/Pending status.

Note: `_compute_entry_hash` INCLUDES `result` (Success/Failed/Pending) since
the hash-chain hardening fix. Rows written before the fix verify under the
legacy scheme and are reported as `legacy_hash_scheme` (not silently valid).
"""

from django.apps import apps
from django.db.models import Q

from core_system.models import GlobalAuditTrail

# Friendly module names keyed by the DB table_name stored on GlobalAuditTrail.
MODULE_LABELS = {
    "contribution": "Contributions",
    "member_contribution": "Contributions",
    "monthly_assessments": "Monthly Dues",
    "member_assessments": "Monthly Dues",
    "medical_aid": "Medical Aid",
    "death_aid": "Death Aid",
    "aid_tracking_post": "Aid Tracking",
    "AID_TRACKING_POST": "Aid Tracking",
    "payroll_batch": "Payroll",
    "PAYROLL_BATCH": "Payroll",
    "member_registration_request": "Member Registration",
    "member": "Member Records",
    "organization_fund_report": "Fund Reports",
    "fund_report": "Fund Reports",
    "officer_user": "System / Security",
    "access_session": "System / Security",
    "system_setting": "System / Security",
    "financial_document_archive": "Document Repository",
}

ACTION_LABELS = {
    "CREATED": "Created",
    "CREATE": "Created",
    "ACCOUNT_ACTIVATED": "Account Activated",
    "RESUBMITTED": "Resubmitted",
    "VERIFIED": "Verified",
    "AUDITOR_VERIFIED": "Verified by Auditor",
    "FINISH_VERIFIED": "Finish Verified",
    "APPROVED": "Approved",
    "REJECTED": "Rejected",
    "RETURNED": "Returned",
    "RETURN": "Returned",
    "RETURNED_TO_TREASURER": "Returned to Treasurer",
    "REJECTED_BY_PRESIDENT": "Rejected by President",
    "RELEASED": "Released",
    "PAID": "Paid",
    "SKIPPED": "Skipped",
    "SUBMIT": "Submitted",
    "SUBMITTED_FOR_AUDIT": "Submitted for Audit",
    "APPROVE": "Approved",
    "REJECT": "Rejected",
    "VERIFY": "Verified",
    "UPLOAD": "Uploaded",
    "DELETE": "Deleted",
    "REVISED": "Revised",
    "FINISH_REQUESTED": "Finish Requested",
    "FINISH_REJECTED": "Finish Rejected",
    "LOGIN": "Logged In",
    "LOGOUT": "Logged Out",
    "LOGIN_FAILED": "Failed Login",
    "LOGIN_MFA_REQUIRED": "Login (MFA Required)",
    "ZT_CONFIRM": "Zero-Trust Confirmed",
    "PASSWORD_CHANGED": "Password Changed",
}

# Tables/actions considered "security / system" rather than financial-operational.
SECURITY_TABLES = {"officer_user", "access_session", "system_setting"}
SECURITY_ACTIONS = {
    "LOGIN",
    "LOGOUT",
    "LOGIN_FAILED",
    "LOGIN_MFA_REQUIRED",
    "ZT_CONFIRM",
    "PASSWORD_CHANGED",
    "ACCOUNT_CREATED",
    "ACCOUNT_UPDATED",
    "ACCOUNT_DEACTIVATED",
    "BACKUP",
    "RESTORE",
    "SAFETY_THRESHOLD_UPDATED",
}

AUDIT_ROLES = ("Treasurer", "Auditor", "President", "Superadmin")

# Friendly column labels for the "Changes" table. Anything not listed is
# humanised automatically (member_id -> "Member", updated_at -> "Updated At"...).
FIELD_LABELS = {
    "member_id": "Member",
    "member_id_FK": "Member",
    "officer_user_id": "Officer",
    "officer_user_id_FK": "Officer",
    "created_by_user_id_FK": "Created By",
    "updated_by_user_id_FK": "Updated By",
    "recorded_by_user_id_FK": "Recorded By",
    "processed_by_user_id_FK": "Processed By",
    "membership_category": "Membership Category",
    "membership_type": "Membership Type",
    "membership_status": "Membership Status",
    "member_classification": "Classification",
    "fee_id": "Membership Fee",
    "amount": "Amount",
}

_MODEL_BY_TABLE = None


def _models_by_table():
    global _MODEL_BY_TABLE
    if _MODEL_BY_TABLE is None:
        mapping = {}
        for model in apps.get_models():
            mapping.setdefault(model._meta.db_table.lower(), model)
        _MODEL_BY_TABLE = mapping
    return _MODEL_BY_TABLE


def _strip_id_suffix(field_name):
    name = field_name or ""
    for suffix in ("_id_FK", "_id"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _field_label(field_name):
    name = field_name or ""
    if name in FIELD_LABELS:
        return FIELD_LABELS[name]
    base = _strip_id_suffix(name).replace("_", " ").strip()
    return base.title() or name


def _relation_model(field_name):
    name = field_name or ""
    base = _strip_id_suffix(name)
    if base == name:
        return None
    return _models_by_table().get(base.lower())


def _display_value(field_name, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict):
        return value.get("name") or value.get("id") or ""
    model = _relation_model(field_name)
    if model is None or str(value).strip() == "":
        return value
    try:
        pk = int(value)
    except (TypeError, ValueError):
        return value
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        return f"#{pk}"
    for attr in ("full_name", "name", "title", "position_name", "username"):
        display = getattr(obj, attr, None)
        if display:
            return display
    return str(obj)


def build_changes(table_name, old_values, new_values):
    """Turn raw old/new JSON into display-ready {field, previous, new} rows.

    Foreign-key ids (member_id, officer_user_id, ...) are resolved to the
    related record's name so the UI never shows a bare numeric id.
    """
    old_values = old_values if isinstance(old_values, dict) else {}
    new_values = new_values if isinstance(new_values, dict) else {}

    keys = []
    for source in (old_values, new_values):
        for key in source.keys():
            if key not in keys:
                keys.append(key)

    changes = []
    for key in keys:
        previous = _display_value(key, old_values.get(key)) if key in old_values else ""
        current = _display_value(key, new_values.get(key)) if key in new_values else ""
        changes.append(
            {
                "field": _field_label(key),
                "previous": previous,
                "new": current,
                "changed": previous != current,
            }
        )
    return changes


def _module_for_table(table_name):
    table = (table_name or "").strip()
    return (
        MODULE_LABELS.get(table)
        or MODULE_LABELS.get(table.lower())
        or table.replace("_", " ").title()
        or "Other"
    )


def module_for(entry):
    return _module_for_table(entry.table_name)


def action_label(action):
    raw = (action or "").strip()
    return ACTION_LABELS.get(raw) or raw.replace("_", " ").title() or "Unknown"


def record_label(entry):
    module = module_for(entry)
    if entry.record_id:
        return f"{module} #{entry.record_id}"
    return module


def is_security_entry(entry):
    return (entry.table_name in SECURITY_TABLES) or (entry.action in SECURITY_ACTIONS)


def tables_for_module(module_label):
    """Reverse lookup: friendly module label -> list of table_name values."""
    return [table for table, label in MODULE_LABELS.items() if label == module_label]


def scoped_queryset(role, officer_id):
    """Return the GlobalAuditTrail queryset a role is allowed to see.

    - President : everything
    - Auditor   : operational/financial only (no security/system events)
    - Treasurer : only their own recorded actions
    - Superadmin: security/system events only
    - anything else (e.g. Member): empty
    """
    qs = GlobalAuditTrail.objects.all()
    role = (role or "").strip()
    if role == "President":
        return qs
    if role == "Auditor":
        return qs.exclude(table_name__in=SECURITY_TABLES).exclude(
            action__in=SECURITY_ACTIONS
        )
    if role == "Treasurer":
        if officer_id is None:
            return qs.none()
        return qs.filter(actor_id=officer_id)
    if role == "Superadmin":
        return qs.filter(
            Q(table_name__in=SECURITY_TABLES) | Q(action__in=SECURITY_ACTIONS)
        )
    return qs.none()


def module_options(queryset):
    """Distinct friendly module labels actually present in a queryset."""
    tables = queryset.values_list("table_name", flat=True).distinct()
    return sorted({_module_for_table(table) for table in tables if table})


def serialize_entry(entry, detail=False):
    data = {
        "trail_id": entry.trail_id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "actor_name": entry.actor_name or "Unknown",
        "actor_role": entry.actor_type or "",
        "actor_id": entry.actor_id,
        "action": entry.action,
        "action_label": action_label(entry.action),
        "module": module_for(entry),
        "table_name": entry.table_name,
        "record_id": entry.record_id,
        "record_label": record_label(entry),
        "status": entry.result or "Success",
        "notes": entry.notes or "",
        "ip_address": str(entry.ip_address) if entry.ip_address else None,
        "device_info": entry.device_info or "",
    }
    if detail:
        data["old_values"] = entry.old_values
        data["new_values"] = entry.new_values
        data["changes"] = build_changes(entry.table_name, entry.old_values, entry.new_values)
    return data
