"""Role-scoped Audit Trail API.

Endpoints
---------
GET /api/audit/trail/                 -> paginated list (role scoped)
GET /api/audit/trail/<trail_id>/      -> Activity Details for one entry

Access
------
Treasurer : own recorded actions
Auditor   : operational/financial events (read-only, no security/system)
President : everything
Superadmin: security/system events
Member    : denied
"""

from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET
from django.db.models import Q

from core_system.audit_trail_utils import (
    AUDIT_ROLES,
    action_label,
    module_options,
    scoped_queryset,
    serialize_entry,
    tables_for_module,
)
from core_system.shared_view_utils import resolve_officer_from_session


def _forbidden(message="Forbidden for this role."):
    return JsonResponse({"ok": False, "error": message}, status=403)


def _current_role(request):
    return (request.session.get("role") or "").strip()


def _scoped_request_queryset(request):
    """Return (queryset, role) for the current session, or (None, role) if denied."""
    role = _current_role(request)
    if role not in AUDIT_ROLES:
        return None, role
    officer = resolve_officer_from_session(request)
    officer_id = getattr(officer, "user_id_PK", None)
    if officer_id is None:
        officer_id = request.session.get("officer_id")
    return scoped_queryset(role, officer_id), role


def _int_param(request, name, default):
    try:
        return int(request.GET.get(name, default))
    except (TypeError, ValueError):
        return default


@require_GET
def audit_trail_list(request):
    qs, role = _scoped_request_queryset(request)
    if qs is None:
        return _forbidden()

    base_qs = qs

    search = (request.GET.get("q") or "").strip()
    module_label = (request.GET.get("module") or "").strip()
    action = (request.GET.get("action") or "").strip()
    actor_role = (request.GET.get("role") or "").strip()
    status = (request.GET.get("status") or "").strip()
    date_from = parse_date(request.GET.get("date_from") or "")
    date_to = parse_date(request.GET.get("date_to") or "")

    if search:
        qs = qs.filter(
            Q(actor_name__icontains=search)
            | Q(action__icontains=search)
            | Q(notes__icontains=search)
            | Q(table_name__icontains=search)
        )
    if module_label:
        tables = tables_for_module(module_label)
        if tables:
            qs = qs.filter(table_name__in=tables)
        else:
            # No known table maps to this label -> match nothing.
            qs = qs.none()
    if action:
        qs = qs.filter(action__iexact=action)
    if actor_role:
        qs = qs.filter(actor_type__iexact=actor_role)
    if status:
        qs = qs.filter(result__iexact=status)
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)

    qs = qs.order_by("-timestamp", "-trail_id")

    limit = max(1, min(_int_param(request, "limit", 50), 200))
    offset = max(0, _int_param(request, "offset", 0))
    total = qs.count()
    entries = qs[offset : offset + limit]

    # Filter dropdown options reflect everything visible to the role.
    distinct_actions = list(
        base_qs.values_list("action", flat=True).distinct()
    )
    action_options = sorted(
        [{"value": a, "label": action_label(a)} for a in distinct_actions],
        key=lambda item: item["label"],
    )

    return JsonResponse(
        {
            "ok": True,
            "role": role,
            "entries": [serialize_entry(entry) for entry in entries],
            "total": total,
            "offset": offset,
            "limit": limit,
            "modules": module_options(base_qs),
            "actions": action_options,
        }
    )


@require_GET
def audit_trail_detail(request, trail_id):
    qs, role = _scoped_request_queryset(request)
    if qs is None:
        return _forbidden()

    entry = qs.filter(trail_id=trail_id).first()
    if entry is None:
        return JsonResponse({"ok": False, "error": "Audit entry not found."}, status=404)

    return JsonResponse({"ok": True, "entry": serialize_entry(entry, detail=True)})
