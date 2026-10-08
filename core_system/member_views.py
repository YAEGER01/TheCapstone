from __future__ import annotations

import json
import calendar
import logging
from math import ceil
from datetime import date, timedelta, datetime as dt
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Sum
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

from core_system.auth_utils import (
    hash_password,
    hash_pin,
    validate_new_password,
    verify_password,
    verify_pin,
)
from core_system.constants.policy_constants import (
    check_medical_aid_once_per_year,
    get_death_aid_amount,
    get_membership_fee_amount,
    get_monthly_dues_amount,
    is_retired_member,
)
from core_system.constants.status_constants import Status
from core_system.guards import require_officer_session
from core_system.ledger_utils import (
    approved_member_assessments,
    build_member_assessment_breakdown,
    member_deduction_overview,
    member_unpaid_months as member_unpaid_month_entries,
    membership_fee_summary,
)
from core_system.models import (
    AccessSession,
    AidTrackingPost,
    Claimant,
    Contribution,
    DeathAid,
    MedicalAid,
    Member,
    MemberAssessment,
    MemberLedger,
    MembershipFee,
    MonthlyDues,
    Notification,
    OfficerUser,
    SupportingProof,
    TransactionVerification,
    Certificate,
    Event,
    SalaryDeductionExemption,
)
from core_system.shared_view_utils import (
    _link_proof_to_record,
    proof_upload_blocked_response,
    _log_sensitive_read,
    _record_audit_trail,
    validate_isu_email,
    validate_ph_contact,
)
from core_system.services import member_transparency as transparency
from core_system.services.dues_status import dues_frontier_month, dues_year_containers

MEMBERSHIP_FEE_SUBMITTED_STATUSES = {"Paid", "Full Payment", "Partial", "Pending"}


def _get_member_from_session(request: HttpRequest) -> tuple[Member | None, str]:
    officer_id = request.session.get("officer_id")
    if not officer_id:
        return None, "No active session"
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
        member = Member.objects.filter(officer_user_id_FK=officer).first()
        if not member:
            return None, "No linked member profile"
        return member, ""
    except OfficerUser.DoesNotExist:
        return None, "Officer not found"


def _compute_dues_summary(member: Member) -> dict:
    """Paid/pending totals plus outstanding balance for a member's monthly dues.

    Uses the canonical Status.ALL_AUDITOR_VERIFIED set for "paid" so records
    written by the president ("Full Payment") and treasurer ("Paid") are both
    counted. Outstanding balance is the monthly-dues value of months the member
    has not yet covered (neither paid nor pending), starting the month after
    joining — the same obligation window used by member_unpaid_months. Members
    with final-approved salary-deduction months instead use that workflow's
    paid and outstanding totals.
    """
    all_dues = MonthlyDues.objects.filter(member_id_FK=member).order_by("-month_covered")
    total_dues_paid = float(
        all_dues.filter(payment_status__in=Status.ALL_AUDITOR_VERIFIED).aggregate(t=Sum("amount"))["t"] or 0
    )
    total_dues_pending = float(
        all_dues.filter(payment_status=Status.PENDING).aggregate(t=Sum("amount"))["t"] or 0
    )

    joined = member.date_joined or (timezone.now().date() - timedelta(days=365))
    covered = set(
        all_dues.filter(
            payment_status__in=["Pending", "Paid", "Full Payment"],
        ).values_list("month_covered", flat=True)
    )
    # Months with an approved salary-deduction exemption are not owed, so they
    # should not count toward the outstanding balance either.
    covered.update(
        SalaryDeductionExemption.objects.filter(
            member_id_FK=member,
            status__in=["Pending", "Approved"],
        ).values_list("month_covered", flat=True)
    )
    unpaid_count = 0
    year, month = joined.year, joined.month + 1
    if month > 12:
        year += 1
        month = 1
    # Backend year container: the obligation window ends at the latest
    # charged dues month (e.g. April 2027 once everyone paid it) — never at
    # the machine date — and never starts inside a closed container (the
    # 2026 batch ended after December 2026; the current batch starts
    # January 2027). Falls back to the wall-clock month when no month has
    # been charged yet.
    calendar = dues_year_containers()
    frontier = calendar["frontier"]
    if frontier:
        start_key = max(f"{year}-{month:02d}", frontier[:4] + "-01")
        year, month = int(start_key[:4]), int(start_key[5:7])
        end_year, end_month = int(frontier[:4]), int(frontier[5:7])
    else:
        today = timezone.now().date()
        end_year, end_month = today.year, today.month
    while (year < end_year) or (year == end_year and month <= end_month):
        if f"{year}-{month:02d}" not in covered:
            unpaid_count += 1
        month += 1
        if month > 12:
            month = 1
            year += 1

    outstanding_balance = round(float(get_monthly_dues_amount()) * unpaid_count, 2)
    deduction_overview = member_deduction_overview(member)
    if deduction_overview is not None:
        # A member with final-approved salary-deduction months is measured by
        # the deduction workflow, not by the legacy direct-payment records.
        # This is the same approved-month data shown in History and emails.
        total_dues_paid = deduction_overview["total_paid"]
        outstanding_balance = deduction_overview["outstanding_balance"]
    if is_retired_member(member):
        # Retirement ends the current obligation. Historical months remain
        # visible, but they no longer create an outstanding balance.
        outstanding_balance = 0.0
    return {
        "all_dues": all_dues,
        "total_dues_paid": total_dues_paid,
        "total_dues_pending": total_dues_pending,
        "outstanding_balance": outstanding_balance,
        "total_dues_unpaid": outstanding_balance,
    }


