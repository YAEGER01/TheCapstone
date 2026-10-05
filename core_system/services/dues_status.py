"""Shared dues-status computation used by the Treasurer, Auditor and
President dashboards.

One definition of "who has paid for month M" (member-based, same as the
President overview and the compliance heatmap):

  - a member is PAID for M when they have a monthly_dues row for M whose
    payment_status is in Status.ALL_AUDITOR_VERIFIED (Paid / Full Payment /
    Auditor Verified / ...),
  - or they have an approved one-time MembershipFee and the dues record for M
    is itself paid/verified (fee months map to the fee's payment month),
  - otherwise PENDING when any M row is in Status.ALL_PENDING,
  - otherwise UNPAID (no qualifying row for M).

Membership fees paid in month M count toward M's compliance via the fee's
payment_date month — this keeps Treasurer/Auditor/President numbers identical
because they all call this one helper.
"""
import re
from datetime import date

from django.utils import timezone

from core_system.constants.status_constants import Status
from core_system.models import MembershipFee, MonthlyAssessment, MonthlyDues, Member


def dues_year_containers() -> dict:
    """Backend year containers for monthly dues (no wall-clock involved).

    Groups the months the organization has actually charged — final-approved
    MonthlyAssessments — by calendar year, so every obligation horizon in the
    system can be answered from backend data instead of the machine date::

        2026 container: Jan..Dec 2026 (ended once December was approved)
        2027 container: Jan 2027..frontier (the current batch)

    Returns ``{"containers": [...], "frontier": "YYYY-MM" | None,
    "current_year": int | None}`` where each container is
    ``{"year", "start", "end", "months", "closed"}``. ``frontier`` is the
    latest charged month (e.g. ``"2027-04"`` while everyone has paid April
    2027); drafts/pending months are never part of a container because no
    one owes a month that was never charged. ``closed`` is True for every
    year before the frontier's year — a closed batch accrues no new
    obligations. Empty when no month has been charged yet (callers fall
    back to the wall-clock month, preserving greenfield behaviour).
    """
    charged = MonthlyAssessment.objects.filter(
        status=MonthlyAssessment.STATUS_FINAL_APPROVED,
        month__isnull=False,
    ).values_list("month", flat=True)
    keys = sorted({d.strftime("%Y-%m") for d in charged if d is not None})
    if not keys:
        return {"containers": [], "frontier": None, "current_year": None}
    frontier = keys[-1]
    current_year = int(frontier[:4])
    by_year: dict[int, list[str]] = {}
    for key in keys:
        by_year.setdefault(int(key[:4]), []).append(key)
    containers = [
        {
            "year": year,
            "start": months[0],
            "end": months[-1],
            "months": months,
            "closed": year < current_year,
        }
        for year, months in sorted(by_year.items())
    ]
    return {"containers": containers, "frontier": frontier, "current_year": current_year}


def dues_frontier_month(default: str = "") -> str:
    """Latest charged dues month (``YYYY-MM``), or ``default``/now when empty."""
    frontier = dues_year_containers()["frontier"]
    if frontier:
        return frontier
    return default or timezone.now().strftime("%Y-%m")


def container_start_for(frontier_month: str) -> str:
    """First month (``YYYY-MM``) of the frontier's year container."""
    return (frontier_month or "")[:4] + "-01" if frontier_month else ""


def resolve_month_key(request, default: str = "") -> str:
    """Read ?month= / ?year= from a request and normalise to YYYY-MM.

    Accepts month as 1-2 digits (with optional year) or a full YYYY-MM string;
    falls back to `default` (or the current month) when absent/invalid. This
    keeps the three dashboards' banners working regardless of format."""
    month = (request.GET.get("month") or "").strip()
    year = (request.GET.get("year") or "").strip()
    if re.fullmatch(r"\d{1,2}", month):
        if not re.fullmatch(r"\d{4}", year):
            year = timezone.now().strftime("%Y")
        return "{}-{:02d}".format(int(year), int(month))
    if re.fullmatch(r"\d{4}-\d{2}", month):
        return month
    # Default to the backend dues frontier (what is actually being
    # collected), not the machine date — falls back to now when nothing
    # was charged yet.
    return default or dues_frontier_month()


def dues_status_for_month(month_key: str, include_retired: bool = False) -> dict:
    """Compute member-based dues status for a YYYY-MM month key.

    Returns {month, paid, pending, unpaid, total, paid_percentage,
    pending_percentage, unpaid_percentage} — the exact payload shape the three
    dashboards already render.
    """
    try:
        year, month = month_key.split("-")
        year, month = int(year), int(month)
    except (ValueError, AttributeError):
        month_key = timezone.now().strftime("%Y-%m")
    year_s, month_s = month_key.split("-")

    members = Member.objects.all()
    if not include_retired:
        members = members.exclude(membership_status__iexact="retired")

    paid_statuses = set(Status.ALL_AUDITOR_VERIFIED)
    pending_statuses = set(Status.ALL_PENDING)

    # Dues rows for the month: best status per member (paid beats pending).
    dues = MonthlyDues.objects.filter(month_covered=month_key)
    best = {}  # member_id -> "paid" | "pending"
    for d in dues:
        st = str(d.payment_status)
        cur = best.get(d.member_id_FK_id)
        if st in paid_statuses:
            best[d.member_id_FK_id] = "paid"
        elif st in pending_statuses and cur != "paid":
            best.setdefault(d.member_id_FK_id, "pending")

    # Membership fees: an approved fee counts its payment month as paid
    # (same rule the President overview applies, but scoped to the month).
    fees = MembershipFee.objects.filter(payment_status__in=paid_statuses)
    for f in fees:
        if f.payment_date is not None:
            fee_month = f.payment_date.strftime("%Y-%m")
            if fee_month == month_key:
                best[f.member_id_FK_id] = "paid"

    paid = pending = 0
    for m in members:
        state = best.get(m.member_id_PK)
        if state == "paid":
            paid += 1
        elif state == "pending":
            pending += 1
    total = members.count()
    unpaid = max(0, total - paid - pending)

    return {
        "month": month_key,
        "paid": paid,
        "pending": pending,
        "unpaid": unpaid,
        "total": total,
        "paid_percentage": round(paid / total * 100, 1) if total else 0.0,
        "pending_percentage": round(pending / total * 100, 1) if total else 0.0,
        "unpaid_percentage": round(unpaid / total * 100, 1) if total else 0.0,
    }