@require_GET
def member_notifications(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    page = max(1, int(request.GET.get("page", "1") or 1))
    page_size = max(1, min(50, int(request.GET.get("page_size", "4") or 4)))
    notif_filter = (request.GET.get("filter", "all") or "all").strip().lower()

    notifs_qs = Notification.objects.filter(
        recipient_type="member",
        recipient_id=member.member_id_PK,
    )
    # Finance = anything money-related. Categories are matched explicitly,
    # plus legacy rows stored without a category whose type is financial
    # (e.g. older Monthly Deduction notices).
    FINANCE_CATEGORIES = (
        "payment", "dues", "monthly_dues", "membership_fee",
        "aid_contribution", "claim", "finance", "contribution",
    )
    FINANCE_TYPES = (
        "Monthly Deduction", "Outstanding Reminder", "Payment Approved",
        "Payment Returned", "Aid Contribution Required", "Aid Released",
        "Claim Submitted", "Claim Update", "Claim Approved",
    )
    if notif_filter == "unread":
        notifs_qs = notifs_qs.filter(is_read=False)
    elif notif_filter == "attendance":
        notifs_qs = notifs_qs.filter(category__iexact="attendance")
    elif notif_filter == "announcement":
        # Announcements = explicitly categorized rows plus anything that is
        # not finance-related, so the tab is never silently empty when
        # general/member notices exist.
        finance_q = (
            Q(category__in=FINANCE_CATEGORIES)
            | Q(category__isnull=True, notification_type__in=FINANCE_TYPES)
        )
        notifs_qs = notifs_qs.filter(
            Q(category__iexact="announcement")
            | Q(notification_type__iexact="announcement")
            | ~finance_q
        )
    elif notif_filter == "finance":
        notifs_qs = notifs_qs.filter(
            Q(category__in=FINANCE_CATEGORIES)
            | Q(category__isnull=True, notification_type__in=FINANCE_TYPES)
        )

    total_items = notifs_qs.count()
    total_pages = ceil(total_items / page_size) if total_items else 0
    if total_pages and page > total_pages:
        page = total_pages
    offset = (page - 1) * page_size
    notifs = notifs_qs.order_by("-sent_at", "-notification_id_PK")[offset:offset + page_size]

    items = []
    for n in notifs:
        items.append({
            "id": n.notification_id_PK,
            "type": n.notification_type,
            "message": n.message,
            "category": n.category or "",
            "sent_at": n.sent_at.isoformat() if n.sent_at else "",
            "is_read": n.is_read,
            "sender_name": n.sender_name or "",
            "sender_role": n.sender_role or "",
            "receipt_number": n.receipt_number or "",
        })

    return JsonResponse({
        "ok": True,
        "items": items,
        "count": len(items),
        "total_items": total_items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": total_pages > 0 and page < total_pages,
        "filter": notif_filter,
    })


def _member_assessment_history_entry(member_assessment):
    """History row for an approved month without a MemberLedger posting."""
    assessment = member_assessment.assessment_id_FK
    if assessment is None:
        return None
    detail = build_member_assessment_breakdown(member_assessment)
    recorded_at = member_assessment.approved_at
    if recorded_at is None:
        recorded_at = timezone.make_aware(
            dt.combine(assessment.month, dt.min.time())
        )
    approver = member_assessment.approved_by_id_FK
    return {
        "id": f"assessment_{member_assessment.member_assessment_id_PK}",
        "transaction_type": "monthly_dues",
        "amount": float(member_assessment.actual_deduction or 0),
        "direction": "credit",
        "description": f"Monthly Deduction - {assessment.month_label}",
        "reference_id": member_assessment.member_assessment_id_PK,
        "reference_type": "MemberAssessment",
        "recorded_at": recorded_at.isoformat(),
        "recorded_by": approver.full_name if approver else "System",
        "breakdown": detail,
        "outstanding_after": detail["outstanding"],
        "_sort_key": recorded_at,
    }


@require_GET
def member_ledger(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    ledger_entries = MemberLedger.objects.filter(
        member_id_FK=member
    ).select_related("recorded_by_user_id_FK")

    # This endpoint powers Monthly Deductions History, so it is scoped to
    # monthly dues. The one-time membership fee is returned separately and is
    # never included in the monthly totals or outstanding balance.
    fee_summary = membership_fee_summary(member)
    monthly_rows = []

    if ledger_entries.exists():
        monthly_ledger_entries = [
            entry
            for entry in ledger_entries.order_by("recorded_at", "ledger_id_PK")
            if entry.transaction_type == "monthly_dues"
        ]
        approved_assessments = list(
            approved_member_assessments(member).prefetch_related(
                "allocations__assessment_item_id_FK",
                "assessment_id_FK__items",
            )
        )
        assessments_by_id = {
            member_assessment.member_assessment_id_PK: member_assessment
            for member_assessment in approved_assessments
        }
        for entry in monthly_ledger_entries:
            assessment_detail = None
            outstanding_after = None
            if (
                entry.reference_type == "MemberAssessment"
                and entry.reference_id in assessments_by_id
            ):
                assessment_detail = build_member_assessment_breakdown(
                    assessments_by_id[entry.reference_id]
                )
                outstanding_after = assessment_detail["outstanding"]
            monthly_rows.append(
                (
                    entry.recorded_at,
                    {
                        "id": entry.ledger_id_PK,
                        "transaction_type": entry.transaction_type,
                        "amount": float(entry.amount),
                        "direction": entry.direction,
                        "description": entry.description,
                        "reference_id": entry.reference_id,
                        "reference_type": entry.reference_type,
                        "recorded_at": entry.recorded_at.isoformat() if entry.recorded_at else "",
                        "recorded_by": entry.recorded_by_user_id_FK.full_name if entry.recorded_by_user_id_FK else "System",
                        "breakdown": assessment_detail,
                        "outstanding_after": outstanding_after,
                    },
                )
            )
        covered_assessment_ids = {
            int(entry.reference_id)
            for entry in monthly_ledger_entries
            if entry.reference_type == "MemberAssessment"
            and entry.reference_id is not None
        }
        for member_assessment in approved_assessments:
            if member_assessment.member_assessment_id_PK in covered_assessment_ids:
                continue
            synthetic = _member_assessment_history_entry(member_assessment)
            if synthetic is not None:
                monthly_rows.append((synthetic.pop("_sort_key"), synthetic))
    else:
        # No MemberLedger entries exist: show fully approved legacy dues and
        # any final-approved assessment months directly.
        dues = MonthlyDues.objects.filter(
            member_id_FK=member,
            payment_date__isnull=False,
            payment_status__in=["Paid", "Full Payment"]
        ).order_by("-payment_date")

        for d in dues:
            recorded_at = timezone.make_aware(dt.combine(d.payment_date, dt.min.time()))
            monthly_rows.append(
                (
                    recorded_at,
                    {
                        "id": f"dues_{d.dues_id_PK}",
                        "transaction_type": "monthly_dues",
                        "amount": float(d.amount),
                        "direction": "credit",
                        "description": f"Monthly Dues - {d.month_covered}",
                        "reference_id": d.dues_id_PK,
                        "reference_type": "MonthlyDues",
                        "recorded_at": d.payment_date.isoformat(),
                        "recorded_by": "System",
                        "breakdown": None,
                        "outstanding_after": None,
                    },
                )
            )
        for member_assessment in approved_member_assessments(member).prefetch_related(
            "allocations__assessment_item_id_FK",
            "assessment_id_FK__items",
        ):
            synthetic = _member_assessment_history_entry(member_assessment)
            if synthetic is not None:
                monthly_rows.append((synthetic.pop("_sort_key"), synthetic))

    monthly_rows.sort(key=lambda row: row[0])
    monthly_running_balance = Decimal("0.00")
    entries = []
    for _, row in monthly_rows:
        if row["direction"] == "credit":
            monthly_running_balance += Decimal(str(row["amount"]))
        else:
            monthly_running_balance -= Decimal(str(row["amount"]))
        row["balance_after"] = float(monthly_running_balance)
        entries.append(row)

    # Present newest first for the dashboard table.
    entries.reverse()
    dues_summary = _compute_dues_summary(member)
    monthly_total_debits = round(
        sum(row["amount"] for row in entries if row["direction"] == "debit"), 2
    )
    monthly_total_paid = round(dues_summary["total_dues_paid"] - monthly_total_debits, 2)
    monthly_outstanding = dues_summary["outstanding_balance"]

    return JsonResponse({
        "ok": True,
        "entries": entries,
        "current_balance": monthly_outstanding,
        "total_credits": monthly_total_paid,
        "total_debits": monthly_total_debits,
        "total_entries": len(entries),
        "monthly_total_paid": monthly_total_paid,
        "monthly_total_debits": monthly_total_debits,
        "monthly_outstanding": monthly_outstanding,
        "monthly_running_balance": float(monthly_running_balance),
        "membership_fee": fee_summary,
    })


@require_GET
def member_unpaid_months(request: HttpRequest):
    """Return list of unpaid months for monthly dues."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    current_date = timezone.now().date()

    # Determine when member should start owing monthly dues
    # Priority: membership fee payment date > date_joined
    # Members owe monthly dues from the month AFTER they paid their membership fee
    start_owing_date = None
    
    # Check if member has a paid membership fee
    try:
        membership_payment = MembershipFee.objects.filter(
            member_id_FK=member,
            payment_status__in=["Paid", "Full Payment"]
        ).order_by('payment_date').first()
        
        if membership_payment and membership_payment.payment_date:
            # Member owes from the month AFTER membership was paid
            start_owing_date = membership_payment.payment_date
    except:
        pass
    
    # If no membership payment found, use date_joined
    if not start_owing_date:
        start_owing_date = member.date_joined
    
    if not start_owing_date:
        start_owing_date = timezone.now().date() - timedelta(days=365)  # Default to 1 year ago if not set

    # Get all paid months
    paid_months = set()
    paid_dues = MonthlyDues.objects.filter(
        member_id_FK=member,
        payment_status__in=["Paid", "Full Payment"]
    ).values_list('month_covered', flat=True)

    for month_str in paid_dues:
        try:
            paid_months.add(month_str)
        except:
            pass
    
    # Months that already have a monthly-dues record (paid, pending, or fully approved)
    # so the member cannot be offered them again in the exemption request dropdown.
    # Exclude salary deductions from covered months since they're processed differently
    covered_months = set(
        MonthlyDues.objects.filter(
            member_id_FK=member,
        ).exclude(payment_method="Salary Deduction").values_list("month_covered", flat=True)
    )
    covered_months.update(paid_months)

    # Months covered by a salary-deduction exemption (pending or approved).
    # These months are not owed, so they must not appear as unpaid/selectable
    # and should not be offered again for another exemption request.
    exempted_months = set(
        SalaryDeductionExemption.objects.filter(
            member_id_FK=member,
            status__in=["Pending", "Approved"],
        ).values_list("month_covered", flat=True)
    )

    # Get approved contribution months (AidTrackingPost with status closed/tracking)
    # Note: AidTrackingPost doesn't have direct member link, so we check for active posts
    approved_contribution_months = set()
    try:
        contribution_posts = AidTrackingPost.objects.filter(
            aid_type__icontains='contribution',
            is_active=True
        ).values_list('target_month', flat=True)
        
        for month_str in contribution_posts:
            if month_str:
                try:
                    # target_month is in YYYY-MM format
                    approved_contribution_months.add(month_str)
                except:
                    pass
    except Exception as e:
        # If there's an error with AidTrackingPost query, log it but continue
        logging.warning(f"Error querying AidTrackingPost: {e}")
        pass

    # Calculate unpaid months from start_owing_date through the backend
    # dues frontier (never the machine date alone): months the organization
    # has actually charged. Closed containers don't accrue — the window
    # never starts inside one (a 2026 batch ended after December 2026 means
    # owing starts January 2027). Falls back to the wall-clock month when no
    # month has been charged yet.
    unpaid_months = []
    calendar = dues_year_containers()
    frontier = calendar["frontier"]
    if frontier:
        current_year, current_month = int(frontier[:4]), int(frontier[5:7])
    else:
        current_year = current_date.year
        current_month = current_date.month

    # Start from the month after start_owing_date
    start_year = start_owing_date.year
    start_month = start_owing_date.month + 1
    if start_month > 12:
        start_year += 1
        start_month = 1
    if frontier:
        start_key = max(
            f"{start_year}-{start_month:02d}", frontier[:4] + "-01"
        )
        start_year, start_month = int(start_key[:4]), int(start_key[5:7])

    # Iterate through months
    year = start_year
    month = start_month

    while (year < current_year) or (year == current_year and month <= current_month):
        month_str = f"{year}-{month:02d}"

        if month_str not in paid_months and month_str not in approved_contribution_months and month_str not in exempted_months:
            # Format month for display
            month_name = dt(year, month, 1).strftime("%B %Y")
            unpaid_months.append({
                "month": month_str,
                "display_name": month_name,
                "is_overdue": (year < current_year) or (year == current_year and month < current_month)
            })

        month += 1
        if month > 12:
            month = 1
            year += 1

    # Advance payment option: include upcoming months so members can pay early (indefinite/continuous)
    # Show next 5 years (60 months) of future months for advance payments,
    # counted from the dues frontier (months past what was charged yet).
    for i in range(1, 61):  # Next 60 months (5 years)
        adv_year = current_year
        adv_month = current_month + i
        if adv_month > 12:
            adv_year += (adv_month - 1) // 12
            adv_month = ((adv_month - 1) % 12) + 1
        advance_month_str = f"{adv_year}-{adv_month:02d}"

        if advance_month_str not in paid_months and advance_month_str not in approved_contribution_months and advance_month_str not in exempted_months:
            advance_month_name = dt(adv_year, adv_month, 1).strftime("%B %Y")
            unpaid_months.append({
                "month": advance_month_str,
                "display_name": advance_month_name,
                "is_overdue": False,
                "is_advance": True,
            })

    return JsonResponse({
        "ok": True,
        "unpaid_months": unpaid_months,
        "total_unpaid": len(unpaid_months),
        "covered_months": sorted(covered_months),
        "exempted_months": sorted(exempted_months),
    })


@require_POST
def member_mark_notifications_read(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    updated = Notification.objects.filter(
        recipient_type="member",
        recipient_id=member.member_id_PK,
        is_read=False,
    ).update(is_read=True)

    return JsonResponse({
        "ok": True,
        "message": f"{updated} notifications marked as read.",
        "updated_count": updated,
    })


@require_POST
def member_mark_notification_read(request: HttpRequest, notification_id: int):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    updated = Notification.objects.filter(
        notification_id_PK=notification_id,
        recipient_type="member",
        recipient_id=member.member_id_PK,
    ).update(is_read=True)

    return JsonResponse({
        "ok": True,
        "updated_count": updated,
    })


@require_GET
def member_attendance_summary(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)
    
    try:
        from core_system.models import Attendance, Event
        
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 6))
        
        # Get all attendance records for this member
        attendances = Attendance.objects.filter(member_id_FK=member).select_related('event_id_FK')
        
        present = attendances.filter(status='Present').count()
        late = attendances.filter(status='Late').count()
        absent = attendances.filter(status='Absent').count()
        total_events = attendances.count()
        
        # Calculate attendance rate
        attendance_rate = 0
        if total_events > 0:
            attendance_rate = round((present / total_events) * 100, 1)
        
        # Calculate total events attended (Present + Late)
        total_events_attended = present + late
        
        # Calculate current streak (consecutive events attended from most recent)
        current_streak = 0
        if attendances.exists():
            # Get attendance records sorted by date (most recent first)
            sorted_attendances = attendances.order_by('-date', '-check_in_time')
            for att in sorted_attendances:
                if att.status in ['Present', 'Late']:
                    current_streak += 1
                else:
                    break  # Streak broken by absence or other status
        
        # Build paginated attendance history
        total_pages = max(1, (total_events + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        
        history = []
        for att in attendances.order_by('-date', '-check_in_time')[start:end]:
            event = att.event_id_FK
            history.append({
                'event_title': event.title if event else 'Unknown Event',
                'event_date': event.event_date.strftime('%B %d, %Y') if event else 'N/A',
                'status': att.status,
                'check_in_time': att.check_in_time.strftime('%I:%M %p') if att.check_in_time else 'N/A',
            })
        
        return JsonResponse({
            "ok": True,
            "present": present,
            "late": late,
            "absent": absent,
            "total_events": total_events,
            "total_events_attended": total_events_attended,
            "current_streak": current_streak,
            "total_pages": total_pages,
            "current_page": page,
            "attendance_rate": attendance_rate,
            "history": history,
            "message": f"Current streak: {current_streak} events. Attendance rate: {attendance_rate}%." if total_events > 0 else "No attendance records yet.",
        })
        
    except Exception as e:
        return JsonResponse({
            "ok": False,
            "error": str(e)
        }, status=500)


@require_GET
def member_events(request: HttpRequest):
    """
    Get all events (upcoming and past) for member
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)
    
    try:
        from core_system.models import Event
        from django.utils import timezone
        
        today = timezone.now().date()
        
        # Get upcoming and ongoing events
        upcoming_events = Event.objects.filter(
            event_date__gte=today,
            status=Event.STATUS_UPCOMING
        ).order_by('event_date', 'event_time')
        
        ongoing_events = Event.objects.filter(
            status=Event.STATUS_ONGOING
        ).order_by('event_date', 'event_time')
        
        completed_page = int(request.GET.get('completed_page', 1))
        completed_page_size = int(request.GET.get('completed_page_size', 6))
        completed_qs = Event.objects.filter(
            status=Event.STATUS_COMPLETED
        ).order_by('-event_date', '-event_time')
        total_completed = completed_qs.count()
        completed_total_pages = max(1, (total_completed + completed_page_size - 1) // completed_page_size)
        completed_start = (completed_page - 1) * completed_page_size
        
        # Get past events this member attended
        from core_system.models import Attendance
        
        attended_page = int(request.GET.get('attended_page', 1))
        attended_page_size = int(request.GET.get('attended_page_size', 6))
        
        attended_qs = Attendance.objects.filter(
            member_id_FK=member,
            event_id_FK__isnull=False
        ).select_related('event_id_FK').order_by('-check_in_time')
        total_attended = attended_qs.count()
        attended_total_pages = max(1, (total_attended + attended_page_size - 1) // attended_page_size)
        attended_start = (attended_page - 1) * attended_page_size
        
        def serialize_event(event):
            return {
                'event_id': event.event_id_PK,
                'title': event.title,
                'event_date': event.event_date.strftime('%B %d, %Y'),
                'event_time': event.event_time.strftime('%I:%M %p') if event.event_time else None,
                'venue': event.venue,
                'event_type': event.event_type,
                'status': event.status,
                'attendance_open': event.attendance_open,
            }
        
        upcoming_list = [serialize_event(e) for e in upcoming_events[:10]]
        ongoing_list = [serialize_event(e) for e in ongoing_events[:10]]
        completed_list = [serialize_event(e) for e in completed_qs[completed_start:completed_start + completed_page_size]]
        
        attended_list = []
        for att in attended_qs[attended_start:attended_start + attended_page_size]:
            event = att.event_id_FK
            attended_list.append({
                'event_id': event.event_id_PK,
                'title': event.title,
                'event_date': event.event_date.strftime('%B %d, %Y'),
                'event_time': event.event_time.strftime('%I:%M %p') if event.event_time else 'N/A',
                'venue': event.venue,
                'status': att.status,
                'check_in_time': att.check_in_time.strftime('%I:%M %p') if att.check_in_time else 'N/A',
            })
        
        return JsonResponse({
            "ok": True,
            "upcoming_events": upcoming_list,
            "ongoing_events": ongoing_list,
            "completed_events": completed_list,
            "completed_page": completed_page,
            "completed_total_pages": completed_total_pages,
            "total_completed": total_completed,
            "attended_events": attended_list,
            "attended_page": attended_page,
            "attended_total_pages": attended_total_pages,
            "total_attended": total_attended,
        })
        
    except Exception as e:
        return JsonResponse({
            "ok": False,
            "error": str(e)
        }, status=500)


@require_POST
def member_update_profile(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    allowed_fields = {"contact_number", "email"}
    changed = False

    # B17: Email changes must verify the PIN (same security as member_change_email).
    if "email" in data:
        new_email = str(data.get("email", "")).strip()
        if not new_email:
            return JsonResponse({"ok": False, "error": "Email cannot be empty."}, status=400)
        _, email_error = validate_isu_email(new_email)
        if email_error:
            return JsonResponse({"ok": False, "error": email_error}, status=400)
        if member.pin_code:
            current_pin = str(data.get("current_pin", "")).strip()
            if len(current_pin) != 6 or not current_pin.isdigit():
                return JsonResponse({"ok": False, "error": "Current PIN is required and must be 6 digits to change email."}, status=400)
            if not verify_pin(current_pin, member.pin_code):
                return JsonResponse({"ok": False, "error": "Current PIN is incorrect."}, status=403)
        if Member.objects.filter(email__iexact=new_email).exclude(member_id_PK=member.member_id_PK).exists():
            return JsonResponse({"ok": False, "error": "This email is already in use by another member."}, status=409)
        if OfficerUser.objects.filter(email__iexact=new_email).exists():
            return JsonResponse({"ok": False, "error": "This email is already in use by another user."}, status=409)
        member.email = new_email
        changed = True

    if "contact_number" in data:
        contact_number = str(data.get("contact_number", "")).strip()
        if contact_number:
            # Validate PH mobile number format: 11 digits, starts with 09
            if len(contact_number) != 11:
                return JsonResponse({"ok": False, "error": "Contact number must be exactly 11 digits."}, status=400)
            if not contact_number.startswith('09'):
                return JsonResponse({"ok": False, "error": "Contact number must start with 09."}, status=400)
            if not contact_number.isdigit():
                return JsonResponse({"ok": False, "error": "Contact number must contain only digits."}, status=400)
        member.contact_number = contact_number
        changed = True

    # Personal information — self-service editable from the member's profile.
    valid_civil_status = {value for value, _ in Member.CIVIL_STATUS_CHOICES}
    if "civil_status" in data:
        civil_status = str(data.get("civil_status", "")).strip()
        if civil_status and civil_status not in valid_civil_status:
            return JsonResponse({"ok": False, "error": "Invalid civil status."}, status=400)
        member.civil_status = civil_status or None
        changed = True

    valid_sex = {value for value, _ in Member.SEX_CHOICES}
    if "sex" in data:
        sex = str(data.get("sex", "")).strip()
        if sex and sex not in valid_sex:
            return JsonResponse({"ok": False, "error": "Invalid sex."}, status=400)
        member.sex = sex or None
        changed = True

    if "date_of_birth" in data:
        dob_raw = str(data.get("date_of_birth", "")).strip()
        if dob_raw:
            try:
                dob = date.fromisoformat(dob_raw)
            except ValueError:
                return JsonResponse({"ok": False, "error": "Date of birth must be a valid date (YYYY-MM-DD)."}, status=400)
            today = timezone.now().date()
            if dob >= today:
                return JsonResponse({"ok": False, "error": "Date of birth must be in the past."}, status=400)
            if dob.year < 1900:
                return JsonResponse({"ok": False, "error": "Date of birth looks invalid (before 1900)."}, status=400)
            member.date_of_birth = dob
        else:
            member.date_of_birth = None
        changed = True

    if "address" in data:
        address = str(data.get("address", "")).strip()
        if len(address) > 500:
            return JsonResponse({"ok": False, "error": "Address is too long (max 500 characters)."}, status=400)
        member.address = address
        changed = True

    if changed:
        update_fields = [f for f in ("email", "contact_number", "civil_status", "sex", "date_of_birth", "address") if f in data]
        member.save(update_fields=update_fields)

    return JsonResponse({
        "ok": True,
        "message": "Profile updated successfully.",
    })


@require_POST
def member_change_email(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    new_email = (data.get("new_email") or "").strip()
    contact_number = (data.get("contact_number") or "").strip()
    current_pin = (data.get("current_pin") or "").strip()

    if not new_email:
        return JsonResponse({"ok": False, "error": "Email is required."}, status=400)

    _, email_error = validate_isu_email(new_email)
    if email_error:
        return JsonResponse({"ok": False, "error": email_error}, status=400)

    if member.pin_code:
        if not current_pin or len(current_pin) != 6 or not current_pin.isdigit():
            return JsonResponse({"ok": False, "error": "Current PIN is required and must be 6 digits."}, status=400)
        if not verify_pin(current_pin, member.pin_code):
            return JsonResponse({"ok": False, "error": "Current PIN is incorrect."}, status=403)

    if Member.objects.filter(email__iexact=new_email).exclude(member_id_PK=member.member_id_PK).exists():
        return JsonResponse({"ok": False, "error": "This email is already in use by another member."}, status=409)
    if OfficerUser.objects.filter(email__iexact=new_email).exists():
        return JsonResponse({"ok": False, "error": "This email is already in use by another user."}, status=409)

    if contact_number:
        _, contact_error = validate_ph_contact(contact_number)
        if contact_error:
            return JsonResponse({"ok": False, "error": contact_error}, status=400)

    member.email = new_email
    if contact_number:
        member.contact_number = contact_number
    member.save(update_fields=["email", "contact_number"] if contact_number else ["email"])

    return JsonResponse({"ok": True, "message": "Email updated successfully."})


@require_POST
def member_send_email_otp(request: HttpRequest):
    """Send OTP to current email for email change verification."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    # Verify current email matches
    current_email = (data.get("current_email") or "").strip()
    if not current_email:
        return JsonResponse({"ok": False, "error": "Current email is required."}, status=400)
    
    if current_email.lower() != member.email.lower():
        return JsonResponse({"ok": False, "error": "Current email does not match your account email."}, status=400)

    # Check rate limit
    from django.utils import timezone
    from datetime import timedelta
    rate_limit_key = f"email_otp_{member.member_id_PK}"
    last_sent = request.session.get(rate_limit_key)
    if last_sent:
        last_sent_time = timezone.datetime.fromisoformat(last_sent)
        if timezone.now() - last_sent_time < timedelta(minutes=5):
            return JsonResponse({"ok": False, "error": "OTP was recently sent. Please wait 5 minutes before requesting another."}, status=429)

    # Generate and send OTP
    from core_system.services.mfa_service import generate_otp, send_mfa_email
    import secrets
    
    # Generate a simple 6-digit OTP for members (no MFA secret needed)
    otp = f"{secrets.randbelow(1000000):06d}"
    
    # Store OTP in session with expiry
    request.session["email_change_otp"] = otp
    request.session["email_change_otp_created_at"] = timezone.now().isoformat()
    request.session["email_change_target_email"] = current_email
    request.session[rate_limit_key] = timezone.now().isoformat()
    
    # Send OTP email (queued — SMTP would otherwise block this response 8-15s)
    from core_system.services.email_service import send_html_email_async
    result = send_html_email_async(
        subject="CAUFA Email Change Verification",
        recipient_list=[member.email],
        html_template="emails/email_change_otp.html",
        context={
            "full_name": member.full_name,
            "otp_code": otp,
            "expiry_minutes": 5,
        },
    )
    
    if result:
        return JsonResponse({"ok": True, "message": "OTP sent to your current email."})
    else:
        return JsonResponse({"ok": False, "error": "Failed to send OTP email. Please try again."}, status=500)


@require_POST
def member_verify_email_otp(request: HttpRequest):
    """Verify OTP and allow email change."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    otp_input = (data.get("otp") or "").strip()
    new_email = (data.get("new_email") or "").strip()
    contact_number = (data.get("contact_number") or "").strip()

    if not otp_input:
        return JsonResponse({"ok": False, "error": "OTP is required."}, status=400)
    if not new_email:
        return JsonResponse({"ok": False, "error": "New email is required."}, status=400)

    # Verify OTP from session
    stored_otp = request.session.get("email_change_otp")
    otp_created_at = request.session.get("email_change_otp_created_at")
    target_email = request.session.get("email_change_target_email")

    if not stored_otp or not otp_created_at or not target_email:
        return JsonResponse({"ok": False, "error": "OTP session expired. Please request a new OTP."}, status=400)

    # Check OTP expiry (5 minutes)
    from django.utils import timezone
    from datetime import timedelta
    created = timezone.datetime.fromisoformat(otp_created_at)
    if timezone.now() - created > timedelta(minutes=5):
        request.session.pop("email_change_otp", None)
        request.session.pop("email_change_otp_created_at", None)
        request.session.pop("email_change_target_email", None)
        return JsonResponse({"ok": False, "error": "OTP expired. Please request a new OTP."}, status=400)

    # Verify OTP matches
    if otp_input != stored_otp:
        return JsonResponse({"ok": False, "error": "Invalid OTP. Please try again."}, status=400)

    # Verify target email matches current email
    if target_email.lower() != member.email.lower():
        return JsonResponse({"ok": False, "error": "Email verification mismatch. Please start over."}, status=400)

    # Check email uniqueness
    if Member.objects.filter(email__iexact=new_email).exclude(member_id_PK=member.member_id_PK).exists():
        return JsonResponse({"ok": False, "error": "This email is already in use by another member."}, status=409)
    if OfficerUser.objects.filter(email__iexact=new_email).exists():
        return JsonResponse({"ok": False, "error": "This email is already in use by another user."}, status=409)

    # Update email
    member.email = new_email
    if contact_number:
        # Validate PH mobile number format: 11 digits, starts with 09
        if len(contact_number) != 11:
            return JsonResponse({"ok": False, "error": "Contact number must be exactly 11 digits."}, status=400)
        if not contact_number.startswith('09'):
            return JsonResponse({"ok": False, "error": "Contact number must start with 09."}, status=400)
        if not contact_number.isdigit():
            return JsonResponse({"ok": False, "error": "Contact number must contain only digits."}, status=400)
        member.contact_number = contact_number
    member.save(update_fields=["email", "contact_number"] if contact_number else ["email"])

    # Clear OTP session
    request.session.pop("email_change_otp", None)
    request.session.pop("email_change_otp_created_at", None)
    request.session.pop("email_change_target_email", None)

    return JsonResponse({"ok": True, "message": "Email updated successfully."})


@require_GET
def member_check_email_exists(request: HttpRequest):
    """Check if an email already exists in the system."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    email = request.GET.get("email", "").strip()
    if not email:
        return JsonResponse({"ok": False, "error": "Email is required."}, status=400)

    # Check if email exists (excluding current member's email)
    exists = False
    if Member.objects.filter(email__iexact=email).exclude(member_id_PK=member.member_id_PK).exists():
        exists = True
    elif OfficerUser.objects.filter(email__iexact=email).exists():
        exists = True

    return JsonResponse({"ok": True, "exists": exists})


@require_POST
def member_submit_payment(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    # Handle both JSON and multipart/form-data (for file uploads)
    content_type = request.content_type or ""
    if "multipart/form-data" in content_type:
        # Handle file upload
        payment_type = str(request.POST.get("payment_type", "")).strip()
        amount = Decimal(str(request.POST.get("amount", "0")))
        payment_method = str(request.POST.get("payment_method", "")).strip()
        reference_number = str(request.POST.get("reference_number", "")).strip()
        uploaded_files = request.FILES.getlist("proof_file")
        transaction_date = str(request.POST.get("transaction_date", "")).strip()
    else:
        # Handle JSON
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        payment_type = str(data.get("payment_type", "")).strip()
        amount = Decimal(str(data.get("amount", "0")))
        payment_method = str(data.get("payment_method", "")).strip()
        reference_number = str(data.get("reference_number", "")).strip()
        uploaded_files = []
        transaction_date = str(data.get("transaction_date", "")).strip()

    if not payment_type or amount <= 0 or not payment_method:
        return JsonResponse({"ok": False, "error": "Missing required fields: payment_type, amount, payment_method"}, status=400)

    # Server-side amount enforcement (S20): members cannot submit arbitrary amounts.
    if payment_type == "Membership Fee":
        expected_fee = Decimal(str(get_membership_fee_amount()))
        if abs(amount - expected_fee) > Decimal("0.01"):
            return JsonResponse(
                {"ok": False, "error": f"Membership fee amount must be exactly ₱{expected_fee:.2f}."},
                status=400,
            )
    elif payment_type == "Monthly Dues":
        # Get number of months being paid (from month_covered field)
        if "multipart/form-data" in content_type:
            month_covered_raw = request.POST.get("month_covered", "")
        else:
            month_covered_raw = data.get("month_covered", "")
        
        num_months = 1
        if month_covered_raw:
            month_covered_list = [str(m).strip() for m in month_covered_raw.split(",")]
            num_months = len(month_covered_list)
        
        expected_dues_per_month = Decimal(str(get_monthly_dues_amount()))
        expected_total = expected_dues_per_month * Decimal(num_months)
        if abs(amount - expected_total) > Decimal("0.01"):
            return JsonResponse(
                {"ok": False, "error": f"Monthly dues amount must be exactly ₱{expected_total:.2f} for {num_months} month(s) at ₱{expected_dues_per_month:.2f} per month."},
                status=400,
            )

    # Find the treasurer user (or use the member's linked officer as recorded_by)
    officer_id = request.session.get("officer_id")
    officer = OfficerUser.objects.get(user_id_PK=officer_id)

    if payment_type == "Membership Fee":
        # Prevent duplicate membership fee submissions if a membership fee record is already present.
        existing_fee = MembershipFee.objects.filter(
            member_id_FK=member,
            payment_status__in=MEMBERSHIP_FEE_SUBMITTED_STATUSES,
        ).exists()
        if existing_fee:
            return JsonResponse({"ok": True, "message": "Membership fee payment has already been submitted. Thank you."})

        fee = MembershipFee.objects.create(
            member_id_FK=member,
            amount=amount,
            payment_method=payment_method,
            payment_status="Pending",
            payment_date=timezone.now().date(),
            receipt_number=reference_number,
            recorded_by_user_id_FK=officer,
            deposit_reference=reference_number,
        )
        # Link proof files if uploaded
        try:
            for uploaded_file in uploaded_files:
                _link_proof_to_record(uploaded_file, fee, officer)
        except ValueError as exc:
            # Blocked proof upload (duplicate content, disallowed type,
            # oversize): drop the proof-less Pending fee so the member can
            # retry with the actual document, and answer with the specific
            # reason + log the attempt instead of a generic 500.
            fee.delete()
            return proof_upload_blocked_response(
                request, exc,
                table="membership_fee", record_id=0,
                actor=officer, member=member,
            )
        # Create TransactionVerification record for the approval workflow so the
        # fee appears in the Auditor's pending membership-fee queue (mirrors the
        # monthly-dues branch below and the treasurer walk-in flow).
        TransactionVerification.objects.create(
            table_name="membership_fee",
            record_id=fee.fee_id_PK,
            verification_status="Pending Treasurer Review",
        )
    elif payment_type == "Monthly Dues":
        if "multipart/form-data" in content_type:
            month_covered_raw = request.POST.get("month_covered", "")
            if month_covered_raw:
                month_covered_list = [str(m).strip() for m in month_covered_raw.split(",")]
            else:
                month_covered_list = []
        else:
            month_covered_raw = data.get("month_covered", "")
            if month_covered_raw:
                month_covered_list = [str(m).strip() for m in month_covered_raw.split(",")]
            else:
                month_covered_list = []
        
        # Use current month if not provided
        if not month_covered_list:
            # Default to the backend dues frontier (what is actually being
            # collected), not the machine date.
            month_covered_list = [dues_frontier_month()]

        # Calculate expected amount per month
        expected_dues_per_month = Decimal(str(get_monthly_dues_amount()))
        expected_total = expected_dues_per_month * Decimal(len(month_covered_list))
        
        # Validate total amount matches expected
        if abs(amount - expected_total) > Decimal("0.01"):
            return JsonResponse(
                {"ok": False, "error": f"Total amount must be exactly ₱{expected_total:.2f} for {len(month_covered_list)} month(s) at ₱{expected_dues_per_month:.2f} per month."},
                status=400,
            )

        # "Advance" is relative to the dues frontier (the latest charged
        # month), not the machine date — April 2027 is current dues, not
        # an advance payment, once the backend has charged through it.
        current_month = dues_frontier_month()
        created_dues = []
        
        for month_covered in month_covered_list:
            # Guard against duplicate monthly dues records for the same covered month
            if MonthlyDues.objects.filter(
                member_id_FK=member,
                month_covered=month_covered,
                payment_status__in=["Pending", "Paid", "Full Payment"],
            ).exists():
                return JsonResponse({"ok": False, "error": f"Monthly dues for {month_covered} have already been submitted."}, status=409)

            is_advance = month_covered > current_month

            dues = MonthlyDues.objects.create(
                member_id_FK=member,
                month_covered=month_covered,
                amount=expected_dues_per_month,
                payment_method=payment_method,
                payment_status="Pending",
                payment_date=timezone.now().date(),
                receipt_number=reference_number,
                recorded_by_user_id_FK=officer,
                treasurer_status="Pending Treasurer Review",
                is_advance=is_advance,
            )
            created_dues.append(dues)

            SalaryDeductionExemption.objects.filter(
                member_id_FK=member,
                month_covered=month_covered,
            ).delete()
            
            # Link proof files if uploaded (only link to first record to avoid duplicates)
            if created_dues.index(dues) == 0:
                try:
                    for uploaded_file in uploaded_files:
                        _link_proof_to_record(uploaded_file, dues, officer)
                except ValueError as exc:
                    # Blocked proof upload (duplicate content, disallowed type,
                    # oversize): drop the proof-less Pending dues so the member
                    # can retry with the actual document, and answer with the
                    # specific reason + log the attempt instead of a generic 500.
                    for created in created_dues:
                        created.delete()
                    return proof_upload_blocked_response(
                        request, exc,
                        table="monthly_dues", record_id=0,
                        actor=officer, member=member,
                    )
            
            # Create TransactionVerification record for the approval workflow
            TransactionVerification.objects.create(
                table_name="monthly_dues",
                record_id=dues.dues_id_PK,
                target_category="payment",
                verification_status="Pending Treasurer Review",
            )
    else:
        return JsonResponse({"ok": False, "error": f"Unknown payment type: {payment_type}"}, status=400)

    return JsonResponse({
        "ok": True,
        "message": f"{payment_type} payment submitted for verification.",
    })


@require_POST
def member_request_exemption(request: HttpRequest):
    """Handle member salary deduction exemption requests."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    month_covered = str(data.get("month_covered", "")).strip()
    reason = str(data.get("reason", "")).strip()

    if not month_covered:
        return JsonResponse({"ok": False, "error": "Month is required for exemption request."}, status=400)

    # Check if exemption already exists for this month
    if SalaryDeductionExemption.objects.filter(
        member_id_FK=member,
        month_covered=month_covered,
    ).exists():
        return JsonResponse(
            {"ok": False, "error": "You already have an exemption request for this month."},
            status=409,
        )

    # Create exemption request
    exemption = SalaryDeductionExemption.objects.create(
        member_id_FK=member,
        month_covered=month_covered,
        reason=reason if reason else None,
        status="Pending Treasurer Review",
        requested_by_member=True,
    )

    # Create notification for treasurer
    try:
        # Get treasurer users
        from core_system.services.notifications import notify_officer
        treasurer_users = OfficerUser.objects.filter(role="Treasurer", account_status="Active")
        for treasurer in treasurer_users:
            notify_officer(
                treasurer,
                notification_type="exemption_request",
                message=f"{member.full_name} has requested a salary deduction exemption for {month_covered}. Reason: {reason if reason else 'Not specified'}",
                category="dues",
                url="/treasurer/dashboard/?section=exemptions",
            )
    except Exception as e:
        # Log but don't fail the request
        pass

    return JsonResponse({
        "ok": True,
        "message": "Your salary deduction exemption request has been submitted for Treasurer review.",
    })


@require_POST
def member_file_claim(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    # Management policy: retired members are exempt from paying dues and
    # contributions per ARTICLE XI Section 2, and they must not file new
    # medical or death aid claims.
    if is_retired_member(member):
        return JsonResponse(
            {"ok": False, "error": "Retired members cannot file new medical or death aid claims. Please contact the Treasurer if you need assistance."},
            status=400,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    claim_type = str(data.get("claim_type", "")).strip()

    # Block filing a new claim only if the same claim type is already pending
    pending_statuses = tuple(Status.ALL_PENDING) + (
        "Pending Review",
        "Pending Treasurer Review",
        "Pending Auditor Verification",
        "Pending President Approval",
    )
    if claim_type == "medical_aid":
        has_pending = MedicalAid.objects.filter(member_id_FK=member, status__in=pending_statuses).exists()
    elif claim_type == "death_aid":
        has_pending = DeathAid.objects.filter(member_id_FK=member, status__in=pending_statuses).exists()
    else:
        return JsonResponse({"ok": False, "error": f"Unknown claim type: {claim_type}"}, status=400)

    if has_pending:
        return JsonResponse({"ok": False, "error": "You already have a pending claim of this type. Please wait until it is processed or rejected."}, status=400)

    if claim_type == "medical_aid":
        hospital_name = str(data.get("hospital_name", "")).strip()
        hospital_address = str(data.get("hospital_address", "")).strip()
        admission_date = str(data.get("admission_date", "")).strip()
        discharge_date = str(data.get("discharge_date", "")).strip()
        hospital_bill = Decimal(str(data.get("hospital_bill_amount", "0")))
        if not hospital_name or hospital_bill <= 0:
            return JsonResponse({"ok": False, "error": "Hospital name and bill amount required."}, status=400)

        adm = None
        dis = None
        if admission_date:
            try:
                from datetime import datetime as dt
                adm = dt.strptime(admission_date, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"ok": False, "error": "Invalid admission_date format."}, status=400)
        if discharge_date:
            try:
                from datetime import datetime as dt
                dis = dt.strptime(discharge_date, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"ok": False, "error": "Invalid discharge_date format."}, status=400)
        if adm and dis and adm > dis:
            return JsonResponse({"ok": False, "error": "Admission date cannot be after discharge date."}, status=400)
        # Allow any date for admission (past, present, or future)
        # No validation needed for admission date

        year = timezone.now().year
        err_msg = check_medical_aid_once_per_year(member, year)
        if err_msg:
            return JsonResponse({"ok": False, "error": err_msg}, status=400)

        reason_for_request = str(data.get("reason_for_request", "")).strip()

        claim = MedicalAid.objects.create(
            member_id_FK=member,
            request_date=timezone.now().date(),
            requested_amount=hospital_bill,
            hospital_name=hospital_name,
            hospital_address=hospital_address,
            admission_date=adm,
            discharge_date=dis,
            reason_for_request=reason_for_request,
            hospital_bill_amount=hospital_bill,
            claim_year=timezone.now().year,
            document_status="Pending",
            policy_record_status="Pending",
            validated_aid_amount=0,
            status="Pending Treasurer Review",
        )

        # Send notification to member that claim was submitted
        try:
            from core_system.services.notifications import notify_member
            notify_member(
                member,
                notification_type="Claim Submitted",
                message=f"Your Medical Aid claim has been submitted successfully. It is now pending Treasurer review.",
                category="claim",
                url="/member/",
                send_email=True,
            )
        except Exception as e:
            logger.warning("Failed to send submission notification to member %s: %s", member.member_id_PK, e)

        return JsonResponse({
            "ok": True,
            "message": "Medical Aid claim submitted successfully.",
            "claim_id": claim.medical_aid_id_PK,
            "claim_type": "medical_aid",
        })

    elif claim_type == "death_aid":
        deceased_name = str(data.get("deceased_name", "")).strip()
        relationship = str(data.get("relationship", "")).strip()
        # Server-side amount enforcement: the benefit amount is system-controlled
        # based on the relationship category. Client-submitted amounts are ignored.
        benefit_amount = Decimal(str(get_death_aid_amount(relationship)))
        funeral_location = str(data.get("funeral_location", "")).strip()
        date_of_death = str(data.get("date_of_death", "")).strip()
        interment_date = str(data.get("interment_date", "")).strip()
        claimant_name = str(data.get("claimant_name", "")).strip()
        claimant_contact = str(data.get("claimant_contact", "")).strip()

        if not deceased_name or not relationship or benefit_amount <= 0:
            return JsonResponse({"ok": False, "error": "Deceased name and a valid relationship category are required."}, status=400)

        if not date_of_death:
            return JsonResponse({"ok": False, "error": "Date of death is required for death aid claims."}, status=400)

        death_date = None
        if date_of_death:
            try:
                from datetime import datetime as dt
                death_date = dt.strptime(date_of_death, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"ok": False, "error": "Invalid date_of_death format."}, status=400)

        # Allow today's date and past dates for death of death, but not future dates
        if death_date and death_date > timezone.now().date():
            return JsonResponse({"ok": False, "error": "The date of death cannot be a future date."}, status=400)

        interment = None
        if interment_date:
            try:
                from datetime import datetime as dt
                interment = dt.strptime(interment_date, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"ok": False, "error": "Invalid interment_date format."}, status=400)

        # Allow any date for interment (past, present, or future)
        # No validation needed for interment date

        claimant, _ = Claimant.objects.get_or_create(
            member_id_FK=member,
            full_name=claimant_name or member.full_name,
            defaults={
                "contact_number": claimant_contact,
                "relationship_to_member": relationship,
                "authorization_status": "Pending",
            },
        )

        claim = DeathAid.objects.create(
            member_id_FK=member,
            claimant_id_FK=claimant,
            claim_date=timezone.now().date(),
            claim_type=relationship,
            date_of_death=death_date,
            deceased_name=deceased_name,
            relationship_to_member=relationship,
            funeral_location=funeral_location,
            interment_date=interment,
            benefit_amount=benefit_amount,
            bill_amount=None,
            document_status="Pending",
            status="Pending Treasurer Review",
        )

        # Send notification to member that claim was submitted
        try:
            from core_system.services.notifications import notify_member
            notify_member(
                member,
                notification_type="Claim Submitted",
                message=f"Your Death Aid claim has been submitted successfully. It is now pending Treasurer review.",
                category="claim",
                url="/member/",
                send_email=True,
            )
        except Exception as e:
            logger.warning("Failed to send submission notification to member %s: %s", member.member_id_PK, e)

        return JsonResponse({
            "ok": True,
            "message": "Death Aid claim submitted successfully.",
            "claim_id": claim.death_aid_id_PK,
            "claim_type": "death_aid",
        })

    else:
        return JsonResponse({"ok": False, "error": f"Unknown claim type: {claim_type}"}, status=400)


@require_POST
def member_claim_upload_proof(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    officer_id = request.session.get("officer_id")
    officer = OfficerUser.objects.get(user_id_PK=officer_id)

    claim_type = str(request.POST.get("claim_type", "")).strip()
    claim_id_str = str(request.POST.get("claim_id", "")).strip()
    uploaded_file = request.FILES.get("file")

    if not claim_type or not claim_id_str or not uploaded_file:
        return JsonResponse({"ok": False, "error": "claim_type, claim_id, and file are required."}, status=400)

    try:
        claim_id = int(claim_id_str)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid claim_id."}, status=400)

    if claim_type == "medical_aid":
        try:
            claim = MedicalAid.objects.get(medical_aid_id_PK=claim_id, member_id_FK=member)
        except MedicalAid.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Medical aid claim not found."}, status=404)
    elif claim_type == "death_aid":
        try:
            claim = DeathAid.objects.get(death_aid_id_PK=claim_id, member_id_FK=member)
        except DeathAid.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Death aid claim not found."}, status=404)
    else:
        return JsonResponse({"ok": False, "error": "claim_type must be 'medical_aid' or 'death_aid'."}, status=400)

    # Status gate (S13): only allow proof upload for pending claims.
    if claim.status not in ("Pending", "Pending Review", "Pending Treasurer Review", "Pending Auditor Verification", "Pending President Approval", "Returned for Revision"):
        return JsonResponse(
            {"ok": False, "error": "Proof can only be uploaded for pending or returned claims."},
            status=400,
        )

    # MIME and size validation (S13).
    allowed_mime = {
        "image/jpeg", "image/png", "image/webp", "image/gif",
        "application/pdf",
    }
    if uploaded_file.content_type not in allowed_mime:
        return JsonResponse(
            {"ok": False, "error": "Only JPG, PNG, WebP, GIF, and PDF files are allowed."},
            status=400,
        )
    if uploaded_file.size > 10 * 1024 * 1024:
        return JsonResponse(
            {"ok": False, "error": "File size must not exceed 10MB."},
            status=400,
        )

    proof = SupportingProof(
        content_object=claim,
        file=uploaded_file,
        file_name=uploaded_file.name,
        file_type=uploaded_file.content_type or "",
        uploaded_by=officer,
    )
    proof.save()

    proof.file_sha256 = proof.compute_file_hash()
    proof.row_signature = proof.compute_row_signature(proof.file_sha256, proof.object_id)
    proof.save(update_fields=["file_sha256", "row_signature"])

    return JsonResponse({
        "ok": True,
        "proof_id": proof.proof_id_PK,
        "file_name": proof.file_name,
        "message": "File uploaded.",
    })


@require_GET
def member_claims_list(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    ma_ct = ContentType.objects.get_for_model(MedicalAid)
    da_ct = ContentType.objects.get_for_model(DeathAid)

    claims = []

    for ma in MedicalAid.objects.filter(member_id_FK=member).order_by("-request_date"):
        proof_count = SupportingProof.objects.filter(
            content_type=ma_ct, object_id=ma.medical_aid_id_PK
        ).count()
        claims.append({
            "id": ma.medical_aid_id_PK,
            "claim_type": "medical_aid",
            "status": ma.status,
            "submitted": ma.request_date.isoformat() if ma.request_date else "",
            "hospital_name": ma.hospital_name,
            "hospital_address": ma.hospital_address or "",
            "admission_date": ma.admission_date.isoformat() if ma.admission_date else "",
            "discharge_date": ma.discharge_date.isoformat() if ma.discharge_date else "",
            "reason_for_request": ma.reason_for_request or "",
            "amount": float(ma.requested_amount or 0),
            "proof_count": proof_count,
        })

    for da in DeathAid.objects.filter(member_id_FK=member).order_by("-claim_date"):
        proof_count = SupportingProof.objects.filter(
            content_type=da_ct, object_id=da.death_aid_id_PK
        ).count()
        claims.append({
            "id": da.death_aid_id_PK,
            "claim_type": "death_aid",
            "status": da.status,
            "submitted": da.claim_date.isoformat() if da.claim_date else "",
            "deceased_name": da.deceased_name,
            "amount": float(da.benefit_amount or 0),
            "proof_count": proof_count,
        })

    claims.sort(key=lambda c: c["submitted"], reverse=True)

    return JsonResponse({"ok": True, "claims": claims})


@require_GET
def member_claim_detail(request: HttpRequest, claim_id: int):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    claim_type = str(request.GET.get("claim_type", "")).strip()
    ma = None
    da = None
    
    if claim_type == "medical_aid":
        ma = MedicalAid.objects.filter(medical_aid_id_PK=claim_id, member_id_FK=member).first()
    elif claim_type == "death_aid":
        da = DeathAid.objects.filter(death_aid_id_PK=claim_id, member_id_FK=member).first()
    else:
        # Try both if claim_type not specified
        ma = MedicalAid.objects.filter(medical_aid_id_PK=claim_id, member_id_FK=member).first()
        if not ma:
            da = DeathAid.objects.filter(death_aid_id_PK=claim_id, member_id_FK=member).first()

    if ma is not None:
        ct = ContentType.objects.get_for_model(MedicalAid)
        proofs = SupportingProof.objects.filter(content_type=ct, object_id=ma.medical_aid_id_PK).order_by("-uploaded_at")
        supporting_proofs = []
        for p in proofs:
            supporting_proofs.append({
                "proof_id": p.proof_id_PK,
                "file_name": p.file_name,
                "file_type": p.file_type,
                "file_url": p.file.url if p.file else "",
                "uploaded_at": p.uploaded_at.isoformat() if p.uploaded_at else "",
            })

        return JsonResponse({
            "ok": True,
            "claim": {
                "id": ma.medical_aid_id_PK,
                "claim_type": "medical_aid",
                "status": ma.status,
                "submitted": ma.request_date.isoformat() if ma.request_date else "",
                "hospital_name": ma.hospital_name,
                "hospital_address": ma.hospital_address or "",
                "admission_date": ma.admission_date.isoformat() if ma.admission_date else "",
                "discharge_date": ma.discharge_date.isoformat() if ma.discharge_date else "",
                "reason_for_request": ma.reason_for_request or "",
                "requested_amount": float(ma.requested_amount or 0),
                "hospital_bill_amount": float(ma.hospital_bill_amount or 0),
                "validated_amount": float(ma.validated_aid_amount or 0),
                "treasurer_validated_by": ma.treasurer_validated_by_user_id_FK.full_name if ma.treasurer_validated_by_user_id_FK else "",
                "auditor_verified_by": ma.auditor_verified_by_user_id_FK.full_name if ma.auditor_verified_by_user_id_FK else "",
                "president_decision": ma.president_decision or "",
                "supporting_proofs": supporting_proofs,
                "status_flow": {
                    "submitted": True,
                    "treasurer_review": ma.treasurer_validated_by_user_id_FK is not None,
                    "auditor_verification": ma.auditor_verified_by_user_id_FK is not None,
                    "president_approval": ma.president_decision == "Approved",
                    "aid_released": ma.status in ["Released", "Completed"],
                    "completed": ma.status == "Completed",
                },
            },
        })

    if da is not None:
        ct = ContentType.objects.get_for_model(DeathAid)
        proofs = SupportingProof.objects.filter(content_type=ct, object_id=da.death_aid_id_PK).order_by("-uploaded_at")
        supporting_proofs = []
        for p in proofs:
            supporting_proofs.append({
                "proof_id": p.proof_id_PK,
                "file_name": p.file_name,
                "file_type": p.file_type,
                "file_url": p.file.url if p.file else "",
                "uploaded_at": p.uploaded_at.isoformat() if p.uploaded_at else "",
            })

        return JsonResponse({
            "ok": True,
            "claim": {
                "id": da.death_aid_id_PK,
                "claim_type": "death_aid",
                "status": da.status,
                "submitted": da.claim_date.isoformat() if da.claim_date else "",
                "date_of_death": da.date_of_death.isoformat() if da.date_of_death else "",
                "deceased_name": da.deceased_name,
                "relationship_to_member": da.relationship_to_member,
                "relationship": da.relationship_to_member,
                "benefit_amount": float(da.benefit_amount or 0),
                "bill_amount": float(da.bill_amount or 0),
                "funeral_location": da.funeral_location,
                "interment_date": da.interment_date.isoformat() if da.interment_date else "",
                "death_claim_type": da.claim_type,
                "treasurer_validated_by": da.treasurer_validated_by_user_id_FK.full_name if da.treasurer_validated_by_user_id_FK else "",
                "auditor_verified_by": da.auditor_verified_by_user_id_FK.full_name if da.auditor_verified_by_user_id_FK else "",
                "president_decision": da.president_decision or "",
                "supporting_proofs": supporting_proofs,
                "status_flow": {
                    "submitted": True,
                    "treasurer_review": da.treasurer_validated_by_user_id_FK is not None,
                    "auditor_verification": da.auditor_verified_by_user_id_FK is not None,
                    "president_approval": da.president_decision == "Approved",
                    "aid_released": da.status in ["Released", "Completed"],
                    "completed": da.status == "Completed",
                },
            },
        })

    return JsonResponse({"ok": False, "error": "Claim not found."}, status=404)


@require_POST
def member_save_pin(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    pin = str(data.get("pin", "")).strip()
    current_pin = str(data.get("current_pin", "")).strip()
    if len(pin) != 6 or not pin.isdigit():
        return JsonResponse({"ok": False, "error": "PIN must be exactly 6 digits."}, status=400)
    if member.pin_code:
        if len(current_pin) != 6 or not current_pin.isdigit():
            return JsonResponse({"ok": False, "error": "Current PIN is required and must be 6 digits."}, status=400)
        if not verify_pin(current_pin, member.pin_code):
            return JsonResponse({"ok": False, "error": "Current PIN is incorrect."}, status=400)

    # Uniqueness check: iterate stored hashes and verify (salted hashes cannot be indexed).
    for other in Member.objects.exclude(member_id_PK=member.member_id_PK).only("pin_code"):
        if other.pin_code and verify_pin(pin, other.pin_code):
            return JsonResponse({"ok": False, "error": "This PIN is already in use by another member."}, status=400)

    member.pin_code = hash_pin(pin)
    member.save(update_fields=["pin_code"])
    return JsonResponse({"ok": True, "message": "Attendance PIN saved successfully."})


@require_POST
def member_onboarding_activate(request: HttpRequest):
    """Account activation step of the member dashboard onboarding.

    Completes the flow demoed in FROMGROUP/isucaufa-onboarding-demo.html:
    verifies the emailed temporary password against the linked login account,
    enforces the canonical password-strength rules, records the privacy/terms
    agreement in the audit trail, and unlocks the dashboard (sets
    Member.setup_complete, clears must_change_password).
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    temp_password = str(data.get("temp_password", ""))
    new_password = str(data.get("new_password", ""))
    confirm_password = str(data.get("confirm_password", ""))
    agreed_terms = bool(data.get("agreed_terms", False))

    officer = member.officer_user_id_FK
    if officer is None:
        return JsonResponse({"ok": False, "error": "No login account is linked to this member profile."}, status=400)

    if member.setup_complete and not officer.must_change_password:
        return JsonResponse({"ok": False, "error": "Onboarding already completed."}, status=400)

    if not agreed_terms:
        return JsonResponse({"ok": False, "error": "Please agree to the Terms and Conditions to continue."}, status=400)

    if not verify_password(temp_password, officer.password_hash):
        _record_audit_trail(
            table="member",
            record_id=member.member_id_PK,
            action="ACCOUNT_ACTIVATED",
            actor=officer,
            ip=request.META.get("REMOTE_ADDR"),
            notes="Failed onboarding activation: temporary password did not match.",
            result="Failed",
        )
        return JsonResponse({"ok": False, "error": "Temporary password is incorrect or expired."}, status=400)

    strength_errors = validate_new_password(new_password)
    if strength_errors:
        return JsonResponse({"ok": False, "error": " ".join(strength_errors)}, status=400)
    if new_password != confirm_password:
        return JsonResponse({"ok": False, "error": "New password and confirmation do not match."}, status=400)
    if new_password == temp_password:
        return JsonResponse({"ok": False, "error": "New password must be different from your temporary password."}, status=400)

    officer.password_hash = hash_password(new_password)
    officer.must_change_password = False
    officer.save(update_fields=["password_hash", "must_change_password"])
    member.setup_complete = True
    member.save(update_fields=["setup_complete"])

    _record_audit_trail(
        table="member",
        record_id=member.member_id_PK,
        action="ACCOUNT_ACTIVATED",
        actor=officer,
        old={"setup_complete": False},
        new={"setup_complete": True},
        ip=request.META.get("REMOTE_ADDR"),
        notes="Member completed dashboard onboarding: Data Privacy Notice and Terms agreed, password set.",
    )
    return JsonResponse({"ok": True, "message": "Account activated."})


@require_POST
def member_save_rep(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    full_name = str(data.get("full_name", "")).strip()
    relationship = str(data.get("relationship", "")).strip()
    contact = str(data.get("contact_number", "")).strip()

    if contact:
        # Validate PH mobile number format: 11 digits, starts with 09
        if len(contact) != 11:
            return JsonResponse({"ok": False, "error": "Contact number must be exactly 11 digits."}, status=400)
        if not contact.startswith('09'):
            return JsonResponse({"ok": False, "error": "Contact number must start with 09."}, status=400)
        if not contact.isdigit():
            return JsonResponse({"ok": False, "error": "Contact number must contain only digits."}, status=400)

    if not full_name or not relationship:
        return JsonResponse({"ok": False, "error": "Name and relationship required."}, status=400)

    Claimant.objects.update_or_create(
        member_id_FK=member,
        full_name=full_name,
        defaults={
            "contact_number": contact,
            "relationship_to_member": relationship,
            "authorization_status": "Active",
        },
    )

    return JsonResponse({
        "ok": True,
        "message": "Authorized representative saved.",
    })


# Family categories selectable on the member profile. These mirror the
# Treasurer's file-death-aid relationship options, so a listed family member
# maps directly to a death-aid benefit tier.
MEMBER_FAMILY_CATEGORIES = {
    "spouse": {"label": "Spouse", "relationship": "Spouse", "group": "spouse"},
    "parent": {"label": "Parent", "relationship": "Parent", "group": "parent_child"},
    "child": {"label": "Child", "relationship": "Child", "group": "parent_child"},
    "sibling": {
        "label": "Brother/Sister (Full Blood)",
        "relationship": "Brother/Sister (Full Blood)",
        "group": "sibling",
    },
}


def _family_category_payload() -> list[dict]:
    """Category options matching the Treasurer's file-death-aid tiers."""
    return [
        {"value": key, "label": spec["label"]}
        for key, spec in MEMBER_FAMILY_CATEGORIES.items()
    ]


def _serialize_family_member(row: Claimant) -> dict:
    category = ""
    for key, spec in MEMBER_FAMILY_CATEGORIES.items():
        if (row.relationship_to_member or "").strip().casefold() == spec["relationship"].casefold():
            category = key
            break
    label = MEMBER_FAMILY_CATEGORIES.get(category, {}).get("label", row.relationship_to_member or "")
    return {
        "id": row.claimant_id_PK,
        "full_name": row.full_name,
        "category": category,
        "category_label": label,
        "relationship": row.relationship_to_member,
        "contact_number": row.contact_number or "",
    }


def _validate_family_contact(contact: str):
    contact = (contact or "").strip()
    if not contact:
        return "", None
    if len(contact) != 11:
        return "", "Contact number must be exactly 11 digits."
    if not contact.startswith("09"):
        return "", "Contact number must start with 09."
    if not contact.isdigit():
        return "", "Contact number must contain only digits."
    return contact, None


@require_GET
def member_family_list(request: HttpRequest):
    """Family list for the signed-in member's profile (edit-profile)."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    rows = Claimant.objects.filter(member_id_FK=member).order_by("full_name")
    return JsonResponse({
        "ok": True,
        "items": [_serialize_family_member(r) for r in rows],
        "categories": _family_category_payload(),
    })


@require_POST
def member_family_save(request: HttpRequest):
    """Add or update one family member (name + death-aid category + contact)."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    row_id = data.get("id")
    full_name = str(data.get("full_name", "")).strip()
    category = str(data.get("category", "")).strip().lower()
    contact, contact_error = _validate_family_contact(str(data.get("contact_number", "")))

    if not full_name:
        return JsonResponse({"ok": False, "error": "Full name is required."}, status=400)
    if len(full_name) > 255:
        return JsonResponse({"ok": False, "error": "Name is too long (max 255 characters)."}, status=400)
    if category not in MEMBER_FAMILY_CATEGORIES:
        return JsonResponse({"ok": False, "error": "Select a valid family category."}, status=400)
    if contact_error:
        return JsonResponse({"ok": False, "error": contact_error}, status=400)

    spec = MEMBER_FAMILY_CATEGORIES[category]

    row = None
    if row_id:
        try:
            row = Claimant.objects.get(claimant_id_PK=row_id, member_id_FK=member)
        except Claimant.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Family member not found."}, status=404)

    # A member may list only ONE spouse. The death-aid tiers assume it: with
    # two Spouse rows the treasurer could not tell which spouse a claim is
    # for. An edit that keeps a row's own spouse status is still allowed (so
    # legacy double-spouse rows stay editable) — only a new entry, or turning
    # a non-spouse row, into a second spouse is blocked.
    if category == "spouse":
        was_already_spouse = bool(row) and (
            (row.relationship_to_member or "").strip().casefold()
            == spec["relationship"].casefold()
        )
        if not was_already_spouse:
            spouse_qs = Claimant.objects.filter(
                member_id_FK=member,
                relationship_to_member__iexact=spec["relationship"],
            )
            if row_id:
                spouse_qs = spouse_qs.exclude(claimant_id_PK=row_id)
            if spouse_qs.exists():
                return JsonResponse(
                    {"ok": False, "error": "Only one spouse can be listed in your family list. Remove the existing spouse entry first."},
                    status=409,
                )

    duplicate = (
        Claimant.objects.filter(member_id_FK=member, full_name__iexact=full_name)
        .exclude(claimant_id_PK=row_id) if row_id else
        Claimant.objects.filter(member_id_FK=member, full_name__iexact=full_name)
    )
    if duplicate.exists():
        return JsonResponse(
            {"ok": False, "error": "This person is already in your family list."},
            status=409,
        )

    if row_id:
        row.full_name = full_name
        row.relationship_to_member = spec["relationship"]
        row.relationship_group = spec["group"]
        row.contact_number = contact
        row.authorization_status = "Active"
        row.save()
        message = "Family member updated."
    else:
        row = Claimant.objects.create(
            member_id_FK=member,
            full_name=full_name,
            contact_number=contact,
            relationship_to_member=spec["relationship"],
            relationship_group=spec["group"],
            authorization_status="Active",
        )
        message = "Family member added."

    return JsonResponse({"ok": True, "message": message, "item": _serialize_family_member(row)})


@require_POST
def member_family_delete(request: HttpRequest):
    """Remove one family member from the signed-in member's list."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    try:
        row = Claimant.objects.get(
            claimant_id_PK=int(data.get("id") or 0), member_id_FK=member
        )
    except (Claimant.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Family member not found."}, status=404)
    row.delete()
    return JsonResponse({"ok": True, "message": "Family member removed."})


@require_GET
def member_dashboard_data(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    member_data = {
        "member_id": member.member_id_PK,
        "full_name": member.full_name,
        "username": (member.officer_user_id_FK.username if member.officer_user_id_FK else "") or member.employee_id or "",
        "employee_id": member.employee_id or "",
        "email": member.email or "",
        "contact_number": member.contact_number or "",
        "department": member.department or "",
        "position": member.position or "",
        "employment_status": member.employment_status,
        "membership_status": member.membership_status,
        "member_classification": member.member_classification,
        "member_type": member.member_type,
        "date_joined": member.date_joined.isoformat() if member.date_joined else "",
        "profile_picture": member.profile_picture.url if member.profile_picture else "",
        "has_pin": bool(member.pin_code),
        "qr_code": member.qr_code.url if member.qr_code else "",
        "emergency_contact": member.emergency_contact or "",
        "emergency_number": member.emergency_number or "",
    }

    # --- Optimized single query with prefetch ---
    member = Member.objects.select_related(
        "officer_user_id_FK", "department_id_FK"
    ).prefetch_related(
        "membershipfee_set",
        "monthlydues_set",
        "medicalaid_set",
        "deathaid_set",
        "contribution_set__aid_tracking_post_id_FK",
        "claimant_set",
    ).get(member_id_PK=member.member_id_PK)

    # --- Membership Fee (single query) ---
    fee = member.membershipfee_set.first()
    has_membership_fee = fee is not None
    membership_fee_status = fee.payment_status if fee else "Unpaid"
    membership_fee_amount = float(fee.amount) if fee else 0
    membership_fee_paid = fee.payment_status in ("Paid", "Full Payment") if fee else False
    membership_fee_submitted = fee.payment_status in MEMBERSHIP_FEE_SUBMITTED_STATUSES if fee else False

    # --- Dues Summary (optimized) ---
    dues_summary = _compute_dues_summary(member)
    total_dues_paid = dues_summary["total_dues_paid"]
    total_dues_pending = dues_summary["total_dues_pending"]
    total_dues_unpaid = dues_summary["total_dues_unpaid"]
    outstanding_balance = dues_summary["outstanding_balance"]

    # Unpaid Balance months context: the pooled carry-over's actual months,
    # oldest first — empty while retired (no current obligation) or when
    # nothing is owed.
    if outstanding_balance and outstanding_balance > 0.005:
        unpaid_months = member_unpaid_month_entries(member)
    else:
        unpaid_months = []

    # Dues records (prefetch already done)
    all_dues = member.monthlydues_set.all().order_by("-payment_date")
    dues_records = [{
        "dues_id": d.dues_id_PK,
        "month_covered": d.month_covered,
        "amount": float(d.amount),
        "payment_status": d.payment_status,
        "payment_method": d.payment_method,
        "payment_date": d.payment_date.isoformat() if d.payment_date else "",
        "is_advance": d.is_advance,
    } for d in all_dues]

    # --- Claims & Contributions (prefetched) ---
    medical_aid_records = []
    medical_aid_pending = 0
    medical_aid_approved = 0
    medical_aid_released = 0
    for ma in member.medicalaid_set.all().order_by("-request_date"):
        record = {
            "medical_aid_id": ma.medical_aid_id_PK,
            "request_date": ma.request_date.isoformat() if ma.request_date else "",
            "requested_amount": float(ma.requested_amount or 0),
            "hospital_name": ma.hospital_name,
            "hospital_address": ma.hospital_address or "",
            "admission_date": ma.admission_date.isoformat() if ma.admission_date else "",
            "discharge_date": ma.discharge_date.isoformat() if ma.discharge_date else "",
            "reason_for_request": ma.reason_for_request or "",
            "hospital_bill_amount": float(ma.hospital_bill_amount or 0),
            "validated_aid_amount": float(ma.validated_aid_amount),
            "status": ma.status,
        }
        medical_aid_records.append(record)
        if ma.status in ("Pending", "Pending Review", "Pending Treasurer Review", "Pending Auditor Verification", "Pending President Approval"):
            medical_aid_pending += 1
        elif ma.status in ("Approved", "Verified"):
            medical_aid_approved += 1
        elif ma.status in ("Released", "Completed"):
            medical_aid_released += 1

    death_aid_records = []
    death_aid_pending = 0
    death_aid_approved = 0
    death_aid_released = 0
    for da in member.deathaid_set.all().order_by("-claim_date"):
        death_aid_records.append({
            "death_aid_id": da.death_aid_id_PK,
            "claim_date": da.claim_date.isoformat() if da.claim_date else "",
            "claim_type": da.claim_type,
            "deceased_name": da.deceased_name,
            "benefit_amount": float(da.benefit_amount),
            "status": da.status,
        })
        if da.status in ("Pending", "Pending Review", "Pending Treasurer Review", "Pending Auditor Verification", "Pending President Approval"):
            death_aid_pending += 1
        elif da.status in ("Approved", "Verified"):
            death_aid_approved += 1
        elif da.status in ("Released", "Completed"):
            death_aid_released += 1

    # Contributions (prefetched)
    medical_claim_ids = list(member.medicalaid_set.values_list("medical_aid_id_PK", flat=True))
    death_claim_ids = list(member.deathaid_set.values_list("death_aid_id_PK", flat=True))
    contribs = member.contribution_set.exclude(
        Q(aid_tracking_post_id_FK__source_type="medical_aid", aid_tracking_post_id_FK__source_id__in=medical_claim_ids)
        | Q(aid_tracking_post_id_FK__source_type="death_aid", aid_tracking_post_id_FK__source_id__in=death_claim_ids)
    ).select_related("aid_tracking_post_id_FK").order_by("-aid_tracking_post_id_FK__created_at")
    total_contributions = float(contribs.aggregate(t=Sum("paid_amount"))["t"] or 0)
    contribution_records = [{
        "contribution_id": c.contribution_id_PK,
        "aid_type": c.aid_tracking_post_id_FK.aid_type if c.aid_tracking_post_id_FK else "",
        "target_month": c.aid_tracking_post_id_FK.target_month if c.aid_tracking_post_id_FK else "",
        "expected_amount": float(c.expected_amount),
        "paid_amount": float(c.paid_amount),
        "payment_date": c.payment_date.isoformat() if c.payment_date else "",
        "status": c.status,
    } for c in contribs]
    total_contributions = float(contribs.aggregate(t=Sum("paid_amount"))["t"] or 0)

    medical_claim_ids = list(member.medicalaid_set.values_list("medical_aid_id_PK", flat=True))
    death_claim_ids = list(member.deathaid_set.values_list("death_aid_id_PK", flat=True))
    for ma in MedicalAid.objects.filter(member_id_FK=member).order_by("-request_date"):
        record = {
            "medical_aid_id": ma.medical_aid_id_PK,
            "request_date": ma.request_date.isoformat() if ma.request_date else "",
            "requested_amount": float(ma.requested_amount or 0),
            "hospital_name": ma.hospital_name,
            "hospital_address": ma.hospital_address or "",
            "admission_date": ma.admission_date.isoformat() if ma.admission_date else "",
            "discharge_date": ma.discharge_date.isoformat() if ma.discharge_date else "",
            "reason_for_request": ma.reason_for_request or "",
            "hospital_bill_amount": float(ma.hospital_bill_amount or 0),
            "validated_aid_amount": float(ma.validated_aid_amount),
            "status": ma.status,
        }
        medical_aid_records.append(record)
        if ma.status in ("Pending", "Pending Review", "Pending Treasurer Review", "Pending Auditor Verification", "Pending President Approval"):
            medical_aid_pending += 1
        elif ma.status in ("Approved", "Verified"):
            medical_aid_approved += 1
        elif ma.status in ("Released", "Completed"):
            medical_aid_released += 1

    death_aid_records = []
    death_aid_pending = 0
    death_aid_approved = 0
    death_aid_released = 0
    for da in DeathAid.objects.filter(member_id_FK=member).order_by("-claim_date"):
        death_aid_records.append({
            "death_aid_id": da.death_aid_id_PK,
            "claim_date": da.claim_date.isoformat() if da.claim_date else "",
            "claim_type": da.claim_type,
            "deceased_name": da.deceased_name,
            "benefit_amount": float(da.benefit_amount),
            "status": da.status,
        })
        if da.status in ("Pending", "Pending Review", "Pending Treasurer Review", "Pending Auditor Verification", "Pending President Approval"):
            death_aid_pending += 1
        elif da.status in ("Approved", "Verified"):
            death_aid_approved += 1
        elif da.status in ("Released", "Completed"):
            death_aid_released += 1

    total_claims = len(medical_aid_records) + len(death_aid_records)

    # Determine if there's an active pending claim with full details for dashboard review
    pending_claim = None
    pending_statuses = tuple(Status.ALL_PENDING) + (
        "Pending Review",
        "Pending Treasurer Review",
        "Pending Auditor Verification",
        "Pending President Approval",
    )
    ma_pending = MedicalAid.objects.filter(member_id_FK=member, status__in=pending_statuses).order_by("-request_date").first()
    if ma_pending:
        pending_claim = {
            "id": ma_pending.medical_aid_id_PK,
            "claim_type": "medical_aid",
            "status": ma_pending.status,
            "hospital_name": ma_pending.hospital_name,
            "hospital_address": ma_pending.hospital_address or "",
            "admission_date": ma_pending.admission_date.isoformat() if ma_pending.admission_date else "",
            "discharge_date": ma_pending.discharge_date.isoformat() if ma_pending.discharge_date else "",
            "reason_for_request": ma_pending.reason_for_request or "",
            "requested_amount": float(ma_pending.requested_amount or 0),
        }
    da_pending = DeathAid.objects.filter(member_id_FK=member, status__in=pending_statuses).order_by("-claim_date").first()
    pending_medical_claim = ma_pending is not None
    pending_death_claim = da_pending is not None
    pending_medical_claim_data = None
    pending_death_claim_data = None
    if ma_pending:
        pending_medical_claim_data = {
            "id": ma_pending.medical_aid_id_PK,
            "claim_type": "medical_aid",
            "status": ma_pending.status,
            "hospital_name": ma_pending.hospital_name,
            "hospital_address": ma_pending.hospital_address or "",
            "admission_date": ma_pending.admission_date.isoformat() if ma_pending.admission_date else "",
            "discharge_date": ma_pending.discharge_date.isoformat() if ma_pending.discharge_date else "",
            "reason_for_request": ma_pending.reason_for_request or "",
            "requested_amount": float(ma_pending.requested_amount or 0),
        }
    if not pending_claim and da_pending:
        pending_claim = {
            "id": da_pending.death_aid_id_PK,
            "claim_type": "death_aid",
            "status": da_pending.status,
            "deceased_name": da_pending.deceased_name,
            "date_of_death": da_pending.date_of_death.isoformat() if da_pending.date_of_death else "",
            "funeral_location": da_pending.funeral_location or "",
            "benefit_amount": float(da_pending.benefit_amount or 0),
        }
    if da_pending:
        pending_death_claim_data = {
            "id": da_pending.death_aid_id_PK,
            "claim_type": "death_aid",
            "status": da_pending.status,
            "deceased_name": da_pending.deceased_name,
            "date_of_death": da_pending.date_of_death.isoformat() if da_pending.date_of_death else "",
            "funeral_location": da_pending.funeral_location or "",
            "benefit_amount": float(da_pending.benefit_amount or 0),
        }

    notifs = Notification.objects.filter(recipient_type="member", recipient_id=member.member_id_PK).order_by("-sent_at")[:20]
    notifications = []
    for n in notifs:
        notifications.append({
            "notification_id": n.notification_id_PK,
            "notification_type": n.notification_type,
            "message": n.message,
            "category": n.category or "",
            "sent_at": n.sent_at.isoformat() if n.sent_at else "",
            "is_read": n.is_read,
            "sender_name": n.sender_name or "",
            "sender_role": n.sender_role or "",
            "receipt_number": n.receipt_number or "",
        })

    payment_history = []
    for f in MembershipFee.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("-payment_date")[:10]:
        payment_history.append({
            "type": "Membership Fee",
            "amount": float(f.amount),
            "method": f.payment_method,
            "status": f.payment_status,
            "date": f.payment_date.isoformat() if f.payment_date else "",
            "reference": f.receipt_number or "",
            "treasurer_status": getattr(f, 'treasurer_status', ''),
            "auditor_status": getattr(f, 'auditor_status', ''),
            "president_status": getattr(f, 'president_status', ''),
        })
    for d in MonthlyDues.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("-payment_date")[:10]:
        # Format month as word (e.g., "September 2024")
        month_name = ""
        if d.month_covered:
            try:
                year, month = d.month_covered.split('-')
                month_name = f"{calendar.month_name[int(month)]} {year}"
            except:
                month_name = d.month_covered
        
        payment_history.append({
            "type": "Monthly Dues",
            "month_covered": d.month_covered,  # Keep original for filtering
            "month_covered_display": month_name,  # Display name
            "amount": float(d.amount),
            "method": d.payment_method,
            "status": d.payment_status,
            "date": d.payment_date.isoformat() if d.payment_date else "",
            "reference": d.receipt_number or "",
        })
    payment_history.sort(key=lambda x: x["date"], reverse=True)

    member_since_date = ""
    member_since_label = ""
    if member.date_joined:
        member_since_date = member.date_joined.isoformat()
        member_since_label = member.date_joined.strftime("%b %Y")
    else:
        earliest = None
        first_fee = MembershipFee.objects.filter(member_id_FK=member).order_by("payment_date").first()
        if first_fee and first_fee.payment_date:
            earliest = first_fee.payment_date
        first_dues = MonthlyDues.objects.filter(member_id_FK=member, payment_date__isnull=False).order_by("payment_date").first()
        if first_dues and first_dues.payment_date:
            if earliest is None or first_dues.payment_date < earliest:
                earliest = first_dues.payment_date
        if earliest:
            member_since_date = earliest.isoformat()
            member_since_label = earliest.strftime("%b %Y")
        else:
            member_since_label = "N/A"

    rep = Claimant.objects.filter(member_id_FK=member).first()
    rep_data = None
    if rep:
        rep_data = {
            "full_name": rep.full_name,
            "contact_number": rep.contact_number or "",
            "relationship": rep.relationship_to_member,
        }

    latest_payment_date = None
    first_payment_method = ""
    
    # Get latest payment from MonthlyDues - use treasurer_approved_at when available (when treasurer encoded it)
    last_dues = MonthlyDues.objects.filter(
        member_id_FK=member,
        treasurer_approved_at__isnull=False
    ).order_by("-treasurer_approved_at").first()
    if last_dues and last_dues.treasurer_approved_at:
        latest_payment_date = last_dues.treasurer_approved_at.date()
        first_payment_method = last_dues.payment_method or ""
    
    # If no treasurer approval date, try payment_date
    if not latest_payment_date:
        last_dues = MonthlyDues.objects.filter(
            member_id_FK=member,
            payment_date__isnull=False
        ).order_by("-payment_date").first()
        if last_dues and last_dues.payment_date:
            latest_payment_date = last_dues.payment_date
            if not first_payment_method:
                first_payment_method = last_dues.payment_method or ""
    
    # If no monthly dues, check MembershipFee
    if not latest_payment_date:
        last_fee = MembershipFee.objects.filter(
            member_id_FK=member,
            payment_date__isnull=False
        ).order_by("-payment_date").first()
        if last_fee and last_fee.payment_date:
            latest_payment_date = last_fee.payment_date
            if not first_payment_method:
                first_payment_method = last_fee.payment_method or ""
    
    # If still no payment date, try to get method from any record
    if not first_payment_method:
        last_pmt = MonthlyDues.objects.filter(member_id_FK=member).order_by("-payment_date").first()
        if last_pmt:
            first_payment_method = last_pmt.payment_method or ""
        if not first_payment_method:
            last_fee = MembershipFee.objects.filter(member_id_FK=member).order_by("-payment_date").first()
            if last_fee:
                first_payment_method = last_fee.payment_method or ""
    
    today = date.today()
    probe = today.replace(day=1)
    covered_months = set(
        MonthlyDues.objects.filter(
            member_id_FK=member,
            payment_status__in=["Pending", "Paid", "Full Payment"],
        ).values_list("month_covered", flat=True)
    )
    next_m = None
    for _ in range(24):
        probe = probe + timedelta(days=32)
        probe = probe.replace(day=1)
        if probe.strftime("%Y-%m") not in covered_months:
            next_m = probe
            break
    next_due_date = next_m if next_m else None
    advance_count = sum(1 for mc in covered_months if mc > today.strftime("%Y-%m"))

    total_claims = len(medical_aid_records) + len(death_aid_records)
    total_financial_contributions = membership_fee_amount + total_dues_paid + total_contributions
    total_paid = membership_fee_amount + total_dues_paid
    pending_amount = total_dues_pending

    rep = Claimant.objects.filter(member_id_FK=member).first()

    return JsonResponse({
        "ok": True,
        "member_data": member_data,
        "membership_fee_status": membership_fee_status,
        "membership_fee_amount": membership_fee_amount,
        "membership_fee_paid": membership_fee_paid,
        "has_membership_fee": has_membership_fee,
        "membership_fee_submitted": membership_fee_submitted,
        "total_dues_paid": total_dues_paid,
        "total_dues_pending": total_dues_pending,
        "total_dues_unpaid": total_dues_unpaid,
        "outstanding_balance": outstanding_balance,
        "unpaid_months": unpaid_months,
        "unpaid_months_label": ", ".join(m["label"] for m in unpaid_months),
        "total_contributions": total_contributions,
        "total_financial_contributions": total_financial_contributions,
        "total_paid": total_paid,
        "pending_amount": pending_amount,
        "next_due_date": next_due_date,
        "advance_count": advance_count,
        "latest_payment_date": latest_payment_date,
        "first_payment_method": first_payment_method,
        "total_claims": total_claims,
        "dues_records": dues_records,
        "contribution_records": contribution_records,
        "medical_aid_records": medical_aid_records,
        "death_aid_records": death_aid_records,
        "notifications": notifications,
        "payment_history": payment_history,
        "rep_data": rep_data,
        "member_since_date": member_since_date,
        "member_since_label": member_since_label,
        "medical_aid_pending": medical_aid_pending,
        "medical_aid_approved": medical_aid_approved,
        "medical_aid_released": medical_aid_released,
        "death_aid_pending": death_aid_pending,
        "death_aid_approved": death_aid_approved,
        "death_aid_released": death_aid_released,
        "pending_claim": pending_claim,
        "pending_medical_claim": pending_medical_claim,
        "pending_death_claim": pending_death_claim,
        "pending_medical_claim_data": pending_medical_claim_data,
        "pending_death_claim_data": pending_death_claim_data,
    })


@require_POST
def member_upload_picture(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)

    file = request.FILES.get("profile_picture")
    if not file:
        return JsonResponse({"ok": False, "error": "No file provided."}, status=400)

    # Validate file type
    allowed = ("image/jpeg", "image/png", "image/webp", "image/gif")
    if file.content_type not in allowed:
        return JsonResponse({"ok": False, "error": "Only JPG, PNG, WebP, GIF allowed."}, status=400)

    # Reject oversized uploads before saving (5 MB cap).
    max_bytes = 5 * 1024 * 1024
    if file.size and file.size > max_bytes:
        return JsonResponse({"ok": False, "error": "Photo must be 5 MB or smaller."}, status=400)

    member.profile_picture = file
    member.save(update_fields=["profile_picture"])
    return JsonResponse({
        "ok": True,
        "url": member.profile_picture.url,
        "message": "Profile picture updated.",
    })


def _friendly_device_name(user_agent: str) -> str:
    """Short human-readable device label from a raw User-Agent string."""
    ua = (user_agent or "").lower()
    if not ua or ua == "unknown":
        return "Unknown device"
    if "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        os_name = "iOS"
    elif "windows" in ua:
        os_name = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Device"
    if "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua and "chromium" not in ua:
        browser = "Chrome"
    elif "firefox" in ua or "fxios" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    return f"{browser} on {os_name}"


@require_GET
def member_sessions(request: HttpRequest):
    """Login activity for the signed-in member: devices, IPs, last-active,
    and status. Member-facing evidence of continuous verification."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer_id = request.session.get("officer_id")
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer not found."}, status=404)

    current_token = request.session.get("access_token")
    now = timezone.now()
    items = []
    sessions = AccessSession.objects.filter(user_id_FK=officer).order_by("-last_activity_at", "-session_id_PK")
    for s in sessions:
        revoked = s.revoked_at is not None or (s.session_status or "").lower() == "revoked"
        expired = (not revoked) and s.expires_at is not None and s.expires_at <= now
        policy = s.session_policy or {}
        items.append({
            "id": s.session_id_PK,
            "device": _friendly_device_name(s.device_info),
            "ip": (policy.get("ip") if isinstance(policy, dict) else None) or s.ip_address or "—",
            "started_at": s.issued_at.isoformat() if s.issued_at else "",
            "last_active_at": s.last_activity_at.isoformat() if s.last_activity_at else "",
            "auth_method": (policy.get("auth_method") if isinstance(policy, dict) else None) or "—",
            "is_current": bool(current_token) and s.token_id == current_token,
            "status": "current" if (bool(current_token) and s.token_id == current_token) else ("revoked" if revoked else ("expired" if expired else "active")),
        })
    return JsonResponse({"ok": True, "sessions": items})


@require_POST
def member_revoke_session(request: HttpRequest, session_id: int):
    """Sign out one of the member's other devices (revoke that session)."""
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    officer_id = request.session.get("officer_id")
    try:
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
    except OfficerUser.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Officer not found."}, status=404)

    try:
        sess = AccessSession.objects.get(session_id_PK=session_id, user_id_FK=officer)
    except AccessSession.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Session not found."}, status=404)

    current_token = request.session.get("access_token")
    if current_token and sess.token_id == current_token:
        return JsonResponse({"ok": False, "error": "This is your current session. Use Log out to end it."}, status=400)
    if sess.revoked_at is not None:
        return JsonResponse({"ok": True, "message": "Session already signed out."})

    sess.revoked_at = timezone.now()
    sess.session_status = "Revoked"
    sess.expires_at = timezone.now()
    sess.save(update_fields=["revoked_at", "session_status", "expires_at"])
    return JsonResponse({"ok": True, "message": "Device signed out."})


@require_GET
def member_certificates(request: HttpRequest):
    """
    Get member's certificates with pagination
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)
    
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 6))
        
        certificates_qs = Certificate.objects.filter(
            member=member
        ).select_related('event').order_by('-generated_at')
        
        total_certificates = certificates_qs.count()
        total_pages = max(1, (total_certificates + page_size - 1) // page_size)
        
        start = (page - 1) * page_size
        end = start + page_size
        
        certificates = certificates_qs[start:end]
        
        cert_list = []
        for cert in certificates:
            cert_list.append({
                'certificate_id': cert.certificate_id_PK,
                'certificate_number': cert.certificate_number,
                'event_title': cert.event.title,
                'event_date': cert.event.event_date.strftime('%B %d, %Y'),
                'issue_date': cert.event.certificate_issue_date.strftime('%B %d, %Y') if cert.event.certificate_issue_date else cert.event.event_date.strftime('%B %d, %Y'),
                'email_status': cert.email_status,
                'generated_at': cert.generated_at.strftime('%B %d, %Y'),
                'pdf_file': cert.pdf_file.url if cert.pdf_file else None,
            })
        
        return JsonResponse({
            'ok': True,
            'certificates': cert_list,
            'total': total_certificates,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages
        })
        
    except Exception as e:
        return JsonResponse({
            'ok': False,
            'error': str(e)
        }, status=500)


@require_GET
def member_certificate_view(request: HttpRequest, certificate_id: int):
    """
    View a specific certificate (render HTML)
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)
    
    try:
        certificate = Certificate.objects.get(
            certificate_id_PK=certificate_id,
            member=member
        )
        
        # Get certificate settings
        from core_system.models import CertificateSettings
        settings_obj = CertificateSettings.objects.first()
        
        # Prepare certificate data
        cert_data = {
            'recipient_name': member.full_name,
            'event_title': certificate.event.title,
            'event_date': certificate.event.event_date.strftime('%Y-%m-%d'),
            'event_venue': certificate.event.venue,
            'day': certificate.event.event_date.day,
            'month_year': certificate.event.event_date.strftime('%B %Y'),
            'place': certificate.event.given_place or certificate.event.venue,
            'president_name': settings_obj.president_name if settings_obj else '',
            'president_position': settings_obj.president_position if settings_obj else 'ISUCauFA President',
            'secretary_name': settings_obj.secretary_name if settings_obj else '',
            'secretary_position': settings_obj.secretary_position if settings_obj else 'ISUCauFA, Inc. Secretary',
            'faculty_regent_name': settings_obj.faculty_regent_name if settings_obj else '',
            'faculty_regent_position': settings_obj.faculty_regent_position if settings_obj else 'Faculty Regent',
            'certificate_number': certificate.certificate_number,
            'president_signature_url': settings_obj.president_signature.url if settings_obj and settings_obj.president_signature else None,
            'secretary_signature_url': settings_obj.secretary_signature.url if settings_obj and settings_obj.secretary_signature else None,
            'faculty_regent_signature_url': settings_obj.faculty_regent_signature.url if settings_obj and settings_obj.faculty_regent_signature else None,
        }
        
        # Render certificate template
        from django.template.loader import render_to_string
        cert_html = render_to_string('website/Secretary/certificate.html', cert_data)
        
        return HttpResponse(cert_html, content_type='text/html')
        
    except Certificate.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Certificate not found"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_GET
def member_certificate_download(request: HttpRequest, certificate_id: int):
    """
    Download a certificate PDF
    """
    guard = require_officer_session(request)
    if guard is not None:
        return guard
    member, err = _get_member_from_session(request)
    if not member:
        return JsonResponse({"ok": False, "error": err}, status=400)
    
    try:
        certificate = Certificate.objects.get(
            certificate_id_PK=certificate_id,
            member=member
        )
        
        # Regenerate the PDF at download time so the download uses current layout.
        from core_system.certificate_pdf import generate_certificate_pdf
        cert_data = {
            'recipient_name': member.full_name,
            'event_title': certificate.event.title,
            'event_date': certificate.event.event_date.strftime('%Y-%m-%d'),
            'event_venue': certificate.event.venue,
            'day': certificate.event.event_date.day,
            'month_year': certificate.event.event_date.strftime('%B %Y'),
            'place': certificate.event.given_place or certificate.event.venue,
            'president_name': certificate.president_name if hasattr(certificate, 'president_name') else '',
            'president_position': certificate.president_position if hasattr(certificate, 'president_position') else 'ISUCauFA President',
            'secretary_name': certificate.secretary_name if hasattr(certificate, 'secretary_name') else '',
            'secretary_position': certificate.secretary_position if hasattr(certificate, 'secretary_position') else 'ISUCauFA, Inc. Secretary',
            'faculty_regent_name': certificate.faculty_regent_name if hasattr(certificate, 'faculty_regent_name') else '',
            'faculty_regent_position': certificate.faculty_regent_position if hasattr(certificate, 'faculty_regent_position') else 'Faculty Regent',
            'certificate_number': certificate.certificate_number,
            'president_signature_url': None,
            'secretary_signature_url': None,
            'faculty_regent_signature_url': None,
        }

        from core_system.models import CertificateSettings
        settings_obj = CertificateSettings.objects.first()
        if settings_obj:
            cert_data.update({
                'president_name': settings_obj.president_name,
                'president_position': settings_obj.president_position,
                'secretary_name': settings_obj.secretary_name,
                'secretary_position': settings_obj.secretary_position,
                'faculty_regent_name': settings_obj.faculty_regent_name,
                'faculty_regent_position': settings_obj.faculty_regent_position,
                'president_signature_url': settings_obj.president_signature.url if settings_obj.president_signature else None,
                'secretary_signature_url': settings_obj.secretary_signature.url if settings_obj.secretary_signature else None,
                'faculty_regent_signature_url': settings_obj.faculty_regent_signature.url if settings_obj.faculty_regent_signature else None,
            })

    except Certificate.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Certificate not found"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# The endpoints below back the Member Dashboard's Transparency tab.
#
# Three rules hold across this whole block:
#   1. Scope fails closed. No linked Member row means 403, never "show
#      everything anyway".
#   2. Financial Overview is the only organisation-wide panel. Balance, total
#      collections, inflows and outflows are the association's own position and
#      a member is entitled to see them, always, unmasked.
#   3. Everything else is member-only, and no endpoint takes a member id from
#      the client — the member comes from the session, so there is no
#      parameter to tamper with.
#
# Officer endpoints stay role-locked; none of them were widened to get here.
# Every read is logged: a member checking the books is itself an auditable
# event.
# ==========================================================================


def _transparency_guard(request):
    """Session guard + member scope for the transparency endpoints.

    Returns (member, error_response). Callers check the response first;
    `member` is None whenever the response is not None.
    """
    guard = require_officer_session(request)
    if guard is not None:
        return None, guard

    member, err = _get_member_from_session(request)
    if not member:
        return None, JsonResponse(
            {"ok": False, "error": err or "No linked member profile."}, status=403
        )

    return member, None


@require_GET
def member_fund_summary(request: HttpRequest):
    """Financial Overview: balance, total collections, inflows, outflows.

    Organisation-wide and always unmasked — this is the one panel a member
    reads as an association member rather than as a private record holder.
    A dashboard-level read, so it is logged once as a summary entry rather than
    one row per figure shown.
    """
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    _log_sensitive_read(
        request, "fund_transaction", [0],
        "Member viewed the fund financial overview",
    )
    payload = transparency.fund_summary()
    payload["member_name"] = member.full_name
    return JsonResponse(payload)


@require_GET
def member_fund_trend(request: HttpRequest):
    """Per-month inflow / outflow / running balance for the trend charts."""
    _member, err = _transparency_guard(request)
    if err is not None:
        return err

    try:
        months = int(request.GET.get("months", 12) or 12)
    except (TypeError, ValueError):
        months = 12

    _log_sensitive_read(request, "fund_transaction", [0], "Member viewed the fund trend")
    return JsonResponse(transparency.monthly_trend(months=months))


@require_GET
def member_fund_ledger(request: HttpRequest):
    """Cash flow: the member's OWN money in / money out, filterable, paginated.

    Member-only. This deliberately replaces the organisation-wide ledger a
    member never needs; it is also the one personal timeline, so it does not
    repeat the dashboard's separate transaction history.
    """
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    _log_sensitive_read(
        request, "member_ledger", [member.member_id_PK],
        "Member viewed their cash flow",
    )
    return JsonResponse(transparency.member_cash_flow(member, request.GET))


@require_GET
def member_fund_movements(request: HttpRequest):
    """Aggregated fund movements for the member FUND Movement card.

    Batch-level (one row per collection batch, full totals) instead of the
    raw per-member FundTransaction rows. Member-only, read-logged.
    ``?limit=`` caps the newest-first groups (default 5 for the Top-5 card,
    up to 200 for the full Transactions view).
    """
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    try:
        limit = int(request.GET.get("limit", 5) or 5)
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 200))
    try:
        offset = int(request.GET.get("offset", 0) or 0)
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)

    _log_sensitive_read(
        request, "fund_transaction", [0],
        "Member viewed aggregated fund movements",
    )
    return JsonResponse(transparency.fund_movements(max_groups=limit, offset=offset))


@require_GET
def member_fund_transaction_detail(request: HttpRequest, movement_id: str):
    """One of the member's own movements, with its supporting remarks.

    The id is resolved through the member's own movement list, so a movement
    belonging to another member is simply not found.
    """
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    detail = transparency.member_transaction_detail(member, movement_id)
    if detail is None:
        return JsonResponse({"ok": False, "error": "Movement not found."}, status=404)

    _log_sensitive_read(
        request, "member_ledger", [member.member_id_PK],
        f"Member viewed their cash flow movement '{movement_id}'",
    )
    return JsonResponse(detail)


@require_GET
def member_contributions(request: HttpRequest):
    """Contribution history for the signed-in member."""
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    _log_sensitive_read(
        request, "contribution", [member.member_id_PK],
        "Member viewed contribution history",
    )
    return JsonResponse(transparency.contributions(member))


@require_GET
def member_dues_matrix(request: HttpRequest):
    """Month x status grid for the member's monthly dues."""
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    try:
        months = int(request.GET.get("months", 24) or 24)
    except (TypeError, ValueError):
        months = 24

    _log_sensitive_read(
        request, "monthly_dues", [member.member_id_PK],
        "Member viewed monthly dues status",
    )
    return JsonResponse(transparency.dues_matrix(member, months=months))


@require_GET
def member_payment_records(request: HttpRequest):
    """Payment records: one-time membership fee + monthly dues, with the
    Treasurer / Auditor / President verification columns."""
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    _log_sensitive_read(
        request, "monthly_dues", [member.member_id_PK],
        "Member viewed payment records",
    )
    return JsonResponse(transparency.payments(member, request.GET))


@require_GET
def member_due_breakdown(request: HttpRequest):
    """Combined due + aid breakdown for a specific month.
    
    Returns detailed breakdown including:
    - Monthly due assessment (expected, deducted, outstanding)
    - Aid contributions for that month (medical/death aid)
    - Recipient details for each aid
    - Total collected across all members for that month
    """
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    year = request.GET.get("year")
    month = request.GET.get("month")
    
    if not year or not month:
        return JsonResponse({"ok": False, "error": "Year and month parameters required"}, status=400)
    
    try:
        year = int(year)
        month = int(month)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid year or month"}, status=400)

    _log_sensitive_read(
        request, "due_breakdown", [member.member_id_PK],
        f"Member viewed due breakdown for {year}-{month:02d}",
    )
    return JsonResponse(transparency.due_breakdown(member, year, month))


@require_GET
def member_due_year_breakdown(request: HttpRequest):
    """Whole-year DUE drawer payload: 12 monthly breakdowns, one request."""
    member, err = _transparency_guard(request)
    if err is not None:
        return err

    try:
        year = int(request.GET.get("year") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid year"}, status=400)
    if year < 2000 or year > 2100:
        return JsonResponse({"ok": False, "error": "Year out of range"}, status=400)

    _log_sensitive_read(
        request, "due_breakdown", [member.member_id_PK],
        f"Member viewed due breakdown for year {year}",
    )
    return JsonResponse(transparency.due_year_breakdown(member, year))
