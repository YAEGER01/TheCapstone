import decimal
import hashlib
import json
import logging
import mimetypes
from decimal import Decimal
import os
import re
import uuid
from datetime import datetime, timedelta
from django.http import Http404, HttpResponse, HttpRequest, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.conf import settings
from django.core.files.storage import default_storage
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F, Q, Sum, Count, Min
from django.db.models.functions import ExtractMonth
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

from core_system.api_utils import member_to_json

from core_system.guards import check_zero_trust, require_officer_session, require_role
from core_system.member_views import MEMBER_FAMILY_CATEGORIES
from core_system.aid_setaside import (
    AID_PURPOSES,
    SETASIDE_SOURCE_TYPES,
    consume_set_asides,
    setaside_available_for_post,
    setaside_reserve_by_aid_type,
    setaside_totals_by_post,
)
from core_system.ledger_utils import member_balance
from core_system.services.mfa_service import (
    generate_otp,
    mask_email,
    send_mfa_email,
    verify_otp,
)
from core_system.models import (
    AidTrackingPost,
    AssessmentItem,
    Contribution,
    FundTransaction,
    MemberAssessment,
    MemberAssessmentAllocation,
    Member,
    MemberRegistrationRequest,
    MembershipFee,
    Notification,
    OfficerUser,
    MonthlyAssessment,
    MonthlyAssessmentDocument,
    MonthlyDues,
    PayrollBatch,
    PayrollDeduction,
    TransactionVerification,
    MedicalAid,
    DeathAid,
    Claimant,
    SupportingProof,
    FinancialDocumentArchive,
    AuditFindingsReport,
    TransactionArchive,
    GlobalAuditTrail,
    SensitiveReadLog,
    SystemSetting,
    MemberLedger,
    SalaryDeductionExemption,
    PositionRank,
    PositionCategory,
    Document,
    DocumentActivity,
    DocumentPin,
    Category,
)
from core_system.constants.policy_constants import (
    check_medical_aid_once_per_year,
    get_accidental_sickness_aid_benefit,
    get_accidental_sickness_aid_threshold,
    get_death_aid_amount,
    get_expected_dues_amount,
    get_membership_fee_amount,
    get_monthly_dues_amount,
    is_exempt_from_dues_and_aid,
    is_retired_member,
)
from core_system.constants.status_constants import RegistrationStatus, Status
from core_system.services.email_service import (
    send_html_email,
    send_html_email_async,
    send_registration_status_update_email,
    send_registration_returned_email,
    send_registration_rejected_email,
    send_registration_received_email,
    send_member_deduction_email,
    send_create_member_received_email,
    send_create_member_status_update_email,
    send_create_member_returned_email,
    send_create_member_rejected_email,
)
from core_system.services.notifications import notify_member
from core_system.isu_email_guard import is_membership_duplicate_email_allowed
from core_system.dues_backfill_guard import should_flag_backfill
from core_system.shared_view_utils import (
    MODEL_MAP,
    UPDATABLE_FIELDS,
    MONTH_COVERED_PATTERN,
    PAYMENT_ENTITY_TYPE_LABELS,
    document_file_bytes,
    normalize_month_covered,
    resolve_officer_from_session,
    resolve_member_from_input,
    check_member_not_retired,
    validate_isu_email,
    validate_ph_contact,
    _get_rejection_info,
    _get_encoder_name,
    _get_proof_url,
    _get_monthly_dues_proof_url,
    _sha256_of_uploaded_file,
    _compute_row_signature,
    _link_proof_to_record,
    proof_upload_blocked_response,
    _audit_evidence_filename,
    _get_auditor_finding_evidence,
    _get_auditor_verification_remarks,
    _serialize_value,
    _serialize_for_audit,
    _officer_to_json,
    _record_audit_trail,
    _log_sensitive_read,
    _notify_release,
    set_treasurer_rejected,
    archive_transaction,
    _broadcast_pending_counts,
    _broadcast_to_group,
    _status_field_updates,
)
from django.core.files.storage import default_storage
from django.http import HttpRequest

logger = logging.getLogger(__name__)

# ==========================================================================
# TREASURER WORKSPACE VIEWS
# ==========================================================================

def _broadcast_treasurer(section: str) -> None:
    try:
        async_to_sync(get_channel_layer().group_send)(
            "treasurer_dashboard",
            {"type": "data_changed", "section": section},
        )
    except Exception:
        pass


@require_GET
def treasurer_officers_list(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    officers = OfficerUser.objects.select_related("department_id_FK").order_by("-created_at", "full_name")
    officers_json = [_officer_to_json(o) for o in officers]

    ip = request.META.get("REMOTE_ADDR")
    device_info = request.META.get("HTTP_USER_AGENT", "")
    actor_name = getattr(officer, "full_name", "") if officer else ""
    actor_role = getattr(officer, "role", "") if officer else ""

    _record_audit_trail(
        table="officer_user",
        record_id=0,
        action="READ",
        actor=officer,
        ip=ip,
        device_info=device_info,
        notes=f"Shared read by {actor_role} — officer dropdown loaded for member enrollment form on treasurer dashboard",
    )

    SensitiveReadLog.objects.bulk_create([
        SensitiveReadLog(
            table_name="officer_user",
            record_id=o["id"],
            reader_type=actor_role,
            reader_id=getattr(officer, "user_id_PK", None) if officer else None,
            device_info=device_info,
        )
        for o in officers_json
    ])

    return JsonResponse({"ok": True, "officers": officers_json})


@never_cache
@ensure_csrf_cookie
def treasurer_dashboard(request):
    """Loads the unified Treasurer/Auditor executive workspace page."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # Header identity: Ambassador Green = logged-in officer full_name (fallback: role: treasurer).
    officer_full_name = ""
    officer_role = "treasurer"

    # Project uses a custom officer session (see auth_views.py). request.user may not be set.
    stored_officer_id = request.session.get("officer_id")
    if stored_officer_id is not None:
        try:
            officer = OfficerUser.objects.get(user_id_PK=int(stored_officer_id))
            officer_full_name = getattr(officer, "full_name", "") or ""
            officer_role = getattr(officer, "role", None) or officer_role
        except Exception:
            pass

    context = {
        "officer_full_name": officer_full_name,
        "officer_role": officer_role,
        "expected_dues_default_amount": get_expected_dues_amount(),
        "membership_fee_amount": get_membership_fee_amount(),
        "access_token": request.session.get("access_token", ""),
        "sickness_aid_threshold": get_accidental_sickness_aid_threshold(),
        "sickness_aid_benefit": get_accidental_sickness_aid_benefit(),
        "available_officers": list(
            OfficerUser.objects.filter(account_status__iexact="active", linked_member_profiles__isnull=True)
            .select_related("department_id_FK")
            .order_by("full_name")
            .distinct()
        ),
    }

    # If full_name missing/empty: use the fallback as required by the spec.
    if not officer_full_name.strip():
        context["officer_full_name"] = context["officer_role"]

    context["returned_entries_count"] = TransactionVerification.objects.filter(
        table_name="membership_fee",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED],
    ).count()

    context["monthly_dues_returned_count"] = TransactionVerification.objects.filter(
        table_name="monthly_dues",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED],
    ).count()

    context["medical_aid_returned_count"] = TransactionVerification.objects.filter(
        table_name="medical_aid",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED],
    ).count()

    context["death_aid_returned_count"] = TransactionVerification.objects.filter(
        table_name="death_aid",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED],
    ).count()

    context["active_aid_posts_count"] = AidTrackingPost.objects.filter(
        is_active=True,
    ).count()

    context["departments"] = list(
        Member.objects.filter(department__isnull=False)
        .values("department")
        .annotate(count=Count("member_id_PK"))
        .order_by("department")
    )
    context["departments_unassigned_count"] = Member.objects.filter(
        Q(department__isnull=True) | Q(department="")
    ).count()

    current_month = timezone.now().strftime("%Y-%m")
    dept_totals = dict(
        Member.objects.filter(department__isnull=False)
        .values("department")
        .annotate(total=Count("member_id_PK"))
        .values_list("department", "total")
    )
    dept_dues_paid = dict(
        MonthlyDues.objects.filter(month_covered=current_month)
        .values("member_id_FK__department")
        .annotate(dues_paid=Count("member_id_FK", distinct=True))
        .values_list("member_id_FK__department", "dues_paid")
    )
    dept_fees_paid = dict(
        MembershipFee.objects.filter(payment_status__in=["Full Payment", "Partial"])
        .values("member_id_FK__department")
        .annotate(fees_paid=Count("member_id_FK", distinct=True))
        .values_list("member_id_FK__department", "fees_paid")
    )

    context["department_payment_tracking"] = []
    for dept_name, total in sorted(dept_totals.items()):
        dues_paid = dept_dues_paid.get(dept_name, 0)
        fees_paid = dept_fees_paid.get(dept_name, 0)
        context["department_payment_tracking"].append({
            "department": dept_name,
            "total_members": total,
            "dues_paid_current_month": dues_paid,
            "dues_collection_rate": round((dues_paid / total * 100) if total > 0 else 0, 1),
            "membership_fee_paid": fees_paid,
            "fee_collection_rate": round((fees_paid / total * 100) if total > 0 else 0, 1),
        })

    return render(request, "website/Treasurer/treasurer_dashboard.html", context)


# --- Member Enrollment / Listing APIs (Treasurer) ---

# PH mobile numbers: 11 digits starting with 09 (e.g. 09171234567).
# Validation lives in shared_view_utils so every enrollment path enforces the
# same ISU email (@isu.edu.ph) and PH mobile rules.
PH_CONTACT_PATTERN = re.compile(r"^09\d{9}$")


def _validate_ph_contact(raw_value: str):
    """Return a normalized 11-digit PH contact number, an error message, or None."""
    value, error = validate_ph_contact(raw_value)
    if error:
        return None, error
    return value, None


def _unique_member_username(full_name: str, email: str, member_id: int) -> str:
    """Generate a unique dashboard login username from the member's NAME.

    Format: firstname.lastname (lowercase, e.g. "juan.delacruz"). Falls back
    to the email local-part (then the member id) when the name is unusable.
    A numeric suffix resolves collisions with existing accounts."""
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    base = ""
    if len(parts) >= 2:
        base = f"{parts[0]}.{parts[-1]}".lower()
    elif parts:
        base = parts[0].lower()
    if not base:
        base = (email or "").split("@", 1)[0].strip().lower() or f"member{member_id}"
    base = re.sub(r"[^a-z0-9.]", "", base) or f"member{member_id}"
    username = base
    suffix = 1
    while (
        OfficerUser.objects.filter(username__iexact=username).exists()
        or Member.objects.filter(employee_id__iexact=username).exists()
    ):
        suffix += 1
        username = f"{base}{suffix}"
    return username


def _parse_classification(value: str) -> str:
    """Normalize a member-classification input to a valid choice."""
    value = (value or "").strip()
    valid = {c[0] for c in Member.MEMBER_CLASSIFICATION_CHOICES}
    return value if value in valid else Member.CLASSIFICATION_TEACHING


def _provision_member_account(member: Member, email: str, officer):
    """Create a dashboard login account for a member with a simple initial password.

    Password format is ISUCauFA_YYMMDD (stamped from the member's join date).
    The password is delivered to the member's email only — it is never shown
    on any officer screen. Links the OfficerUser to the Member, flips
    dashboard_access to "dashboard", and returns (officer_user,
    generated_password). Call inside the same atomic transaction that
    creates the Member.
    """
    from core_system.auth_utils import hash_password
    from core_system.services.email_service import generate_member_password

    username = _unique_member_username(member.full_name, email, member.member_id_PK)
    generated_password = generate_member_password(getattr(member, "date_joined", None))
    officer_user = OfficerUser.objects.create(
        username=username,
        full_name=member.full_name,
        password_hash=hash_password(generated_password),
        email=email,
        role="Member",
        account_status="Active",
        must_change_password=True,
    )
    member.officer_user_id_FK = officer_user
    member.dashboard_access = "dashboard"
    member.save(update_fields=["officer_user_id_FK", "dashboard_access"])
    _ = officer  # kept for signature symmetry / future audit use
    return officer_user, generated_password


def _send_member_credentials_email(member: Member, password: str, old_member: bool = False) -> bool:
    """Email the member their dashboard login credentials (auto-generated password)."""
    from django.conf import settings as _dj_settings
    subject = (
        "Welcome Back to ISUCauFA, Inc. – Your Member Account is Ready"
        if old_member
        else "Welcome to ISUCauFA, Inc. – Membership Registration Confirmed"
    )
    # Placeholder while on localhost — point BASE_URL at the public domain
    # once deployed and every credentials email links the live portal.
    login_url = str(getattr(_dj_settings, "BASE_URL", "http://localhost:8000") or "http://localhost:8000").rstrip("/") + "/login/"
    return send_html_email_async(
        subject=subject,
        recipient_list=[member.email],
        html_template="emails/member_added.html",
        context={
            "full_name": member.full_name,
            "email": member.email or "",
            "username": member.officer_user_id_FK.username if member.officer_user_id_FK else (member.employee_id or "N/A"),
            "old_member": old_member,
            "date_joined": member.date_joined.strftime("%B %d, %Y") if member.date_joined else str(timezone.now().date()),
            "department": member.department or "",
            "monthly_dues_amount": get_monthly_dues_amount(),
            "membership_fee_amount": get_membership_fee_amount(),
            "officer_contact": "",
            "generated_password": password,
            "login_url": login_url,
        },
    )


def _normalize_person_name(value) -> str:
    """Trim and uppercase a name part so stored member names are always ALL CAPS.

    Applied at every treasurer member-creation entry point so a name typed in
    lower/mixed case (e.g. "Justin") is always saved as "JUSTIN" — whether it
    comes from Create Member, Create Member (Old), the batch grid, or an
    uploaded CSV/XLSX file.
    """
    return (value or "").strip().upper()


@require_POST
def treasurer_create_member(request: HttpRequest):
    """Create a NEW ISUCauFA, Inc. member instantly — no approval workflow.

    The membership fee required by the Constitution & By-Laws (Article IV,
    Section 1) is collected at creation: it is recorded as a MembershipFee,
    added to the ISUCauFA, Inc. Fund (inflow), and the member receives a
    dashboard account with an auto-generated password delivered by email."""
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard

    first_name = _normalize_person_name(request.POST.get("first_name"))
    middle_initial = _normalize_person_name(request.POST.get("middle_initial"))
    last_name = _normalize_person_name(request.POST.get("last_name"))
    name_ext = _normalize_person_name(request.POST.get("name_ext"))
    email = (request.POST.get("email") or "").strip()
    department = (request.POST.get("department") or "").strip()
    position = (request.POST.get("position") or "").strip()
    membership_category = (request.POST.get("membership_category") or "Permanent").strip()
    classification = _parse_classification(request.POST.get("classification"))
    contact = (request.POST.get("contact") or "").strip()
    payment_method = (request.POST.get("payment_method") or "Cash").strip()
    # Membership fee is fixed by the President (SystemSetting override or
    # policy constant) — ignore any client-supplied amount so a tampered
    # POST can't change it. The form field is readonly for the same reason.
    amount_raw = str(get_membership_fee_amount()).strip()
    payment_date_raw = (request.POST.get("payment_date") or "").strip()

    if not first_name or not last_name:
        return JsonResponse({"ok": False, "error": "First Name and Last Name are required."}, status=400)
    if not position:
        return JsonResponse({"ok": False, "error": "Academic Rank is required."}, status=400)
    email, email_error = validate_isu_email(email)
    if email_error:
        return JsonResponse({"ok": False, "error": email_error}, status=400)
    if not is_membership_duplicate_email_allowed() and (
        Member.objects.filter(email__iexact=email).exists()
        or OfficerUser.objects.filter(email__iexact=email).exists()
    ):
        return JsonResponse({"ok": False, "error": "This email address already exists — it is already used by a member of the association."}, status=409)

    try:
        amount = Decimal(str(amount_raw))
        payment_date = datetime.strptime(payment_date_raw, "%Y-%m-%d").date() if payment_date_raw else timezone.now().date()
    except (decimal.InvalidOperation, ValueError):
        return JsonResponse({"ok": False, "error": "Enter a valid amount and payment date."}, status=400)

    contact, contact_error = _validate_ph_contact(contact)
    if contact_error:
        return JsonResponse({"ok": False, "error": contact_error}, status=400)

    full_name = " ".join(part for part in [first_name, middle_initial, last_name, name_ext] if part)
    officer = resolve_officer_from_session(request)
    receipt_number = "NEW-" + uuid.uuid4().hex[:12].upper()

    photo = request.FILES.get("photo")

    try:
        with transaction.atomic():
            joined = timezone.now().date()
            member_obj = Member.objects.create(
                full_name=full_name,
                department=department or None,
                position=position or None,
                contact_number=contact or "",
                email=email,
                employment_status="Active",
                # Retired members carry the Retired membership status so every
                # existing dues/aid exclusion picks them up automatically.
                membership_status="Retired" if classification == "Retired" else membership_category,
                member_classification=classification,
                member_type="Member",
                date_joined=joined,
                # Retired owe no monthly dues — never flagged for catch-up
                # generation (matches treasurer_generate_catchup_dues).
                dues_backfill_pending=should_flag_backfill(joined, classification),
                dashboard_access="dashboard",
                profile_picture=photo if photo and getattr(photo, "size", 0) > 0 else None,
            )

            # Every registered member gets a dashboard login: auto-generated
            # password, emailed right after the transaction commits.
            officer_user, generated_password = _provision_member_account(member_obj, email, officer)

            fee = MembershipFee.objects.create(
                member_id_FK=member_obj,
                receipt_number=receipt_number,
                amount=amount,
                payment_date=payment_date,
                payment_method=payment_method,
                payment_status="Paid",
                recorded_by_user_id_FK=officer,
            )

            # The membership fee goes straight into the ISUCauFA, Inc. Fund.
            FundTransaction.objects.create(
                direction="inflow",
                amount=fee.amount,
                source_type="membership_fee",
                source_id=fee.fee_id_PK,
                description=full_name + " - Membership Fee (new member)",
                reference_number=receipt_number,
                recorded_by_user_id_FK=officer,
            )

            MemberLedger.objects.create(
                member_id_FK=member_obj,
                transaction_type="membership_fee",
                amount=fee.amount,
                direction="credit",
                balance_after=member_balance(member_obj),
                reference_id=fee.fee_id_PK,
                reference_type="MembershipFee",
                description="Membership Fee Payment",
                recorded_by_user_id_FK=officer,
            )

            _record_audit_trail(
                table="member",
                record_id=member_obj.member_id_PK,
                action="CREATE_MEMBER_INSTANT",
                actor=officer,
                new={
                    "member_id": member_obj.member_id_PK,
                    "officer_user_id": officer_user.user_id_PK,
                    "fee_id": fee.fee_id_PK,
                    "amount": str(amount),
                    "membership_category": membership_category,
                },
                ip=request.META.get("REMOTE_ADDR"),
                notes="New member " + full_name + " created instantly by the Treasurer with a dashboard account; the by-laws fee was collected into the ISUCauFA, Inc. Fund; credentials email sent.",
            )

        credentials_sent = _send_member_credentials_email(member_obj, generated_password, old_member=False)

        try:
            notify_member(
                member_obj,
                notification_type="Membership",
                message="Welcome to ISUCauFA! You can view your monthly deductions, balance, and announcements on this dashboard.",
                category="membership",
                sender_role="Treasurer",
                # Branded credentials email sent above; suppress notify's
                # plain-text fallback (one email + one push).
                send_email=False,
            )
        except Exception:
            logger.exception("Welcome notification failed for %s", full_name)

        _broadcast_pending_counts()
        return JsonResponse({
            "ok": True,
            "member_id": member_obj.member_id_PK,
            "username": officer_user.username,
            "credentials_sent": credentials_sent,
            "message": "An Account for the new member has been created, notify the member to check the email inbox/spam to get the login credentials.",
        })
    except Exception:
        logger.exception("Failed to create new member %s", full_name)
        return JsonResponse({"ok": False, "error": "Unable to create the member."}, status=500)


@require_POST
def treasurer_create_member_old(request: HttpRequest):
    """Register an OLD / existing ISUCauFA, Inc. member.

    No membership fee is collected (nothing is added to the ISUCauFA, Inc. Fund),
    but like every registered member they receive a dashboard account: the
    password is auto-generated and delivered to their ISU email together with
    their login username."""
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard

    first_name = _normalize_person_name(request.POST.get("first_name"))
    middle_initial = _normalize_person_name(request.POST.get("middle_initial"))
    last_name = _normalize_person_name(request.POST.get("last_name"))
    email = (request.POST.get("email") or "").strip()
    department = (request.POST.get("department") or "").strip()
    position = (request.POST.get("position") or "").strip()
    membership_category = (request.POST.get("membership_category") or "Permanent").strip()
    classification = _parse_classification(request.POST.get("classification"))
    contact = (request.POST.get("contact") or "").strip()

    if not first_name or not last_name:
        return JsonResponse({"ok": False, "error": "First Name and Last Name are required."}, status=400)
    if not position:
        return JsonResponse({"ok": False, "error": "Academic Rank is required."}, status=400)
    email, email_error = validate_isu_email(email)
    if email_error:
        return JsonResponse({"ok": False, "error": email_error}, status=400)
    if not is_membership_duplicate_email_allowed() and (
        Member.objects.filter(email__iexact=email).exists()
        or OfficerUser.objects.filter(email__iexact=email).exists()
    ):
        return JsonResponse({"ok": False, "error": "This email address already exists — it is already used by a member of the association."}, status=409)

    contact, contact_error = _validate_ph_contact(contact)
    if contact_error:
        return JsonResponse({"ok": False, "error": contact_error}, status=400)

    full_name = " ".join(part for part in [first_name, middle_initial, last_name] if part)
    officer = resolve_officer_from_session(request)

    photo = request.FILES.get("photo")

    try:
        with transaction.atomic():
            joined = timezone.now().date()
            member_obj = Member.objects.create(
                full_name=full_name,
                department=department or None,
                position=position or None,
                contact_number=contact or "",
                email=email,
                employment_status="Active",
                membership_status="Retired" if classification == "Retired" else membership_category,
                member_classification=classification,
                member_type="Member",
                date_joined=joined,
                # Retired owe no monthly dues — never flagged for catch-up
                # generation (matches treasurer_generate_catchup_dues).
                dues_backfill_pending=should_flag_backfill(joined, classification),
                dashboard_access="dashboard",
                profile_picture=photo if photo and getattr(photo, "size", 0) > 0 else None,
            )

            # Old members get dashboard access too — auto-generated password
            # emailed right after the transaction commits.
            officer_user, generated_password = _provision_member_account(member_obj, email, officer)

            _record_audit_trail(
                table="member",
                record_id=member_obj.member_id_PK,
                action="CREATE_MEMBER_OLD",
                actor=officer,
                new={
                    "member_id": member_obj.member_id_PK,
                    "officer_user_id": officer_user.user_id_PK,
                    "membership_category": membership_category,
                },
                ip=request.META.get("REMOTE_ADDR"),
                notes="Old/existing member " + full_name + " registered by the Treasurer with a dashboard account. No fee collected, no fund entry; credentials email sent.",
            )

        credentials_sent = _send_member_credentials_email(member_obj, generated_password, old_member=True)

        try:
            notify_member(
                member_obj,
                notification_type="Membership",
                message="Welcome to ISUCauFA! You can view your monthly deductions, balance, and announcements on this dashboard.",
                category="membership",
                sender_role="Treasurer",
                # Branded credentials email sent above; suppress notify's
                # plain-text fallback (one email + one push).
                send_email=False,
            )
        except Exception:
            logger.exception("Welcome notification failed for old member %s", full_name)

        _broadcast_pending_counts()
        return JsonResponse({
            "ok": True,
            "member_id": member_obj.member_id_PK,
            "username": officer_user.username,
            "password": generated_password,
            "credentials_sent": credentials_sent,
            "message": full_name + " registered as an old ISUCauFA, Inc. member. A dashboard account was created and the auto-generated password was emailed. No fees were collected.",
        })
    except Exception:
        logger.exception("Failed to register old member %s", full_name)
        return JsonResponse({"ok": False, "error": "Unable to register the old member."}, status=500)


@require_POST
def treasurer_add_member(request: HttpRequest):
    """
    Enroll a new MEMBER row and conditionally process an initial membership fee ledger
    record synchronously within a single atomic database context payload window.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # Handle availability checks
    check_username = request.POST.get("check_username")
    check_email = request.POST.get("check_email")
    
    if check_username:
        if OfficerUser.objects.filter(username=check_username).exists():
            return JsonResponse({"ok": False, "error": f"Username '{check_username}' is already taken."}, status=409)
        if Member.objects.filter(employee_id=check_username).exists():
            return JsonResponse({"ok": False, "error": f"Employee ID '{check_username}' is already taken."}, status=409)
        return JsonResponse({"ok": True, "available": True})
    
    if check_email:
        if is_membership_duplicate_email_allowed():
            return JsonResponse({"ok": True, "available": True})
        if OfficerUser.objects.filter(email=check_email).exists():
            return JsonResponse({"ok": False, "error": f"Email '{check_email}' is already taken."}, status=409)
        if Member.objects.filter(email=check_email).exists():
            return JsonResponse({"ok": False, "error": f"Email '{check_email}' is already taken."}, status=409)
        return JsonResponse({"ok": True, "available": True})

    # Extract Core Member Variables
    first_name = _normalize_person_name(request.POST.get("first_name"))
    middle_initial = _normalize_person_name(request.POST.get("middle_initial"))
    last_name = _normalize_person_name(request.POST.get("last_name"))
    username = (request.POST.get("username") or "").strip()
    prof_id = username  # Use username as employee_id
    prof_contact = (request.POST.get("prof_contact") or "").strip() or None
    prof_email = (request.POST.get("email") or "").strip() or None
    membership_category = (request.POST.get("membership_category") or "Permanent").strip()
    prof_dept = (request.POST.get("prof_dept") or "").strip()
    prof_pos = (request.POST.get("prof_pos") or "").strip()
    enrollment_amount = request.POST.get("enrollment_amount")
    payment_method = request.POST.get("payment_method")
    payment_date = request.POST.get("payment_date")
    notes = request.POST.get("notes", "").strip()

    # Combine name parts into full_name
    prof_name = f"{first_name} {middle_initial} {last_name}".strip() if middle_initial else f"{first_name} {last_name}".strip()

    # Validations: Member
    if not first_name or not last_name:
        return JsonResponse({"ok": False, "error": "First Name and Last Name are required."}, status=400)
    if not username:
        return JsonResponse({"ok": False, "error": "Username is required."}, status=400)
    if not prof_email:
        return JsonResponse({"ok": False, "error": "Email is required for password delivery."}, status=400)

    _, prof_email_error = validate_isu_email(prof_email)
    if prof_email_error:
        return JsonResponse({"ok": False, "error": prof_email_error}, status=400)

    prof_contact, contact_error = _validate_ph_contact(prof_contact)
    if contact_error:
        return JsonResponse({"ok": False, "error": contact_error}, status=400)

    if OfficerUser.objects.filter(username=username).exists():
        return JsonResponse(
            {"ok": False, "error": f"Username '{username}' is already taken."},
            status=409,
        )

    if Member.objects.filter(employee_id=username).exists():
        return JsonResponse(
            {"ok": False, "error": f"Employee ID '{username}' is already registered to another member."},
            status=409,
        )

    # Resolve Encoder User Identity context
    recorded_by = resolve_officer_from_session(request)
    
    # Auto-generate secure password before transaction
    from core_system.services.email_service import generate_secure_password
    generated_password = generate_secure_password()

    # Enforce transactional data integrity checks across models
    try:
        with transaction.atomic():
            # 1. Store Profile Attachments safely if provided
            prof_uploaded = request.FILES.get("prof_photo_file")
            if prof_uploaded and prof_uploaded.size > 0:
                import os
                safe_name = os.path.basename(prof_uploaded.name)
                if not safe_name:
                    safe_name = "upload"
                default_storage.save(
                    f"member_uploads/{timezone.now().strftime('%Y%m%d')}_{safe_name}",
                    prof_uploaded,
                )

            # 2. Create OfficerUser account for the member
            from core_system.auth_utils import hash_password
            
            officer_user = OfficerUser.objects.create(
                username=username,
                full_name=prof_name,
                password_hash=hash_password(generated_password),
                email=prof_email or "",
                role="Member",
                account_status="Active",
                must_change_password=True,
            )

            # 3. Provision Member Record Block
            member = Member.objects.create(
                full_name=prof_name,
                employee_id=prof_id,
                officer_user_id_FK=officer_user,
                department=prof_dept or None,
                position=prof_pos or None,
                contact_number=prof_contact,
                email=prof_email,
                employment_status="Active",
                membership_status=membership_category,
                member_type="Member",
                date_joined=(joined := timezone.now().date()),
                dues_backfill_pending=should_flag_backfill(joined),
            )

            # 4. Handle membership fee payment if amount and method provided
            if enrollment_amount and payment_method:
                from decimal import Decimal
                from datetime import datetime
                try:
                    amount = Decimal(enrollment_amount)
                    payment_dt = None
                    if payment_date:
                        payment_dt = datetime.strptime(payment_date, "%Y-%m-%d").date()
                    else:
                        payment_dt = timezone.now().date()
                    
                    # Handle proof file upload
                    proof_file = request.FILES.get("proof_file")
                    proof_path = None
                    if proof_file:
                        import os
                        safe_name = os.path.basename(proof_file.name)
                        if not safe_name:
                            safe_name = "proof"
                        proof_path = default_storage.save(
                            f"supporting_proofs/{timezone.now().strftime('%Y%m%d')}_{safe_name}",
                            proof_file
                        )
                    
                    fee = MembershipFee.objects.create(
                        member_id_FK=member,
                        receipt_number=f"REG-{int(timezone.now().timestamp())}",
                        amount=str(amount),
                        payment_date=payment_dt,
                        payment_method=payment_method,
                        payment_status="Paid",
                        recorded_by_user_id_FK=recorded_by,
                    )
                    # Create TransactionVerification for enrollment fee to appear in Auditor Dashboard
                    TransactionVerification.objects.create(
                        table_name="membership_fee",
                        record_id=fee.fee_id_PK,
                        verification_status="Pending",
                        auditor_id_FK=None,  # Unclaimed - available for any auditor
                    )
                    _record_audit_trail(
                        table="membership_fee",
                        record_id=fee.fee_id_PK,
                        action="DIRECT_ENROLLMENT",
                        actor=recorded_by,
                        new={"member": member, "amount": str(fee.amount), "payment_date": str(fee.payment_date)},
                        ip=request.META.get("REMOTE_ADDR"),
                        notes="Direct enrollment by Treasurer - sent to Auditor for review",
                    )
                except Exception as e:
                    # If payment processing fails, still create the member but log the error
                    logger.exception("Failed to process membership fee payment for member %s", prof_name)
            else:
                # Auto-create membership fee if no payment provided
                fee = MembershipFee.objects.create(
                    member_id_FK=member,
                    receipt_number=f"REG-{int(timezone.now().timestamp())}",
                    amount=str(get_membership_fee_amount()),
                    payment_date=timezone.now().date(),
                    # Method genuinely unknown (no payment info supplied);
                    # payment_method must never hold a STATUS value.
                    payment_method="Unknown",
                    payment_status="Paid",
                    recorded_by_user_id_FK=recorded_by,
                )
                # Create TransactionVerification for enrollment fee to appear in Auditor Dashboard
                TransactionVerification.objects.create(
                    table_name="membership_fee",
                    record_id=fee.fee_id_PK,
                    verification_status="Pending",
                    auditor_id_FK=None,  # Unclaimed - available for any auditor
                )
                _record_audit_trail(
                    table="membership_fee",
                    record_id=fee.fee_id_PK,
                    action="DIRECT_ENROLLMENT",
                    actor=recorded_by,
                    new={"member": member, "amount": str(fee.amount), "payment_date": str(fee.payment_date)},
                    ip=request.META.get("REMOTE_ADDR"),
                    notes="Direct enrollment by Treasurer - sent to Auditor for review",
                )

    except ValueError as val_err:
        return JsonResponse({"ok": False, "error": str(val_err)}, status=400)
    except Exception as ex:
        return JsonResponse({"ok": False, "error": f"Internal pipeline transactional exception: {str(ex)}"}, status=500)

    email_sent = True
    try:
        if member.email:
            email_sent = send_html_email_async(
                subject="Welcome to ISUCauFA, Inc. – Membership Registration Confirmed",
                recipient_list=[member.email],
                html_template="emails/member_added.html",
                context={
                    "full_name": member.full_name,
                    "email": member.email or "",
                    "username": officer_user.username if officer_user else (member.employee_id or "N/A"),
                    "old_member": False,
                    "date_joined": member.date_joined.strftime("%B %d, %Y") if member.date_joined else str(timezone.now().date()),
                    "department": member.department or "",
                    "monthly_dues_amount": get_monthly_dues_amount(),
                    "membership_fee_amount": get_membership_fee_amount(),
                    "officer_contact": "",
                    "generated_password": generated_password,
                },
            )
    except Exception:
        pass

    # Create notification for member about their enrollment
    try:
        notify_member(
            member,
            notification_type="Membership Approved",
            message=f"Welcome to ISUCauFA, Inc.! Your membership has been approved by the Treasurer. You can now access all member benefits and services.",
            category="membership",
            sender_name=officer.full_name if officer else "Treasurer",
            sender_role="Treasurer",
            # Branded welcome/credentials email sent above; suppress notify's
            # plain-text fallback so the member gets one email + one push.
            send_email=False,
        )
    except Exception as e:
        logger.warning("Failed to send enrollment notification to member %s: %s", member.member_id_PK, e)

    _broadcast_treasurer("members")

    return JsonResponse(
        {
            "ok": True,
            "email_sent": email_sent,
            "member": {
                "member_id": member.member_id_PK,
                "full_name": member.full_name,
                "employee_id": member.employee_id or "",
                "department": member.department or "",
                "position": member.position or "",
                "contact_number": member.contact_number,
                "email": member.email,
                "membership_status": member.membership_status,
                "employment_status": member.employment_status,
                "member_type": member.member_type or member.employee_id,
                "officer_user_id": member.officer_user_id_FK_id,
                "date_joined": str(member.date_joined),
            },
            "message": "Member registered successfully. Password has been sent to the member's email address."
        }
    )


@require_POST
def treasurer_member_batch_add(request):
    """Accept multiple member entries in one JSON request and create them in a single transaction.

    `member_kind` selects the registration path: "new" (default) collects the
    membership fee, "old" registers the existing member without a fee. Every
    entry receives a dashboard account with an auto-generated password emailed
    to the member's ISU address."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)

    entries = body.get("entries", [])
    member_kind = (body.get("member_kind") or "new").strip().lower()
    if member_kind not in ("new", "old"):
        member_kind = "new"

    if not entries or not isinstance(entries, list):
        return JsonResponse({"ok": False, "error": "No entries provided."}, status=400)

    recorded_by = resolve_officer_from_session(request)
    results = _batch_create_member_entries(entries, member_kind, recorded_by, request)
    _broadcast_treasurer("members")
    return JsonResponse({"ok": True, "results": results})


def _batch_create_member_entries(entries, member_kind: str, recorded_by, request=None):
    """Create member accounts for a list of entries (JSON dicts).

    Shared by treasurer_member_batch_add (JSON payload) and
    treasurer_member_batch_upload (CSV/XLSX file). Returns a per-row results
    list; a failed row never blocks the others.
    """
    results = []

    requested_usernames = [
        (e.get("username") or "").strip() for e in entries if e.get("username")
    ]
    requested_emails = [
        (e.get("email") or "").strip() for e in entries if e.get("email")
    ]

    existing_usernames = set(
        list(Member.objects.filter(employee_id__in=requested_usernames).values_list("employee_id", flat=True))
        + list(OfficerUser.objects.filter(username__in=requested_usernames).values_list("username", flat=True))
    )
    existing_emails = set(
        list(Member.objects.filter(email__in=requested_emails).values_list("email", flat=True))
        + list(OfficerUser.objects.filter(email__in=requested_emails).values_list("email", flat=True))
    )
    seen_usernames = set()
    seen_emails = set()

    from core_system.auth_utils import hash_password
    from core_system.services.email_service import generate_secure_password

    with transaction.atomic():
        for entry in entries:
            first_name = _normalize_person_name(entry.get("first_name"))
            middle_initial = _normalize_person_name(entry.get("middle_initial"))
            last_name = _normalize_person_name(entry.get("last_name"))
            username = (entry.get("username") or "").strip()
            email = (entry.get("email") or "").strip()
            status_val = (entry.get("membership_category") or "Permanent").strip() or "Permanent"
            # Per-row Old/New wins over the batch-level kind — the grid lets
            # the Treasurer mix existing and brand-new members in one upload.
            entry_kind = (entry.get("member_kind") or "").strip().lower()
            if entry_kind not in ("new", "old"):
                entry_kind = member_kind
            classification = _parse_classification(entry.get("classification"))
            prof_dept = (entry.get("prof_dept") or "").strip() or None
            prof_pos = (entry.get("prof_pos") or "").strip() or None
            prof_contact = (entry.get("prof_contact") or "").strip() or None
            enrollment_amount = (entry.get("enrollment_amount") or "").strip()
            payment_method = (entry.get("payment_method") or "").strip() or None
            payment_date = (entry.get("payment_date") or "").strip() or None
            notes = (entry.get("notes") or "").strip() or None
            full_name = (
                f"{first_name} {middle_initial} {last_name}".strip()
                if middle_initial
                else f"{first_name} {last_name}".strip()
            )

            if not first_name or not last_name:
                results.append({"ok": False, "name": full_name, "error": "First Name and Last Name are required."})
                continue
            if not username:
                results.append({"ok": False, "name": full_name, "error": "Username (Employee/Faculty ID) is required."})
                continue
            _, email_error = validate_isu_email(email)
            if email_error:
                results.append({"ok": False, "name": full_name, "error": email_error})
                continue
            if not (entry.get("prof_pos") or "").strip():
                results.append({"ok": False, "name": full_name, "error": "Academic Rank is required."})
                continue
            if username in existing_usernames or username in seen_usernames:
                results.append({"ok": False, "name": full_name, "error": f"Username '{username}' is already registered."})
                continue
            if email.lower() in {e.lower() for e in existing_emails} or email.lower() in {e.lower() for e in seen_emails}:
                results.append({"ok": False, "name": full_name, "error": f"Email '{email}' is already registered."})
                continue

            prof_contact, contact_error = _validate_ph_contact(prof_contact)
            if contact_error:
                results.append({"ok": False, "name": full_name, "error": contact_error})
                continue

            seen_usernames.add(username)
            seen_emails.add(email)

            try:
                with transaction.atomic():
                    generated_password = generate_secure_password()

                    officer_user = OfficerUser.objects.create(
                        username=username,
                        full_name=full_name,
                        password_hash=hash_password(generated_password),
                        email=email,
                        role="Member",
                        account_status="Active",
                        must_change_password=True,
                    )

                    member = Member.objects.create(
                        full_name=full_name,
                        employee_id=username,
                        officer_user_id_FK=officer_user,
                        department=prof_dept,
                        position=prof_pos,
                        contact_number=prof_contact,
                        email=email,
                        employment_status="Active",
                        membership_status="Retired" if classification == "Retired" else status_val,
                        member_classification=classification,
                        member_type="Member",
                        date_joined=(joined := timezone.now().date()),
                        # Retired owe no monthly dues — never flagged for
                        # catch-up generation.
                        dues_backfill_pending=should_flag_backfill(joined, classification),
                        dashboard_access="dashboard",
                    )

                    # Only NEW members pay the membership fee at registration.
                    if entry_kind == "new" and member.membership_status in ("Permanent", "Temporary"):
                        from decimal import Decimal
                        from datetime import datetime

                        fee_amount = get_membership_fee_amount()
                        if enrollment_amount:
                            try:
                                fee_amount = Decimal(enrollment_amount)
                            except Exception:
                                pass

                        fee_date = timezone.now().date()
                        if payment_date:
                            try:
                                fee_date = datetime.strptime(payment_date, "%Y-%m-%d").date()
                            except Exception:
                                pass

                        fee = MembershipFee.objects.create(
                            member_id_FK=member,
                            receipt_number=f"REG-{int(timezone.now().timestamp())}-{member.member_id_PK}",
                            amount=str(fee_amount),
                            payment_date=fee_date,
                            payment_method=payment_method or "Pending",
                            payment_status="Paid",
                            recorded_by_user_id_FK=recorded_by,
                        )
                        # Create TransactionVerification for batch enrollment fee to appear in Auditor Dashboard
                        TransactionVerification.objects.create(
                            table_name="membership_fee",
                            record_id=fee.fee_id_PK,
                            verification_status="Pending",
                            auditor_id_FK=None,  # Unclaimed - available for any auditor
                        )
                        _record_audit_trail(
                            table="membership_fee",
                            record_id=fee.fee_id_PK,
                            action="DIRECT_ENROLLMENT",
                            actor=recorded_by,
                            new={"member": member, "amount": str(fee.amount), "payment_date": str(fee.payment_date)},
                            ip=request.META.get("REMOTE_ADDR") if request is not None else None,
                            notes="Direct batch enrollment by Treasurer - sent to Auditor for review",
                        )

                    if email:
                        _send_member_credentials_email(member, generated_password, old_member=(entry_kind == "old"))

                    # Create notification for member about their enrollment
                    try:
                        notify_member(
                            member,
                            notification_type="Membership Approved",
                            message=f"Welcome to ISUCauFA, Inc.! Your membership has been approved by the Treasurer. Your dashboard account was created and your auto-generated password was sent to your ISU email.",
                            category="membership",
                            sender_name=recorded_by.full_name if recorded_by else "Treasurer",
                            sender_role="Treasurer",
                            # Branded welcome/credentials email sent above; suppress
                            # notify's plain-text fallback (one email + one push).
                            send_email=False,
                        )
                    except Exception as e:
                        logger.warning("Failed to send batch enrollment notification to member %s: %s", member.member_id_PK, e)

                    results.append({"ok": True, "name": full_name, "id": member.member_id_PK, "username": username})
            except Exception as ex:
                results.append({"ok": False, "name": full_name, "error": str(ex)})

    return results


@require_POST
def treasurer_member_batch_upload(request):
    """Batch upload member account registrations from a CSV or XLSX file.

    Supports both NEW members (membership fee collected) and OLD members
    (no fee) via the `member_kind` field. Every row receives a dashboard
    account with an auto-generated password emailed to the ISU address.
    Expected columns (header row, order-independent):
        first_name, middle_initial, last_name, username (Employee/Faculty ID),
        email, contact_number, department, position, membership_category,
        amount (new members), payment_method, payment_date
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"ok": False, "error": "No file uploaded."}, status=400)

    member_kind = (request.POST.get("member_kind") or "new").strip().lower()
    if member_kind not in ("new", "old"):
        member_kind = "new"

    filename = (upload.name or "").lower()
    content_type = (getattr(upload, "content_type", "") or "").lower()
    rows = []
    parse_error = None

    # File type: prefer the extension, fall back to the MIME type, and finally
    # assume CSV (some browsers/clients upload text without a usable name).
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        file_kind = "xlsx"
    elif filename.endswith(".csv") or filename.endswith(".txt"):
        file_kind = "csv"
    elif "spreadsheetml" in content_type or "ms-excel" in content_type:
        file_kind = "xlsx"
    elif "csv" in content_type or content_type.startswith("text/"):
        file_kind = "csv"
    else:
        file_kind = "csv"

    try:
        if file_kind == "csv":
            import csv
            import io

            raw = upload.read().decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(raw))
            for row in reader:
                cleaned = {
                    (k or "").strip().lower().replace(" ", "_"): (v or "").strip()
                    for k, v in row.items()
                    if k is not None
                }
                rows.append(cleaned)
        else:
            from openpyxl import load_workbook
            import io

            workbook = load_workbook(io.BytesIO(upload.read()), read_only=True, data_only=True)
            sheet = workbook.active
            excel_rows = sheet.iter_rows(values_only=True)
            headers = []
            for header_cell in next(excel_rows, []):
                headers.append(str(header_cell or "").strip().lower().replace(" ", "_"))
            for values in excel_rows:
                row = {}
                for idx, header in enumerate(headers):
                    if not header:
                        continue
                    value = values[idx] if idx < len(values) else None
                    row[header] = "" if value is None else str(value).strip()
                rows.append(row)
            workbook.close()
    except Exception as ex:
        parse_error = f"Could not read the uploaded file: {ex}"

    if parse_error:
        return JsonResponse({"ok": False, "error": parse_error}, status=400)

    # Header aliases so spreadsheet authors can use friendlier column names.
    alias_map = {
        "first_name": ("first_name", "firstname", "first"),
        "middle_initial": ("middle_initial", "middleinitial", "middle", "mi"),
        "last_name": ("last_name", "lastname", "last", "surname"),
        "username": ("username", "employee_id", "employeefaculty_id", "employee_faculty_id", "employeeid"),
        "email": ("email", "email_address", "isu_email"),
        "prof_contact": ("prof_contact", "contact_number", "contactnumber", "contact", "mobile", "mobile_number", "phone"),
        "prof_dept": ("prof_dept", "department", "dept"),
        "prof_pos": ("prof_pos", "position", "rank", "position_rank"),
        "membership_category": ("membership_category", "membership_type", "membership", "membership_status"),
        "enrollment_amount": ("enrollment_amount", "amount", "membership_fee", "fee"),
        "payment_method": ("payment_method", "payment"),
        "payment_date": ("payment_date", "date"),
    }

    normalized_entries = []
    skipped_rows = []
    for row in rows:
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue  # blank padding row
        entry = {}
        for target, aliases in alias_map.items():
            for alias in aliases:
                if alias in row and (row[alias] or "").strip():
                    entry[target] = row[alias]
                    break
        if not entry:
            skipped_rows.append({"row": row, "error": "No recognizable columns."})
            continue
        normalized_entries.append(entry)

    if not normalized_entries:
        return JsonResponse({
            "ok": False,
            "error": "No member rows were found. Make sure the file has a header row (first_name, last_name, username, email, ...).",
        }, status=400)

    if len(normalized_entries) > 500:
        return JsonResponse({"ok": False, "error": "Batch upload is limited to 500 members per file."}, status=400)

    recorded_by = resolve_officer_from_session(request)
    results = _batch_create_member_entries(normalized_entries, member_kind, recorded_by, request)
    _broadcast_treasurer("members")

    succeeded = sum(1 for r in results if r.get("ok"))
    return JsonResponse({
        "ok": True,
        "member_kind": member_kind,
        "total_rows": len(normalized_entries),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    })


@require_GET
def treasurer_membership_fee_list(request):
    """Return all membership fee ledger entries for the Treasurer dashboard."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    fees = (
        MembershipFee.objects.select_related("member_id_FK", "recorded_by_user_id_FK")
        .all()
        .order_by("-fee_id_PK")
    )

    # OfficerUser model does not guarantee a display name, so we return recorded_by_user_id_FK_id as fallback.
    rows = []
    for f in fees:
        encoder_name = None
        if getattr(f, "recorded_by_user_id_FK", None) is not None:
            encoder_name = getattr(f.recorded_by_user_id_FK, "full_name", None)
            if not encoder_name:
                encoder_name = str(getattr(f.recorded_by_user_id_FK, "user_id_PK", f.recorded_by_user_id_FK_id))

        rows.append(
            {
                "fee_id": f.fee_id_PK,
                "ref": f.receipt_number or "",
                "member_id": f.member_id_FK.member_id_PK,
                "member_name": f.member_id_FK.full_name,
                "amount": str(f.amount),
                "payment_date": str(f.payment_date),
                "payment_status": f.payment_status,
                "payment_method": f.payment_method,
                "deposit_reference": f.deposit_reference,
                "encoded_by": encoder_name or "",
            }
        )

    return JsonResponse({"ok": True, "fees": rows})


@require_GET
def treasurer_registration_requests_list(request):
    """Return public member registration requests for Treasurer review."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # Only return pending and returned requests, not already-processed ones
    requests_qs = MemberRegistrationRequest.objects.filter(
        status__in=[
            RegistrationStatus.PENDING_TREASURER_REVIEW,
            RegistrationStatus.RETURNED_FOR_REVISION,
        ]
    ).select_related("processed_by_user_id_FK").order_by("-submitted_at")
    rows = []
    for req in requests_qs:
        rows.append({
            "request_id": req.request_id_PK,
            "full_name": req.full_name,
            "employee_id": req.employee_id,
            "email": req.email or "",
            "department": req.department or "",
            "position": req.position or "",
            "membership_category": req.membership_category,
            "payment_method": req.payment_method,
            "amount": str(req.amount),
            "receipt_number": req.receipt_number,
            "reference_number": req.reference_number or "",
            "payment_date": str(req.payment_date) if req.payment_date else "",
            "status": req.status,
            "returned_reason": req.returned_reason or "",
            "submitted_at": req.submitted_at.isoformat() if req.submitted_at else "",
            "processed_by": getattr(req.processed_by_user_id_FK, "full_name", "") if req.processed_by_user_id_FK else "",
            "proof_url": _get_proof_url(MemberRegistrationRequest, req.request_id_PK) or "",
        })

    return JsonResponse({"ok": True, "requests": rows})


@require_POST
def treasurer_registration_request_action(request: HttpRequest, request_id: int):
    """Accept or return a public registration request."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    request_row = get_object_or_404(MemberRegistrationRequest, request_id_PK=request_id)
    action = (request.POST.get("action") or "").strip().lower()
    reason = (request.POST.get("reason") or "").strip()

    if action not in {"approve", "return", "reject"}:
        return JsonResponse({"ok": False, "error": "Invalid action specified."}, status=400)

    if request_row.status not in {
        RegistrationStatus.PENDING_TREASURER_REVIEW,
        RegistrationStatus.RETURNED_FOR_REVISION,
    }:
        return JsonResponse(
            {"ok": False, "error": "This registration request has already been processed."},
            status=400,
        )

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Unable to resolve officer session."}, status=401)

    if action == "approve":
        with transaction.atomic():
            request_row.status = RegistrationStatus.TREASURER_VERIFIED
            request_row.processed_by_user_id_FK = officer
            request_row.treasurer_verified_by_user_id_FK = officer
            request_row.save()

        _record_audit_trail(
            table="member_registration_request",
            record_id=request_row.request_id_PK,
            action="TREASURER_VERIFIED",
            actor=officer,
            ip=request.META.get("REMOTE_ADDR"),
            notes=f"Treasurer verified registration request for {request_row.full_name}",
        )

        _broadcast_pending_counts()

        try:
            if request_row.account_creation_requested:
                send_registration_status_update_email(
                    request_row.email,
                    request_row.full_name,
                    new_status="Treasurer Verified",
                    next_stage="Auditor Review",
                )
            else:
                send_create_member_status_update_email(
                    request_row.email,
                    request_row.full_name,
                    new_status="Treasurer Verified",
                    next_stage="Auditor Review",
                    department=request_row.department or "",
                    position=request_row.position or "",
                    membership_type=request_row.membership_category,
                )
        except Exception:
            logger.exception("Failed to send status update email for %s", request_row.full_name)

        return JsonResponse({
            "ok": True,
            "status": request_row.status,
        })

    if action in {"return", "reject"}:
        if not reason:
            return JsonResponse({"ok": False, "error": "Reason is required for returning or rejecting a request."}, status=400)

        request_row.status = (
            RegistrationStatus.RETURNED_FOR_REVISION if action == "return" else RegistrationStatus.REJECTED
        )
        request_row.returned_reason = reason
        request_row.processed_by_user_id_FK = officer
        request_row.save()

        try:
            if action == "return":
                if request_row.account_creation_requested:
                    send_registration_returned_email(
                        request_row.email,
                        request_row.full_name,
                        reason=reason,
                    )
                else:
                    send_create_member_returned_email(
                        request_row.email,
                        request_row.full_name,
                        reason=reason,
                    )
            else:
                if request_row.account_creation_requested:
                    send_registration_rejected_email(
                        request_row.email,
                        request_row.full_name,
                        reason=reason,
                    )
                else:
                    send_create_member_rejected_email(
                        request_row.email,
                        request_row.full_name,
                        reason=reason,
                    )
        except Exception:
            logger.exception("Failed to send %s email for %s", action, request_row.full_name)

        return JsonResponse({"ok": True, "status": request_row.status})


@require_GET
def treasurer_membership_fees_returned_list(request):
    """Return membership fee records that have been returned for revision."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    returned_verifications = TransactionVerification.objects.filter(
        table_name="membership_fee",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED]
    )

    rows = []
    for tv in returned_verifications:
        try:
            fee = MembershipFee.objects.select_related("member_id_FK", "recorded_by_user_id_FK").get(
                fee_id_PK=tv.record_id
            )
        except MembershipFee.DoesNotExist:
            continue

        rejection_reason, rejection_details = _get_rejection_info("membership_fee", fee.fee_id_PK)
        encoder_name = _get_encoder_name(fee)
        proof_url = _get_proof_url(MembershipFee, fee.fee_id_PK)

        rows.append({
            "fee_id_PK": fee.fee_id_PK,
            "receipt_number": fee.receipt_number or "",
            "member_id_PK": fee.member_id_FK.member_id_PK,
            "member_name": fee.member_id_FK.full_name,
            "amount": str(fee.amount),
            "payment_date": str(fee.payment_date),
            "payment_status": fee.payment_status,
            "payment_method": fee.payment_method,
            "deposit_reference": fee.deposit_reference,
            "encoded_by": encoder_name or "",
            "partial_amount": str(getattr(fee, "partial_amount", "") or ""),
            "rejection_reason": rejection_reason,
            "rejection_details": rejection_details,
            "proof_url": proof_url or "",
        })

    return JsonResponse({"ok": True, "records": rows})


@require_GET
def treasurer_monthly_dues_returned_list(request):
    """Return monthly dues records (OTC and Salary Deduction) that have been returned for revision."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    returned_verifications = TransactionVerification.objects.filter(
        table_name="monthly_dues",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED]
    )

    rows = []
    for tv in returned_verifications:
        try:
            dues = MonthlyDues.objects.select_related("member_id_FK", "recorded_by_user_id_FK").get(
                dues_id_PK=tv.record_id
            )
        except MonthlyDues.DoesNotExist:
            continue

        rejection_reason, rejection_details = _get_rejection_info("monthly_dues", dues.dues_id_PK)
        encoder_name = _get_encoder_name(dues)
        proof_url = _get_monthly_dues_proof_url(dues)

        rows.append({
            "dues_id_PK": dues.dues_id_PK,
            "receipt_number": dues.receipt_number or "",
            "member_id_PK": dues.member_id_FK.member_id_PK,
            "member_name": dues.member_id_FK.full_name,
            "amount": str(dues.amount),
            "month_covered": dues.month_covered or "",
            "payment_date": str(dues.payment_date),
            "payment_status": dues.payment_status,
            "payment_method": dues.payment_method,
            "remittance_reference": dues.remittance_reference or "",
            "deduction_batch_reference": dues.deduction_batch_reference or "",
            "encoded_by": encoder_name or "",
            "rejection_reason": rejection_reason,
            "rejection_details": rejection_details,
            "proof_url": proof_url or "",
        })

    return JsonResponse({"ok": True, "records": rows})


@require_GET
def treasurer_medical_aid_returned_list(request):
    """Return medical aid records that have been returned for revision."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    returned_verifications = TransactionVerification.objects.filter(
        table_name="medical_aid",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED]
    )

    rows = []
    record_ids = []
    from core_system.shared_view_utils import _collect_aid_documents, _get_return_info
    for tv_rec in returned_verifications:
        try:
            aid = MedicalAid.objects.select_related("member_id_FK").get(
                medical_aid_id_PK=tv_rec.record_id
            )
        except MedicalAid.DoesNotExist:
            continue

        # Claims withdrawn by the Treasurer leave the returned queue.
        if (aid.status or "").lower() == "withdrawn":
            continue

        record_ids.append(aid.medical_aid_id_PK)

        return_info = _get_return_info("medical_aid", aid.medical_aid_id_PK)
        proof_url = _get_proof_url(MedicalAid, aid.medical_aid_id_PK)

        rows.append({
            "record_id": aid.medical_aid_id_PK,
            "display_id": f"MED-{aid.medical_aid_id_PK}",
            "member_id_PK": aid.member_id_FK.member_id_PK,
            "member_name": aid.member_id_FK.full_name,
            "request_date": str(aid.request_date),
            "requested_amount": str(aid.requested_amount or ""),
            "hospital_name": aid.hospital_name or "",
            "hospital_date": str(aid.hospital_date) if aid.hospital_date else "",
            "hospital_bill_amount": str(aid.hospital_bill_amount),
            "claim_year": str(aid.claim_year),
            "document_status": aid.document_status or "",
            "status": aid.status or "",
            "validated_aid_amount": str(aid.validated_aid_amount),
            "rejection_reason": return_info["reason"],
            "rejection_details": return_info["details"],
            "returned_by": return_info["returned_by"],
            "returned_at": return_info["returned_at"],
            "documents": _collect_aid_documents(MedicalAid, [aid.medical_aid_id_PK]).get(aid.medical_aid_id_PK, []),
            "proof_url": proof_url or "",
        })

    _log_sensitive_read(request, "medical_aid", record_ids, "Treasurer viewed returned medical aid list")

    return JsonResponse({"ok": True, "records": rows})


@require_GET
def treasurer_death_aid_returned_list(request):
    """Return death aid records that have been returned for revision."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    returned_verifications = TransactionVerification.objects.filter(
        table_name="death_aid",
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED]
    )

    rows = []
    from core_system.shared_view_utils import _collect_aid_documents, _get_return_info
    for tv_rec in returned_verifications:
        try:
            aid = DeathAid.objects.select_related("member_id_FK", "claimant_id_FK").get(
                death_aid_id_PK=tv_rec.record_id
            )
        except DeathAid.DoesNotExist:
            continue

        # Claims withdrawn by the Treasurer leave the returned queue.
        if (aid.status or "").lower() == "withdrawn":
            continue

        return_info = _get_return_info("death_aid", aid.death_aid_id_PK)
        proof_url = _get_proof_url(DeathAid, aid.death_aid_id_PK)

        rows.append({
            "record_id": aid.death_aid_id_PK,
            "display_id": f"DTH-{aid.death_aid_id_PK}",
            "member_id_PK": aid.member_id_FK.member_id_PK,
            "member_name": aid.member_id_FK.full_name,
            "claimant_name": aid.claimant_id_FK.full_name if aid.claimant_id_FK else "",
            "claim_date": str(aid.claim_date),
            "claim_type": aid.claim_type or "",
            "deceased_name": aid.deceased_name or "",
            "relationship_to_member": aid.relationship_to_member or "",
            "benefit_amount": str(aid.benefit_amount),
            "bill_amount": str(aid.bill_amount) if aid.bill_amount else "",
            "document_status": aid.document_status or "",
            "status": aid.status or "",
            "rejection_reason": return_info["reason"],
            "rejection_details": return_info["details"],
            "returned_by": return_info["returned_by"],
            "returned_at": return_info["returned_at"],
            "documents": _collect_aid_documents(DeathAid, [aid.death_aid_id_PK]).get(aid.death_aid_id_PK, []),
            "proof_url": proof_url or "",
        })

    return JsonResponse({"ok": True, "records": rows})


def _member_display_name(member_id) -> str:
    """Real name for a member id, falling back to the raw id if unknown."""
    return (
        Member.objects.filter(member_id_PK=int(member_id))
        .values_list("full_name", flat=True)
        .first()
    ) or f"member {member_id}"


def _simple_fund_description(description: str) -> str:
    """Plain-terms version of a fund movement description: real member names
    instead of "member 12", and no "disbursement" jargon."""
    text = (description or "").replace(" disbursement", "")
    return re.sub(r"member (\d+)", lambda m: _member_display_name(m.group(1)), text)


@require_GET
def fund_overview_api(request: HttpRequest):
    """ISUCauFA, Inc. Fund overview — simple-terms data for the fund pages."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    totals = FundTransaction.objects.aggregate(
        tin=Sum("amount", filter=Q(direction="inflow")),
        tout=Sum("amount", filter=Q(direction="outflow")),
    )
    money_in = float(totals["tin"] or 0)
    money_out = float(totals["tout"] or 0)
    balance = money_in - money_out

    month_agg = FundTransaction.objects.filter(recorded_at__gte=month_start).aggregate(
        tin=Sum("amount", filter=Q(direction="inflow")),
        tout=Sum("amount", filter=Q(direction="outflow")),
    )
    month_in = float(month_agg["tin"] or 0)
    month_out = float(month_agg["tout"] or 0)
    month_count = FundTransaction.objects.filter(recorded_at__gte=month_start).count()

    # Member headcount for the overview strip (same source as Member Directory).
    active_members = Member.objects.filter(employment_status="Active").count()
    permanent_members = Member.objects.filter(membership_status="Permanent").count()
    temporary_members = Member.objects.filter(membership_status="Temporary").count()
    retired_members = Member.objects.filter(
        Q(membership_status="Retired") | Q(member_classification="Retired")
    ).count()

    # Last 6 calendar months: money in / money out + running balance
    series = []
    running = balance
    months = []
    cursor = month_start
    for _ in range(6):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months.reverse()
    for m_start in months:
        next_start = (m_start + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        agg = FundTransaction.objects.filter(
            recorded_at__gte=m_start, recorded_at__lt=next_start
        ).aggregate(
            tin=Sum("amount", filter=Q(direction="inflow")),
            tout=Sum("amount", filter=Q(direction="outflow")),
        )
        tin = float(agg["tin"] or 0)
        tout = float(agg["tout"] or 0)
        series.append({
            "label": m_start.strftime("%b %Y"),
            "money_in": tin,
            "money_out": tout,
            "change": tin - tout,
        })
    # running balance: walk the series forward from (balance - total change of window)
    window_change = sum(s["change"] for s in series)
    running = balance - window_change
    for s_row in series:
        running += s_row["change"]
        s_row["balance"] = round(running, 2)

    # Fund journey: running balance after every recorded movement, oldest
    # first — each money-in lifts the line, each money-out dips it, so the
    # trend tracks the actual ins and outs rather than month averages.
    trend = []
    running = 0.0
    for t in FundTransaction.objects.order_by("recorded_at", "transaction_id_PK"):
        running += float(t.amount) if t.direction == "inflow" else -float(t.amount)
        trend.append({
            "label": t.recorded_at.strftime("%b %d") if t.recorded_at else "",
            "balance": round(running, 2),
            "direction": t.direction,
            "amount": float(t.amount),
        })

    # Inflow by source. Monthly-deduction collections are decomposed into the
    # assessment purposes the President set (monthly due / aid funds) so the
    # breakdown reflects them instead of everything reading as "Monthly Dues".
    # Miscellaneous purposes ("other" / "token_incentive") fold into a single
    # "Other" entity that carries its own sub-lines. Other inflows keep their
    # own categories.
    PURPOSE_INFLOW_LABELS = {
        "monthly_due": "Monthly Dues",
        "medical_aid_fund": "Medical Aid Fund",
        "death_aid_fund": "Death Aid Fund",
    }
    OTHER_PURPOSES = {AssessmentItem.PURPOSE_OTHER, AssessmentItem.PURPOSE_TOKEN_INCENTIVE}
    SOURCE_LABEL_MAP = dict(FundTransaction.SOURCE_TYPES)
    dues_inflow_ids = list(
        FundTransaction.objects.filter(direction="inflow", source_type="monthly_dues")
        .values_list("source_id", flat=True)
    )
    # Members whose aid portions were booked as their own set-aside inflows.
    # Those pesos are summed from the set-aside rows below, so decomposing the
    # member's allocations again would count them twice. Members booked before
    # the split still carry their aid inside the single monthly_dues row and
    # keep decomposing as before.
    setaside_ma_ids = set(
        FundTransaction.objects.filter(
            direction="inflow", source_type__in=SETASIDE_SOURCE_TYPES
        ).values_list("source_id", flat=True)
    )
    inflow_map = {}
    other_sub = {}
    if dues_inflow_ids:
        alloc_rows = (
            MemberAssessmentAllocation.objects
            .filter(member_assessment_id_FK_id__in=dues_inflow_ids)
            .values(
                "member_assessment_id_FK_id",
                "assessment_item_id_FK_id",
                "assessment_item_id_FK__purpose",
                "assessment_item_id_FK__custom_label",
            )
            .annotate(total=Sum("amount_applied"))
        )
        item_labels = {
            it.item_id_PK: it.label
            for it in AssessmentItem.objects.filter(
                item_id_PK__in={row["assessment_item_id_FK_id"] for row in alloc_rows}
            )
        }
        for row in alloc_rows:
            purpose = row["assessment_item_id_FK__purpose"]
            if (
                purpose in AID_PURPOSES
                and row["member_assessment_id_FK_id"] in setaside_ma_ids
            ):
                continue
            total = float(row["total"] or 0)
            if purpose in OTHER_PURPOSES:
                sub_label = item_labels.get(row["assessment_item_id_FK_id"]) or "Other"
                other_sub[sub_label] = other_sub.get(sub_label, 0.0) + total
            else:
                label = PURPOSE_INFLOW_LABELS.get(purpose) or row["assessment_item_id_FK__custom_label"] or purpose
                inflow_map[label] = inflow_map.get(label, 0.0) + total
        prior_total = (
            MemberAssessment.objects.filter(member_assessment_id_PK__in=dues_inflow_ids)
            .aggregate(t=Sum("prior_outstanding_collected"))["t"]
            or 0
        )
        if float(prior_total) > 0.005:
            inflow_map["Prior Balance Collected"] = inflow_map.get("Prior Balance Collected", 0.0) + float(prior_total)
        excess_total = (
            MemberAssessment.objects.filter(member_assessment_id_PK__in=dues_inflow_ids)
            .aggregate(t=Sum("change_amount"))["t"]
            or 0
        )
        if float(excess_total) > 0.005:
            inflow_map["Excess Collections"] = inflow_map.get("Excess to Fund", 0.0) + float(excess_total)
    for r in (
        FundTransaction.objects.filter(direction="inflow")
        .exclude(source_type="monthly_dues")
        .values("source_type")
        .annotate(total=Sum("amount"))
    ):
        label = SOURCE_LABEL_MAP.get(r["source_type"], r["source_type"] or "Other")
        inflow_map[label] = inflow_map.get(label, 0.0) + float(r["total"] or 0)
    if other_sub:
        inflow_map["Other"] = inflow_map.get("Other", 0.0) + sum(other_sub.values())
    other_rows = [
        {"label": k, "total": round(v, 2)}
        for k, v in sorted(other_sub.items(), key=lambda kv: -kv[1])
        if v > 0.005
    ]
    inflow_breakdown = [
        {"source": k, "total": round(v, 2)}
        if k != "Other"
        else {"source": k, "total": round(v, 2), "sub_items": other_rows}
        for k, v in sorted(inflow_map.items(), key=lambda kv: -kv[1])
        if v > 0.005
    ]
    outflow_breakdown = [
        {"source": r["source_type"], "total": float(r["total"] or 0)}
        for r in FundTransaction.objects.filter(direction="outflow").values("source_type").annotate(total=Sum("amount")).order_by("-total")
    ]

    # Recent activity in plain terms. One row per covered month: every
    # member's dues for that month become a single "money in" total, and the
    # per-member aid-fund allocations booked alongside the deductions fold
    # into one set-aside line instead of reading like aid paid to every
    # member. Real assistance payouts (approved and released claims) get
    # their own row naming only the member who requested the aid. The Fund
    # Ledger remains the exact per-movement record.
    # Inflows that belong to the covered month's collection: the dues row plus
    # the medical/death aid set-aside rows booked alongside it, so the month
    # bucket still totals the deposit even though the money is now split.
    MONTH_INFLOW_TYPES = ("monthly_dues",) + SETASIDE_SOURCE_TYPES
    recent = []
    buckets = {}
    for t in FundTransaction.objects.order_by("-recorded_at", "-transaction_id_PK")[:300]:
        description = t.description or ""
        match = re.match(r"^(.*) for (.+) — member (\d+)$", description)
        date_str = t.recorded_at.strftime("%b %d, %Y") if t.recorded_at else ""
        if t.direction == "outflow" and t.source_type == "aid_post_payment":
            key = ("release", t.transaction_id_PK)
        elif match and (
            (t.direction == "inflow" and t.source_type in MONTH_INFLOW_TYPES)
            or (t.direction == "outflow" and t.source_type in ("medical_aid", "death_aid"))
        ):
            key = ("month", match.group(2))
        else:
            key = ("solo", t.transaction_id_PK)
        bucket = buckets.get(key)
        if bucket is None:
            if len(recent) >= 10:
                continue
            if key[0] == "release":
                name_match = re.match(r"^Fund disbursement — (.+?) \((.+?)\)", description)
                bucket = {
                    "row_type": "release",
                    "date": date_str,
                    "member": name_match.group(1) if name_match else "",
                    "aid_type": name_match.group(2) if name_match else "",
                    "amount": float(t.amount),
                    "description": _simple_fund_description(description),
                }
            elif key[0] == "month":
                bucket = {
                    "row_type": "month",
                    "date": date_str,
                    "month": match.group(2),
                    "in_total": 0.0,
                    "in_members": set(),
                    "ma_ids": set(),
                    "out_total": 0.0,
                    "out_members": set(),
                    "out_types": [],
                }
            else:
                bucket = {
                    "row_type": "solo",
                    "date": date_str,
                    "direction": t.direction,
                    "source_type": t.source_type,
                    "amount": float(t.amount),
                    "description": _simple_fund_description(description),
                }
            buckets[key] = bucket
            recent.append(bucket)
        if bucket["row_type"] == "month":
            if t.direction == "inflow":
                bucket["in_total"] += float(t.amount)
                bucket["in_members"].add(match.group(3))
                bucket["ma_ids"].add(t.source_id)
            else:
                bucket["out_total"] += float(t.amount)
                bucket["out_members"].add(match.group(3))
                if t.source_type not in bucket["out_types"]:
                    bucket["out_types"].append(t.source_type)
    for row in recent:
        if row["row_type"] == "month":
            row["in_members"] = len(row["in_members"])
            row["out_members"] = len(row["out_members"])
            row["in_total"] = round(row["in_total"], 2)
            row["out_total"] = round(row["out_total"], 2)
            row["amount"] = round(row["in_total"] - row["out_total"], 2)
            # Per-item expectation vs collection for the month, plus any
            # prior-balance money collected — the treasurer's audit trail.
            ma_ids = list(row.pop("ma_ids") or [])
            row["expected_items"] = []
            row["prior_collected"] = 0.0
            row["excess_total"] = 0.0
            if ma_ids:
                mas = list(
                    MemberAssessment.objects.filter(member_assessment_id_PK__in=ma_ids)
                    .select_related("assessment_id_FK")
                )
                row["excess_total"] = round(sum(float(ma.change_amount or 0) for ma in mas), 2)
                row["prior_collected"] = round(
                    sum(float(ma.prior_outstanding_collected or 0) for ma in mas), 2
                )
                if mas:
                    collected_map = {
                        a["assessment_item_id_FK_id"]: float(a["collected"] or 0)
                        for a in (
                            MemberAssessmentAllocation.objects
                            .filter(member_assessment_id_FK_id__in=ma_ids)
                            .values("assessment_item_id_FK_id")
                            .annotate(collected=Sum("amount_applied"))
                        )
                    }
                    n = len(mas)
                    row["expected_items"] = [
                        {
                            "label": it.label,
                            "per_member": float(it.amount),
                            "expected": round(float(it.amount) * n, 2),
                            "collected": round(collected_map.get(it.item_id_PK, 0.0), 2),
                        }
                        for it in mas[0].assessment_id_FK.items.all()
                    ]

    return JsonResponse({
        "ok": True,
        "balance": balance,
        "money_in": money_in,
        "money_out": money_out,
        "increase": money_in - money_out,
        "month_in": month_in,
        "month_out": month_out,
        "month_count": month_count,
        "active_members": active_members,
        "permanent_members": permanent_members,
        "temporary_members": temporary_members,
        "retired_members": retired_members,
        "series": series,
        "trend": trend,
        "inflow_breakdown": inflow_breakdown,
        "outflow_breakdown": outflow_breakdown,
        "recent": recent,
    })


@require_GET
def fund_ledger_api(request: HttpRequest):
    """Fund Ledger — every fund movement, newest first (simple-terms page)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    totals = FundTransaction.objects.aggregate(
        tin=Sum("amount", filter=Q(direction="inflow")),
        tout=Sum("amount", filter=Q(direction="outflow")),
    )

    # newest first for display, with the balance AFTER each movement
    display = []
    for t in FundTransaction.objects.order_by("-recorded_at", "-transaction_id_PK")[:300]:
        display.append({
            "date": t.recorded_at.strftime("%b %d, %Y") if t.recorded_at else "",
            "direction": t.direction,
            "source_type": t.source_type,
            "description": _simple_fund_description(t.description),
            "amount": float(t.amount),
            "reference": t.reference_number or "",
        })

    return JsonResponse({
        "ok": True,
        "money_in": float(totals["tin"] or 0),
        "money_out": float(totals["tout"] or 0),
        "balance": float(totals["tin"] or 0) - float(totals["tout"] or 0),
        "entries": display,
    })


def _other_transaction_reference(tx_id: int) -> str:
    return f"OTH-{timezone.localdate().strftime('%Y%m%d')}-{tx_id:06d}"


def _other_transaction_proof_archive(tx_id: int):
    return (
        FinancialDocumentArchive.objects.filter(
            related_module="OTHER_TRANSACTION",
            related_record_id=tx_id,
            document_type="proof_receipt",
        )
        .order_by("-document_id_PK")
        .first()
    )


def _other_transaction_counterparty(description: str) -> tuple:
    """Split the donor/recipient prefix back out of a stored description.

    Recorded as ``"From {donor} — {notes}"`` (inflow) or
    ``"To {recipient} — {notes}"`` (outflow); returns ``(donor, recipient)``.
    """
    desc = (description or "").strip()
    for prefix in ("From ", "To "):
        if desc.startswith(prefix):
            rest = desc[len(prefix):]
            name, _, _notes = rest.partition(" — ")
            name = name.strip()
            if name:
                return (name, "") if prefix == "From " else ("", name)
            break
    return ("", "")


def _other_transaction_serialize(t):
    proof = _other_transaction_proof_archive(t.transaction_id_PK)
    donor, recipient = _other_transaction_counterparty(t.description)
    return {
        "id": t.transaction_id_PK,
        "date": t.recorded_at.strftime("%b %d, %Y %I:%M %p") if t.recorded_at else "",
        "sort_at": t.recorded_at.isoformat() if t.recorded_at else "",
        "direction": t.direction,
        "action": "deposit" if t.direction == "inflow" else "withdraw",
        "action_label": "Deposit" if t.direction == "inflow" else "Withdraw",
        "amount": float(t.amount),
        "description": t.description,
        "donor": donor,
        "recipient": recipient,
        "reference_number": t.reference_number or "",
        "collection_reference": "",
        "recorded_by": t.recorded_by_user_id_FK.full_name if t.recorded_by_user_id_FK_id else "Treasurer",
        "has_proof": bool(proof),
        "proof_url": (
            f"/api/treasurer/other-transactions/proof/{proof.document_id_PK}/"
            if proof
            else ""
        ),
        "source": "other_transaction",
    }


def _monthly_dues_deposit_serialize(a) -> dict:
    """A treasurer-deposited monthly dues batch, shaped like an other-transaction row."""
    slip = (
        MonthlyAssessmentDocument.objects
        .filter(assessment_id_FK=a, kind=MonthlyAssessmentDocument.KIND_DEPOSIT_SLIP)
        .order_by("-document_id_PK")
        .first()
    )
    return {
        "id": a.assessment_id_PK,
        "date": a.deposited_at.strftime("%b %d, %Y %I:%M %p") if a.deposited_at else "",
        "sort_at": a.deposited_at.isoformat() if a.deposited_at else "",
        "direction": "inflow",
        "action": "deposit",
        "action_label": "Collection",
        "amount": float(a.deposited_amount or 0),
        "description": f"Monthly Dues — {a.month_label} ({a.get_status_display()})",
        "reference_number": a.deposit_reference or "",
        "collection_reference": f"COL-{a.assessment_id_PK:05d}",
        "recorded_by": a.deposited_by_id_FK.full_name if a.deposited_by_id_FK_id else "Treasurer",
        "has_proof": bool(slip),
        "proof_url": (
            f"/api/officers/monthly-assessment/documents/{slip.document_id_PK}/file/"
            if slip
            else ""
        ),
        "source": "monthly_dues",
    }


@require_POST
def treasurer_other_transaction_record(request: HttpRequest):
    """Record a deposit/withdraw 'Other Transaction' and its proof receipt."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    try:
        amount = Decimal(str(request.POST.get("amount") or "")).quantize(Decimal("0.01"))
    except (decimal.InvalidOperation, ValueError):
        return JsonResponse({"ok": False, "error": "Enter a valid Release Amount."}, status=400)
    if amount <= 0:
        return JsonResponse({"ok": False, "error": "Release Amount must be greater than zero."}, status=400)

    action = (request.POST.get("action") or "").strip().lower()
    if action not in ("deposit", "withdraw"):
        return JsonResponse({"ok": False, "error": "Choose Deposit or Withdraw."}, status=400)
    direction = "inflow" if action == "deposit" else "outflow"

    description = (request.POST.get("description") or "").strip()
    if len(description) > 255:
        return JsonResponse({"ok": False, "error": "Notes must be 255 characters or fewer."}, status=400)

    # Optional counterparty: donor (receipts, e.g. another campus/entity giving
    # money in) or recipient (disbursements, e.g. CAUFA donating aid out to
    # another campus). Folded into the 255-char description — no schema change.
    donor = (request.POST.get("donor") or "").strip()[:120]
    recipient = (request.POST.get("recipient") or "").strip()[:120]
    # The " — " sequence is the counterparty separator in stored
    # descriptions — neutralize it inside free-text names so parsing holds.
    donor = donor.replace(" — ", " - ")
    recipient = recipient.replace(" — ", " - ")
    # Withdrawal purpose (Meal / Emergency / Aid / Token / custom). Stored as
    # a "[Purpose]" tag inside the notes segment so the "To {recipient} — …"
    # counterparty parsing keeps working — no schema change.
    purpose = (request.POST.get("purpose") or "").strip()
    # Aid subtype (Medical = member recipient, Death = external beneficiary).
    # Only meaningful with purpose Aid; folded as "[Aid - Medical|Death]".
    aid_type = (request.POST.get("aid_type") or "").strip().capitalize()
    if aid_type and purpose != "Aid":
        return JsonResponse({"ok": False, "error": "Aid type applies to Aid withdrawals only."}, status=400)
    if aid_type and aid_type not in ("Medical", "Death"):
        return JsonResponse({"ok": False, "error": "Aid type must be Medical or Death."}, status=400)
    if purpose:
        if action != "withdraw":
            return JsonResponse({"ok": False, "error": "Purpose applies to withdrawals only."}, status=400)
        if len(purpose) > 60 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '\-.&]*", purpose):
            return JsonResponse({"ok": False, "error": "Purpose must be 60 characters or fewer (letters, numbers, spaces)."}, status=400)
        purpose = re.sub(r"\s+", " ", purpose)
        tag = f"{purpose} - {aid_type}" if aid_type else purpose
        description = f"[{tag}]" + (f" {description}" if description else "")
    if action == "deposit" and donor:
        description = f"From {donor}" + (f" — {description}" if description else "")
        description = description[:255]
    elif action == "withdraw" and recipient:
        description = f"To {recipient}" + (f" — {description}" if description else "")
        description = description[:255]

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session not found."}, status=401)

    uploaded = request.FILES.get("proof_receipt")

    with transaction.atomic():
        tx = FundTransaction.objects.create(
            direction=direction,
            amount=amount,
            source_type="other_transaction",
            source_id=0,
            description=description or ("Non-Dues Receipt" if action == "deposit" else "Non-Dues Disbursement"),
            reference_number="",
            recorded_by_user_id_FK=officer,
        )
        tx.reference_number = _other_transaction_reference(tx.transaction_id_PK)
        archive = None
        if uploaded:
            from core_system.secure_upload import SecureUploadError, validate_and_store

            try:
                saved = validate_and_store(uploaded, subdir="secure_uploads/other_transactions")
            except SecureUploadError as exc:
                return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
            archive = FinancialDocumentArchive.objects.create(
                related_module="OTHER_TRANSACTION",
                related_record_id=tx.transaction_id_PK,
                document_type="proof_receipt",
                file_path=saved["stored_name"],
                file_name=saved["original_name"],
                file_type=saved["mime"],
                file_hash=saved["sha256"],
                verification_status="Recorded",
                uploaded_by_user_id_FK=officer,
            )
        tx.save(update_fields=["reference_number"])

    return JsonResponse({"ok": True, "transaction": _other_transaction_serialize(tx)})


@require_GET
def treasurer_other_transaction_list(request: HttpRequest):
    """Transaction history for the 'Other Transactions' module (Treasurer only).

    Merges one-off non-dues transactions with treasurer-deposited monthly dues
    batches so the Record Transaction page shows both kinds of deposits.
    """
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    other_qs = FundTransaction.objects.filter(source_type="other_transaction")
    # Monthly dues deposits live on MonthlyAssessment (no FundTransaction row is
    # written until the President final-approves). The deposit evidence is
    # cleared (deposit_reference nulled) on reject/return, which drops the row
    # from history automatically.
    dues_qs = (
        MonthlyAssessment.objects
        .filter(deposit_reference__isnull=False, deposited_at__isnull=False)
        .exclude(deposit_reference="")
        .select_related("deposited_by_id_FK")
    )

    merged = [
        (t.recorded_at or timezone.now(), t.transaction_id_PK, _other_transaction_serialize(t))
        for t in other_qs
    ] + [
        (a.deposited_at, a.assessment_id_PK, _monthly_dues_deposit_serialize(a))
        for a in dues_qs
    ]
    merged.sort(key=lambda r: (r[0], r[1]), reverse=True)
    rows = [entry for _, _, entry in merged[:200]]

    totals = other_qs.aggregate(
        tin=Sum("amount", filter=Q(direction="inflow")),
        tout=Sum("amount", filter=Q(direction="outflow")),
    )
    # Collections (recorded dues batches the Treasurer deposited) are kept
    # apart from one-off bank receipts so the two flows stay separable:
    #   collection = money gathered from members, then banked
    #   deposit    = a one-off receipt booked straight into the fund
    collected_total = dues_qs.aggregate(s=Sum("deposited_amount"))["s"] or 0
    deposited_total = totals["tin"] or 0
    withdrawn_total = totals["tout"] or 0
    return JsonResponse({
        "ok": True,
        "entries": rows,
        "total_collected": float(collected_total),
        "total_deposited": float(deposited_total),
        "total_withdrawn": float(withdrawn_total),
        "net": float(collected_total + deposited_total - withdrawn_total),
    })


@require_GET
def treasurer_transaction_detail(request: HttpRequest, source: str, record_id: int):
    """Full trace for one Transaction History row (monthly dues deposit or one-off)."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    if source == "other_transaction":
        tx = FundTransaction.objects.filter(
            pk=record_id, source_type="other_transaction"
        ).select_related("recorded_by_user_id_FK").first()
        if tx is None:
            return JsonResponse({"ok": False, "error": "Transaction not found."}, status=404)
        proof = _other_transaction_proof_archive(tx.transaction_id_PK)
        is_deposit = tx.direction == "inflow"
        _donor, _recipient = _other_transaction_counterparty(tx.description)
        return JsonResponse({
            "ok": True,
            "detail": {
                "source": "other_transaction",
                "type_label": "Deposit" if is_deposit else "Withdraw",
                "title": tx.description or ("Non-Dues Receipt" if is_deposit else "Non-Dues Disbursement"),
                "description": tx.description or ("Non-Dues " + ("Receipt" if is_deposit else "Disbursement") + " recorded directly into the fund."),
                "donor": _donor,
                "recipient": _recipient,
                "status": "",
                "status_label": "",
                "amount": float(tx.amount),
                "reference_number": tx.reference_number or "",
                "collection_reference": "",
                "encoded_by": tx.recorded_by_user_id_FK.full_name if tx.recorded_by_user_id_FK_id else "Treasurer",
                "recorded_at": tx.recorded_at.isoformat() if tx.recorded_at else "",
                "has_proof": bool(proof),
                "proof_url": (
                    f"/api/treasurer/other-transactions/proof/{proof.document_id_PK}/"
                    if proof
                    else ""
                ),
                "deposit": {},
                "milestones": {},
                "workflow_logs": [],
            },
        })

    if source == "monthly_dues":
        assessment = (
            MonthlyAssessment.objects
            .filter(pk=record_id)
            .select_related("deposited_by_id_FK", "created_by_id_FK")
            .first()
        )
        if assessment is None:
            return JsonResponse({"ok": False, "error": "Monthly dues record not found."}, status=404)

        logs = [
            {
                "log_id": log.pk,
                "action": log.action,
                "performed_by": log.performed_by_id_FK.full_name if log.performed_by_id_FK_id else "",
                "notes": log.notes or "",
                "created_at": log.created_at.isoformat() if log.created_at else "",
            }
            for log in assessment.workflow_logs.all().select_related("performed_by_id_FK")
        ]

        def first_log_time(actions) -> str:
            wanted = set(actions)
            for entry in logs:
                if entry["action"] in wanted and entry["created_at"]:
                    return entry["created_at"]
            return ""

        def first_log_actor(actions) -> str:
            wanted = set(actions)
            for entry in logs:
                if entry["action"] in wanted and entry["performed_by"]:
                    return entry["performed_by"]
            return ""

        recorded_at = first_log_time({"treasurer_submit"}) or first_log_time({"treasurer_save_draft"})
        recorded_by = (
            first_log_actor({"treasurer_submit", "treasurer_save_draft"})
            or (assessment.created_by_id_FK.full_name if assessment.created_by_id_FK_id else "")
        )

        member_assessments = list(assessment.member_assessments.all())
        total_recorded = sum((m.actual_deduction for m in member_assessments), Decimal("0"))
        total_outstanding = sum((m.outstanding_balance for m in member_assessments), Decimal("0"))

        slips = [
            {
                "id": doc.document_id_PK,
                "url": f"/api/officers/monthly-assessment/documents/{doc.document_id_PK}/file/",
                "name": os.path.basename(doc.image.name),
            }
            for doc in assessment.documents.filter(
                kind=MonthlyAssessmentDocument.KIND_DEPOSIT_SLIP
            ).order_by("document_id_PK")
        ]

        return JsonResponse({
            "ok": True,
            "detail": {
                "source": "monthly_dues",
                "type_label": "Dues Deposit" if assessment.deposit_reference else "Monthly Dues",
                "title": f"Monthly Dues — {assessment.month_label}",
                "description": (
                    f"Batch collection of monthly dues for {assessment.month_label}: "
                    f"{len(member_assessments)} member(s) recorded at ₱{assessment.total_amount} per member "
                    f"(₱{total_recorded} collected, ₱{total_outstanding} outstanding). "
                    "Recorded by the Treasurer, deposited to the bank, then routed to the "
                    "Auditor for verification and the President for final approval before "
                    "the fund is credited."
                ),
                "status": assessment.status,
                "status_label": assessment.get_status_display(),
                "amount": float(assessment.deposited_amount if assessment.deposited_amount is not None else total_recorded),
                "reference_number": assessment.deposit_reference or "",
                "collection_reference": f"COL-{assessment.assessment_id_PK:05d}",
                "encoded_by": recorded_by,
                "recorded_at": recorded_at,
                "expected_per_member": float(assessment.total_amount),
                "recorded_count": len(member_assessments),
                "total_recorded": float(total_recorded),
                "total_outstanding": float(total_outstanding),
                "created_at": assessment.created_at.isoformat() if assessment.created_at else "",
                "updated_at": assessment.updated_at.isoformat() if assessment.updated_at else "",
                "has_proof": bool(slips),
                "proof_url": slips[0]["url"] if slips else "",
                "deposit": {
                    "reference": assessment.deposit_reference or "",
                    "amount": float(assessment.deposited_amount) if assessment.deposited_amount is not None else None,
                    "deposited_at": assessment.deposited_at.isoformat() if assessment.deposited_at else "",
                    "deposited_by": assessment.deposited_by_id_FK.full_name if assessment.deposited_by_id_FK_id else "",
                    "slips": slips,
                },
                "milestones": {
                    "recorded_at": recorded_at,
                    "deposited_at": assessment.deposited_at.isoformat() if assessment.deposited_at else "",
                    "verified_at": first_log_time({"auditor_verify"}),
                    "approved_at": first_log_time({"president_approve"}),
                },
                "workflow_logs": logs,
            },
        })

    return JsonResponse({"ok": False, "error": "Unknown transaction source."}, status=400)


@require_GET
def treasurer_other_transaction_proof(request: HttpRequest, document_id: int):
    """Serve a stored proof receipt for inline viewing."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    archive = get_object_or_404(FinancialDocumentArchive, pk=document_id, document_type="proof_receipt")
    try:
        blob = default_storage.open(archive.file_path)
    except Exception:
        raise Http404("Proof file is missing on the server.")
    content = blob.read()
    blob.close()
    filename = archive.file_name or f"proof_{document_id}"
    content_type = archive.file_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@require_GET
def treasurer_approved_transactions_total(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    qs = TransactionArchive.objects.filter(
        status="Approved",
        transaction_type__in=["membership_fee", "monthly_dues"],
    ).select_related()

    total = sum(float(entry.amount or 0) for entry in qs)

    return JsonResponse({"ok": True, "total": total})


@require_GET
def cash_flow_summary(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard

    totals = FundTransaction.objects.aggregate(
        funds_in=Sum("amount", filter=Q(direction="inflow")),
        funds_out=Sum("amount", filter=Q(direction="outflow")),
    )
    funds_in = float(totals["funds_in"] or 0)
    funds_out = float(totals["funds_out"] or 0)

    return JsonResponse({
        "ok": True,
        "funds_in": funds_in,
        "funds_out": funds_out,
        "fund_balance": funds_in - funds_out,
    })


@require_GET
def treasurer_dashboard_inflow_outflow(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    totals = FundTransaction.objects.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    total_in = float(totals["total_in"] or 0)
    total_out = float(totals["total_out"] or 0)
    fund_balance = total_in - total_out

    recent_inflows = FundTransaction.objects.filter(
        direction="inflow",
    ).order_by("-recorded_at")[:50]

    recent_outflows = FundTransaction.objects.filter(
        direction="outflow",
    ).order_by("-recorded_at")[:50]

    inflows = []
    for ft in recent_inflows:
        inflows.append({
            "description": ft.description,
            "source_type": ft.source_type,
            "amount": float(ft.amount),
            "recorded_at": str(ft.recorded_at.date()) if ft.recorded_at else "",
        })

    outflows = []
    for ft in recent_outflows:
        outflows.append({
            "description": ft.description,
            "source_type": ft.source_type,
            "amount": float(ft.amount),
            "recorded_at": str(ft.recorded_at.date()) if ft.recorded_at else "",
        })

    safety_threshold = float(SystemSetting.objects.get_or_create(
        setting_key="safety_threshold", defaults={"setting_value": "20000"}
    )[0].setting_value)

    return JsonResponse({
        "ok": True,
        "fund_balance": fund_balance,
        "money_in": total_in,
        "money_out": total_out,
        "inflows": inflows,
        "outflows": outflows,
        "safety_threshold": safety_threshold,
        "available": fund_balance - safety_threshold,
    })


@require_GET
def treasurer_monthly_flow(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    year = request.GET.get("year") or timezone.now().year
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = timezone.now().year

    membership_fee_map = {}
    monthly_dues_map = {}
    medical_setaside_map = {}
    death_setaside_map = {}
    medical_aid_map = {}
    death_aid_map = {}
    fund_payment_map = {}
    contribution_map = {}

    for ft in FundTransaction.objects.filter(recorded_at__year=year).iterator():
        m = ft.recorded_at.month
        amount = float(ft.amount)

        if ft.direction == "inflow":
            if ft.source_type == "membership_fee":
                membership_fee_map[m] = membership_fee_map.get(m, 0) + amount
            elif ft.source_type == "monthly_dues":
                monthly_dues_map[m] = monthly_dues_map.get(m, 0) + amount
            elif ft.source_type == "aid_setaside_medical":
                medical_setaside_map[m] = medical_setaside_map.get(m, 0) + amount
            elif ft.source_type == "aid_setaside_death":
                death_setaside_map[m] = death_setaside_map.get(m, 0) + amount
            elif ft.source_type == "contribution":
                contribution_map[m] = contribution_map.get(m, 0) + amount
        elif ft.direction == "outflow":
            if ft.source_type == "medical_aid":
                medical_aid_map[m] = medical_aid_map.get(m, 0) + amount
            elif ft.source_type == "death_aid":
                death_aid_map[m] = death_aid_map.get(m, 0) + amount
            elif ft.source_type == "aid_post_payment":
                fund_payment_map[m] = fund_payment_map.get(m, 0) + amount

    month_labels = []
    membership_fee_data = []
    monthly_dues_data = []
    medical_setaside_data = []
    death_setaside_data = []
    medical_aid_data = []
    death_aid_data = []
    fund_payment_data = []
    contribution_data = []

    for m in range(1, 13):
        month_labels.append(f"{year}-{m:02d}")
        membership_fee_data.append(membership_fee_map.get(m, 0))
        monthly_dues_data.append(monthly_dues_map.get(m, 0))
        medical_setaside_data.append(medical_setaside_map.get(m, 0))
        death_setaside_data.append(death_setaside_map.get(m, 0))
        medical_aid_data.append(medical_aid_map.get(m, 0))
        death_aid_data.append(death_aid_map.get(m, 0))
        fund_payment_data.append(fund_payment_map.get(m, 0))
        contribution_data.append(contribution_map.get(m, 0))

    return JsonResponse({
        "ok": True,
        "months": month_labels,
        "membership_fee": membership_fee_data,
        "monthly_dues": monthly_dues_data,
        "medical_setaside": medical_setaside_data,
        "death_setaside": death_setaside_data,
        "medical_aid": medical_aid_data,
        "death_aid": death_aid_data,
        "fund_payment": fund_payment_data,
        "contribution": contribution_data,
    })


# ============================================================================
# TREASURER: VISUALIZATION DATA ENDPOINTS
# ============================================================================

@require_GET
def treasurer_dashboard_payment_methods(request: HttpRequest):
    """Payment method distribution for monthly dues."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    current_month = request.GET.get("month") or timezone.now().strftime("%Y-%m")
    dues = MonthlyDues.objects.filter(month_covered=current_month).select_related("member_id_FK")

    method_counts = {}
    for d in dues:
        method = d.payment_method or "Unknown"
        method_counts[method] = method_counts.get(method, 0) + 1

    total = sum(method_counts.values())
    distribution = [
        {"method": method, "count": count, "percentage": round(count / total * 100, 1) if total else 0}
        for method, count in sorted(method_counts.items(), key=lambda x: -x[1])
    ]

    return JsonResponse({
        "ok": True,
        "month": current_month,
        "total_transactions": total,
        "distribution": distribution,
    })


@require_GET
def treasurer_dashboard_monthly_collection(request: HttpRequest):
    """Monthly collection trend for the last 12 months."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    year = request.GET.get("year") or timezone.now().year
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = timezone.now().year

    collected_map = {}
    paying_members_map = {}

    for ft in FundTransaction.objects.filter(recorded_at__year=year, direction="inflow").iterator():
        m = ft.recorded_at.month
        amount = float(ft.amount)
        if ft.source_type in ("monthly_dues",) + SETASIDE_SOURCE_TYPES + ("membership_fee",):
            collected_map[m] = collected_map.get(m, 0) + amount

    for md in MonthlyDues.objects.filter(month_covered__startswith=str(year), payment_status__in=list(Status.ALL_AUDITOR_VERIFIED)).iterator():
        try:
            m = int(md.month_covered.split("-")[1])
            paying_members_map[m] = paying_members_map.get(m, 0) + 1
        except (ValueError, IndexError):
            pass

    months = []
    collected_data = []
    paying_members_data = []

    for m in range(1, 13):
        month_name = timezone.datetime(year, m, 1).strftime("%b %Y")
        months.append(month_name)
        collected_data.append(collected_map.get(m, 0))
        paying_members_data.append(paying_members_map.get(m, 0))

    return JsonResponse({
        "ok": True,
        "months": months,
        "collected": collected_data,
        "paying_members": paying_members_data,
    })


@require_GET
def treasurer_dashboard_dues_status(request: HttpRequest):
    """Dues processing status: Paid / Pending / Unpaid breakdown.

    Member-based shared computation (core_system.services.dues_status) so the
    Treasurer, Auditor and President dashboards always agree. Honours the
    banner month/year via ?month=YYYY-MM."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    from core_system.services.dues_status import dues_status_for_month, resolve_month_key

    current_month = resolve_month_key(request)
    return JsonResponse({
        "ok": True,
        **dues_status_for_month(current_month),
    })


@require_GET
def treasurer_dashboard_aid_progress(request: HttpRequest):
    """Active aid contribution progress for Medical/Death Aid tracking posts."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    active_posts = AidTrackingPost.objects.filter(is_active=True).select_related("archive_id_FK")

    posts_data = []
    for post in active_posts:
        expected = float(post.total_expected or 0)
        collected = float(post.total_collected or 0)
        remaining = expected - collected
        percentage = round(collected / expected * 100, 1) if expected else 0

        contribs = Contribution.objects.filter(aid_tracking_post_id_FK=post)
        members_paid = contribs.filter(
            status__in=[Contribution.STATUS_PAID, Contribution.STATUS_RECORDED, Contribution.STATUS_PENDING_VERIFICATION]
        ).count()
        members_pending = contribs.filter(status=Contribution.STATUS_NOT_PAID).count()

        posts_data.append({
            "post_id": post.post_id_PK,
            "aid_type": post.aid_type,
            "target_month": post.target_month,
            "expected": expected,
            "collected": collected,
            "remaining": remaining,
            "percentage": percentage,
            "members_paid": members_paid,
            "members_pending": members_pending,
            "status": post.status,
        })

    return JsonResponse({
        "ok": True,
        "posts": posts_data,
    })


@require_GET
def treasurer_dashboard_action_queue(request: HttpRequest):
    """Action queue counts for the Treasurer."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    pending_aid_requests = MedicalAid.objects.filter(
        status__in=["Pending Treasurer Review", "Pending Auditor Verification"]
    ).count() + DeathAid.objects.filter(
        status__in=["Pending Treasurer Review", "Pending Auditor Verification"]
    ).count()

    current_month = timezone.now().strftime("%Y-%m")
    pending_dues = MonthlyDues.objects.filter(
        month_covered=current_month,
        payment_status__in=list(Status.ALL_PENDING)
    ).count()

    pending_registrations = MemberRegistrationRequest.objects.filter(
        status__in=["Pending Treasurer Review", "Pending"]
    ).count()

    returned_entries = TransactionVerification.objects.filter(
        table_name__in=["membership_fee", "monthly_dues", "medical_aid", "death_aid"],
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED]
    ).count()

    ready_for_release = AidTrackingPost.objects.filter(
        is_active=True,
        finish_status="pending_release"
    ).count()

    return JsonResponse({
        "ok": True,
        "pending_aid_requests": pending_aid_requests,
        "pending_dues": pending_dues,
        "pending_registrations": pending_registrations,
        "returned_entries": returned_entries,
        "ready_for_release": ready_for_release,
    })


#new_membership_add
@require_POST
def treasurer_membership_fee_add(request: HttpRequest):
    """Create a MEMBERSHIP_FEE row from the Treasurer membership fee form."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    from core_system.services.membership_fee_rules import (
        check_membership_fee_requirement,
        validate_membership_fee_payment,
    )

    fee_member = (request.POST.get("fee_member") or "").strip()
    fee_method = (request.POST.get("fee_method") or "").strip()
    fee_status = (request.POST.get("fee_status") or "").strip()
    fee_date = (request.POST.get("fee_date") or "").strip()
    fee_ref = (request.POST.get("fee_ref") or "").strip()
    fee_encoder = (request.POST.get("fee_encoder") or "").strip()

    if not fee_member:
        return JsonResponse({"ok": False, "error": "Associated Member ID is required."}, status=400)
    if not fee_method:
        return JsonResponse({"ok": False, "error": "Payment method is required."}, status=400)
    if not fee_status:
        fee_status = "Full Payment"
    if fee_status not in ("Full Payment", "Partial"):
        return JsonResponse({"ok": False, "error": "Payment status must be Full Payment or Partial."}, status=400)
    if not fee_date:
        return JsonResponse({"ok": False, "error": "Payment Date is required."}, status=400)
    if not fee_ref:
        return JsonResponse({"ok": False, "error": "Receipt / Reference Number is required."}, status=400)

    member_obj, err = resolve_member_from_input(fee_member)
    if err:
        return err

    if is_exempt_from_dues_and_aid(member_obj):
        return JsonResponse(
            {"ok": False, "error": "Retired members are exempt from monthly dues per ARTICLE XI Section 2."},
            status=400,
        )

    # Resolve officer session for potential exceptions and workflows
    recorded_by = resolve_officer_from_session(request)
    
    # Check policy requirement
    required_check = check_membership_fee_requirement(member_obj)
    if not required_check.required_to_pay:
        if recorded_by is not None:
            from core_system.services.membership_fee_rules import (
                record_membership_fee_policy_exception,
            )
            record_membership_fee_policy_exception(
                member=member_obj,
                reason=required_check.exception_reason or "Fee not required.",
                officer=recorded_by,
                request=request,
            )

        return JsonResponse(
            {
                "ok": False,
                "error": "Membership fee policy exception",
                "reason": required_check.exception_reason or "Fee not required.",
            },
            status=400,
        )

    validation = validate_membership_fee_payment(
        payload={
            "fee_status": fee_status,
            "fee_ref": fee_ref,
            "fee_amount": request.POST.get("fee_amount"),
            "fee_partial_amount": request.POST.get("fee_partial_amount"),
        }
    )

    if not validation.valid:
        from core_system.services.membership_fee_rules import (
            create_correction_artifacts_for_membership_fee,
        )
        if recorded_by is None:
            return JsonResponse(
                {"ok": False, "error": "Unable to resolve officer session for encoding."},
                status=401,
            )

        amount_value = str((validation.normalized.get("fee_amount")))

        with transaction.atomic():
            fee = MembershipFee.objects.create(
                member_id_FK=member_obj,
                receipt_number=fee_ref,
                amount=amount_value,
                payment_date=fee_date,
                payment_method=fee_method,
                payment_status=fee_status,
                deposit_reference=fee_encoder or None,
                recorded_by_user_id_FK=recorded_by,
            )

            TransactionVerification.objects.create(
                table_name="membership_fee",
                record_id=fee.fee_id_PK,
                verification_status="Returned for Revision",
            )

            create_correction_artifacts_for_membership_fee(
                fee=fee,
                officer=recorded_by,
                validation_errors=validation.errors,
                request=request,
            )

        return JsonResponse(
            {
                "ok": False,
                "error": "Payment requires correction",
                "errors": validation.errors,
                "fee_id": fee.fee_id_PK,
            },
            status=400,
        )

    amount_value = str(validation.normalized.get("fee_amount"))

    if recorded_by is None:
        return JsonResponse({"ok": False, "error": "Unable to resolve officer session for encoding."}, status=401)

    from core_system.services.membership_fee_rules import (
        has_duplicate_membership_fee,
    )
    dup_check = has_duplicate_membership_fee(
        member=member_obj,
        receipt_number=fee_ref,
    )
    if dup_check.is_duplicate:
        return JsonResponse(
            {
                "ok": False,
                "error": "Duplicate fee entry detected for this member and receipt number.",
                "existing_fee_id": dup_check.existing_fee_id,
            },
            status=400,
        )

    uploaded = request.FILES.get("fee_photo_file")

    try:
        with transaction.atomic():
            fee = MembershipFee.objects.create(
                member_id_FK=member_obj,
                receipt_number=fee_ref,
                amount=amount_value,
                payment_date=fee_date,
                payment_method=fee_method,
                payment_status=fee_status,
                deposit_reference=fee_encoder or None,
                recorded_by_user_id_FK=recorded_by,
            )

            TransactionVerification.objects.create(
                table_name="membership_fee",
                record_id=fee.fee_id_PK,
                verification_status="Pending Auditor Review",
            )

            if uploaded and uploaded.size > 0:
                _link_proof_to_record(uploaded, fee, recorded_by)

            _record_audit_trail(
                table="membership_fee",
                record_id=fee.fee_id_PK,
                action="CREATED",
                actor=recorded_by,
                new={
                    "member": member_obj,
                    "receipt_number": fee_ref,
                    "amount": amount_value,
                    "payment_date": fee_date,
                    "payment_method": fee_method,
                    "payment_status": fee_status,
                    "deposit_reference": fee_encoder or None,
                },
                ip=request.META.get("REMOTE_ADDR"),
            )
    except ValueError as exc:
        # Blocked proof upload (duplicate content, disallowed type, oversize):
        # the atomic block already rolled back the fee, so answer with the
        # specific reason + log the attempt instead of a generic 500.
        return proof_upload_blocked_response(
            request, exc,
            table="membership_fee", record_id=0,
            actor=recorded_by, member=member_obj,
        )

    _broadcast_treasurer("membership_fees")

    return JsonResponse(
        {
            "ok": True,
            "fee": {
                "fee_id": fee.fee_id_PK,
                "member_id": member_obj.member_id_PK,
                "member_name": member_obj.full_name,
                "amount": str(fee.amount),
                "payment_date": str(fee.payment_date),
                "payment_status": fee.payment_status,
                "payment_method": fee.payment_method,
                "ref": fee.receipt_number,
                "encoded_by": recorded_by.full_name,
                "proof_attached": bool(uploaded and uploaded.size > 0),
            },
        }
    )

#end_new_


def _process_monthly_dues_entry(request, payment_type, **kwargs):
    """Shared monthly dues creation logic for OTC and Salary Deduction.

    kwargs must contain:
      member_input, month_raw, amount_raw
    OTC: date_raw, method, ref, uploaded
    Salary: summary, sal_ref, uploaded
    """
    member_input = kwargs.get("member_input", "").strip()
    month_raw = kwargs.get("month_raw", "").strip()
    amount_raw = kwargs.get("amount_raw", "").strip()

    if not member_input:
        return JsonResponse({"ok": False, "error": "Associated Member ID is required."}, status=400)
    if not month_raw:
        return JsonResponse({"ok": False, "error": "Month Covered is required."}, status=400)
    if not amount_raw:
        return JsonResponse({"ok": False, "error": "Amount Paid is required."}, status=400)

    month = normalize_month_covered(month_raw)

    try:
        amount_decimal = decimal.Decimal(amount_raw)
    except decimal.InvalidOperation:
        return JsonResponse({"ok": False, "error": "Amount must be a valid number."}, status=400)

    if amount_decimal <= 0:
        return JsonResponse({"ok": False, "error": "Amount must be positive."}, status=400)

    expected = decimal.Decimal(str(get_monthly_dues_amount()))
    if abs(amount_decimal - expected) > decimal.Decimal("0.01"):
        return JsonResponse(
            {"ok": False, "error": f"Monthly dues amount must be exactly ₱{expected:.2f} per ARTICLE XI Section 1.c."},
            status=400,
        )

    member, err = resolve_member_from_input(member_input)
    if err:
        return err

    ret = check_member_not_retired(member)
    if ret:
        return ret

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Unable to resolve officer session for encoding."}, status=401)

    if payment_type == "otc":
        date_raw = kwargs.get("date_raw", "").strip()
        method = kwargs.get("method", "").strip() or "Unknown"
        ref = kwargs.get("ref", "").strip()
        uploaded = kwargs.get("uploaded")

        if not date_raw:
            return JsonResponse({"ok": False, "error": "Payment Date is required."}, status=400)
        if not ref:
            return JsonResponse({"ok": False, "error": "Receipt / Reference Number is required."}, status=400)

        with transaction.atomic():
            if MonthlyDues.objects.filter(member_id_FK=member, month_covered=month).exists():
                return JsonResponse(
                    {"ok": False, "error": "Monthly dues already recorded for this member and month."},
                    status=409,
                )
            is_advance = month > timezone.now().strftime("%Y-%m")
            dues = MonthlyDues.objects.create(
                member_id_FK=member,
                month_covered=month,
                amount=str(amount_decimal),
                payment_method=method,
                payment_status="Pending",
                payment_date=date_raw,
                receipt_number=ref,
                recorded_by_user_id_FK=officer,
                is_advance=is_advance,
                treasurer_status="Treasurer Approved",
                treasurer_id_FK=officer,
                treasurer_approved_at=timezone.now(),
                auditor_status="Pending Auditor Review",
            )
            TransactionVerification.objects.create(
                table_name="monthly_dues",
                record_id=dues.dues_id_PK,
                verification_status="Pending Auditor Review",
            )
            if uploaded and getattr(uploaded, "size", 0) > 0:
                _link_proof_to_record(uploaded, dues, officer)
            _record_audit_trail(
                table="monthly_dues",
                record_id=dues.dues_id_PK,
                action="CREATED",
                actor=officer,
                new={"member": member, "month_covered": month, "amount": str(amount_decimal),
                     "payment_method": method, "payment_date": date_raw, "receipt_number": ref,
                     "is_advance": is_advance},
                ip=request.META.get("REMOTE_ADDR"),
            )
        _broadcast_treasurer("monthly_dues")
        return JsonResponse({"ok": True, "dues": {
            "dues_id": dues.dues_id_PK,
            "ref": dues.receipt_number or "",
            "member_id": member.member_id_PK,
            "member_name": member.full_name,
            "month": dues.month_covered,
            "amount": str(dues.amount),
            "method": dues.payment_method,
            "date": str(dues.payment_date),
            "proof_attached": bool(uploaded and getattr(uploaded, "size", 0) > 0),
        }})

    else:  # salary
        summary = kwargs.get("summary", "").strip()
        sal_ref = kwargs.get("sal_ref", "").strip()
        uploaded = kwargs.get("uploaded")

        if not summary:
            return JsonResponse({"ok": False, "error": "Accounting Deduction Summary Remarks are required."}, status=400)
        if not sal_ref:
            return JsonResponse({"ok": False, "error": "Remittance Reference Number is required."}, status=400)

        try:
            payment_date = datetime.strptime(month + "-01", "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"ok": False, "error": "Invalid deduction month format."}, status=400)

        with transaction.atomic():
            if MonthlyDues.objects.filter(member_id_FK=member, month_covered=month).exists():
                return JsonResponse(
                    {"ok": False, "error": "Monthly dues already recorded for this member and month."},
                    status=409,
                )
            is_advance = month > timezone.now().strftime("%Y-%m")
            dues = MonthlyDues.objects.create(
                member_id_FK=member,
                month_covered=month,
                amount=str(amount_decimal),
                payment_method="Salary Deduction",
                payment_status="Pending",
                payment_date=payment_date,
                deduction_batch_reference=summary,
                remittance_reference=sal_ref,
                recorded_by_user_id_FK=officer,
                is_advance=is_advance,
                treasurer_status="Treasurer Approved",
                treasurer_id_FK=officer,
                treasurer_approved_at=timezone.now(),
                auditor_status="Pending Auditor Review",
            )
            TransactionVerification.objects.create(
                table_name="monthly_dues",
                record_id=dues.dues_id_PK,
                verification_status="Pending Auditor Review",
            )
            if uploaded and getattr(uploaded, "size", 0) > 0:
                _link_proof_to_record(uploaded, dues, officer)

            # NOTE: MemberLedger is intentionally NOT written here. Monthly dues
            # reach the ledger once — at President approval — so MemberLedger and
            # FundTransaction always describe the same approved financial event.

            _record_audit_trail(
                table="monthly_dues",
                record_id=dues.dues_id_PK,
                action="CREATED",
                actor=officer,
                new={"member": member, "month_covered": month, "amount": str(amount_decimal),
                     "payment_method": "Salary Deduction", "payment_date": str(payment_date),
                     "deduction_batch_reference": summary, "remittance_reference": sal_ref},
                ip=request.META.get("REMOTE_ADDR"),
            )
        _broadcast_treasurer("monthly_dues")
        return JsonResponse({"ok": True, "dues": {
            "dues_id": dues.dues_id_PK,
            "ref": dues.remittance_reference or "",
            "member_id": member.member_id_PK,
            "member_name": member.full_name,
            "month": dues.month_covered,
            "amount": str(dues.amount),
            "remarks": dues.deduction_batch_reference or "",
        }})


@require_POST
def treasurer_monthly_dues_add(request: HttpRequest):
    """Unified monthly dues add view. Supports both 'otc' and 'salary' payment_type."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    payment_type = (request.POST.get("payment_type") or "").strip().lower()
    if not payment_type:
        if "otc_member" in request.POST or "otc_ref" in request.POST:
            payment_type = "otc"
        elif "sal_member" in request.POST or "sal_ref" in request.POST:
            payment_type = "salary"
        else:
            return JsonResponse({"ok": False, "error": "payment_type must be 'otc' or 'salary'."}, status=400)

    if payment_type == "otc":
        return _process_monthly_dues_entry(request, "otc",
            member_input=request.POST.get("otc_member") or request.POST.get("member") or "",
            month_raw=request.POST.get("otc_month") or request.POST.get("month") or "",
            amount_raw=request.POST.get("otc_amount") or request.POST.get("amount") or "",
            date_raw=request.POST.get("otc_date") or request.POST.get("date") or "",
            method=request.POST.get("otc_method") or request.POST.get("method") or "",
            ref=request.POST.get("otc_ref") or request.POST.get("ref") or "",
            uploaded=request.FILES.get("otc_photo_file") or request.FILES.get("photo_file"),
        )
    else:
        return _process_monthly_dues_entry(request, "salary",
            member_input=request.POST.get("sal_member") or request.POST.get("member") or "",
            month_raw=request.POST.get("sal_month") or request.POST.get("month") or "",
            amount_raw=request.POST.get("sal_amount") or request.POST.get("amount") or "",
            summary=request.POST.get("sal_summary") or request.POST.get("summary") or "",
            sal_ref=request.POST.get("sal_ref") or request.POST.get("remittance_ref") or "",
            uploaded=request.FILES.get("sal_photo_file") or request.FILES.get("photo_file"),
        )


@require_POST
def treasurer_monthly_dues_otc_add(request: HttpRequest):
    """Legacy OTC add wrapper — delegates to unified view."""
    return treasurer_monthly_dues_add(request)


def treasurer_monthly_dues_otc_list(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    dues = (
        MonthlyDues.objects.select_related("member_id_FK", "recorded_by_user_id_FK")
        .filter(treasurer_status="Pending Treasurer Review")
        .exclude(payment_method="Salary Deduction")  # Exclude salary deductions from Treasurer queue
        .order_by("-dues_id_PK")
    )

    rows = []
    for d in dues:
        rows.append(
            {
                "dues_id": d.dues_id_PK,
                "dues_id_PK": d.dues_id_PK,
                "ref": d.receipt_number or "",
                "member_id": d.member_id_FK.member_id_PK,
                "member_name": d.member_id_FK.full_name,
                "member_employee_id": d.member_id_FK.employee_id,
                "month": d.month_covered,
                "month_covered": d.month_covered,
                "amount": str(d.amount),
                "method": d.payment_method,
                "payment_method": d.payment_method,
                "date": str(d.payment_date) if d.payment_date else "",
                "payment_status": d.payment_status,
                "treasurer_status": d.treasurer_status,
                "auditor_status": d.auditor_status,
                "president_status": d.president_status,
            }
        )

    return JsonResponse({"ok": True, "otc_dues": rows, "dues": rows})


@require_GET
def treasurer_monthly_dues_detail(request: HttpRequest, dues_id: int):
    """Get full details of a monthly dues submission for review."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    dues = get_object_or_404(
        MonthlyDues.objects.select_related("member_id_FK", "recorded_by_user_id_FK"),
        dues_id_PK=dues_id
    )

    # Get supporting proofs. A member may submit one payment covering multiple
    # months (advance dues); all sibling MonthlyDues rows share the same
    # receipt_number but the proof is only linked to the first row. Include
    # proofs from sibling rows so the review shows the uploaded proof for every
    # month of the submission, not just the first.
    ct = ContentType.objects.get_for_model(MonthlyDues)
    sibling_ids = [dues.dues_id_PK]
    if dues.receipt_number:
        sibling_ids.extend(
            MonthlyDues.objects.filter(
                member_id_FK=dues.member_id_FK,
                receipt_number=dues.receipt_number,
            ).exclude(dues_id_PK=dues.dues_id_PK).values_list("dues_id_PK", flat=True)
        )
    proofs = (
        SupportingProof.objects.filter(
            content_type=ct,
            object_id__in=sibling_ids,
        )
        .order_by("-uploaded_at")
        .distinct()
    )

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
        "dues": {
            "dues_id_PK": dues.dues_id_PK,
            "member_id_PK": dues.member_id_FK.member_id_PK,
            "member_name": dues.member_id_FK.full_name,
            "member_employee_id": dues.member_id_FK.employee_id,
            "member_department": dues.member_id_FK.department or "",
            "member_position": dues.member_id_FK.position or "",
            "member_contact": dues.member_id_FK.contact_number or "",
            "month_covered": dues.month_covered,
            "amount": str(dues.amount),
            "payment_method": dues.payment_method,
            "payment_status": dues.payment_status,
            "payment_date": dues.payment_date.isoformat() if dues.payment_date else "",
            "receipt_number": dues.receipt_number or "",
            "treasurer_status": dues.treasurer_status,
            "auditor_status": dues.auditor_status,
            "president_status": dues.president_status,
            "treasurer_remarks": dues.treasurer_remarks or "",
            "auditor_remarks": dues.auditor_remarks or "",
            "president_remarks": dues.president_remarks or "",
            "recorded_by": dues.recorded_by_user_id_FK.full_name if dues.recorded_by_user_id_FK else "",
            "recorded_at": dues.payment_date.isoformat() if dues.payment_date else "",
            "supporting_proofs": supporting_proofs,
        }
    })


@require_POST
def treasurer_monthly_dues_salary_add(request: HttpRequest):
    """Legacy Salary Deduction add wrapper — delegates to unified view."""
    return treasurer_monthly_dues_add(request)


@require_GET
def treasurer_monthly_dues_salary_list(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    dues = (
        MonthlyDues.objects.select_related("member_id_FK", "recorded_by_user_id_FK")
        .filter(payment_method="Salary Deduction")
        .order_by("-dues_id_PK")
    )

    rows = []
    batches_map = {}
    for d in dues:
        rows.append(
            {
                "dues_id": d.dues_id_PK,
                "ref": d.remittance_reference or "",
                "member_id": d.member_id_FK.member_id_PK,
                "member_name": d.member_id_FK.full_name,
                "month": d.month_covered,
                "amount": str(d.amount),
                "remarks": d.deduction_batch_reference or "",
                "treasurer_status": d.treasurer_status,
                "payment_status": d.payment_status,
                "is_advance": bool(d.is_advance),
                "recorded_by": d.recorded_by_user_id_FK.full_name if d.recorded_by_user_id_FK else "Unknown",
            }
        )

        br = (d.deduction_batch_reference or "").strip()
        if not br:
            continue
        if br not in batches_map:
            batches_map[br] = {
                "batch_reference": br,
                "month": d.month_covered,
                "member_count": 0,
                "total_amount": 0.0,
                "members": [],
                "recorded_by": d.recorded_by_user_id_FK.full_name if d.recorded_by_user_id_FK else "Unknown",
            }
        batches_map[br]["member_count"] += 1
        batches_map[br]["total_amount"] += float(d.amount)
        batches_map[br]["members"].append({
            "dues_id": d.dues_id_PK,
            "member_id": d.member_id_FK.member_id_PK,
            "member_name": d.member_id_FK.full_name,
            "amount": str(d.amount),
        })

    return JsonResponse({
        "ok": True,
        "salary_dues": rows,
        "batches": list(batches_map.values()),
    })


@require_GET
def treasurer_monthly_dues_report_list(request: HttpRequest):
    """Complete monthly-dues dataset for Reports Management.

    The Member Contribution Report must see EVERY legitimate dues record —
    OTC queue, approved OTC, salary deductions, advances — not just the rows
    that are still waiting on the Treasurer. The report layer (not this API)
    decides which rows to show; here we expose the database as-is:
      - one row per MonthlyDues record, no status/method filtering
      - payment_status is the honest payment state (what the report should
        display); treasurer_status stays available for workflow context.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    dues = (
        MonthlyDues.objects.select_related("member_id_FK", "recorded_by_user_id_FK")
        .order_by("-dues_id_PK")
    )
    rows = []
    for d in dues:
        rows.append(
            {
                "dues_id": d.dues_id_PK,
                "ref": d.receipt_number or d.remittance_reference or "",
                "member_id": d.member_id_FK.member_id_PK,
                "member_name": d.member_id_FK.full_name,
                "month": d.month_covered,
                "amount": str(d.amount),
                "payment_method": d.payment_method,
                "payment_status": d.payment_status,
                "payment_date": str(d.payment_date) if d.payment_date else "",
                "is_advance": bool(d.is_advance),
                "treasurer_status": d.treasurer_status,
                "recorded_by": d.recorded_by_user_id_FK.full_name if d.recorded_by_user_id_FK else "Unknown",
            }
        )
    return JsonResponse({
        "ok": True,
        "dues": rows,
        "monthly_dues_amount": str(get_monthly_dues_amount()),
    })


@require_GET
def treasurer_monthly_dues_tracking(request):
    """Returns per-member per-month dues status for a given year."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    year = request.GET.get("year", "")
    if not year or not year.isdigit():
        return JsonResponse({"ok": False, "error": "year query parameter required."}, status=400)

    year_int = int(year)
    prefix = year + "-"
    
    logger.info(f"Loading dues tracking for year: {year_int}")
    
    # Get all active members
    members = Member.objects.exclude(membership_status__iexact="retired").order_by("full_name")
    logger.info(f"Found {members.count()} active members")
    
    # Get all monthly dues for the selected year
    dues = MonthlyDues.objects.filter(
        month_covered__startswith=prefix
    ).select_related("member_id_FK")
    logger.info(f"Found {dues.count()} dues records for year {year_int}")
    
    # Get membership fees for the selected year
    membership_fees = MembershipFee.objects.filter(
        payment_date__year=year_int
    ).select_related("member_id_FK")
    logger.info(f"Found {membership_fees.count()} membership fee records for year {year_int}")
    
    # Build tracking data
    tracking = {}
    member_info = {}
    
    for member in members:
        mid = member.member_id_PK
        member_info[mid] = {
            "member_id": mid,
            "member_name": member.full_name,
            "department": member.department or "",
            "position": member.position or "",
            "date_joined": member.date_joined.isoformat() if member.date_joined else "",
        }
        tracking[mid] = {}
        
        # Initialize all 12 months for the year
        for month in range(1, 13):
            month_key = f"{year}-{month:02d}"
            tracking[mid][month_key] = "unpaid"
    
    # Update with monthly dues status
    for d in dues:
        mid = d.member_id_FK.member_id_PK
        if mid not in tracking:
            continue
        month_key = d.month_covered
        if month_key not in tracking[mid]:
            continue
            
        # Match the Auditor heat map: a paid row wins over pending/other rows.
        # This matters when duplicate workflow rows exist for one member/month.
        if d.payment_status in ["Paid", "Full Payment"]:
            current_status = tracking[mid][month_key]
            if not d.is_advance or current_status not in ["paid", "advance"]:
                tracking[mid][month_key] = "advance" if d.is_advance else "paid"
            elif current_status == "advance" and not d.is_advance:
                tracking[mid][month_key] = "paid"
        elif d.payment_status == "Pending" and tracking[mid][month_key] == "unpaid":
            tracking[mid][month_key] = "pending"
    
    # Mark months where membership fee was paid
    membership_fee_months = {}
    for fee in membership_fees:
        mid = fee.member_id_FK.member_id_PK
        if mid not in membership_fee_months:
            membership_fee_months[mid] = []
        membership_fee_months[mid].append(fee.payment_date.strftime("%Y-%m"))
    
    from core_system.services.dues_status import dues_year_containers

    calendar = dues_year_containers()
    return JsonResponse({
        "ok": True,
        "year": year_int,
        "member_info": member_info,
        "tracking": tracking,
        "membership_fee_months": membership_fee_months,
        # Backend dues timeline so the grid knows what to display: the
        # latest charged month and the year containers behind it, instead
        # of deriving "current/past" from the machine date.
        "frontier": calendar["frontier"],
        "containers": calendar["containers"],
    })


@require_POST
def treasurer_approve_monthly_dues(request: HttpRequest):
    """Treasurer approves or rejects monthly dues payments, supporting single or batch approvals."""
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    action = data.get("action")
    remarks = data.get("remarks", "")

    if action not in ["approve", "reject"]:
        return JsonResponse({"ok": False, "error": "Missing required fields: action"}, status=400)

    raw_dues_ids = data.get("dues_ids") or data.get("dues_id")
    if isinstance(raw_dues_ids, list):
        dues_ids = [int(item) for item in raw_dues_ids if str(item).strip()]
    elif raw_dues_ids is not None:
        dues_ids = [int(raw_dues_ids)]
    else:
        dues_ids = []

    if not dues_ids:
        return JsonResponse({"ok": False, "error": "Missing required fields: dues_id or dues_ids"}, status=400)

    with transaction.atomic():
        officer_id = request.session.get("officer_id")
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
        processed = 0
        skipped = 0

        for dues_id in dues_ids:
            dues = MonthlyDues.objects.select_for_update().filter(dues_id_PK=dues_id).first()
            if dues is None:
                skipped += 1
                continue

            if action == "approve" and dues.treasurer_status not in ("Pending Treasurer Review", "Pending"):
                skipped += 1
                continue

            # Check for approved exemption before allowing OTC payment
            if action == "approve" and dues.payment_method == "OTC Payment":
                try:
                    from core_system.models import SalaryDeductionExemption
                    exemption = SalaryDeductionExemption.objects.filter(
                        member_id_FK=dues.member_id_FK,
                        month_covered=dues.month_covered,
                        status="Approved"
                    ).first()
                    
                    if exemption:
                        # Block the payment - member is exempted
                        return JsonResponse({
                            "ok": False,
                            "error": f"Member {dues.member_id_FK.full_name} has an approved exemption for {dues.month_covered}. No payment is required for this month.",
                            "exemption_id": exemption.exemption_id_PK
                        }, status=400)
                except Exception as e:
                    logger.warning("Failed to check exemption for dues %s: %s", dues_id, e)

            if action == "approve":
                dues.treasurer_status = "Treasurer Verified"
                dues.treasurer_id_FK = officer
                dues.treasurer_remarks = remarks
                dues.treasurer_approved_at = timezone.now()
                dues.auditor_status = "Pending Auditor Review"
                dues.save()

                tv = TransactionVerification.objects.filter(
                    table_name="monthly_dues",
                    record_id=dues_id,
                ).order_by("-verification_id").first()
                if tv:
                    tv.verification_status = "Pending Auditor Review"
                    tv.auditor_id_FK = None
                    tv.save()
                else:
                    TransactionVerification.objects.create(
                        table_name="monthly_dues",
                        record_id=dues_id,
                        target_category="payment",
                        verification_status="Pending Auditor Review",
                    )

                _record_audit_trail(
                    table="monthly_dues",
                    record_id=dues_id,
                    action="Treasurer Approved",
                    actor=officer,
                    new={"member": dues.member_id_FK, "month_covered": str(dues.month_covered), "amount": str(dues.amount)},
                    ip=request.META.get("REMOTE_ADDR"),
                    notes=remarks,
                )

                                # Isolate notifications from the approval transaction: a slow or
                # failing email/push for a single member must NOT roll back the
                # whole batch (which previously surfaced as a "network error" on
                # the client - I5).
                try:
                    notify_member(
                        dues.member_id_FK,
                        notification_type="Payment Approved",
                        message=f"Your monthly dues payment for {dues.month_covered} (₱{dues.amount}) has been approved by the Treasurer and forwarded to the Auditor.",
                        category="payment",
                        sender_name=officer.full_name if officer else "Treasurer",
                        sender_role="Treasurer",
                        receipt_number=dues.receipt_number or "",
                    )
                except Exception as _notify_err:
                    logger.warning(
                        "notify_member failed for dues %s: %s", dues_id, _notify_err
                    )
            else:
                set_treasurer_rejected(
                    "monthly_dues",
                    dues_id,
                    officer,
                    remarks,
                    request,
                    member=dues.member_id_FK,
                    is_rejected=False,
                    extra_updates={
                        "treasurer_id_FK": officer,
                        "treasurer_remarks": remarks,
                        "treasurer_approved_at": timezone.now(),
                    },
                    details=f"Your monthly dues payment for {dues.month_covered} was returned for revision.",
                )

            processed += 1

        return JsonResponse({
            "ok": True,
            "message": f"Monthly dues payments {'approved' if action == 'approve' else 'returned'} successfully.",
            "processed": processed,
            "skipped": skipped,
        })


@require_POST
def treasurer_salary_bulk_preview(request: HttpRequest):
    """Preview active members for bulk salary deduction processing."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    sal_month = (request.POST.get("sal_month") or "").strip()
    if not sal_month:
        return JsonResponse({"ok": False, "error": "sal_month is required."}, status=400)

    expected_amount = get_monthly_dues_amount()

    active_members = (
        Member.objects
        .exclude(membership_status__iexact="retired")
        .exclude(member_classification=Member.CLASSIFICATION_RETIRED)
        .order_by("full_name")
    )

    # Check for ANY monthly dues record for this month (already paid/recorded via any method)
    already_paid = set(
        MonthlyDues.objects.filter(
            month_covered=sal_month,
            member_id_FK__in=active_members.values_list("member_id_PK", flat=True),
        ).values_list("member_id_FK_id", flat=True)
    )

    # Also check for salary deduction exemptions for this month
    exempted = set(
        SalaryDeductionExemption.objects.filter(
            month_covered=sal_month,
            status__in=["Pending", "Approved"],
            member_id_FK__in=active_members.values_list("member_id_PK", flat=True),
        ).values_list("member_id_FK_id", flat=True)
    )

    members = []
    for m in active_members:
        already = m.member_id_PK in already_paid
        is_exempted = m.member_id_PK in exempted
        members.append({
            "member_id": m.member_id_PK,
            "member_name": m.full_name,
            "department": m.department or "",
            "status": m.membership_status,
            "already_exists": already,
            "is_exempted": is_exempted,
            "default_checked": not already and not is_exempted,
        })

    return JsonResponse({
        "ok": True,
        "month": sal_month,
        "expected_amount": float(expected_amount),
        "members": members,
        "total_active": active_members.count(),
        "already_processed": len(already_paid),
        "already_exempted": len(exempted),
        "next_batch_ref": _next_batch_ref(sal_month),
    })


def _next_batch_ref(month_str):
    """Generate the next batch reference: ISUCauFA-{YY}-{N}."""
    yy = month_str.split("-")[0][-2:]
    prefix = f"ISUCauFA-{yy}-"
    existing = MonthlyDues.objects.filter(
        remittance_reference__startswith=prefix,
    ).values_list("remittance_reference", flat=True)
    max_n = 0
    for ref in existing:
        try:
            n = int(ref[len(prefix):])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_n + 1}"


@require_GET
def treasurer_next_batch_ref(request: HttpRequest):
    """Return the next auto-generated batch ref for a given month."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    month = (request.GET.get("month") or "").strip()
    if not month:
        return JsonResponse({"ok": False, "error": "month is required."}, status=400)

    return JsonResponse({
        "ok": True,
        "next_batch_ref": _next_batch_ref(month),
    })


@require_GET
def treasurer_member_unpaid_months(request: HttpRequest, member_id: int):
    """Return unpaid months for a specific member (for dropdown filtering in treasurer forms)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        member = Member.objects.get(member_id_PK=member_id)
    except (Member.DoesNotExist, ValueError):
        return JsonResponse({"ok": False, "error": "Member not found."}, status=404)

    # Get member's join date
    join_date = member.date_joined
    if not join_date:
        join_date = timezone.now().date() - timedelta(days=365)

    current_date = timezone.now().date()

    # Get all paid/covered months
    covered_months = set(
        MonthlyDues.objects.filter(
            member_id_FK=member,
        ).values_list("month_covered", flat=True)
    )

    # Months covered by salary-deduction exemption
    exempted_months = set(
        SalaryDeductionExemption.objects.filter(
            member_id_FK=member,
            status__in=["Pending", "Approved"],
        ).values_list("month_covered", flat=True)
    )

    # Calculate unpaid months
    from core_system.services.dues_status import dues_year_containers

    # Backend year container: months run through the latest charged dues
    # month (e.g. April 2027 once everyone paid it) — never the machine
    # date — and never start inside a closed container (the 2026 batch
    # ended after December 2026; the current batch starts January 2027).
    unpaid_months = []
    calendar = dues_year_containers()
    frontier = calendar["frontier"]
    if frontier:
        current_year, current_month = int(frontier[:4]), int(frontier[5:7])
    else:
        current_year = current_date.year
        current_month = current_date.month

    # Obligation starts January of the join year through the dues frontier,
    # inclusive of the join month itself. This mirrors the catch-up policy
    # (_catchup_month_starts: Jan..join-month inclusive) so a member who
    # joined in September sees Jan-Aug as selectable back dues plus
    # September as the current month, instead of starting at October and
    # hiding everything owed. January joiners likewise owe January itself.
    start_year = join_date.year
    start_month = 1
    if frontier:
        start_key = max(
            f"{start_year}-{start_month:02d}", frontier[:4] + "-01"
        )
        start_year, start_month = int(start_key[:4]), int(start_key[5:7])

    year = start_year
    month = start_month

    current_key = f"{current_year}-{current_month:02d}"
    while (year < current_year) or (year == current_year and month <= current_month):
        month_str = f"{year}-{month:02d}"

        if month_str not in covered_months and month_str not in exempted_months:
            from datetime import datetime as dt
            month_name = dt(year, month, 1).strftime("%B %Y")
            unpaid_months.append({
                "value": month_str,
                "label": month_name,
                "is_overdue": month_str < current_key,
                "is_current": month_str == current_key,
                # Back dues = any owed month before the current one. The
                # frontend uses this to show e.g. "8 back dues (Jan-Aug) +
                # Sep current = 900" and to allow all/selected payment.
                "is_backfill": month_str < current_key,
            })

        month += 1
        if month > 12:
            month = 1
            year += 1

    # Include advance payment months (next 5 years for continuous payments),
    # counted from the dues frontier (months past what was charged yet).
    for i in range(1, 61):  # Next 60 months (5 years)
        adv_year = current_year
        adv_month = current_month + i
        if adv_month > 12:
            adv_year += (adv_month - 1) // 12
            adv_month = ((adv_month - 1) % 12) + 1
        advance_month_str = f"{adv_year}-{adv_month:02d}"

        if advance_month_str not in covered_months and advance_month_str not in exempted_months:
            from datetime import datetime as dt
            advance_month_name = dt(adv_year, adv_month, 1).strftime("%B %Y")
            unpaid_months.append({
                "value": advance_month_str,
                "label": advance_month_name,
                "is_overdue": False,
                "is_advance": True,
            })

    return JsonResponse({
        "ok": True,
        "member_id": member.member_id_PK,
        "member_name": member.full_name,
        "unpaid_months": unpaid_months,
    })


@require_GET
def treasurer_exemption_requests_list(request):
    """Return salary deduction exemption requests for Treasurer review."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        exemptions = (
            SalaryDeductionExemption.objects
            .select_related("member_id_FK")
            .all()
            .order_by("-requested_at")
        )
        logger.info(f"Found {exemptions.count()} exemption requests")
    except Exception as e:
        logger.error("Error loading exemption requests: %s", e)
        return JsonResponse({"ok": True, "exemptions": []})

    rows = []
    for exemption in exemptions:
        member = exemption.member_id_FK
        rows.append({
            "exemption_id": exemption.exemption_id_PK,
            "member_id": member.member_id_PK,
            "member_name": member.full_name,
            "department": member.department or "",
            "month_covered": exemption.month_covered,
            "reason": exemption.reason or "",
            "status": exemption.status,
            "requested_by_member": exemption.requested_by_member,
            "created_at": exemption.requested_at.isoformat() if exemption.requested_at else "",
            "reviewed_at": exemption.reviewed_at.isoformat() if exemption.reviewed_at else "",
        })

    logger.info(f"Returning {len(rows)} exemption requests")
    return JsonResponse({"ok": True, "exemptions": rows})


@require_POST
def treasurer_exemption_action(request: HttpRequest, exemption_id: int):
    """Treasurer reviews exemption request."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        officer = resolve_officer_from_session(request)
        if officer is None:
            return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

        exemption = get_object_or_404(SalaryDeductionExemption, exemption_id_PK=exemption_id)
        action = (request.POST.get("action") or "").strip().lower()
        reason = (request.POST.get("reason") or "").strip()

        if action not in {"approve", "reject"}:
            return JsonResponse({"ok": False, "error": "Invalid action. Use 'approve' or 'reject'."}, status=400)

        if exemption.status != "Pending Treasurer Review":
            return JsonResponse({"ok": False, "error": f"Exemption is already {exemption.status}."}, status=400)

        if action == "reject":
            exemption.status = "Rejected"
            exemption.reviewed_by_user_id_FK = officer
            exemption.reviewed_at = timezone.now()
            exemption.review_remarks = reason if reason else None
            exemption.save()
            
            # Create notification for member
            try:
                notify_member(
                    exemption.member_id_FK,
                    notification_type="exemption_response",
                    message=f"Your salary deduction exemption request for {exemption.month_covered} has been rejected by the Treasurer.",
                    category="dues",
                    sender_name=officer.full_name if officer else "Treasurer",
                    sender_role="Treasurer",
                    extra_context={
                        "subject": "Salary Deduction Exemption Request Rejected",
                        "remarks": reason or "",
                    },
                )
            except Exception:
                pass

            return JsonResponse({
                "ok": True,
                "status": exemption.status,
                "message": f"Exemption request rejected successfully."
            })
        else:
            # Approve the exemption
            exemption.status = "Approved"
            exemption.reviewed_by_user_id_FK = officer
            exemption.reviewed_at = timezone.now()
            exemption.review_remarks = reason if reason else None
            exemption.save()
            
            # Create notification for member
            try:
                notify_member(
                    exemption.member_id_FK,
                    notification_type="exemption_response",
                    message=f"Your salary deduction exemption request for {exemption.month_covered} has been approved by the Treasurer.",
                    category="dues",
                    sender_name=officer.full_name if officer else "Treasurer",
                    sender_role="Treasurer",
                    extra_context={
                        "subject": "Salary Deduction Exemption Request Approved",
                        "remarks": reason or "",
                    },
                )
            except Exception:
                pass

            return JsonResponse({
                "ok": True,
                "status": exemption.status,
                "message": f"Exemption request approved successfully."
            })
    except Exception as e:
        logger.error(f"Error in treasurer_exemption_action: {e}")
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_exemption_override(request: HttpRequest, exemption_id: int):
    """Treasurer overrides an approved exemption with audit trail."""
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    exemption = get_object_or_404(SalaryDeductionExemption, exemption_id_PK=exemption_id)
    override_reason = (request.POST.get("override_reason") or "").strip()

    if exemption.status != "Approved":
        return JsonResponse({"ok": False, "error": "Can only override approved exemptions."}, status=400)

    if not override_reason:
        return JsonResponse({"ok": False, "error": "Override reason is required."}, status=400)

    # Record the override
    exemption.override_reason = override_reason
    exemption.override_by = officer
    exemption.override_at = timezone.now()
    exemption.save()

    # Create audit trail entry
    try:
        GlobalAuditTrail.objects.create(
            table_name="SalaryDeductionExemption",
            record_id=exemption.exemption_id_PK,
            action="EXEMPTION_OVERRIDE",
            actor=officer,
            new={
                "exemption_id": exemption.exemption_id_PK,
                "member": exemption.member_id_FK.full_name,
                "month_covered": exemption.month_covered,
                "override_reason": override_reason,
                "overridden_by": officer.full_name,
            },
            ip=request.META.get("REMOTE_ADDR") if request else None,
            notes=f"Treasurer overrode approved exemption for {exemption.month_covered}",
        )
    except Exception:
        pass

    return JsonResponse({
        "ok": True,
        "message": "Exemption override recorded with audit trail."
    })


@require_GET
def treasurer_member_deductions(request: HttpRequest, member_id: int):
    """Return deduction history for a specific member for Treasurer dashboard."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        member = Member.objects.get(member_id_PK=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Member not found."}, status=404)

    deductions = PayrollDeduction.objects.filter(
        member_id_FK=member,
        batch_id_FK__status="Approved",
    ).select_related("batch_id_FK", "aid_tracking_post_id_FK").order_by("-batch_id_FK__created_at")

    items = []
    for d in deductions:
        batch = d.batch_id_FK
        aid_ref = ""
        if d.aid_tracking_post_id_FK:
            post = d.aid_tracking_post_id_FK
            aid_ref = f"{post.aid_type}#{post.source_id}" if post.source_id else post.aid_type
        items.append({
            "date": batch.president_approved_at.isoformat() if batch.president_approved_at else "",
            "payroll_period": batch.payroll_period,
            "category": d.category,
            "amount": float(d.amount),
            "fund_impact": d.fund_impact,
            "aid_reference": aid_ref,
            "month_covered": d.month_covered or "",
            "batch_id": batch.batch_id_PK,
            "description": _build_member_deduction_desc(d, batch),
        })

    total_deducted = sum(i["amount"] for i in items)

    return JsonResponse({
        "ok": True,
        "member_id": member.member_id_PK,
        "member_name": member.full_name,
        "deductions": items,
        "total_deducted": total_deducted,
        "count": len(items),
    })


def _build_member_deduction_desc(deduction: PayrollDeduction, batch: PayrollBatch) -> str:
    label = dict(PayrollDeduction.CATEGORY_CHOICES).get(deduction.category, deduction.category)
    period = f" ({deduction.month_covered})" if deduction.month_covered else ""
    return f"{label}{period} — {batch.payroll_period}"


@require_POST
def treasurer_salary_bulk_process(request: HttpRequest):
    """Create salary deduction records for multiple members in one batch."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Officer session missing."}, status=401)

    sal_month = (request.POST.get("sal_month") or "").strip()
    summary = (request.POST.get("summary") or "").strip()
    member_ids_raw = (request.POST.get("member_ids") or "").strip()
    uploaded = request.FILES.get("sal_photo_file")

    if not sal_month:
        return JsonResponse({"ok": False, "error": "sal_month is required."}, status=400)
    if not member_ids_raw:
        return JsonResponse({"ok": False, "error": "member_ids is required."}, status=400)

    try:
        member_ids = json.loads(member_ids_raw)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"ok": False, "error": "member_ids must be a JSON array."}, status=400)

    if not isinstance(member_ids, list) or not member_ids:
        return JsonResponse({"ok": False, "error": "member_ids must be a non-empty array."}, status=400)

    expected_amount = get_monthly_dues_amount()

    try:
        payment_date = datetime.strptime(sal_month + "-01", "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"ok": False, "error": "Invalid month format."}, status=400)

    # Auto-generate batch reference
    batch_ref = _next_batch_ref(sal_month)

    # Deduplicate member_ids
    unique_ids = list(set(member_ids))

    # Fetch members in bulk
    members_map = {
        m.member_id_PK: m
        for m in Member.objects.filter(member_id_PK__in=unique_ids)
    }

    processed = 0
    skipped = 0
    created_dues = []

    with transaction.atomic():
        # Per-member duplicate protection: skip members that already have a
        # monthly dues record for this month instead of blocking the whole
        # batch. The UI already filters out "already paid" members; this keeps
        # the API consistent even if stale selections are submitted.
        already_covered = set(
            MonthlyDues.objects.select_for_update().filter(
                member_id_FK__in=unique_ids,
                month_covered=sal_month,
            ).values_list("member_id_FK", flat=True)
        )

        for mid in unique_ids:
            member = members_map.get(mid)
            if not member:
                skipped += 1
                continue
            if str(member.membership_status).strip().casefold() == "retired" or (
                str(member.member_classification).strip().casefold()
                == "retired"
            ):
                skipped += 1
                continue
            if member.member_id_PK in already_covered:
                skipped += 1
                continue

            # Advance-payment consistency (matches the single-entry salary
            # branch): future covered months are flagged is_advance and the
            # payment_date records when the deduction was RECORDED, not the
            # future month itself. month_covered stays the contribution period.
            is_advance = sal_month > timezone.now().strftime("%Y-%m")
            dues = MonthlyDues.objects.create(
                member_id_FK=member,
                month_covered=sal_month,
                amount=str(expected_amount),
                payment_method="Salary Deduction",
                payment_status="Pending",
                payment_date=timezone.now().date() if is_advance else payment_date,
                deduction_batch_reference=summary,
                remittance_reference=batch_ref,
                recorded_by_user_id_FK=officer,
                is_advance=is_advance,
            )
            TransactionVerification.objects.create(
                table_name="monthly_dues",
                record_id=dues.dues_id_PK,
                verification_status="Pending Auditor Review",
            )
            if uploaded and getattr(uploaded, "size", 0) > 0:
                _link_proof_to_record(uploaded, dues, officer)

            # NOTE: MemberLedger is intentionally NOT written here. Monthly dues
            # reach the ledger once — at President approval — so MemberLedger and
            # FundTransaction always describe the same approved financial event.

            _record_audit_trail(
                table="monthly_dues",
                record_id=dues.dues_id_PK,
                action="CREATED",
                actor=officer,
                new={
                    "member": getattr(member, "full_name", str(mid)),
                    "month_covered": sal_month,
                    "amount": str(expected_amount),
                    "payment_method": "Salary Deduction",
                    "batch_ref": batch_ref,
                },
                ip=request.META.get("REMOTE_ADDR"),
            )
            processed += 1
            created_dues.append(dues.dues_id_PK)

    _broadcast_pending_counts()
    return JsonResponse({
        "ok": True,
        "processed": processed,
        "skipped": skipped,
        "batch_ref": batch_ref,
        "month": sal_month,
    })


@require_GET
def treasurer_releases_list(request: HttpRequest):
    """Return released transactions from the archive."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    qs = TransactionArchive.objects.filter(
        status="Released",
        transaction_type__in=["medical_aid", "death_aid"],
    ).select_related(
        "released_by_user_id_FK",
    ).order_by("-archive_id_PK")

    releases = []
    for entry in qs:
        released_by = (
            getattr(entry.released_by_user_id_FK, "full_name", "") or ""
        )
        aid_type = "Medical Aid" if entry.transaction_type == "medical_aid" else "Death Aid"
        ft = FundTransaction.objects.filter(
            Q(source_type=entry.transaction_type, source_id=entry.record_id)
            | Q(source_type="aid_post_payment", source_id=entry.archive_id_PK),
            direction="outflow",
        ).order_by("-recorded_at").first()
        releases.append(
            {
                "id": f"REL-{entry.archive_id_PK}",
                "aidId": f"{'MED' if entry.transaction_type == 'medical_aid' else 'DTH'}-{entry.record_id}",
                "type": aid_type,
                "payee": entry.member_name,
                "amount": float(entry.amount or 0),
                "releaseDate": entry.release_reference or "",
                "releasedBy": released_by,
                "released_at": ft.recorded_at.isoformat() if ft else "",
                "reqId": f"{'MED' if entry.transaction_type == 'medical_aid' else 'DTH'}-{entry.record_id}",
            }
        )

    return JsonResponse({"ok": True, "releases": releases})


@require_POST
def treasurer_release_aid(request: HttpRequest):
    """Deprecated parallel release endpoint for MedicalAid / DeathAid.

    Kept only so a stray caller gets a clear answer instead of silently
    flipping a claim to "Released". It moved no fund money and skipped every
    control the real release path enforces (set-aside draw-down, benefit
    ceiling, fund balance, verification code, named recipient, audit trail),
    so it is retired. Releasing aid now happens through
    ``/api/treasurer/aid-post-release/``.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    return JsonResponse(
        {
            "ok": False,
            "error": "This release route has been retired. Release aid from the "
            "Release Queue (POST /api/treasurer/aid-post-release/) so the claim is "
            "verified, capped at its approved benefit amount and logged on the "
            "audit trails.",
            "redirect_to": "/api/treasurer/aid-post-release/",
        },
        status=410,
    )


@require_POST
def treasurer_medical_aid_add(request: HttpRequest):
    """Create a MedicalAid entry from the Treasurer medical aid form."""

    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # Extract fields
    med_member = (request.POST.get("med_member") or "").strip()
    med_date = (request.POST.get("med_date") or "").strip()
    med_req_amount = (request.POST.get("med_req_amount") or "").strip()
    med_hospital = (request.POST.get("med_hospital") or "").strip()
    med_hospital_date = (request.POST.get("med_hospital_date") or "").strip()
    med_bill = (request.POST.get("med_bill") or "").strip()
    med_validation = (request.POST.get("med_validation") or "").strip()
    med_reason = (request.POST.get("med_reason") or "").strip()
    med_source = (request.POST.get("med_source") or "").strip()

    # Parse hospital_date to extract admission and discharge dates
    admission_date = None
    discharge_date = None
    if med_hospital_date:
        # hospital_date format is expected to be "YYYY-MM-DD to YYYY-MM-DD" or similar
        date_parts = med_hospital_date.split(" to ")
        if len(date_parts) >= 1 and date_parts[0].strip():
            try:
                admission_date = date_parts[0].strip()
            except:
                pass
        if len(date_parts) >= 2 and date_parts[1].strip():
            try:
                discharge_date = date_parts[1].strip()
            except:
                pass

    if not med_member:
        return JsonResponse({"ok": False, "error": "Beneficiary Member ID is required."}, status=400)
    if not med_date:
        return JsonResponse({"ok": False, "error": "Request Date is required."}, status=400)
    if not med_req_amount:
        med_req_amount = "0"

    # Resolve member
    member_obj, err = resolve_member_from_input(med_member)
    if err:
        return err

    if is_retired_member(member_obj):
        return JsonResponse(
            {"ok": False, "error": "Retired members are exempt from dues and contributions, so medical aid claims cannot be filed for them."},
            status=400,
        )

    # Once-per-year constraint per ARTICLE XI Section 1.b
    try:
        req_year = int(med_date[:4])
    except (ValueError, IndexError):
        req_year = timezone.now().year
    err_msg = check_medical_aid_once_per_year(member_obj, req_year)
    if err_msg:
        return JsonResponse({"ok": False, "error": err_msg}, status=400)

    from core_system.services.membership_fee_rules import (
        is_member_in_good_standing,
    )

    if not is_member_in_good_standing(member_obj):
        return JsonResponse(
            {"ok": False, "error": "Member is not in good standing per ARTICLE XI Section 4."},
            status=400,
        )

    try:
        bill_value = float(med_bill) if med_bill else 0.0
    except ValueError:
        return JsonResponse(
            {"ok": False, "error": "Hospital bill must be a valid number."}, status=400
        )

    if bill_value < get_accidental_sickness_aid_threshold():
        return JsonResponse(
            {
                "ok": False,
                "error": f"Hospital bill must be at least ₱{get_accidental_sickness_aid_threshold():,.2f} to qualify for accidental/sickness aid per By-Laws ARTICLE XI Section 1.b. Submitted: ₱{bill_value:,.2f}",
            },
            status=400,
        )

    # File uploads: request letter + hospital bill(s) are required documents
    # (aid requirements); med_photo_files remain optional "other" documents.
    recorded_by = resolve_officer_from_session(request)
    request_letters = [
        f for f in request.FILES.getlist("med_request_letter")
        if f and getattr(f, "size", 0) > 0
    ]
    hospital_bills = [
        f for f in request.FILES.getlist("med_hospital_bill")
        if f and getattr(f, "size", 0) > 0
    ]
    uploaded_files = [
        f for f in request.FILES.getlist("med_photo_files")
        if f and getattr(f, "size", 0) > 0
    ]

    if not request_letters:
        return JsonResponse(
            {
                "ok": False,
                "error": "Missing required document: Request Letter (addressed to the CAUFA President).",
            },
            status=400,
        )
    if not hospital_bills:
        return JsonResponse(
            {
                "ok": False,
                "error": "Missing required document: Hospital Bill.",
            },
            status=400,
        )

    try:
        with transaction.atomic():
            aid = MedicalAid.objects.create(
                member_id_FK=member_obj,
                request_date=med_date,
                requested_amount=med_req_amount,
                hospital_name=med_hospital,
                hospital_date=med_hospital_date or None,
                admission_date=admission_date,
                discharge_date=discharge_date,
                hospital_bill_amount=med_bill,
                claim_year=req_year,
                document_status="Pending",
                reason_for_request=med_reason or None,
                policy_record_status="Pending",
                validated_aid_amount=get_accidental_sickness_aid_benefit(),
                status="Treasurer Direct",  # Special status for treasurer-created claims - goes directly to Auditor
                disbursement_source=med_source if med_source in ("fund", "direct") else None,
                treasurer_validated_by_user_id_FK=recorded_by,
            )

            TransactionVerification.objects.create(
                table_name="medical_aid",
                record_id=aid.medical_aid_id_PK,
                verification_status="Pending Auditor Review",
            )

            for f in request_letters:
                _link_proof_to_record(f, aid, recorded_by, document_type="request_letter")
            for f in hospital_bills:
                _link_proof_to_record(f, aid, recorded_by, document_type="hospital_bill")
            for f in uploaded_files:
                _link_proof_to_record(f, aid, recorded_by, document_type="other")

            _record_audit_trail(
                table="medical_aid",
                record_id=aid.medical_aid_id_PK,
                action="CREATED",
                actor=recorded_by,
                new={
                    "member": member_obj,
                    "request_date": med_date,
                    "requested_amount": med_req_amount,
                    "hospital_name": med_hospital,
                    "hospital_date": med_hospital_date,
                    "hospital_bill_amount": med_bill,
                    "status": "Treasurer Direct",
                    "document_status": med_reason or "Pending",
                },
                ip=request.META.get("REMOTE_ADDR"),
            )
    except ValueError as exc:
        # Blocked proof upload (duplicate content, disallowed type, oversize):
        # the atomic block already rolled back the claim, so answer with the
        # specific reason + log the attempt instead of a generic 500.
        return proof_upload_blocked_response(
            request, exc,
            table="medical_aid", record_id=0,
            actor=recorded_by, member=member_obj,
            filename=getattr(exc, "filename", "") or "",
        )

    _broadcast_treasurer("aids")

    # Stage email: claim filed by Treasurer — member is notified before Auditor verification.
    try:
        notify_member(
            member_obj,
            notification_type="Claim Submitted",
            message="Your Medical Aid claim has been filed by the Treasurer and is now pending Auditor verification.",
            category="claim",
            sender_name=recorded_by.full_name if recorded_by else "Treasurer",
            sender_role="Treasurer",
            send_email=True,
        )
    except Exception:
        logger.warning("Treasurer medical aid filing notification failed for member %s", member_obj.member_id_PK)

    return JsonResponse({"ok": True, "aid_id": aid.medical_aid_id_PK})


@require_POST
@transaction.atomic
def treasurer_medical_aid_batch_add(request: HttpRequest):
    """Create MedicalAid entries for multiple members in one transaction."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    from core_system.services.membership_fee_rules import is_member_in_good_standing

    try:
        batch_data = json.loads(request.POST.get("med_batch_data", "[]"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid batch data."}, status=400)

    if not isinstance(batch_data, list) or len(batch_data) == 0:
        return JsonResponse({"ok": False, "error": "No members in batch."}, status=400)

    if len(batch_data) > 5:
        return JsonResponse({"ok": False, "error": "Maximum 5 members per batch."}, status=400)

    recorded_by = resolve_officer_from_session(request)
    created_ids = []
    created_members = []

    for idx, entry in enumerate(batch_data):
        member_id = (entry.get("member_id") or "").strip()
        request_date = (entry.get("request_date") or "").strip()
        reason = (entry.get("reason") or "").strip()
        hospital = (entry.get("hospital") or "").strip()
        hospital_date = (entry.get("hospital_date") or "").strip()
        bill_str = (entry.get("bill") or "").strip()

        # Parse hospital_date to extract admission and discharge dates
        admission_date = None
        discharge_date = None
        if hospital_date:
            date_parts = hospital_date.split(" to ")
            if len(date_parts) >= 1 and date_parts[0].strip():
                try:
                    admission_date = date_parts[0].strip()
                except:
                    pass
            if len(date_parts) >= 2 and date_parts[1].strip():
                try:
                    discharge_date = date_parts[1].strip()
                except:
                    pass

        if not member_id or not request_date or not reason or not bill_str:
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1}: Member, Date, Reason, and Bill are required."
            }, status=400)

        # Resolve member
        member_obj, err = resolve_member_from_input(member_id)
        if err:
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1} ({member_id}): Could not resolve member."
            }, status=400)

        if is_retired_member(member_obj):
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1} ({member_obj.full_name}): Retired members cannot file medical aid claims."
            }, status=400)

        # Once-per-year constraint
        try:
            req_year = int(request_date[:4])
        except (ValueError, IndexError):
            req_year = timezone.now().year
        err_msg = check_medical_aid_once_per_year(member_obj, req_year)
        if err_msg:
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1} ({member_obj.full_name}): {err_msg}"
            }, status=400)

        # Good standing check
        if not is_member_in_good_standing(member_obj):
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1} ({member_obj.full_name}): Member is not in good standing."
            }, status=400)

        # Bill threshold check
        try:
            bill_value = float(bill_str)
        except ValueError:
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1}: Bill must be a valid number."
            }, status=400)

        threshold = get_accidental_sickness_aid_threshold()
        if bill_value < threshold:
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1} ({member_obj.full_name}): Bill must be at least ₱{threshold:,.2f} to qualify."
            }, status=400)

        # Required documents per the aid requirements: request letter (addressed
        # to the CAUFA President) + at least one hospital bill.
        request_letters = [
            f for f in request.FILES.getlist(f"med_request_letter_{idx}")
            if f and getattr(f, "size", 0) > 0
        ]
        hospital_bills = [
            f for f in request.FILES.getlist(f"med_hospital_bill_{idx}")
            if f and getattr(f, "size", 0) > 0
        ]
        if not request_letters:
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1} ({member_obj.full_name}): Missing required document: Request Letter (addressed to the CAUFA President)."
            }, status=400)
        if not hospital_bills:
            return JsonResponse({
                "ok": False,
                "error": f"Card {idx + 1} ({member_obj.full_name}): Missing required document: Hospital Bill."
            }, status=400)

        # Create MedicalAid record
        aid = MedicalAid.objects.create(
            member_id_FK=member_obj,
            request_date=request_date,
            requested_amount=str(get_accidental_sickness_aid_benefit()),
            hospital_name=hospital,
            hospital_date=hospital_date or None,
            admission_date=admission_date,
            discharge_date=discharge_date,
            hospital_bill_amount=bill_str,
            claim_year=req_year,
            document_status="Pending",
            reason_for_request=reason or None,
            policy_record_status="Pending",
            validated_aid_amount=get_accidental_sickness_aid_benefit(),
            status="Treasurer Direct",  # Special status for treasurer-created claims - goes directly to Auditor
            treasurer_validated_by_user_id_FK=recorded_by,
        )

        TransactionVerification.objects.create(
            table_name="medical_aid",
            record_id=aid.medical_aid_id_PK,
            verification_status="Pending Auditor Review",
        )

        # Attach typed documents (request letter + bills required, others optional)
        for f in request_letters:
            _link_proof_to_record(f, aid, recorded_by, document_type="request_letter")
        for f in hospital_bills:
            _link_proof_to_record(f, aid, recorded_by, document_type="hospital_bill")
        fi = 0
        while True:
            key = f"med_file_{idx}_{fi}"
            f = request.FILES.get(key)
            if not f or getattr(f, "size", 0) <= 0:
                break
            _link_proof_to_record(f, aid, recorded_by, document_type="other")
            fi += 1

        _record_audit_trail(
            table="medical_aid",
            record_id=aid.medical_aid_id_PK,
            action="CREATED",
            actor=recorded_by,
            new={
                "member": member_obj.full_name,
                "request_date": request_date,
                "requested_amount": str(get_accidental_sickness_aid_benefit()),
                "hospital_name": hospital,
                "hospital_date": hospital_date,
                "hospital_bill_amount": bill_str,
                "status": "Treasurer Direct",
                "document_status": reason,
            },
            ip=request.META.get("REMOTE_ADDR"),
        )

        created_ids.append(aid.medical_aid_id_PK)
        created_members.append(member_obj)

    _broadcast_treasurer("aids")

    # Stage email: each batch claim filed by Treasurer — member is notified before Auditor verification.
    for member_obj in created_members:
        try:
            notify_member(
                member_obj,
                notification_type="Claim Submitted",
                message="Your Medical Aid claim has been filed by the Treasurer and is now pending Auditor verification.",
                category="claim",
                sender_name=recorded_by.full_name if recorded_by else "Treasurer",
                sender_role="Treasurer",
                send_email=True,
            )
        except Exception:
            logger.warning("Treasurer batch medical aid notification failed for member %s", member_obj.member_id_PK)

    return JsonResponse({"ok": True, "aid_ids": created_ids, "count": len(created_ids)})


@require_GET
def treasurer_medical_aid_list(request: HttpRequest):
    """Return MedicalAid records for the Treasurer dashboard."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # MedicalAid model has no recorded_by_user_id_FK field.
    aids = (
        MedicalAid.objects.select_related("member_id_FK")
        .order_by("-medical_aid_id_PK")
    )

    rows = []
    for aid in aids:
        # UI expects the legacy key names used by AidsAndClaims.js:
        # - id (like MED-501)
        # - name, reason, hospital, bill, reqAmount, status, validation
        requested_amount = aid.requested_amount if aid.requested_amount is not None else aid.hospital_bill_amount

        rows.append(
            {
                # API keys used by static/js/Treasurer/AidsAndClaims.js
                "id": f"MED-{aid.medical_aid_id_PK}",
                "memberId": aid.member_id_FK.member_id_PK,
                "name": aid.member_id_FK.full_name,
                "date": aid.request_date.isoformat() if aid.request_date else "",
                # Your UI label uses `reason` for case description.
                "reason": aid.status or "Medical Aid Request",
                "reqAmount": float(requested_amount) if requested_amount is not None else 0,
                "hospital": aid.hospital_name or aid.member_id_FK.full_name,
                "hospital_date": str(aid.hospital_date) if aid.hospital_date else "",
                "bill": float(aid.hospital_bill_amount) if aid.hospital_bill_amount is not None else 0,
                "validation": aid.status or "Pending",
                "status": aid.status or "Pending",

                # Extra keys (kept for consistency with other callers/debugging)
                "aid_id": aid.medical_aid_id_PK,
                "member_id": aid.member_id_FK.member_id_PK,
                "member_name": aid.member_id_FK.full_name,
                "request_date": str(aid.request_date) if aid.request_date else "",
                "requested_amount": str(aid.requested_amount) if aid.requested_amount is not None else "",
                "hospital_bill_amount": str(aid.hospital_bill_amount)
                if getattr(aid, "hospital_bill_amount", None) is not None
                else "",
                "claim_year": aid.claim_year,
                "document_status": aid.document_status,
                "policy_record_status": aid.policy_record_status,
                "validated_aid_amount": str(aid.validated_aid_amount)
                if getattr(aid, "validated_aid_amount", None) is not None
                else "",
                "encoded_by": "",
            }
        )
    record_ids = [aid.medical_aid_id_PK for aid in aids]
    _log_sensitive_read(request, "medical_aid", record_ids, "Treasurer viewed medical aid list")

    return JsonResponse({"ok": True, "medical_aids": rows})


# --- Death Aid (Claims) APIs (Treasurer) ---
@require_POST
def treasurer_death_aid_add(request: HttpRequest):
    """Create a DEATH_AID row from the Treasurer death aid claim form."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    death_member = (request.POST.get("death_member") or "").strip()
    death_deceased = (request.POST.get("death_deceased") or "").strip()
    death_rel = (request.POST.get("death_rel") or "").strip()
    death_type = (request.POST.get("death_type") or "").strip()
    death_scenario = (request.POST.get("death_scenario") or "").strip()
    death_claimant = (request.POST.get("death_claimant") or "").strip()
    death_contact = (request.POST.get("death_contact") or "").strip() or None
    death_bill = (request.POST.get("death_bill") or "").strip()
    death_date = (request.POST.get("death_date") or "").strip()
    death_funeral_location = (request.POST.get("death_funeral_location") or "").strip()
    death_interment_date = (request.POST.get("death_interment_date") or "").strip() or None
    death_source = (request.POST.get("death_source") or "").strip()

    death_contact, contact_error = _validate_ph_contact(death_contact)
    if contact_error:
        return JsonResponse({"ok": False, "error": contact_error}, status=400)

    if not death_member:
        return JsonResponse(
            {"ok": False, "error": "Associated Member ID is required."}, status=400
        )
    if not death_deceased:
        return JsonResponse(
            {"ok": False, "error": "Deceased person name is required."}, status=400
        )
    if not death_rel:
        return JsonResponse(
            {"ok": False, "error": "Relationship to member is required."}, status=400
        )
    death_rel_group = (request.POST.get("death_rel_group") or "").strip()
    if not death_rel_group:
        from core_system.constants.policy_constants import DEATH_AID_RELATIONSHIP_MAP
        death_rel_group = "immediate" if death_rel.lower() in [k.lower() for k in DEATH_AID_RELATIONSHIP_MAP] else "extended"
    if not death_date:
        return JsonResponse(
            {"ok": False, "error": "Date of death is required."}, status=400
        )

    try:
        death_date_obj = datetime.strptime(death_date, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse(
            {"ok": False, "error": "Invalid date of death format."}, status=400
        )
    if death_date_obj > timezone.now().date():
        return JsonResponse(
            {"ok": False, "error": "The date of death cannot be a future date."}, status=400
        )
    if death_interment_date:
        try:
            interment_obj = datetime.strptime(death_interment_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse(
                {"ok": False, "error": "Invalid interment date format."}, status=400
            )
        # Allow any date for interment (past, present, or future)
        # No validation needed for interment date

    member_obj, err = resolve_member_from_input(death_member)
    if err:
        return err

    # Claimant is automatically the member filing the claim for dependent death aid
    # categories (full blood sibling, parent, spouse/husband, child, etc.).
    if not death_claimant:
        if death_scenario != "dependent":
            return JsonResponse(
                {"ok": False, "error": "Claimant name is required."}, status=400
            )
        death_claimant = member_obj.full_name

    from core_system.services.membership_fee_rules import is_member_in_good_standing

    # Management policy: retired members are exempt from paying dues and
    # contributions per ARTICLE XI Section 2, and they must not file new
    # medical/death aid claims either.

    if is_retired_member(member_obj):
        return JsonResponse(
            {"ok": False, "error": "Retired members are exempt from dues and contributions, so death aid claims cannot be filed for them."},
            status=400,
        )

    if not is_member_in_good_standing(member_obj):
        return JsonResponse(
            {"ok": False, "error": "Member is not in good standing per ARTICLE XI Section 4."},
            status=400,
        )

    # Optional bill amount
    bill_value = None
    if death_bill:
        try:
            bill_value = float(death_bill)
        except ValueError:
            return JsonResponse({"ok": False, "error": "Bill amount must be a valid number."}, status=400)

    from decimal import Decimal
    # If the deceased person IS the member (policyholder), the benefit tier is
    # always the Member rate — the claimant's relationship to the deceased must
    # not change the amount.
    policy_relationship = death_rel
    if (
        death_scenario == "member"
        or death_deceased.strip().lower() == member_obj.full_name.strip().lower()
    ):
        policy_relationship = "self"
        death_rel_group = "immediate"
    benefit_amount = Decimal(str(get_death_aid_amount(policy_relationship)))
    if benefit_amount <= 0:
        return JsonResponse(
            {"ok": False, "error": f"Unknown relationship '{death_rel}' — death aid amount is ₱0. Please select a valid relationship from the list."},
            status=400,
        )

    claimant_obj, _ = Claimant.objects.get_or_create(
        member_id_FK=member_obj,
        full_name=death_claimant,
        relationship_to_member=death_rel,
        defaults={
            "contact_number": death_contact,
            "authorization_status": "Pending Authorization",
            "relationship_group": death_rel_group,
        },
    )

    if death_contact is not None and not claimant_obj.contact_number:
        claimant_obj.contact_number = death_contact
        claimant_obj.save(update_fields=["contact_number"])

    treasurer_user = resolve_officer_from_session(request)

    uploaded_files = request.FILES.getlist("death_photo_files")

    try:
        with transaction.atomic():
            death_aid = DeathAid.objects.create(
                member_id_FK=member_obj,
                claimant_id_FK=claimant_obj,
                claim_date=timezone.now().date(),
                claim_type=death_type or "Immediate Family",
                date_of_death=death_date,
                deceased_name=death_deceased,
                relationship_to_member=policy_relationship,
                relationship_group=death_rel_group,
                funeral_location=death_funeral_location,
                interment_date=death_interment_date,
                benefit_amount=benefit_amount,
                bill_amount=bill_value,
                document_status="Pending",
                status="Treasurer Direct",  # Special status for treasurer-created claims - goes directly to Auditor
                disbursement_source=death_source if death_source in ("fund", "direct") else None,
                treasurer_validated_by_user_id_FK=treasurer_user,
                auditor_verified_by_user_id_FK=None,
                president_decided_by_user_id_FK=None,
                released_by_user_id_FK=None,
            )

            TransactionVerification.objects.create(
                table_name="death_aid",
                record_id=death_aid.death_aid_id_PK,
                verification_status="Pending Auditor Review",
            )

            for f in uploaded_files:
                if f and getattr(f, "size", 0) > 0:
                    _link_proof_to_record(f, death_aid, treasurer_user, document_type="other")

            _record_audit_trail(
                table="death_aid",
                record_id=death_aid.death_aid_id_PK,
                action="CREATED",
                actor=treasurer_user,
                new={
                    "member": member_obj,
                    "claimant": claimant_obj,
                    "claim_date": death_date,
                    "claim_type": death_type or "Immediate Family",
                    "deceased_name": death_deceased,
                    "relationship_to_member": death_rel,
                    "relationship_group": death_rel_group,
                    "benefit_amount": str(benefit_amount),
                    "status": "Treasurer Direct",
                },
                ip=request.META.get("REMOTE_ADDR"),
            )
    except ValueError as exc:
        # Blocked proof upload (duplicate content, disallowed type, oversize):
        # the atomic block already rolled back the claim, so answer with the
        # specific reason + log the attempt instead of a generic 500.
        return proof_upload_blocked_response(
            request, exc,
            table="death_aid", record_id=0,
            actor=treasurer_user, member=member_obj,
        )

    _broadcast_treasurer("aids")

    # Stage email: claim filed by Treasurer — member is notified before Auditor verification.
    try:
        notify_member(
            member_obj,
            notification_type="Claim Submitted",
            message="Your Death Aid claim has been filed by the Treasurer and is now pending Auditor verification.",
            category="claim",
            sender_name=treasurer_user.full_name if treasurer_user else "Treasurer",
            sender_role="Treasurer",
            send_email=True,
        )
    except Exception:
        logger.warning("Treasurer death aid filing notification failed for member %s", member_obj.member_id_PK)

    return JsonResponse({"ok": True, "death_aid_id": death_aid.death_aid_id_PK})


@require_GET
def treasurer_death_aids_list(request: HttpRequest):
    """Return DeathAid rows for the Treasurer death aid table."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    aids = (
        DeathAid.objects.select_related("member_id_FK", "claimant_id_FK")
        .order_by("-death_aid_id_PK")
    )

    rows = []
    for a in aids:
        is_member = (
            a.deceased_name.strip().lower() == a.member_id_FK.full_name.strip().lower()
            or a.relationship_to_member.strip().lower() == "self"
        )
        rows.append(
            {
                "id": f"DTH-{a.death_aid_id_PK}",
                "memberId": a.member_id_FK.member_id_PK,
                "name": a.member_id_FK.full_name,
                "claimant": a.claimant_id_FK.full_name if a.claimant_id_FK else "",
                "deceased": a.deceased_name,
                "relationship": a.relationship_to_member,
                "relationshipGroup": a.relationship_group,
                "claimType": a.claim_type,
                "contact": a.claimant_id_FK.contact_number if a.claimant_id_FK else "",
                "date": a.claim_date.isoformat() if a.claim_date else "",
                "dateOfDeath": a.claim_date.isoformat() if a.claim_date else "",
                "bill_amount": float(a.bill_amount) if a.bill_amount is not None else 0,
                "benefit_amount": float(a.benefit_amount) if a.benefit_amount is not None else 0,
                "status": a.status or "Pending Verification",
                "document_status": a.document_status or "Pending",
                "is_member_deceased": is_member,
            }
        )

    return JsonResponse({"ok": True, "death_aids": rows})


@require_POST
@transaction.atomic
def treasurer_resubmit_entry(request: HttpRequest, table_name: str, record_id: int):

    """Flow B: Treasurer corrects and resubmits a rejected entry."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    if table_name not in MODEL_MAP:
        return JsonResponse({"ok": False, "error": "Invalid table."}, status=400)

    Model = MODEL_MAP[table_name]
    try:
        record = Model.objects.get(pk=int(record_id))
    except (ValueError, Model.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Record not found."}, status=404)

    old_snapshot = _serialize_for_audit({
        field.name: getattr(record, field.name)
        for field in record._meta.fields
    })

    officer = resolve_officer_from_session(request)

    # Treasurer's response/clarification notes sent with the resubmission.
    treasurer_notes = (request.POST.get("treasurer_notes") or "").strip()

    # Explicitly bind Treasurer resubmission payload fields to model fields.
    # Bug A: the Treasurer frontend posts keys like fee_ref / fee_encoder / fee_month,
    # but membership_fee model fields are receipt_number / deposit_reference, etc.
    if table_name == "membership_fee":
        payload_map = {
            "fee_ref": "receipt_number",
            "fee_encoder": "deposit_reference",
            "fee_method": "payment_method",
            "fee_date": "payment_date",
            "fee_status": "payment_status",
        }

        for payload_key, model_field in payload_map.items():
            if payload_key in request.POST:
                setattr(record, model_field, (request.POST.get(payload_key) or "").strip())

        # amount vs partial_amount
        if "fee_amount" in request.POST:
            setattr(record, "amount", (request.POST.get("fee_amount") or "").strip())
        if "fee_partial_amount" in request.POST:
            # Some UIs send both fee_amount + fee_partial_amount. We keep partial_amount consistent if present.
            if hasattr(record, "partial_amount"):
                setattr(record, "partial_amount", (request.POST.get("fee_partial_amount") or "").strip())
            # Keep amount in sync with partial amount for Partial resubmission.
            if (request.POST.get("fee_status") or "").strip() == "Partial":
                setattr(record, "amount", (request.POST.get("fee_partial_amount") or "").strip())

        # Persist with explicit update_fields to ensure DB columns are updated.
        update_fields = [
            "receipt_number",
            "deposit_reference",
            "payment_method",
            "payment_date",
            "payment_status",
            "amount",
        ]
        if hasattr(record, "partial_amount"):
            update_fields.append("partial_amount")
        record.save(update_fields=update_fields)
    else:
        # Default behavior for other tables that already use model-field key names.
        for field in UPDATABLE_FIELDS.get(table_name, []):
            if field in request.POST:
                setattr(record, field, request.POST[field])
        record.save()


    # Handle photo file upload for resubmission — all entity types.
    # The frontend sends entity-specific file field names.
    PHOTO_FIELDS = {
        "membership_fee": "fee_photo_file",
        "monthly_dues": "md_returned_photo_file",
        "medical_aid": "ma_returned_photo_file",
        "death_aid": "da_returned_photo_file",
    }
    upload_field = PHOTO_FIELDS.get(table_name)
    if upload_field:
        try:
            for uploaded in request.FILES.getlist(upload_field):
                if uploaded and getattr(uploaded, "size", 0) > 0:
                    _link_proof_to_record(uploaded, record, officer, document_type="other")
        except ValueError as exc:
            # Blocked proof upload (duplicate content, disallowed type,
            # oversize): answer with the specific reason + log the attempt
            # instead of a generic 500.
            return proof_upload_blocked_response(
                request, exc,
                table=table_name, record_id=record_id,
                actor=officer,
            )

    # Reset the model status fields so the entry flows back through the
    # pipeline (Treasurer → Auditor → President) instead of remaining stuck
    # in "Returned for Revision".
    reset_updates = _status_field_updates(table_name, is_rejected=False)
    # For monthly_dues, _status_field_updates sets treasurer_status back to
    # "Returned for Revision" which is wrong — it should go back to pending.
    if table_name == "monthly_dues":
        reset_updates["treasurer_status"] = "Pending Treasurer Review"
        reset_updates["auditor_status"] = "Pending Auditor Review"
        reset_updates["president_status"] = "Pending President Approval"
    if table_name == "membership_fee":
        reset_updates["payment_status"] = "Pending"
    if table_name in ("medical_aid", "death_aid"):
        # Route back to the Auditor's aid queue ("Pending Auditor Verification" is
        # in Status.ALL_PENDING; "Pending Treasurer Review" is NOT, so it would
        # disappear from the auditor inbox).
        reset_updates["status"] = "Pending Auditor Verification"
        # Clear any stale President decision (e.g. a previous rejection) — otherwise
        # the President queue filter (president_decided_by_user_id_FK__isnull=True)
        # would permanently hide this entry after the Auditor re-verifies it.
        reset_updates["president_decided_by_user_id_FK"] = None
        reset_updates["president_decision"] = None
    for field, value in reset_updates.items():
        if hasattr(record, field):
            setattr(record, field, value)
    record.save()

    # Reset verification state so the Auditor inbox re-loads this entry.
    # IMPORTANT: Auditor inbox only shows TransactionVerification rows with:
    # - verification_status == "Pending"
    current_tv = TransactionVerification.objects.filter(
        table_name=table_name,
        record_id=int(record_id),
    ).first()
    original_auditor_fk = current_tv.returned_by_auditor_id_FK_id if current_tv else None

    same_auditor = request.POST.get("same_auditor") == "true"
    # When routing back to the same auditor, keep both the assignment and the
    # "previously returned by" marker so the Auditor's Payments Audit list shows
    # the entry again (assigned to them) with the returned badge.
    kept_auditor_fk = original_auditor_fk if (same_auditor and original_auditor_fk) else None
    updated_count = TransactionVerification.objects.filter(
        table_name=table_name,
        record_id=int(record_id),
    ).update(
        verification_status="Pending",
        auditor_id_FK_id=kept_auditor_fk,
        verified_at=None,
        returned_reason="",
        returned_by_auditor_id_FK_id=kept_auditor_fk,
    )

    # Safety: ensure at least one row was updated; otherwise the resubmission
    # won't reappear in the Auditor Payments Audit inbox.
    if updated_count == 0:
        return JsonResponse(
            {
                "ok": False,
                "error": "Resubmit failed: no TransactionVerification row matched.",
                "table_name": table_name,
                "record_id": record_id,
            },
            status=400,
        )

    new_snapshot = _serialize_for_audit({
        field.name: getattr(record, field.name)
        for field in record._meta.fields
    })

    _record_audit_trail(
        table=table_name,
        record_id=int(record_id),
        action="RESUBMITTED",
        actor=officer,
        old=old_snapshot,
        new=new_snapshot,
        ip=request.META.get("REMOTE_ADDR"),
        notes="Treasurer resubmitted entry after revision." + (f" — Treasurer response: {treasurer_notes}" if treasurer_notes else ""),
    )

    _broadcast_treasurer("returned_entries")
    _broadcast_pending_counts()

    return JsonResponse({"ok": True})


@require_POST
def treasurer_withdraw_aid(request: HttpRequest):
    """Treasurer withdraws a returned/rejected aid claim — closes it without resubmitting."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        body = json.loads(request.body)
    except Exception:
        body = request.POST

    target_id = (body.get("target_id") or request.POST.get("target_id") or "").strip()
    record = None
    table_name = None
    if target_id.startswith("MED-"):
        record = MedicalAid.objects.filter(medical_aid_id_PK=int(target_id.replace("MED-", ""))).first()
        table_name = "medical_aid"
    elif target_id.startswith("DTH-"):
        record = DeathAid.objects.filter(death_aid_id_PK=int(target_id.replace("DTH-", ""))).first()
        table_name = "death_aid"
    if record is None:
        return JsonResponse({"ok": False, "error": "Claim not found."}, status=404)

    officer = resolve_officer_from_session(request)
    record.status = "Withdrawn"
    if hasattr(record, "document_status"):
        record.document_status = "Withdrawn"
    record.save()

    TransactionVerification.objects.filter(
        table_name=table_name, record_id=record.pk
    ).update(verification_status="Withdrawn")

    _record_audit_trail(
        table=table_name,
        record_id=record.pk,
        action="WITHDRAWN",
        actor=officer,
        ip=request.META.get("REMOTE_ADDR"),
    )

    try:
        notify_member(
            record.member_id_FK,
            notification_type="Claim Update",
            message=f"Your {table_name.replace('_', ' ').title()} request has been withdrawn by the Treasurer and will no longer proceed.",
            category="claim",
            sender_name=officer.full_name if officer else "Treasurer",
            sender_role="Treasurer",
            send_email=True,
        )
    except Exception:
        logger.exception("Withdraw notification failed for %s %s", table_name, record.pk)

    _broadcast_treasurer("returned_entries")
    _broadcast_pending_counts()

    return JsonResponse({"ok": True})


# ==========================================================================
# TREASURER MEMBER LISTING & REVISION VIEWS (migrated from views_members_api)
# ==========================================================================

def _treasurer_payment_item_to_json(kind: str, obj) -> dict:
    member = getattr(obj, "member_id_FK", None)
    amount = getattr(obj, "amount", None)
    payment_date = getattr(obj, "payment_date", None)
    payment_method = getattr(obj, "payment_status", None) if kind == "membership_fee" else getattr(obj, "payment_method", None)
    return {
        "id": str(obj.fee_id_PK if kind == "membership_fee" else obj.dues_id_PK),
        "entity_id": int(obj.fee_id_PK if kind == "membership_fee" else obj.dues_id_PK),
        "type": "OTC Fee Payment" if kind == "membership_fee" else "Monthly Dues",
        "ref": getattr(obj, "receipt_number", None) or "",
        "member": {
            "member_id": member.member_id_PK if member else None,
            "member_name": member.full_name if member else "",
            "employee_id": member.employee_id or "" if member else "",
            "department": member.department or "" if member else "",
            "position": member.position or "" if member else "",
            "contact": getattr(member, "contact_number", None) or "",
            "email": getattr(member, "email", None) or "",
            "membership_status": getattr(member, "membership_status", None) or "",
        },
        "amount": str(amount) if amount is not None else "0",
        "month": getattr(obj, "month_covered", None) or "N/A",
        "date": str(payment_date) if payment_date is not None else "",
        "method": str(payment_method) if payment_method is not None else "",
        "encoded_by": getattr(getattr(obj, "recorded_by_user_id_FK", None), "full_name", "") or "",
        "payment_status": getattr(obj, "payment_status", None) or "",
        "verification_status": "Pending",
    }


@require_GET
def treasurer_member_profiles(request: HttpRequest):
    """Member Lists — profile information for every member (no finance data).

    Supports server-side filtering and pagination:
      ?q=             matches name, employee ID, department, position, contact
                      (a comma splits surname/given parts, so
                      "Dela Cruz, Juan" matches "JUAN A DELA CRUZ")
      ?classification=Teaching|Retired
      ?membership_status=Permanent|Temporary|...
      ?department=<name substring>
      ?page=&per_page=   (per_page capped at 100)
      ?order=asc|desc    (alphabetical by SURNAME — rows carry a
                      "Lastname, Firstname M.I." display_name; defaults to asc)
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # Local import: monthly_deduction_views owns the canonical
    # "SURNAME, Given" formatter (suffix + particle aware) and importing it
    # at module level would risk a views-layer import cycle.
    from core_system.monthly_deduction_views import _formatted_name

    q = (request.GET.get("q") or "").strip()
    classification = (request.GET.get("classification") or "").strip()
    membership_status = (request.GET.get("membership_status") or "").strip()
    department = (request.GET.get("department") or "").strip()
    order = (request.GET.get("order") or "asc").strip().lower()
    try:
        page = max(1, int(request.GET.get("page", "1") or "1"))
    except ValueError:
        page = 1
    try:
        per_page = min(100, max(5, int(request.GET.get("per_page", "25") or "25")))
    except ValueError:
        per_page = 25

    members = Member.objects.all()
    if q:
        if "," in q:
            # "Lastname, Firstname" search: every comma-separated part must
            # match the stored "FIRST M LAST" full_name somewhere.
            for part in [p.strip() for p in q.split(",") if p.strip()]:
                members = members.filter(
                    Q(full_name__icontains=part)
                    | Q(employee_id__icontains=part)
                    | Q(department__icontains=part)
                    | Q(department_id_FK__name__icontains=part)
                    | Q(position__icontains=part)
                    | Q(contact_number__icontains=part)
                )
        else:
            members = members.filter(
                Q(full_name__icontains=q)
                | Q(employee_id__icontains=q)
                | Q(department__icontains=q)
                | Q(department_id_FK__name__icontains=q)
                | Q(position__icontains=q)
                | Q(contact_number__icontains=q)
            )
    if classification:
        members = members.filter(member_classification=classification)
    if membership_status:
        members = members.filter(membership_status=membership_status)
    if department:
        members = members.filter(
            Q(department__icontains=department) | Q(department_id_FK__name__icontains=department)
        )

    # Surname ordering: the directory displays "LASTNAME, Firstname M.I.",
    # so sort by that formatted value (surname first, then given names).
    # Stored full_name is free text ("FIRST M LAST"), which a plain DB
    # order_by would sort by first name — the reported caret-sort bug.
    member_list = list(members)
    member_list.sort(
        key=lambda m: (
            _formatted_name(m.full_name).casefold(),
            (m.full_name or "").casefold(),
        ),
        reverse=(order == "desc"),
    )

    total = len(member_list)
    total_pages = (total + per_page - 1) // per_page if per_page else 1
    page = min(page, max(1, total_pages))
    member_list = member_list[(page - 1) * per_page: page * per_page]

    record_ids = []
    rows = []
    for m in member_list:
        record_ids.append(m.member_id_PK)
        rows.append({
            "member_id": m.member_id_PK,
            "full_name": m.full_name,
            "display_name": _formatted_name(m.full_name),
            "employee_id": m.employee_id or "",
            "department": m.department_id_FK.name if m.department_id_FK else (m.department or ""),
            "position": m.position or "",
            "membership_status": m.membership_status or "",
            "member_classification": m.member_classification or "",
            "classification": m.member_classification or "Teaching",
            "member_type": m.member_type or "",
            "employment_status": m.employment_status or "",
            "contact_number": m.contact_number or "",
            "email": m.email or "",
            "date_joined": str(m.date_joined) if m.date_joined else "",
            "emergency_contact": m.emergency_contact or "",
            "emergency_number": m.emergency_number or "",
            "address": m.address or "",
            "civil_status": m.civil_status or "",
            "sex": m.sex or "",
            "date_of_birth": m.date_of_birth.isoformat() if m.date_of_birth else "",
            "age": m.age,
            "photo_url": m.profile_picture.url if m.profile_picture else "",
        })

    _log_sensitive_read(request, "member", record_ids, "Treasurer viewed member profiles list")
    return JsonResponse({
        "ok": True,
        "members": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


@require_GET
def treasurer_members_list(request):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    members = Member.objects.all().order_by("member_id_PK")

    # Optional server-side narrowing for pickers that ask for it; existing
    # consumers that pass no params keep receiving the full list.
    q = (request.GET.get("q") or "").strip()
    if q:
        members = members.filter(
            Q(full_name__icontains=q) | Q(employee_id__icontains=q) | Q(position__icontains=q)
        )
    try:
        limit = int(request.GET.get("limit", "0") or "0")
    except (TypeError, ValueError):
        limit = 0
    if limit > 0:
        members = members[: min(limit, 5000)]

    return JsonResponse(
        {
            "ok": True,
            "members": [member_to_json(m) for m in members],
        }
    )


@require_GET
def treasurer_member_details(request, member_id):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    member = get_object_or_404(Member, pk=member_id)
    year = timezone.now().year
    expected_dues = get_expected_dues_amount()
    fee_amount = get_membership_fee_amount()

    paid_months = set(
        MonthlyDues.objects.filter(
            member_id_FK=member,
            payment_date__year=year,
        ).values_list("month_covered", flat=True)
    )
    missed_months = []
    for m in range(1, 13):
        key = f"{year}-{m:02d}"
        if key not in paid_months:
            missed_months.append(key)

    outstanding_contributions = Contribution.objects.filter(
        member_id_FK=member,
        status="NOT_PAID",
        aid_tracking_post_id_FK__status="tracking",
    ).select_related("aid_tracking_post_id_FK")

    fee_paid = MembershipFee.objects.filter(
        member_id_FK=member,
    ).exclude(
        payment_status__iexact="unpaid",
    ).exists()

    active_aids = []
    for c in outstanding_contributions:
        post = c.aid_tracking_post_id_FK
        active_aids.append({
            "post_id": post.post_id_PK,
            "aid_type": post.aid_type,
            "expected_amount": float(c.expected_amount),
            "paid_amount": float(c.paid_amount),
            "status": c.status,
        })

    return JsonResponse({
        "ok": True,
        "member_id": member.member_id_PK,
        "full_name": member.full_name,
        "employee_id": member.employee_id or "",
        "membership_status": member.membership_status,
        "missed_months": missed_months,
        "membership_fee_paid": fee_paid,
        "expected_dues_amount": expected_dues,
        "membership_fee_amount": fee_amount,
        "active_aid_obligations": active_aids,
    })


def _family_rel_key(raw: str) -> str:
    """Normalize a family-list relationship to a file-death-aid category key.

    Matches the member-profile family categories first, then falls back to
    keyword matching so legacy free-text rows still resolve.
    """
    norm = (raw or "").strip().casefold()
    for key, spec in MEMBER_FAMILY_CATEGORIES.items():
        if norm == (spec["relationship"] or "").casefold():
            return key
    if norm in ("member", "self"):
        return "member"
    if any(w in norm for w in ("spouse", "husband", "wife")):
        return "spouse"
    if any(w in norm for w in ("parent", "father", "mother")):
        return "parent"
    if any(w in norm for w in ("child", "son", "daughter")):
        return "child"
    if any(w in norm for w in ("brother", "sister", "sibling")):
        return "sibling"
    return ""


@require_GET
def treasurer_member_family(request, member_id):
    """Family list of one member for the file-death-aid form.

    Lets the Treasurer auto-fill the deceased name once the relationship
    category is selected.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    member = get_object_or_404(Member, pk=member_id)
    items = []
    for row in Claimant.objects.filter(member_id_FK=member).order_by("full_name"):
        key = _family_rel_key(row.relationship_to_member)
        spec = MEMBER_FAMILY_CATEGORIES.get(key)
        items.append({
            "id": row.claimant_id_PK,
            "full_name": row.full_name,
            "category": key,
            "category_label": spec["label"] if spec else (row.relationship_to_member or ""),
            "contact_number": row.contact_number or "",
        })
    return JsonResponse({"ok": True, "member_id": member.member_id_PK, "items": items})


@require_GET
def treasurer_active_members_count(request):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    active_count = Member.objects.filter(membership_status__in=['Permanent', 'Temporary']).count()

    return JsonResponse({"ok": True, "active_count": active_count})


@require_GET
def treasurer_records_requiring_revision(request):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    revision_verifications = TransactionVerification.objects.filter(
        verification_status__in=[Status.RETURNED_REVISION, Status.REJECTED]
    )

    items = []
    for tv in revision_verifications:
        table_name = str(tv.table_name).lower()
        if table_name not in MODEL_MAP:
            continue

        Model = MODEL_MAP[table_name]
        try:
            record = Model.objects.get(pk=tv.record_id)
        except Model.DoesNotExist:
            continue

        revision_log = GlobalAuditTrail.objects.filter(
            table_name=table_name,
            record_id=tv.record_id,
            action__in=["RETURNED", "CORRECTION_REQUIRED", "REJECTED"],
        ).order_by("-timestamp").first()

        if table_name in ("membership_fee", "monthly_dues"):
            item = _treasurer_payment_item_to_json(table_name.replace("_", ""), record)
            item["verificationStatus"] = tv.verification_status
            item["rejection_reason"] = revision_log.notes if revision_log else ""
            items.append(item)

    return JsonResponse({"ok": True, "records": items})


# ==========================================================================
# TREASURER MEMBER UPDATE/RETIRE VIEWS (migrated from member_api)
# ==========================================================================

@require_POST
def treasurer_member_update(request):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    payload_member_id = (request.POST.get("member_id") or "").strip()
    if not payload_member_id:
        return JsonResponse({"ok": False, "error": "member_id is required."}, status=400)

    member, err = resolve_member_from_input(payload_member_id)
    if err:
        return err

    fields = {}
    for field in [
        "full_name",
        "employee_id",
        "department",
        "position",
        "contact_number",
        "email",
        "employment_status",
        "membership_status",
        "member_type",
        "emergency_contact",
        "emergency_number",
    ]:
        if field in request.POST:
            raw = (request.POST.get(field) or "").strip()
            fields[field] = raw if raw != "" else None

    if "employment_status" in fields and fields["employment_status"] is None:
        return JsonResponse({"ok": False, "error": "employment_status cannot be empty."}, status=400)
    if "membership_status" in fields and fields["membership_status"] is None:
        return JsonResponse({"ok": False, "error": "membership_status cannot be empty."}, status=400)

    # Domain validation — keep the two status concepts separate and valid.
    # Membership Type (By-Laws): Permanent / Temporary / Retired.
    # Employment Status: Active / Inactive.
    if "membership_status" in fields and fields["membership_status"] not in ("Permanent", "Temporary", "Retired"):
        return JsonResponse(
            {"ok": False, "error": "membership_status must be Permanent, Temporary or Retired."},
            status=400,
        )
    if "employment_status" in fields and fields["employment_status"] not in ("Active", "Inactive"):
        return JsonResponse(
            {"ok": False, "error": "employment_status must be Active or Inactive."},
            status=400,
        )

    # Member emails must be ISU addresses and contact numbers valid PH mobiles.
    if "email" in fields and fields["email"]:
        normalized_email, email_error = validate_isu_email(fields["email"])
        if email_error:
            return JsonResponse({"ok": False, "error": email_error}, status=400)
        fields["email"] = normalized_email
    if "contact_number" in fields and fields["contact_number"]:
        normalized_contact, contact_error = _validate_ph_contact(fields["contact_number"])
        if contact_error:
            return JsonResponse({"ok": False, "error": contact_error}, status=400)
        fields["contact_number"] = normalized_contact

    old_status = member.membership_status

    for k, v in fields.items():
        setattr(member, k, v)

    # Department: match against the Department registry when possible so the
    # member shows in the correct department across every module.
    if "department" in fields:
        from core_system.models import Department
        dept = Department.objects.filter(name__iexact=fields["department"] or "").first()
        if dept:
            member.department = dept.name
            member.department_id_FK = dept

    # Profile photo (optional upload from Member Lists).
    photo = request.FILES.get("photo")
    if photo and getattr(photo, "size", 0) > 0:
        member.profile_picture = photo

    if hasattr(member, "full_name") and not (member.full_name or "").strip():
        return JsonResponse({"ok": False, "error": "full_name is required."}, status=400)

    member.save()

    new_status = member.membership_status
    if new_status in ("Permanent", "Temporary") and old_status != new_status:
        has_fee = MembershipFee.objects.filter(member_id_FK=member).exists()
        if not has_fee:
            fee = MembershipFee.objects.create(
                member_id_FK=member,
                receipt_number=f"REG-{int(timezone.now().timestamp())}",
                amount=str(get_membership_fee_amount()),
                payment_date=timezone.now().date(),
                # Method unknown until the fee is actually collected/encoded;
                # payment_method must never hold a STATUS value.
                payment_method="Unknown",
                payment_status="Pending",
                recorded_by_user_id_FK=resolve_officer_from_session(request),
            )
            TransactionVerification.objects.create(
                table_name="membership_fee",
                record_id=fee.fee_id_PK,
                verification_status="Pending",
            )

    _broadcast_treasurer("members")

    return JsonResponse({"ok": True, "member": {"id": member.member_id_PK, "full_name": member.full_name}})


@require_POST
def treasurer_member_retire(request):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    payload_member_id = (request.POST.get("member_id") or "").strip()
    if not payload_member_id:
        return JsonResponse({"ok": False, "error": "member_id is required."}, status=400)

    member, err = resolve_member_from_input(payload_member_id)
    if err:
        return err

    member.membership_status = "Retired"
    member.employment_status = "Retired"
    member.member_classification = Member.CLASSIFICATION_RETIRED
    member.save()

    _broadcast_treasurer("members")

    return JsonResponse({"ok": True, "member_id": member.member_id_PK})


# ==========================================================================
# TREASURER AID TRACKING POSTS
# ==========================================================================

_DEATH_RELATIONSHIP_LABELS = (
    (("member", "self"), "member"),
    (("spouse", "husband", "wife"), "spouse"),
    (("parent", "father", "mother", "child", "son", "daughter"), "parent/child"),
    (
        (
            "brother",
            "sister",
            "sibling",
            "full-blood brother",
            "full-blood sister",
            "full blood brother",
            "full blood sister",
            "full-blood sibling",
        ),
        "full-blood sibling",
    ),
)


def _relationship_label(raw: str) -> str:
    """Plain-language tier name for a death-aid relationship."""
    norm = (raw or "").strip().casefold()
    for keys, label in _DEATH_RELATIONSHIP_LABELS:
        if norm in keys:
            return label
    return norm or ""


@require_GET
def treasurer_approved_aid_posts(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    include_all = (request.GET.get("all") == "1")
    posts = AidTrackingPost.objects.select_related(
        "archive_id_FK",
        "archive_id_FK__member_id_FK",
        "created_by_user_id_FK",
    ).all()
    if not include_all:
        posts = posts.filter(is_active=True)
    posts = list(posts)

    # Non-retired members: the pool that funds aid, and the basis for the
    # quick per-member sanity check shown on the release screen.
    active_members = [
        m
        for m in Member.objects.all().order_by("full_name")
        if not is_retired_member(m)
    ]

    # Which family tier each death-aid claim falls under (member / spouse /
    # parent-child / full-blood sibling) — needed to explain the amount.
    death_ids = [
        p.archive_id_FK.record_id
        for p in posts
        if p.aid_type == "death_aid"
        and p.archive_id_FK
        and p.archive_id_FK.transaction_type == "death_aid"
    ]
    death_by_id = {
        d.death_aid_id_PK: d
        for d in DeathAid.objects.filter(death_aid_id_PK__in=death_ids)
    }

    # Fund availability for the "Paid with Funds" option. Matches the check used
    # at release time so the button only enables when the payout can actually be made.
    safety_threshold = float(SystemSetting.objects.get_or_create(
        setting_key="safety_threshold", defaults={"setting_value": "20000"}
    )[0].setting_value)
    fund_totals = FundTransaction.objects.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    fund_balance = float((fund_totals["total_in"] or 0) - (fund_totals["total_out"] or 0))

    # Earmarked cash: what members paid through the monthly deduction that is
    # ring-fenced for an aid claim, and how much of it the releases already
    # drew down. Linked rows show against a specific claim; the aid_type
    # reserve also counts the pooled rows no claim has claimed yet.
    setaside_by_post = setaside_totals_by_post()
    setaside_reserve = {
        aid_type: {k: float(v) for k, v in values.items()}
        for aid_type, values in setaside_reserve_by_aid_type().items()
    }

    # Contributors per post: members who actually owe a share. The recipient
    # carries an EXCLUDED_REQUESTER row and must never be counted — otherwise
    # the release quick-check reads e.g. 500 x 12 = 6000 while the claim only
    # expects 5500 from its 11 contributors.
    post_ids = [p.post_id_PK for p in posts]
    contributor_counts = {}
    if post_ids:
        for row in Contribution.objects.filter(
            aid_tracking_post_id_FK_id__in=post_ids
        ).exclude(status=Contribution.STATUS_EXCLUDED_REQUESTER).values(
            "aid_tracking_post_id_FK_id"
        ).annotate(n=Count("contribution_id_PK")):
            contributor_counts[row["aid_tracking_post_id_FK_id"]] = row["n"]

    items = []
    for post in posts:
        archive = post.archive_id_FK
        member = archive.member_id_FK if archive else None
        aid_label = "Medical Aid" if post.aid_type == "medical_aid" else "Death Aid"
        collection_rate = 0
        if post.total_expected > 0:
            collection_rate = round(float(post.total_collected) / float(post.total_expected) * 100, 1)

        per_member_qs = Contribution.objects.filter(
            aid_tracking_post_id_FK=post,
        ).exclude(status=Contribution.STATUS_EXCLUDED_REQUESTER).aggregate(per_member=Min("expected_amount"))
        per_member_amount = str(per_member_qs["per_member"]) if per_member_qs["per_member"] is not None else "0"

        # Intelligent quick check: policy rate for this aid × contributors
        # (active members minus this claim's recipient).
        contributor_count = contributor_counts.get(post.post_id_PK)
        if contributor_count is None:
            # No contribution rows yet (e.g. legacy post): fall back to the
            # stored expectation so the check still matches total_expected.
            try:
                _per_member_fallback = float(per_member_qs["per_member"] or 0)
            except Exception:
                _per_member_fallback = 0
            if _per_member_fallback > 0:
                contributor_count = int(round(float(post.total_expected) / _per_member_fallback))
            else:
                contributor_count = 0
        relationship = ""
        relationship_label = ""
        if post.aid_type == "death_aid":
            death = (
                death_by_id.get(archive.record_id)
                if archive and archive.transaction_type == "death_aid"
                else None
            )
            relationship = (death.relationship_to_member or "").strip() if death else ""
            relationship_label = _relationship_label(relationship)
            suggested_per_member = get_death_aid_amount(relationship)
        else:
            suggested_per_member = get_accidental_sickness_aid_benefit()
        if not suggested_per_member and per_member_qs["per_member"] is not None:
            suggested_per_member = float(per_member_qs["per_member"])

        setaside = setaside_by_post.get(post.post_id_PK) or {}
        setaside_collected = float(setaside.get("collected") or 0)
        setaside_released = float(setaside.get("released") or 0)

        items.append({
            "post_id": post.post_id_PK,
            "aid_type": post.aid_type,
            "aid_label": aid_label,
            "member_name": archive.member_name if archive else "",
            "member_id": member.member_id_PK if member else None,
            "is_external": (post.source_type or "") == "external_aid",
            "source_type": post.source_type or "",
            "external_campus": post.external_campus or "",
            "external_beneficiary": post.external_beneficiary or "",
            "external_display": (
                f"{(post.external_campus or '').strip()} — {(post.external_beneficiary or '').strip()}"
                if (post.external_campus or post.external_beneficiary) and (post.source_type or "") == "external_aid"
                else (archive.member_name if archive else "")
            ),
            "target_month": post.target_month,
            "total_expected": str(post.total_expected),
            "total_collected": str(post.total_collected),
            "per_member_amount": per_member_amount,
            "collection_rate": collection_rate,
            "status": archive.status if archive else "",
            "amount": str(archive.amount) if archive else "0",
            "finish_status": post.finish_status or "",
            "finish_paid_with_funds": post.finish_paid_with_funds,
            "finish_cycle": post.finish_cycle,
            "collection_started": post.collection_started,
            "remaining_balance": max(0, float(post.total_expected) - float(post.total_collected)),
            "paid_with_funds_available": (fund_balance >= float(post.total_expected) + safety_threshold),
            "created_at": post.created_at.isoformat() if post.created_at else "",
            "created_by": post.created_by_user_id_FK.full_name if post.created_by_user_id_FK else "",
            "has_deduction_sheet": bool(post.deduction_sheet),
            "deduction_batch_reference": post.deduction_batch_reference or "",
            "deduction_payroll_period": post.deduction_payroll_period or "",
            "has_remittance": bool(post.deduction_remitted_amount is not None),
            "deduction_remitted_amount": str(post.deduction_remitted_amount) if post.deduction_remitted_amount is not None else None,
            "deduction_remittance_reference": post.deduction_remittance_reference or "",
            "deduction_remitted_date": post.deduction_remitted_date.isoformat() if post.deduction_remitted_date else None,
            "is_active": bool(post.is_active),
            "set_aside_collected": round(setaside_collected, 2),
            "set_aside_released": round(setaside_released, 2),
            "set_aside_available": round(
                max(0.0, setaside_collected - setaside_released), 2
            ),
            "relationship": relationship,
            "relationship_label": relationship_label,
            "suggested_per_member": round(float(suggested_per_member or 0), 2),
            "contributor_count": int(contributor_count or 0),
        })

    response = JsonResponse({
        "ok": True,
        "posts": items,
        "fund_balance": fund_balance,
        "safety_threshold": safety_threshold,
        "active_member_count": len(active_members),
        "member_names": [m.full_name for m in active_members],
        "set_aside_reserve": setaside_reserve,
    })
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@require_GET
def treasurer_unfiled_setasides(request: HttpRequest):
    """Aid set-asides with no tracking post — earmarked through monthly
    deductions but no claim filed yet. Feeds the UNFILED AIDS table next to
    tracked-but-unready posts. Shaped like approved-aid-post rows so the
    table renders both identically."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    from core_system.models import AidSetAside

    rows = (
        AidSetAside.objects.filter(aid_tracking_post_id_FK__isnull=True)
        .values(
            "assessment_item_id_FK_id",
            "assessment_item_id_FK__purpose",
            "assessment_item_id_FK__custom_label",
            "assessment_item_id_FK__recipient",
            "assessment_item_id_FK__recipient_type",
            "assessment_item_id_FK__external_campus",
            "assessment_item_id_FK__external_beneficiary",
            "assessment_item_id_FK__assessment_id_FK__month",
        )
        .annotate(
            collected=Sum("amount"),
            released=Sum("amount_released"),
            contributors=Count("member_assessment_id_FK", distinct=True),
        )
        .order_by("-assessment_item_id_FK__assessment_id_FK__month")
    )

    items = []
    for r in rows:
        collected = float(r["collected"] or 0)
        released = float(r["released"] or 0)
        available = round(max(0.0, collected - released), 2)
        if available <= 0:
            continue
        purpose = r["assessment_item_id_FK__purpose"] or ""
        if purpose == "medical_aid_fund":
            aid_label = "Medical Aid"
        elif purpose == "death_aid_fund":
            aid_label = "Death Aid"
        else:
            aid_label = r["assessment_item_id_FK__custom_label"] or "Aid"
        is_external = (r["assessment_item_id_FK__recipient_type"] or "") == "external"
        campus = (r["assessment_item_id_FK__external_campus"] or "").strip()
        bene = (r["assessment_item_id_FK__external_beneficiary"] or "").strip()
        if is_external and (campus or bene):
            display = f"{campus} — {bene}".strip(" —") or "External beneficiary"
        else:
            display = (r["assessment_item_id_FK__recipient"] or "").strip() or "—"
        month = r["assessment_item_id_FK__assessment_id_FK__month"]
        month_label = month.strftime("%b %Y") if month else ""
        items.append({
            "member_name": display,
            "aid_label": aid_label,
            "post_id": None,
            "finish_status": "unfiled",
            "total_collected": round(collected, 2),
            "set_aside_available": available,
            "is_external": is_external,
            "external_display": display if is_external else "",
            "member_id": None,
            "case_suffix": f"Set-aside · {month_label}" if month_label else "Set-aside",
            "contributors": int(r["contributors"] or 0),
        })

    response = JsonResponse({"ok": True, "unfiled": items})
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@require_GET
def treasurer_aid_post_members(request: HttpRequest, post_id: int):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        post = AidTrackingPost.objects.select_related("archive_id_FK").get(
            post_id_PK=post_id
        )
    except AidTrackingPost.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Post not found."}, status=404)

    contributions = Contribution.objects.filter(
        aid_tracking_post_id_FK=post,
    ).exclude(status=Contribution.STATUS_EXCLUDED_REQUESTER).select_related("member_id_FK").order_by("member_id_FK__full_name")

    members_data = []
    for c in contributions:
        member = c.member_id_FK
        members_data.append({
            "contribution_id": c.contribution_id_PK,
            "member_id": member.member_id_PK,
            "member_name": member.full_name,
            "employee_id": member.employee_id or "",
            "department": member.department or "",
            "expected_amount": str(c.expected_amount),
            "paid_amount": str(c.paid_amount),
            "payment_date": str(c.payment_date) if c.payment_date else None,
            "status": c.status,
            "is_manually_overridden": c.is_manually_overridden,
            "notes": c.notes,
        })

    return JsonResponse({
        "ok": True,
        "post": {
            "post_id": post.post_id_PK,
            "aid_type": post.aid_type,
            "target_month": post.target_month,
            "total_expected": str(post.total_expected),
            "total_collected": str(post.total_collected),
            "finish_cycle": post.finish_cycle,
            "collection_started": post.collection_started,
            "has_deduction_sheet": bool(post.deduction_sheet),
            "deduction_batch_reference": post.deduction_batch_reference or "",
            "deduction_payroll_period": post.deduction_payroll_period or "",
            "has_remittance": bool(post.deduction_remitted_amount is not None),
            "deduction_remitted_amount": str(post.deduction_remitted_amount) if post.deduction_remitted_amount is not None else None,
            "deduction_remittance_reference": post.deduction_remittance_reference or "",
            "deduction_remitted_date": post.deduction_remitted_date.isoformat() if post.deduction_remitted_date else None,
        },
        "members": members_data,
    })


def _recalculate_total_collected(post_id: int) -> None:
    total = Contribution.objects.filter(
        aid_tracking_post_id_FK=post_id,
        status__in=["PAID", "RECORDED", "PENDING_VERIFICATION"],
    ).aggregate(total=Sum("paid_amount"))["total"] or 0
    AidTrackingPost.objects.filter(post_id_PK=post_id).update(total_collected=total)


def _aid_requester_name(post) -> str:
    """Resolve the full name of the member who filed the aid request for a post."""
    try:
        from core_system.models import MedicalAid, DeathAid
        if post.source_id:
            if post.aid_type == "medical_aid":
                aid_record = MedicalAid.objects.filter(medical_aid_id_PK=post.source_id).first()
            elif post.aid_type == "death_aid":
                aid_record = DeathAid.objects.filter(death_aid_id_PK=post.source_id).first()
            else:
                aid_record = None
            if aid_record and aid_record.member_id_FK:
                return aid_record.member_id_FK.full_name
    except Exception:
        logger.warning("Could not resolve aid requester name for post %s", getattr(post, "post_id_PK", None))
    archive_member = getattr(post.archive_id_FK, "member_name", "") if post.archive_id_FK else ""
    return archive_member or "A Fellow Member"


def _notify_contribution_recorded(contribution) -> None:
    """Send the thank-you email + in-app notification to a member whose aid contribution was recorded."""
    member = contribution.member_id_FK
    post = contribution.aid_tracking_post_id_FK
    if member is None:
        return

    aid_label = "Medical Aid" if post.aid_type == "medical_aid" else "Death Aid"
    requester_name = _aid_requester_name(post)

    try:
        from core_system.services.email_service import send_contribution_thank_you_email
        send_contribution_thank_you_email(
            member=member,
            aid_type=aid_label,
            amount=float(contribution.paid_amount),
            target_month=post.target_month,
            requesting_member_name=requester_name,
        )
    except Exception:
        logger.exception("Contribution thank-you email failed for member %s", member.member_id_PK)

    # In-app/bell notification only — the branded thank-you email above already
    # covers the email channel, so suppress notify_member's plain-text fallback.
    try:
        notify_member(
            member,
            notification_type="Contribution Recorded",
            message=(
                f"Thank you for contributing to the {aid_label} of {requester_name} "
                f"({post.target_month}). Your contribution of ₱{contribution.paid_amount:,.2f} "
                f"is really appreciated."
            ),
            category="contribution",
            url="/member/",
            send_email=False,
        )
    except Exception:
        logger.exception("Contribution recorded notification failed for member %s", member.member_id_PK)


@require_POST
@transaction.atomic
def treasurer_aid_post_member_pay(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    contribution_ids = request.POST.getlist("contribution_id")
    if not contribution_ids:
        return JsonResponse({"ok": False, "error": "Missing contribution_id."}, status=400)

    contributions = Contribution.objects.select_related(
        "aid_tracking_post_id_FK", "member_id_FK"
    ).filter(
        contribution_id_PK__in=[int(cid) for cid in contribution_ids if cid.strip()],
        status__in=["NOT_PAID"],
    )

    if not contributions:
        return JsonResponse({"ok": False, "error": "No valid payable contributions found."}, status=404)

    post = None
    channel_layer = get_channel_layer()

    for contribution in contributions:
        post = contribution.aid_tracking_post_id_FK

        contribution.paid_amount = contribution.expected_amount
        contribution.payment_date = timezone.now().date()
        contribution.status = "RECORDED"
        contribution.is_manually_overridden = False
        contribution.updated_by_user_id_FK = officer
        contribution.save()

        _record_audit_trail(
            table="contribution",
            record_id=contribution.contribution_id_PK,
            action="PAYMENT_RECORDED",
            actor=officer,
            new={
                "status": "RECORDED",
                "paid_amount": str(contribution.expected_amount),
                "payment_date": str(contribution.payment_date),
                "aid_tracking_post_id": post.post_id_PK,
                "member_id": getattr(contribution.member_id_FK, "member_id_PK", None),
            },
            ip=request.META.get("REMOTE_ADDR"),
            notes="Contribution payment recorded.",
        )

        async_to_sync(channel_layer.group_send)(
            "treasurer_dashboard",
            {
                "type": "contribution_updated",
                "post_id": post.post_id_PK,
                "contribution_id": contribution.contribution_id_PK,
                "member_name": getattr(contribution.member_id_FK, "full_name", ""),
                "status": "RECORDED",
                "paid_amount": float(contribution.expected_amount),
            },
        )
        async_to_sync(channel_layer.group_send)(
            "auditor_dashboard",
            {
                "type": "contribution_updated",
                "post_id": post.post_id_PK,
                "contribution_id": contribution.contribution_id_PK,
                "member_name": getattr(contribution.member_id_FK, "full_name", ""),
                "status": "RECORDED",
                "paid_amount": float(contribution.expected_amount),
            },
        )

        # Thank the member for contributing (email + in-app notification).
        try:
            _notify_contribution_recorded(contribution)
        except Exception:
            logger.exception("Contribution thank-you flow failed for contribution %s", contribution.contribution_id_PK)

    if post:
        _recalculate_total_collected(post.post_id_PK)

    return JsonResponse({"ok": True, "status": "RECORDED", "paid": len(contributions)})


@require_POST
@transaction.atomic
def treasurer_aid_post_start_collection(request: HttpRequest):
    """Mark that the treasurer has started collecting contributions for a post."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    try:
        post = AidTrackingPost.objects.get(post_id_PK=int(post_id), is_active=True)
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Post not found."}, status=404)

    post.collection_started = True
    post.save(update_fields=["collection_started"])

    return JsonResponse({"ok": True, "message": "Collection started."})


@require_POST
@transaction.atomic
def treasurer_aid_post_member_skip(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    contribution_id = (request.POST.get("contribution_id") or "").strip()
    notes = (request.POST.get("notes") or "").strip()

    if not contribution_id:
        return JsonResponse({"ok": False, "error": "Missing contribution_id."}, status=400)

    try:
        contribution = Contribution.objects.get(contribution_id_PK=int(contribution_id))
    except (ValueError, Contribution.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Contribution not found."}, status=404)

    if contribution.status == Contribution.STATUS_EXCLUDED_REQUESTER:
        return JsonResponse({"ok": False, "error": "Not included (requester) contributions cannot be skipped."}, status=400)

    old_status = contribution.status
    contribution.status = "SKIPPED"
    contribution.is_manually_overridden = True
    contribution.paid_amount = 0
    contribution.notes = notes or contribution.notes
    contribution.updated_by_user_id_FK = officer
    contribution.save()

    _record_audit_trail(
        table="contribution",
        record_id=contribution.contribution_id_PK,
        action="SKIPPED",
        actor=officer,
        old={"status": old_status},
        new={
            "status": "SKIPPED",
            "paid_amount": "0",
            "notes": notes or "",
        },
        ip=request.META.get("REMOTE_ADDR"),
        notes=notes or None,
    )

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "treasurer_dashboard",
        {
            "type": "contribution_updated",
            "post_id": contribution.aid_tracking_post_id_FK_id,
            "contribution_id": contribution.contribution_id_PK,
            "member_name": getattr(contribution.member_id_FK, "full_name", ""),
            "status": "SKIPPED",
            "paid_amount": 0,
        },
    )
    async_to_sync(channel_layer.group_send)(
        "auditor_dashboard",
        {
            "type": "contribution_updated",
            "post_id": contribution.aid_tracking_post_id_FK_id,
            "contribution_id": contribution.contribution_id_PK,
            "member_name": getattr(contribution.member_id_FK, "full_name", ""),
            "status": "SKIPPED",
            "paid_amount": 0,
        },
    )

    _recalculate_total_collected(contribution.aid_tracking_post_id_FK_id)

    return JsonResponse({"ok": True, "status": "SKIPPED"})


@require_POST
@transaction.atomic
def treasurer_aid_post_member_unskip(request: HttpRequest):
    """Reverse a skip action - change member from SKIPPED back to NOT_PAID."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    contribution_id = (request.POST.get("contribution_id") or "").strip()
    if not contribution_id:
        return JsonResponse({"ok": False, "error": "Missing contribution_id."}, status=400)

    try:
        contribution = Contribution.objects.select_related(
            "member_id_FK", "aid_tracking_post_id_FK"
        ).get(contribution_id_PK=int(contribution_id))
    except (ValueError, Contribution.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Contribution not found."}, status=404)

    if contribution.status != "SKIPPED":
        return JsonResponse({"ok": False, "error": "Can only unskip SKIPPED contributions."}, status=400)

    contribution.status = "NOT_PAID"
    contribution.paid_amount = 0
    contribution.save(update_fields=["status", "paid_amount"])

    _record_audit_trail(
        table="contribution",
        record_id=contribution.contribution_id_PK,
        action="UNSKIPPED",
        actor=officer,
        new={"member": getattr(contribution.member_id_FK, "full_name", str(contribution.member_id_FK.pk))},
        ip=request.META.get("REMOTE_ADDR"),
    )

    _recalculate_total_collected(contribution.aid_tracking_post_id_FK_id)

    return JsonResponse({"ok": True, "status": "NOT_PAID", "message": "Contribution unskipped successfully."})


@require_POST
@transaction.atomic
def treasurer_aid_post_finish(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    skip_remaining = (request.POST.get("skip_remaining") or "").strip().lower() == "true"

    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    try:
        post = AidTrackingPost.objects.get(post_id_PK=int(post_id), is_active=True)
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Active post not found."}, status=404)

    # Prevent duplicate finish requests regardless of current pending stage
    if post.finish_status in ("pending_approval", "pending_auditor"):
        return JsonResponse({"ok": False, "error": "A finish request is already pending."}, status=400)

    # Route the Treasurer's finish request to the Auditor for verification first
    post.finish_status = "pending_auditor"
    post.finish_skip_remaining = skip_remaining
    post.save(update_fields=["finish_status", "finish_skip_remaining"])

    _record_audit_trail(
        table="AID_TRACKING_POST",
        record_id=post.post_id_PK,
        action="FINISH_REQUESTED",
        actor=officer,
        new={
            "finish_status": "pending_auditor",
            "finish_skip_remaining": skip_remaining,
        },
        ip=request.META.get("REMOTE_ADDR"),
    )

    archive = post.archive_id_FK
    member_name = archive.member_name if archive else ""

    channel_layer = get_channel_layer()
    # include stage so websocket consumers and clients can interpret the target role
    payload = {
        "type": "aid_post_finish_requested",
        "post_id": post.post_id_PK,
        "member_name": member_name,
        "stage": "auditor",
    }
    async_to_sync(channel_layer.group_send)("treasurer_dashboard", payload)
    async_to_sync(channel_layer.group_send)("auditor_dashboard", payload)
    # Prompt auditor clients to refresh their aids section so the new pending_auditor item appears
    _broadcast_to_group("auditor_dashboard", {"type": "data_changed", "section": "aids"})
    # Also explicitly send a dashboard_refresh to auditor group to ensure clients reload aid lists
    async_to_sync(channel_layer.group_send)("auditor_dashboard", {"type": "dashboard_refresh", "section": "aid_tracking"})
    # Also signal treasurer clients to refresh relevant aids section
    _broadcast_to_group("treasurer_dashboard", {"type": "data_changed", "section": "aids"})

    return JsonResponse({"ok": True, "message": "Finish request submitted for Auditor verification."})


@require_POST
@transaction.atomic
def treasurer_aid_post_mark_finished(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    try:
        post = AidTrackingPost.objects.get(post_id_PK=int(post_id), is_active=True)
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Active post not found."}, status=404)

    if post.finish_status:
        return JsonResponse({"ok": False, "error": "A finish request is already in progress for this post (status: " + post.finish_status + ")."}, status=400)

    eligible = Contribution.objects.filter(
        aid_tracking_post_id_FK=post,
    ).exclude(status=Contribution.STATUS_EXCLUDED_REQUESTER)
    total = eligible.count()
    paid_or_pending = eligible.filter(
        status__in=["PAID", "RECORDED", "PENDING_VERIFICATION"],
    ).count()
    if total == 0:
        return JsonResponse({"ok": False, "error": "No contributions found for this post."}, status=400)
    if (paid_or_pending / total) < 0.7:
        return JsonResponse({"ok": False, "error": f"At least 70% of members must be PAID (currently {paid_or_pending}/{total})."}, status=400)

    if not post.deduction_sheet:
        return JsonResponse({
            "ok": False,
            "error": "Salary deduction sheet must be uploaded before marking as finished. Please upload the deduction sheet with batch reference and payroll period first.",
        }, status=400)

    post.finish_status = "pending_auditor"
    post.finish_skip_remaining = True
    post.save(update_fields=["finish_status", "finish_skip_remaining"])

    archive = post.archive_id_FK
    member_name = archive.member_name if archive else ""

    _record_audit_trail(
        table="AID_TRACKING_POST",
        record_id=post.post_id_PK,
        action="FINISH_REQUESTED",
        actor=officer,
        new={
            "finish_status": "pending_auditor",
            "finish_skip_remaining": True,
            "paid_ratio": f"{paid_or_pending}/{total}",
            "deduction_batch_reference": post.deduction_batch_reference,
            "deduction_payroll_period": post.deduction_payroll_period,
        },
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Finish requested with deduction ref {post.deduction_batch_reference} for period {post.deduction_payroll_period}",
    )

    channel_layer = get_channel_layer()
    payload = {
        "type": "aid_post_finish_requested",
        "post_id": post.post_id_PK,
        "member_name": member_name,
        "stage": "auditor",
    }
    async_to_sync(channel_layer.group_send)("auditor_dashboard", payload)
    async_to_sync(channel_layer.group_send)("treasurer_dashboard", payload)
    _broadcast_to_group("treasurer_dashboard", {"type": "data_changed", "section": "aids"})

    return JsonResponse({"ok": True, "message": "Finish request sent to Auditor for verification."})


@require_POST
@transaction.atomic
def treasurer_aid_post_paid_with_funds(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    try:
        post = AidTrackingPost.objects.select_related("archive_id_FK").get(
            post_id_PK=int(post_id), is_active=True
        )
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Active post not found."}, status=404)

    if post.finish_status in ("paid_with_funds", "pending_auditor", "pending_approval", "pending_president", "approved"):
        return JsonResponse({"ok": False, "error": "A finish or fund request is already in progress for this post."}, status=400)

    # Enforce the fund-sufficiency gate here (same rule used at release time) so a post
    # can never enter the approval/release pipeline when the fund cannot cover the payout.
    safety_threshold = float(SystemSetting.objects.get_or_create(
        setting_key="safety_threshold", defaults={"setting_value": "20000"}
    )[0].setting_value)
    fund_totals = FundTransaction.objects.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    current_balance = float((fund_totals["total_in"] or 0) - (fund_totals["total_out"] or 0))
    required_after_threshold = float(post.total_expected) + safety_threshold
    if current_balance < required_after_threshold:
        return JsonResponse({
            "ok": False,
            "error": "Insufficient funds. Current balance ₱{:.2f} must cover payout ₱{:.2f} plus safety threshold ₱{:.2f} (₱{:.2f}). The Paid-with-Funds option is unavailable.".format(
                current_balance, float(post.total_expected), safety_threshold, required_after_threshold
            ),
        }, status=400)

    archive = post.archive_id_FK
    member_name = archive.member_name if archive else "Unknown"

    post.finish_status = "pending_auditor"
    post.finish_skip_remaining = True
    post.finish_paid_with_funds = True
    post.finish_cycle = 1
    post.save(update_fields=["finish_status", "finish_skip_remaining", "finish_paid_with_funds", "finish_cycle"])

    _record_audit_trail(
        table="aid_tracking_post",
        record_id=post.post_id_PK,
        action="PAID_WITH_FUNDS",
        actor=officer,
        new={
            "finish_status": "pending_auditor",
            "finish_skip_remaining": True,
            "finish_paid_with_funds": True,
        },
        ip=request.META.get("REMOTE_ADDR"),
    )

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "auditor_dashboard",
        {
            "type": "aid_post_finish_requested",
            "post_id": post.post_id_PK,
            "member_name": member_name,
            "stage": "auditor",
        },
    )
    async_to_sync(channel_layer.group_send)(
        "treasurer_dashboard",
        {"type": "data_changed", "section": "aids"},
    )

    _recalculate_total_collected(post.post_id_PK)

    return JsonResponse({"ok": True, "status": "pending_auditor", "message": "Fund disbursement sent to Auditor for verification."})


@require_POST
def treasurer_aid_post_member_notify(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    contribution_id = (request.POST.get("contribution_id") or "").strip()
    if not contribution_id:
        return JsonResponse({"ok": False, "error": "Missing contribution_id."}, status=400)

    try:
        contribution = Contribution.objects.select_related(
            "member_id_FK", "aid_tracking_post_id_FK"
        ).get(contribution_id_PK=int(contribution_id))
    except (ValueError, Contribution.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Contribution not found."}, status=404)

    member = contribution.member_id_FK
    logger.info("Debug: member type = %s, member value = %s", type(member), member)

    # Only members who have NOT paid yet can be notified for a reminder.
    if contribution.status != "NOT_PAID":
        return JsonResponse(
            {"ok": False, "error": "This member has already paid or been processed — no reminder needed."},
            status=400,
        )

    _record_audit_trail(
        table="contribution",
        record_id=contribution.contribution_id_PK,
        action="NOTIFIED",
        actor=officer,
        new={"member": getattr(member, "full_name", str(member.pk))},
        ip=request.META.get("REMOTE_ADDR"),
    )

    # Send notification to member
    try:
        post = contribution.aid_tracking_post_id_FK
        aid_label = "Medical Aid" if post.aid_type == "medical_aid" else "Death Aid"
        if member and hasattr(member, 'member_id_PK'):
            notify_member(
                member,
                notification_type="Payment Reminder",
                message=f"Please pay your contribution for {aid_label} - {post.target_month}. Amount: ₱{contribution.expected_amount}",
                category="payment",
                url="/member/",
            )
            return JsonResponse({"ok": True, "message": f"Notification sent to {getattr(member, 'full_name', 'member')}"})
        else:
            return JsonResponse({"ok": False, "error": f"Invalid member object. Type: {type(member).__name__}"}, status=500)
    except Exception as e:
        logger.exception("Failed to send payment reminder notification to member %s: %s", member, e)
        return JsonResponse({"ok": False, "error": f"Notification failed: {str(e)}"}, status=500)
    except Exception:
        logger.exception("Failed to send payment reminder notification to member %s", member.member_id_PK)

    return JsonResponse({"ok": True, "message": f"Notification sent to {getattr(member, 'full_name', 'member')}."})


@require_GET
def treasurer_aid_post_history(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    posts = AidTrackingPost.objects.filter(is_active=False).select_related(
        "archive_id_FK",
        "archive_id_FK__member_id_FK",
        "created_by_user_id_FK",
    ).all()

    items = []
    for post in posts:
        archive = post.archive_id_FK
        member = archive.member_id_FK if archive else None
        aid_label = "Medical Aid" if post.aid_type == "medical_aid" else "Death Aid"
        collection_rate = 0
        if post.total_expected > 0:
            collection_rate = round(float(post.total_collected) / float(post.total_expected) * 100, 1)

        items.append({
            "post_id": post.post_id_PK,
            "aid_type": post.aid_type,
            "aid_label": aid_label,
            "member_name": archive.member_name if archive else "",
            "member_id": member.member_id_PK if member else None,
            "target_month": post.target_month,
            "total_expected": str(post.total_expected),
            "total_collected": str(post.total_collected),
            "collection_rate": collection_rate,
            "status": archive.status if archive else "",
            "amount": str(archive.amount) if archive else "0",
            "created_at": post.created_at.isoformat() if post.created_at else "",
            "updated_at": post.updated_at.isoformat() if post.updated_at else "",
            "created_by": post.created_by_user_id_FK.full_name if post.created_by_user_id_FK else "",
        })

    return JsonResponse({"ok": True, "posts": items})


# ============================================================================
# PAYROLL BATCH CRUD
# ============================================================================


@require_POST
def treasurer_payroll_batch_create(request: HttpRequest):
    """Create a PayrollBatch with its per-member deductions."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    deductions_data = data.get("deductions", [])
    if not deductions_data:
        return JsonResponse({"ok": False, "error": "At least one deduction required."}, status=400)

    total_amount = sum(d["amount"] for d in deductions_data)

    batch = PayrollBatch.objects.create(
        payroll_period=data.get("payroll_period", ""),
        total_amount=total_amount,
        member_count=len(deductions_data),
        hardcopy_reference=data.get("hardcopy_reference", ""),
        notes=data.get("notes", ""),
        status="Pending",
        recorded_by_user_id_FK=officer,
    )

    ded_records = []
    for d in deductions_data:
        # Check if member has approved exemption for this month (for salary deductions)
        member_id = d["member_id"]
        month_covered = d.get("month_covered", "")
        category = d["category"]
        
        if category == "monthly_dues":
            member_obj = Member.objects.filter(member_id_PK=member_id).first()
            if member_obj and (
                str(member_obj.membership_status).strip().casefold() == "retired"
                or str(member_obj.member_classification).strip().casefold()
                == "retired"
            ):
                continue
        if category == "monthly_dues" and month_covered:
            try:
                from core_system.models import SalaryDeductionExemption
                # Check for approved exemption
                exemption = SalaryDeductionExemption.objects.filter(
                    member_id_FK_id=member_id,
                    month_covered=month_covered,
                    status="Approved"
                ).first()
                
                if exemption:
                    # Skip this deduction - member is exempted
                    logger.info("Skipping salary deduction for member %s month %s - approved exemption found", member_id, month_covered)
                    continue
            except Exception as e:
                logger.warning("Failed to check exemption for member %s: %s", member_id, e)
        
        ded = PayrollDeduction.objects.create(
            batch_id_FK=batch,
            member_id_FK_id=member_id,
            amount=d["amount"],
            category=category,
            fund_impact=d.get("fund_impact", "inflow"),
            month_covered=month_covered,
            aid_tracking_post_id_FK_id=d.get("aid_tracking_post_id"),
            notes=d.get("notes", ""),
        )
        ded_records.append(ded)
        
        # Send deduction email to member if it's an aid contribution
        if d["category"] == "aid_contribution" and ded.member_id_FK and ded.member_id_FK.email:
            try:
                # Get aid tracking post details
                requesting_member_name = "A Fellow Member"
                aid_type = "Aid"
                if ded.aid_tracking_post_id_FK:
                    post = ded.aid_tracking_post_id_FK
                    # Try to get the requesting member from the post's source record
                    if hasattr(post, 'source_id') and post.source_id:
                        try:
                            from core_system.models import MedicalAid, DeathAid
                            if post.aid_type == "medical_aid":
                                aid_record = MedicalAid.objects.filter(medical_aid_id=post.source_id).first()
                            elif post.aid_type == "death_aid":
                                aid_record = DeathAid.objects.filter(death_aid_id=post.source_id).first()
                            else:
                                aid_record = None
                            
                            if aid_record and aid_record.member_id_FK:
                                requesting_member_name = aid_record.member_id_FK.full_name
                        except Exception:
                            pass
                    
                    aid_type_map = {
                        "medical_aid": "Medical Aid",
                        "death_aid": "Death Aid",
                    }
                    aid_type = aid_type_map.get(post.aid_type, "Aid")
                
                send_member_deduction_email(
                    member=ded.member_id_FK,
                    deduction_amount=float(d["amount"]),
                    deduction_type="Aid Contribution",
                    requesting_member_name=requesting_member_name,
                    aid_type=aid_type,
                )

                # Email == panel row == push parity for every member-facing
                # deduction notice. notify_member sends one push (same path
                # send_member_push used) and adds the in-app row so the
                # notifications page matches the email exactly.
                try:
                    notify_member(
                        ded.member_id_FK,
                        notification_type="Aid Contribution",
                        message=(
                            f"A {aid_type} contribution of ₱{float(d['amount']):,.2f} "
                            f"(for {requesting_member_name}) was deducted from your payroll."
                        ),
                        category="payment",
                        url="/member/",
                        # Branded deduction email sent above; suppress notify's
                        # plain-text fallback (one email + one push + one row).
                        send_email=False,
                    )
                except Exception as e:
                    logger.warning("Failed to send deduction notice to member %s: %s", ded.member_id_FK.full_name if ded.member_id_FK else "Unknown", e)
            except Exception as e:
                logger.warning("Failed to send deduction email to member %s: %s", ded.member_id_FK.full_name if ded.member_id_FK else "Unknown", e)

    for f in request.FILES.getlist("files"):
        from core_system.shared_view_utils import _compute_row_signature
        from core_system.secure_upload import SecureUploadError, validate_and_store

        try:
            saved = validate_and_store(f, subdir="secure_uploads/supporting_proofs")
        except SecureUploadError as exc:
            return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
        from django.core.files.base import ContentFile

        SupportingProof.objects.create(
            content_type=ContentType.objects.get_for_model(PayrollBatch),
            object_id=batch.pk,
            file=saved["stored_name"],
            file_name=saved["original_name"],
            file_type=saved["mime"],
            file_sha256=saved["sha256"],
            row_signature=_compute_row_signature(saved["sha256"], batch.pk),
            uploaded_by=officer,
        )

    _record_audit_trail(
        table="PAYROLL_BATCH",
        record_id=batch.pk,
        action="CREATED",
        actor=officer,
        new={
            "payroll_period": batch.payroll_period,
            "total_amount": float(total_amount),
            "member_count": len(deductions_data),
        },
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Payroll batch created with {len(deductions_data)} deductions",
    )

    _broadcast_pending_counts()

    return JsonResponse({
        "ok": True,
        "batch_id": batch.pk,
        "total_amount": float(total_amount),
        "deduction_count": len(ded_records),
    })


@require_GET
def treasurer_payroll_batch_list(request: HttpRequest):
    """List all PayrollBatches for the Treasurer dashboard."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    batches = PayrollBatch.objects.select_related(
        "recorded_by_user_id_FK",
        "auditor_verified_by_user_id_FK",
        "president_approved_by_user_id_FK",
    ).all().order_by("-created_at")

    items = []
    for b in batches:
        items.append({
            "batch_id": b.batch_id_PK,
            "payroll_period": b.payroll_period,
            "total_amount": float(b.total_amount),
            "member_count": b.member_count,
            "hardcopy_reference": b.hardcopy_reference or "",
            "status": b.status,
            "recorded_by": b.recorded_by_user_id_FK.full_name if b.recorded_by_user_id_FK else "",
            "recorded_at": b.created_at.isoformat() if b.created_at else "",
            "verified_by": b.auditor_verified_by_user_id_FK.full_name if b.auditor_verified_by_user_id_FK else "",
            "approved_by": b.president_approved_by_user_id_FK.full_name if b.president_approved_by_user_id_FK else "",
        })

    return JsonResponse({"ok": True, "batches": items})


@require_GET
def treasurer_payroll_batch_detail(request: HttpRequest, batch_id: int):
    """Get a single PayrollBatch with all its deductions."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    deductions = PayrollDeduction.objects.filter(batch_id_FK=batch).select_related("member_id_FK")

    ded_list = []
    for d in deductions:
        ded_list.append({
            "deduction_id": d.deduction_id_PK,
            "member_id": d.member_id_FK.member_id_PK,
            "member_name": d.member_id_FK.full_name,
            "amount": float(d.amount),
            "category": d.category,
            "fund_impact": d.fund_impact,
            "month_covered": d.month_covered or "",
            "aid_tracking_post_id": d.aid_tracking_post_id_FK_id,
            "notes": d.notes or "",
        })

    return JsonResponse({
        "ok": True,
        "batch": {
            "batch_id": batch.batch_id_PK,
            "payroll_period": batch.payroll_period,
            "total_amount": float(batch.total_amount),
            "member_count": batch.member_count,
            "hardcopy_reference": batch.hardcopy_reference or "",
            "notes": batch.notes or "",
            "status": batch.status,
            "recorded_by": batch.recorded_by_user_id_FK.full_name if batch.recorded_by_user_id_FK else "",
            "created_at": batch.created_at.isoformat() if batch.created_at else "",
            "auditor_remarks": batch.auditor_remarks or "",
            "returned_reason": batch.returned_reason or "",
            "president_remarks": batch.president_remarks or "",
        },
        "deductions": ded_list,
    })


@require_POST
def treasurer_payroll_batch_edit(request: HttpRequest, batch_id: int):
    """Edit a PayrollBatch and its deductions (only if Pending or Returned)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    if batch.status not in ("Pending", "Returned for Revision"):
        return JsonResponse({"ok": False, "error": "Can only edit Pending or Returned batches."}, status=400)

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    deductions_data = data.get("deductions", [])
    total_amount = sum(d["amount"] for d in deductions_data) if deductions_data else 0

    batch.payroll_period = data.get("payroll_period", batch.payroll_period)
    batch.total_amount = total_amount
    batch.member_count = len(deductions_data)
    batch.hardcopy_reference = data.get("hardcopy_reference", batch.hardcopy_reference)
    batch.notes = data.get("notes", batch.notes)
    batch.save(update_fields=[
        "payroll_period", "total_amount", "member_count",
        "hardcopy_reference", "notes",
    ])

    if deductions_data:
        batch.deductions.all().delete()
        for d in deductions_data:
            ded = PayrollDeduction.objects.create(
                batch_id_FK=batch,
                member_id_FK_id=d["member_id"],
                amount=d["amount"],
                category=d["category"],
                fund_impact=d.get("fund_impact", "inflow"),
                month_covered=d.get("month_covered", ""),
                aid_tracking_post_id_FK_id=d.get("aid_tracking_post_id"),
                notes=d.get("notes", ""),
            )
            
            # Send deduction email to member if it's an aid contribution
            if d["category"] == "aid_contribution" and ded.member_id_FK and ded.member_id_FK.email:
                try:
                    # Get aid tracking post details
                    requesting_member_name = "A Fellow Member"
                    aid_type = "Aid"
                    if ded.aid_tracking_post_id_FK:
                        post = ded.aid_tracking_post_id_FK
                        # Try to get the requesting member from the post's source record
                        if hasattr(post, 'source_id') and post.source_id:
                            try:
                                from core_system.models import MedicalAid, DeathAid
                                if post.aid_type == "medical_aid":
                                    aid_record = MedicalAid.objects.filter(medical_aid_id=post.source_id).first()
                                elif post.aid_type == "death_aid":
                                    aid_record = DeathAid.objects.filter(death_aid_id=post.source_id).first()
                                else:
                                    aid_record = None
                                
                                if aid_record and aid_record.member_id_FK:
                                    requesting_member_name = aid_record.member_id_FK.full_name
                            except Exception:
                                pass
                        
                        aid_type_map = {
                            "medical_aid": "Medical Aid",
                            "death_aid": "Death Aid",
                        }
                        aid_type = aid_type_map.get(post.aid_type, "Aid")
                    
                    send_member_deduction_email(
                        member=ded.member_id_FK,
                        deduction_amount=float(d["amount"]),
                        deduction_type="Aid Contribution",
                        requesting_member_name=requesting_member_name,
                        aid_type=aid_type,
                    )

                    # Email == panel row == push parity for every member-facing
                    # deduction notice. notify_member sends one push (same path
                    # send_member_push used) and adds the in-app row so the
                    # notifications page matches the email exactly.
                    try:
                        notify_member(
                            ded.member_id_FK,
                            notification_type="Aid Contribution",
                            message=(
                                f"A {aid_type} contribution of ₱{float(d['amount']):,.2f} "
                                f"(for {requesting_member_name}) was deducted from your payroll."
                            ),
                            category="payment",
                            url="/member/",
                            # Branded deduction email sent above; suppress
                            # notify's plain-text fallback (one email + one
                            # push + one row).
                            send_email=False,
                        )
                    except Exception as e:
                        logger.warning("Failed to send deduction notice to member %s: %s", ded.member_id_FK.full_name if ded.member_id_FK else "Unknown", e)
                except Exception as e:
                    logger.warning("Failed to send deduction email to member %s: %s", ded.member_id_FK.full_name if ded.member_id_FK else "Unknown", e)

    _record_audit_trail(
        table="PAYROLL_BATCH",
        record_id=batch.pk,
        action="EDITED",
        actor=officer,
        new={"total_amount": float(total_amount), "member_count": len(deductions_data)},
        ip=request.META.get("REMOTE_ADDR"),
    )

    return JsonResponse({"ok": True, "batch_id": batch.pk})


@require_POST
def treasurer_payroll_batch_delete(request: HttpRequest, batch_id: int):
    """Delete a PayrollBatch (only if Pending)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    if batch.status != "Pending":
        return JsonResponse({"ok": False, "error": "Can only delete Pending batches."}, status=400)

    officer = resolve_officer_from_session(request)
    batch.delete()

    _record_audit_trail(
        table="PAYROLL_BATCH",
        record_id=batch_id,
        action="DELETED",
        actor=officer,
        ip=request.META.get("REMOTE_ADDR"),
    )

    return JsonResponse({"ok": True, "message": "Batch deleted."})


@require_GET
def treasurer_payroll_batch_history(request: HttpRequest, batch_id: int):
    """Get audit trail for a PayrollBatch."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    trails = GlobalAuditTrail.objects.filter(
        table_name="PAYROLL_BATCH",
        record_id=batch_id,
    ).order_by("-timestamp")

    items = []
    for t in trails:
        items.append({
            "action": t.action,
            "actor": t.actor_name,
            "timestamp": t.timestamp.isoformat() if t.timestamp else "",
            "notes": t.notes or "",
            "old_values": t.old_values,
            "new_values": t.new_values,
        })

    return JsonResponse({"ok": True, "history": items})


# ============================================================================
# DEPARTMENT-SEGREGATED VISUALIZATION APIs
# ============================================================================

@require_GET
def treasurer_member_stats_by_department(request: HttpRequest):
    """Return member count and status breakdown per department."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    dept_stats_qs = Member.objects.filter(department__isnull=False).values('department').annotate(
        total=Count('member_id_PK'),
        active=Count('member_id_PK', filter=Q(membership_status__in=['Permanent', 'Temporary'])),
        permanent=Count('member_id_PK', filter=Q(membership_status='Permanent')),
        temporary=Count('member_id_PK', filter=Q(membership_status='Temporary')),
        retired=Count('member_id_PK', filter=Q(membership_status='Retired')),
    ).order_by('department')

    dept_stats = {row['department']: row for row in dept_stats_qs}

    all_departments = sorted(Member.objects.filter(department__isnull=False).values_list('department', flat=True).distinct())
    departments = []
    for dept_name in all_departments:
        stats = dept_stats.get(dept_name, {})
        departments.append({
            "department": dept_name,
            "total": stats.get('total', 0),
            "active": stats.get('active', 0),
            "permanent": stats.get('permanent', 0),
            "temporary": stats.get('temporary', 0),
            "retired": stats.get('retired', 0),
        })

    unassigned_count = Member.objects.filter(
        Q(department__isnull=True) | Q(department='')
    ).count()

    return JsonResponse({
        "ok": True,
        "departments": departments,
        "unassigned_count": unassigned_count,
    })


@require_GET
def treasurer_payment_tracking_by_department(request: HttpRequest):
    """Return payment tracking metrics per department for the current month."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    current_month = request.GET.get("month") or timezone.now().strftime('%Y-%m')

    all_departments = sorted(Member.objects.filter(department__isnull=False).values_list('department', flat=True).distinct())
    dept_totals = dict(
        Member.objects.filter(department__isnull=False).values('department').annotate(
            total=Count('member_id_PK')
        ).values_list('department', 'total')
    )

    dept_dues_paid = dict(
        MonthlyDues.objects.filter(month_covered=current_month).values(
            'member_id_FK__department'
        ).annotate(
            dues_paid=Count('member_id_FK', distinct=True)
        ).values_list('member_id_FK__department', 'dues_paid')
    )

    dept_fees_paid = dict(
        MembershipFee.objects.filter(
            payment_status__in=['Full Payment', 'Partial', 'Pending']
        ).values('member_id_FK__department').annotate(
            fees_paid=Count('member_id_FK', distinct=True)
        ).values_list('member_id_FK__department', 'fees_paid')
    )

    departments = []
    for dept_name in all_departments:
        total = dept_totals.get(dept_name, 0)
        dues_paid = dept_dues_paid.get(dept_name, 0)
        fees_paid = dept_fees_paid.get(dept_name, 0)
        departments.append({
            "department": dept_name,
            "total_members": total,
            "dues_paid_current_month": dues_paid,
            "dues_collection_rate": round((dues_paid / total * 100) if total > 0 else 0, 1),
            "membership_fee_paid": fees_paid,
            "fee_collection_rate": round((fees_paid / total * 100) if total > 0 else 0, 1),
        })

    return JsonResponse({
        "ok": True,
        "current_month": current_month,
        "departments": departments,
    })


@require_GET
def treasurer_financial_summary_by_department(request: HttpRequest):
    """Return financial summary (collections and disbursements) per department for the current year."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    year = timezone.now().year

    dept_data = {}

    dues_qs = MonthlyDues.objects.filter(payment_date__year=year).values(
        'member_id_FK__department'
    ).annotate(total=Sum('amount'))
    for row in dues_qs:
        dept = row['member_id_FK__department'] or 'Unassigned'
        dept_data.setdefault(dept, {})['monthly_dues'] = float(row['total'] or 0)

    fees_qs = MembershipFee.objects.filter(payment_date__year=year).values(
        'member_id_FK__department'
    ).annotate(total=Sum('amount'))
    for row in fees_qs:
        dept = row['member_id_FK__department'] or 'Unassigned'
        dept_data.setdefault(dept, {})['membership_fees'] = float(row['total'] or 0)

    med_qs = MedicalAid.objects.filter(request_date__year=year).values(
        'member_id_FK__department'
    ).annotate(total=Sum('validated_aid_amount'))
    for row in med_qs:
        dept = row['member_id_FK__department'] or 'Unassigned'
        dept_data.setdefault(dept, {})['medical_aid'] = float(row['total'] or 0)

    death_qs = DeathAid.objects.filter(claim_date__year=year).values(
        'member_id_FK__department'
    ).annotate(total=Sum('benefit_amount'))
    for row in death_qs:
        dept = row['member_id_FK__department'] or 'Unassigned'
        dept_data.setdefault(dept, {})['death_aid'] = float(row['total'] or 0)

    all_departments = sorted(Member.objects.filter(department__isnull=False).values_list('department', flat=True).distinct())
    departments = []
    for dept_name in all_departments:
        data = dept_data.get(dept_name, {})
        total_in = data.get('monthly_dues', 0) + data.get('membership_fees', 0)
        total_out = data.get('medical_aid', 0) + data.get('death_aid', 0)
        departments.append({
            "department": dept_name,
            "monthly_dues": data.get('monthly_dues', 0),
            "membership_fees": data.get('membership_fees', 0),
            "medical_aid": data.get('medical_aid', 0),
            "death_aid": data.get('death_aid', 0),
            "total_inflow": total_in,
            "total_outflow": total_out,
            "net_position": total_in - total_out,
        })

    return JsonResponse({
        "ok": True,
        "year": year,
        "departments": departments,
    })


@require_GET
def treasurer_aid_trends_by_department(request: HttpRequest):
    """Return aid request trends per department by month for the current year."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    year = timezone.now().year

    med_trends = MedicalAid.objects.filter(request_date__year=year).annotate(
        month=ExtractMonth('request_date')
    ).values('member_id_FK__department', 'month').annotate(
        count=Count('medical_aid_id_PK'),
        total_amount=Sum('validated_aid_amount')
    )

    death_trends = DeathAid.objects.filter(claim_date__year=year).annotate(
        month=ExtractMonth('claim_date')
    ).values('member_id_FK__department', 'month').annotate(
        count=Count('death_aid_id_PK'),
        total_amount=Sum('benefit_amount')
    )

    dept_months = {}
    for row in med_trends:
        dept = row['member_id_FK__department'] or 'Unassigned'
        month = row['month']
        key = (dept, month)
        dept_months[key] = {
            "department": dept,
            "month": month,
            "medical_aid_count": row['count'],
            "medical_aid_amount": float(row['total_amount'] or 0),
            "death_aid_count": 0,
            "death_aid_amount": 0,
            "total_count": row['count'],
            "total_amount": float(row['total_amount'] or 0),
        }

    for row in death_trends:
        dept = row['member_id_FK__department'] or 'Unassigned'
        month = row['month']
        key = (dept, month)
        if key in dept_months:
            dept_months[key]['death_aid_count'] = row['count']
            dept_months[key]['death_aid_amount'] = float(row['total_amount'] or 0)
            dept_months[key]['total_count'] += row['count']
            dept_months[key]['total_amount'] += float(row['total_amount'] or 0)
        else:
            dept_months[key] = {
                "department": dept,
                "month": month,
                "medical_aid_count": 0,
                "medical_aid_amount": 0,
                "death_aid_count": row['count'],
                "death_aid_amount": float(row['total_amount'] or 0),
                "total_count": row['count'],
                "total_amount": float(row['total_amount'] or 0),
            }

    month_labels = [f"{year}-{m:02d}" for m in range(1, 13)]
    all_departments = sorted(Member.objects.filter(department__isnull=False).values_list('department', flat=True).distinct())

    trends_by_dept = {}
    for dept in all_departments:
        dept_months_for_dept = {k: v for k, v in dept_months.items() if k[0] == dept}
        medical_aid_counts = []
        medical_aid_amounts = []
        death_aid_counts = []
        death_aid_amounts = []
        total_counts = []
        total_amounts = []
        for m in range(1, 13):
            key = (dept, m)
            entry = dept_months_for_dept.get(key, {
                "department": dept,
                "month": m,
                "medical_aid_count": 0,
                "medical_aid_amount": 0,
                "death_aid_count": 0,
                "death_aid_amount": 0,
                "total_count": 0,
                "total_amount": 0,
            })
            medical_aid_counts.append(entry["medical_aid_count"])
            medical_aid_amounts.append(entry["medical_aid_amount"])
            death_aid_counts.append(entry["death_aid_count"])
            death_aid_amounts.append(entry["death_aid_amount"])
            total_counts.append(entry["total_count"])
            total_amounts.append(entry["total_amount"])
        trends_by_dept[dept] = {
            "department": dept,
            "months": month_labels,
            "medical_aid_counts": medical_aid_counts,
            "medical_aid_amounts": medical_aid_amounts,
            "death_aid_counts": death_aid_counts,
            "death_aid_amounts": death_aid_amounts,
            "total_counts": total_counts,
            "total_amounts": total_amounts,
        }

    return JsonResponse({
        "ok": True,
        "year": year,
        "months": month_labels,
        "departments": list(trends_by_dept.values()),
    })


@require_GET
def treasurer_payroll_analysis_by_department(request: HttpRequest):
    """Return payroll deduction analysis per department."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    dept_stats_qs = PayrollDeduction.objects.select_related(
        'member_id_FK'
    ).filter(
        member_id_FK__department__isnull=False
    ).values('member_id_FK__department').annotate(
        total_deductions=Sum('amount'),
        deduction_count=Count('deduction_id_PK'),
    )

    dept_stats = {row['member_id_FK__department']: row for row in dept_stats_qs}

    all_departments = sorted(Member.objects.filter(department__isnull=False).values_list('department', flat=True).distinct())
    departments = []
    for dept_name in all_departments:
        row = dept_stats.get(dept_name, {})
        total_deductions = float(row.get('total_deductions') or 0)
        deduction_count = row.get('deduction_count', 0)
        departments.append({
            "department": dept_name,
            "total_deductions": total_deductions,
            "deduction_count": deduction_count,
            "average_deduction": round(total_deductions / deduction_count, 2) if deduction_count > 0 else 0,
        })

    return JsonResponse({
        "ok": True,
        "departments": departments,
    })


RELEASE_OTP_SESSION_KEY = "aid_release_otp"
RELEASE_OTP_TTL_SECONDS = 300
RELEASE_OTP_RESEND_SECONDS = 45
# Boilerplate the old UI auto-filled into override_reason — never good enough
# as a justification for paying out more than the claim's own earmarked cash.
STOCK_OVERRIDE_REASONS = {
    "manual amount entered by treasurer",
    "manual amount",
    "override",
    "n/a",
    "na",
    "-",
}


def _release_ceiling(post, archive) -> Decimal:
    """Hard cap on any release: benefit amount x contributing members.

    ``post.total_expected`` is computed at claim approval as
    ``per_member_amount * contributor_count`` — i.e. exactly "benefit amount
    times members". Nothing can be disbursed above it, whatever is typed in
    the amount box and whatever reason is given.
    """
    expected = Decimal(str(getattr(post, "total_expected", 0) or 0))
    if expected > 0:
        return expected
    fallback = Decimal(str(archive.amount or 0)) if archive is not None else Decimal("0")
    return max(fallback, Decimal("0"))


def _release_otp_error(request, officer, post_id, otp_input) -> str | None:
    """Why this release is not allowed to proceed, or ``None`` when it is.

    A code is issued for one specific claim, expires in 5 minutes, and is
    verified against the officer's own TOTP secret — so a code harvested from
    one session cannot be replayed against another claim.
    """
    if not otp_input:
        return "Verification code required to release aid funds."
    stored = request.session.get(RELEASE_OTP_SESSION_KEY) or {}
    if not stored:
        return "Request a verification code first."
    try:
        bound_post = int(stored.get("post_id") or 0)
    except (TypeError, ValueError):
        bound_post = 0
    if bound_post != int(post_id or 0):
        return "Verification code was issued for a different claim."
    expires_at = stored.get("expires_at")
    if expires_at:
        try:
            expiry = timezone.datetime.fromisoformat(str(expires_at))
            if timezone.is_naive(expiry):
                expiry = timezone.make_aware(expiry)
        except ValueError:
            expiry = None
        if expiry is not None and timezone.now() > expiry:
            return "Verification code expired. Request a new one."
    if not verify_otp(officer.mfa_secret or "", str(otp_input).strip()):
        return "Invalid verification code."
    return None


@require_POST
@transaction.atomic
def treasurer_aid_release_otp(request: HttpRequest):
    """Email a one-time code the Treasurer must enter to release aid funds.

    Bound to a single claim and short-lived; issuing it is itself written to
    the audit trail so an attempted release is visible even if it never
    completes.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    try:
        post = AidTrackingPost.objects.get(
            post_id_PK=int(post_id), is_active=True, finish_status="pending_release"
        )
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse(
            {"ok": False, "error": "Post not found or not pending release."},
            status=404,
        )

    stored = request.session.get(RELEASE_OTP_SESSION_KEY) or {}
    now_epoch = timezone.now().timestamp()
    sent_at = stored.get("sent_at")
    if sent_at and (now_epoch - float(sent_at)) < RELEASE_OTP_RESEND_SECONDS:
        wait = int(RELEASE_OTP_RESEND_SECONDS - (now_epoch - float(sent_at)))
        return JsonResponse(
            {"ok": False, "error": f"A verification code was already sent. Wait {wait}s."},
            status=429,
        )

    otp = generate_otp(officer.mfa_secret or "")
    if not send_mfa_email(officer, otp):
        return JsonResponse(
            {"ok": False, "error": "Could not send the verification code. Try again."},
            status=400,
        )

    request.session[RELEASE_OTP_SESSION_KEY] = {
        "post_id": int(post.post_id_PK),
        "sent_at": now_epoch,
        "expires_at": (
            timezone.now() + timedelta(seconds=RELEASE_OTP_TTL_SECONDS)
        ).isoformat(),
    }
    request.session.modified = True

    _record_audit_trail(
        table="AID_TRACKING_POST",
        record_id=post.post_id_PK,
        action="RELEASE_OTP_ISSUED",
        actor=officer,
        new={"release_otp_issued": True},
        notes=f"Verification code issued to {officer.full_name} for release.",
        ip=request.META.get("REMOTE_ADDR"),
    )

    return JsonResponse(
        {
            "ok": True,
            "delivery": "email",
            "email": mask_email(officer.email or ""),
            "expires_in": RELEASE_OTP_TTL_SECONDS,
            "message": (
                "Verification code sent. This release will be recorded and "
                "logged on the audit trails."
            ),
        }
    )


@require_POST
@transaction.atomic
def treasurer_aid_post_release(request: HttpRequest):
    """Treasurer releases the aid payout: records fund in/out and closes the post."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    # Optional release-modal details (method / reference / received by)
    release_method = (request.POST.get("release_method") or "").strip()
    release_reference = (request.POST.get("release_reference") or "").strip()
    received_by = (request.POST.get("received_by") or "").strip()
    method_note = " · ".join(
        piece for piece in (
            release_method,
            f"Ref: {release_reference}" if release_reference else "",
            f"Received by: {received_by}" if received_by else "",
        ) if piece
    )

    # Release amount (auto from collected contributions) with optional manual
    # override straight from the ISUCauFA, Inc. fund.
    treasurer_notes = (request.POST.get("treasurer_notes") or "").strip()
    override_reason = (request.POST.get("override_reason") or "").strip()
    override_amount = None
    raw_override = (request.POST.get("override_amount") or "").strip()
    if raw_override:
        try:
            override_amount = Decimal(str(raw_override))
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid override amount."}, status=400)
        if override_amount <= 0:
            return JsonResponse({"ok": False, "error": "Override amount must be greater than zero."}, status=400)

    release_amount_raw = (request.POST.get("release_amount") or "").strip()
    release_amount = None
    if release_amount_raw and not override_amount:
        try:
            release_amount = Decimal(str(release_amount_raw))
        except Exception:
            release_amount = None
        # A zero/negative release can never be honored — reject it outright
        # instead of silently falling back to the auto amount.
        if release_amount is not None and release_amount <= 0:
            return JsonResponse({"ok": False, "error": "Release amount must be greater than zero."}, status=400)

    try:
        post = AidTrackingPost.objects.select_related("archive_id_FK").get(
            post_id_PK=int(post_id), is_active=True, finish_status="pending_release"
        )
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Post not found or not pending release."}, status=404)

    archive = post.archive_id_FK
    member_name = archive.member_name if archive else "Unknown"

    # Other-campus aid has its own turnover path (single Other-Transaction
    # outflow + acknowledgement receipt). The member release below would apply
    # the wrong controls (benefit ceiling, requester exclusion), so refuse it
    # here with a pointer instead of silently mis-posting.
    if (post.source_type or "") == "external_aid":
        return JsonResponse({
            "ok": False,
            "is_external": True,
            "error": "This is other-campus aid — turn it over via 'Turnover to Other Campus' (POST /api/treasurer/external-aid-turnover/), not the member release.",
            "turnover_to": "/api/treasurer/external-aid-turnover/",
        }, status=409)

    release_query = Q(
        source_type="aid_post_payment",
        source_id=post.post_id_PK,
    )
    if archive is not None:
        release_query |= Q(
            source_type=archive.transaction_type,
            source_id=archive.record_id,
        )
    already_released = FundTransaction.objects.filter(
        release_query,
        direction="outflow",
    ).exists()
    if already_released:
        return JsonResponse({"ok": False, "error": "This post was already released."}, status=400)

    # The default release is the aid cash this claim is actually holding — the
    # set-asides booked from members' monthly deduction. Contribution rows are
    # a separate, legacy collection and only come into play as a fallback.
    held_setaside = setaside_available_for_post(post)

    # --- Strict release controls ---------------------------------------
    # 1. A verification code issued for THIS claim is mandatory. No code, no
    #    release — regardless of role or how much is being asked for.
    otp_input = (request.POST.get("otp") or "").strip()
    otp_error = _release_otp_error(request, officer, post.post_id_PK, otp_input)
    if otp_error is not None:
        return JsonResponse(
            {"ok": False, "requires_otp": True, "error": otp_error}, status=403
        )

    # 2. Somebody has to be named as receiving the cash.
    if not received_by:
        return JsonResponse(
            {
                "ok": False,
                "requires_received_by": True,
                "error": "Received by is required — record who physically received the aid.",
            },
            status=400,
        )

    # Fund-balance guard:
    # a release can never exceed what the fund holds —
    # e.g. a ₱400 fund must refuse a ₱401 release, even by manual override.
    # Mirrors the outflow math of both paths below (fund-paid posts and
    # contribution posts) so the checked amount is the recorded amount.
    fund_totals = FundTransaction.objects.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    current_balance = (fund_totals["total_in"] or Decimal("0")) - (fund_totals["total_out"] or Decimal("0"))
    manual_release = override_amount if override_amount is not None else release_amount
    amount_is_manual = manual_release is not None and manual_release > 0
    if post.finish_paid_with_funds:
        effective_outflow = override_amount if override_amount is not None else post.total_expected
    else:
        if amount_is_manual:
            effective_outflow = manual_release
        else:
            # Held set-aside first: this claim's own earmarked aid cash.
            # Deliberately NO fallback to archive.amount — a claim with
            # nothing collected has nothing to release by default. The
            # Treasurer must type an amount, and it still has to clear the
            # ceiling and the fund-deduction acknowledgement below.
            effective_outflow = held_setaside or post.total_collected or 0

    amount_dec = Decimal(str(effective_outflow))

    # 3. Benefit ceiling (benefit amount x contributing members) governs the
    #    AUTOMATIC amount only. An amount the Treasurer types in is taken at
    #    face value — the fund-balance guard below is the real limit — and the
    #    fact that it beat the ceiling is written into the audit trail.
    ceiling = _release_ceiling(post, archive)
    above_ceiling = amount_dec > ceiling
    if ceiling <= 0 and not amount_is_manual:
        return JsonResponse(
            {
                "ok": False,
                "restricted": True,
                "error": (
                    "Restricted: this claim has no approved benefit amount on "
                    "record. Release rejected and this attempt has been logged."
                ),
            },
            status=400,
        )
    if above_ceiling and not amount_is_manual:
        # The automatic default (the claim's own earmarked cash) can overshoot
        # the approved benefit when members contributed more than the benefit
        # asks for. The benefit amount is what the recipient is entitled to, so
        # the payout is trimmed to it; the surplus stays earmarked and
        # consume_set_asides returns it to the pooled reserve for the next
        # claim. A typed amount is released as typed (see above).
        amount_dec = ceiling
        effective_outflow = ceiling
    ceiling_note = (
        f"Released above the approved benefit amount × members "
        f"(₱{ceiling:,.2f})"
        if above_ceiling and amount_is_manual
        else ""
    )

    # 4. Nothing to disburse.
    if amount_dec <= 0:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Nothing has been collected for this claim — enter an amount "
                    "to release from the fund."
                ),
            },
            status=400,
        )

    # 5. The fund cannot pay out more than it holds.
    if Decimal(str(effective_outflow)) > current_balance:
        return JsonResponse({
            "ok": False,
            "error": "Release amount ₱{:.2f} exceeds the available fund balance ₱{:.2f}.".format(
                float(effective_outflow), float(current_balance)
            ),
        }, status=400)

    # 6. Anything past the claim's own earmarked cash comes straight out of
    #    the fund. Make the Treasurer say so before it happens — this
    #    is the last gate, so a rejected amount above never reaches it.
    shortfall = (amount_dec - (held_setaside or Decimal("0"))).quantize(Decimal("0.01"))
    if shortfall > 0 and request.POST.get("ack_fund_deduction") != "1":
        return JsonResponse(
            {
                "ok": False,
                "requires_ack": True,
                "shortfall": float(shortfall),
                "warning": (
                    f"This aid claim has no dedicated set-aside covering the full "
                    f"amount. \u20b1{shortfall:,.2f} has no earmarked aid cash behind "
                    "it and will come straight out of the fund. Proceed?"
                ),
            },
            status=409,
        )

    # 7. Un-earmarked money no longer needs a mandatory written justification.
    #    The ack gate above already forces an explicit fund-deduction confirm,
    #    so a zero-set-aside claim releases with ack alone. An optional note
    #    is still recorded for the audit trail when the Treasurer provides one.
    #    (override_reason / treasurer_notes are picked up below as-is.)

    if post.finish_paid_with_funds:
        safety_threshold = float(SystemSetting.objects.get_or_create(
            setting_key="safety_threshold", defaults={"setting_value": "20000"}
        )[0].setting_value)
        fund_totals = FundTransaction.objects.aggregate(
            total_in=Sum("amount", filter=Q(direction="inflow")),
            total_out=Sum("amount", filter=Q(direction="outflow")),
        )
        current_balance = float((fund_totals["total_in"] or 0) - (fund_totals["total_out"] or 0))
        required = float(post.total_expected)
        if current_balance < required + safety_threshold:
            return JsonResponse({
                "ok": False,
                "error": "Insufficient funds. Current balance ₱{:.2f} must cover payout ₱{:.2f} plus safety threshold ₱{:.2f}.".format(
                    current_balance, required, safety_threshold
                ),
            }, status=400)

    transactions = []

    if post.finish_paid_with_funds:
        # Fund already covered the aid — record outflow for the full expected amount
        transactions.append(
            FundTransaction(
                direction="outflow",
                amount=override_amount if override_amount else post.total_expected,
                source_type="aid_post_payment",
                source_id=post.post_id_PK,
                description=f"Fund disbursement — {member_name} ({post.aid_type})" + (f" · {method_note}" if method_note else "") + (" · MANUAL OVERRIDE" if override_amount else ""),
                reference_number=release_reference or None,
                recorded_by_user_id_FK=officer,
            )
        )
    else:
        # Record outflow for EXACTLY the amount the balance guard already
        # checked above (manual amount, else held set-aside, else collected
        # contributions). Keeping this a single source means the guard and the
        # ledger can never disagree about what is being disbursed.
        outflow_amount = effective_outflow
        transactions.append(
            FundTransaction(
                direction="outflow",
                amount=outflow_amount,
                source_type=archive.transaction_type if archive else "aid_post_payment",
                source_id=archive.record_id if archive else post.post_id_PK,
                description=f"Aid disbursement — {member_name} ({post.aid_type})" + (f" · {method_note}" if method_note else "") + (" · MANUAL OVERRIDE" if override_amount else ""),
                reference_number=release_reference or None,
                recorded_by_user_id_FK=officer,
            )
        )

    with transaction.atomic():
        FundTransaction.objects.bulk_create(transactions)
        # Draw this claim's earmarked aid set-aside down oldest-first (FIFO).
        # Whatever it cannot cover came from the fund, exactly as the
        # outflow rows above already recorded. Atomic with the outflow so the
        # ledger and the earmark accounting can never disagree.
        consume_set_asides(post, effective_outflow)
        # Single-use: the code is burned only once the money has actually
        # moved, so a rejected attempt can be corrected and retried.
        request.session.pop(RELEASE_OTP_SESSION_KEY, None)
    from core_system.signals import broadcast_fund_update
    broadcast_fund_update()

    channel_layer = get_channel_layer()

    if post.finish_paid_with_funds:
        # Mark aid as Completed (fund paid the recipient) for consistency
        if archive is not None:
            if archive.transaction_type == "death_aid":
                DeathAid.objects.filter(death_aid_id_PK=archive.record_id).update(status="Completed")
            elif archive.transaction_type == "medical_aid":
                MedicalAid.objects.filter(medical_aid_id_PK=archive.record_id).update(status="Completed")

        # Send notification to member about aid release — the released
        # payout amount is shown to the member only from this point on.
        released_amount = float(override_amount if override_amount else post.total_expected)
        try:
            notify_member(
                archive.member_id_FK,
                notification_type="Aid Released",
                message=f"Your {post.aid_type.replace('_', ' ').title()} claim has been released. Total payout: ₱{released_amount:,.2f}. Please contact the Treasurer to receive your assistance.",
                category="claim",
                url="/member/",
                extra_context={"payout_amount": f"{released_amount:,.2f}"},
            )
        except Exception:
            logger.exception("Member release notification failed for post %s", post.post_id_PK)

        # Enter repayment phase — members still owe the fund
        post.finish_status = "repayment"
        post.save(update_fields=["finish_status"])

        _record_audit_trail(
            table="AID_TRACKING_POST",
            record_id=post.post_id_PK,
            action="FINISH_RELEASED",
            actor=officer,
            new={
                "finish_status": "repayment",
                "is_active": True,
                "members_still_owe": float(post.total_expected - post.total_collected),
            },
            notes=ceiling_note or None,
            ip=request.META.get("REMOTE_ADDR"),
        )

        async_to_sync(channel_layer.group_send)("treasurer_dashboard", {
            "type": "data_changed", "section": "aids",
        })
        async_to_sync(channel_layer.group_send)("auditor_dashboard", {
            "type": "data_changed", "section": "aids",
        })
        async_to_sync(channel_layer.group_send)("president_dashboard", {
            "type": "data_changed", "section": "aids",
        })

        return JsonResponse({"ok": True, "message": "Funds disbursed. Members still owe repayments to replenish the fund.", "status": "repayment"})
    else:
        # Close the post normally
        if archive is not None:
            if archive.transaction_type == "death_aid":
                DeathAid.objects.filter(death_aid_id_PK=archive.record_id).update(status="Completed")
            elif archive.transaction_type == "medical_aid":
                MedicalAid.objects.filter(medical_aid_id_PK=archive.record_id).update(status="Completed")

        post.finish_status = "approved"
        post.is_active = False
        post.save(update_fields=["finish_status", "is_active"])

        _record_audit_trail(
            table="AID_TRACKING_POST",
            record_id=post.post_id_PK,
            action="FINISH_RELEASED",
            actor=officer,
            new={
                "finish_status": "approved",
                "is_active": False,
                "inflow_count": sum(1 for t in transactions if t.direction == "inflow"),
                "outflow_count": sum(1 for t in transactions if t.direction == "outflow"),
            },
            notes=" · ".join(piece for piece in (method_note, f"Manual override: {override_amount} — {override_reason}" if override_amount else "", f"Notes: {treasurer_notes}" if treasurer_notes else "", ceiling_note) if piece) or None,
            ip=request.META.get("REMOTE_ADDR"),
        )

        payload = {
            "type": "aid_post_finished",
            "post_id": post.post_id_PK,
            "member_name": member_name,
        }
        async_to_sync(channel_layer.group_send)("treasurer_dashboard", payload)
        async_to_sync(channel_layer.group_send)("auditor_dashboard", payload)
        async_to_sync(channel_layer.group_send)("president_dashboard", payload)

        try:
            _notify_release(post, officer, request=request)
        except Exception:
            logger.exception("Release notification failed for post %s", post.post_id_PK)

        # Send notification to member about aid release
        try:
            notify_member(
                archive.member_id_FK,
                notification_type="Aid Released",
                message=f"Your {post.aid_type.replace('_', ' ').title()} claim has been released. Total payout: ₱{float(outflow_amount or 0):,.2f}. Please contact the Treasurer to receive your assistance.",
                category="claim",
                url="/member/",
                extra_context={"payout_amount": f"{float(outflow_amount or 0):,.2f}"},
            )
        except Exception:
            logger.exception("Member release notification failed for post %s", post.post_id_PK)

        return JsonResponse({"ok": True, "message": "Funds released. Aid post closed."})


@require_POST
def treasurer_aid_post_release_acknowledge(request: HttpRequest, post_id: int):
    guard = require_role(request, role=["Auditor", "President"])
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    try:
        post = AidTrackingPost.objects.select_related("archive_id_FK").get(
            post_id_PK=post_id, is_active=False, finish_status="approved"
        )
    except AidTrackingPost.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Released post not found."}, status=404)

    archive = post.archive_id_FK
    member_name = archive.member_name if archive else "Unknown"
    aid_label = "Medical Aid" if post.aid_type == "medical_aid" else "Death Aid"

    already = GlobalAuditTrail.objects.filter(
        action="RELEASE_ACKNOWLEDGED",
        table_name="AID_TRACKING_POST",
        record_id=post_id,
        actor_id=officer.user_id_PK,
    ).exists()
    if already:
        return JsonResponse({"ok": True, "acknowledged": True})

    _record_audit_trail(
        table="AID_TRACKING_POST",
        record_id=post_id,
        action="RELEASE_ACKNOWLEDGED",
        actor=officer,
        new={
            "finish_status": post.finish_status,
            "total_collected": float(post.total_collected),
        },
        ip=request.META.get("REMOTE_ADDR"),
        notes=f'{officer.role} acknowledged release of {member_name}\'s {aid_label} aid \u2014 \u20b1{post.total_collected:,.2f}',
    )

    return JsonResponse({"ok": True, "acknowledged": True})


@require_POST
def treasurer_external_aid_turnover(request: HttpRequest):
    """Turn over other-campus aid: the single canonical release for external posts.

    Orderly flow, mirroring the member release gates but with external rules:
      1. post must be external + pending_release + active (else 404/409)
      2. not already turned over (exactly ONE outflow with source_id=post PK)
      3. received_by (person) required — who physically accepted for the campus
      4. proof receipt (acknowledgement letter) required — filed on the OT row
      5. amount defaults to held set-aside (collected earmark); a manual amount
         above the held earmark needs ack_fund_deduction=1 and still cannot
         exceed the fund balance (turn over only collected, unless explicitly
         acknowledged)
      6. books ONE FundTransaction outflow (source_type='other_transaction',
         source_id=post PK) so it appears in Other Transactions history AND
         traces back to the aid post; draws earmarks down FIFO; closes post.

    Never use /api/treasurer/aid-post-release/ for external posts (it refuses
    them) — otherwise the fund would double-count the outflow.
    """
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)
    try:
        post = AidTrackingPost.objects.select_related("archive_id_FK").get(
            post_id_PK=int(post_id), is_active=True, finish_status="pending_release"
        )
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "External aid post not found or not pending turnover."}, status=404)
    if (post.source_type or "") != "external_aid":
        return JsonResponse({
            "ok": False,
            "error": "This is a member aid post — release it from the Release Queue, not the external turnover.",
        }, status=409)

    from core_system.external_aid import find_turnover_outflow, turnover_description
    already = find_turnover_outflow(post)
    if already is not None:
        return JsonResponse({"ok": False, "error": "This external aid was already turned over."}, status=400)

    received_by = (request.POST.get("received_by") or "").strip()
    if not received_by:
        return JsonResponse({"ok": False, "requires_received_by": True,
                             "error": "Received by is required — name the campus representative who accepted the turnover."}, status=400)
    uploaded = request.FILES.get("proof_receipt")
    if uploaded is None:
        return JsonResponse({"ok": False, "requires_proof": True,
                             "error": "Acknowledgement receipt is required — upload the signed turnover proof."}, status=400)

    release_reference = (request.POST.get("release_reference") or "").strip()
    release_method = (request.POST.get("release_method") or "").strip() or "Turnover"
    method_note = " · ".join(piece for piece in (
        release_method, f"Ref: {release_reference}" if release_reference else "",
        f"Received by: {received_by}",
    ) if piece)

    raw_amount = (request.POST.get("release_amount") or request.POST.get("override_amount") or "").strip()
    manual_amount = None
    if raw_amount:
        try:
            manual_amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
        except (decimal.InvalidOperation, ValueError):
            return JsonResponse({"ok": False, "error": "Invalid turnover amount."}, status=400)
        if manual_amount <= 0:
            return JsonResponse({"ok": False, "error": "Turnover amount must be greater than zero."}, status=400)

    held = setaside_available_for_post(post)
    amount = manual_amount if manual_amount is not None else (held or post.total_collected or Decimal("0.00"))
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        return JsonResponse({"ok": False, "error": "Nothing has been collected for this external aid — no turnover to record."}, status=400)

    fund_totals = FundTransaction.objects.aggregate(
        total_in=Sum("amount", filter=Q(direction="inflow")),
        total_out=Sum("amount", filter=Q(direction="outflow")),
    )
    current_balance = (fund_totals["total_in"] or Decimal("0")) - (fund_totals["total_out"] or Decimal("0"))
    if amount > current_balance:
        return JsonResponse({"ok": False, "error": "Turnover amount ₱{:.2f} exceeds the available fund balance ₱{:.2f}.".format(
            float(amount), float(current_balance))}, status=400)
    shortfall = (amount - (held or Decimal("0"))).quantize(Decimal("0.01"))
    if shortfall > 0 and request.POST.get("ack_fund_deduction") != "1":
        return JsonResponse({"ok": False, "requires_ack": True, "shortfall": float(shortfall),
            "warning": (f"Only ₱{float(held or 0):,.2f} of earmarked external-aid cash is held. "
                        f"₱{float(shortfall):,.2f} will come straight out of the fund. Proceed?")}, status=409)

    campus = (post.external_campus or "").strip() or "Other campus"
    description = turnover_description(post, post.target_month or "")
    if method_note:
        description = f"{description} · {method_note}"
    description = description[:255]

    with transaction.atomic():
        tx = FundTransaction.objects.create(
            direction="outflow",
            amount=amount,
            source_type="other_transaction",
            source_id=post.post_id_PK,
            description=description,
            reference_number=release_reference or None,
            recorded_by_user_id_FK=officer,
        )
        if not tx.reference_number:
            tx.reference_number = _other_transaction_reference(tx.transaction_id_PK)
            tx.save(update_fields=["reference_number"])
        from core_system.secure_upload import SecureUploadError, validate_and_store

        try:
            saved = validate_and_store(uploaded, subdir="secure_uploads/other_transactions")
        except SecureUploadError as exc:
            return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
        FinancialDocumentArchive.objects.create(
            related_module="OTHER_TRANSACTION",
            related_record_id=tx.transaction_id_PK,
            document_type="proof_receipt",
            file_path=saved["stored_name"],
            file_name=saved["original_name"],
            file_type=saved["mime"],
            file_hash=saved["sha256"],
            verification_status="Recorded",
            uploaded_by_user_id_FK=officer,
        )
        consume_set_asides(post, amount)
        post.finish_status = "approved"
        post.is_active = False
        post.save(update_fields=["finish_status", "is_active"])
        _record_audit_trail(
            table="AID_TRACKING_POST",
            record_id=post.post_id_PK,
            action="FINISH_RELEASED",
            actor=officer,
            new={"finish_status": "approved", "is_active": False,
                 "turnover_to": campus, "amount": float(amount),
                 "other_transaction_id": tx.transaction_id_PK},
            notes=f"External aid turned over to {campus} — ₱{float(amount):,.2f} · {method_note}"[:500] or None,
            ip=request.META.get("REMOTE_ADDR"),
        )
    from core_system.signals import broadcast_fund_update
    broadcast_fund_update()
    channel_layer = get_channel_layer()
    payload = {"type": "aid_post_finished", "post_id": post.post_id_PK,
               "member_name": campus, "is_external": True}
    for group in ("treasurer_dashboard", "auditor_dashboard", "president_dashboard"):
        try:
            async_to_sync(channel_layer.group_send)(group, payload)
        except Exception:
            pass
    return JsonResponse({"ok": True, "message": f"Turned over ₱{float(amount):,.2f} to {campus}.",
                         "post_id": post.post_id_PK, "transaction_id": tx.transaction_id_PK,
                         "reference_number": tx.reference_number or ""})


@require_POST
@transaction.atomic
def treasurer_aid_post_close_repayment(request: HttpRequest):
    """Close a paid-with-funds post after members have repaid or been skipped."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    try:
        post = AidTrackingPost.objects.get(
            post_id_PK=int(post_id), finish_status="repayment"
        )
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Repayment post not found."}, status=404)

    # Skip any remaining NOT_PAID contributions
    skipped = Contribution.objects.filter(
        aid_tracking_post_id_FK=post, status="NOT_PAID",
    ).update(
        status="SKIPPED", is_manually_overridden=True, paid_amount=0,
    )

    totals = Contribution.objects.filter(aid_tracking_post_id_FK=post).aggregate(
        total_collected=Sum("paid_amount"),
    )
    post.total_collected = totals["total_collected"] or 0
    post.finish_status = "pending_auditor"
    post.finish_cycle = 2
    post.save(update_fields=["finish_status", "total_collected", "finish_cycle"])

    _record_audit_trail(
        table="AID_TRACKING_POST",
        record_id=post.post_id_PK,
        action="REPAYMENT_SUBMITTED_FOR_VERIFICATION",
        actor=officer,
        new={
            "finish_status": "pending_auditor",
            "skipped_count": skipped,
            "total_collected": float(post.total_collected),
        },
        ip=request.META.get("REMOTE_ADDR"),
    )

    member_name = ""
    archive = post.archive_id_FK
    if archive:
        member_name = archive.member_name or ""

    channel_layer = get_channel_layer()
    payload = {
        "type": "aid_post_repayment_pending",
        "post_id": post.post_id_PK,
        "member_name": member_name,
    }
    async_to_sync(channel_layer.group_send)("treasurer_dashboard", payload)
    async_to_sync(channel_layer.group_send)("auditor_dashboard", payload)
    async_to_sync(channel_layer.group_send)("president_dashboard", payload)

    return JsonResponse({"ok": True, "message": f"Repayment submitted for verification. {skipped} members skipped. Total collected: ₱{post.total_collected:.2f}"})


@require_POST
@transaction.atomic
def treasurer_aid_post_upload_deduction_sheet(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or request.POST.get("post") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    try:
        post = AidTrackingPost.objects.get(post_id_PK=int(post_id))
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Post not found."}, status=404)

    sheet_file = request.FILES.get("deduction_sheet")
    batch_reference = (request.POST.get("batch_reference") or "").strip()
    payroll_period = (request.POST.get("payroll_period") or "").strip()

    if not sheet_file:
        return JsonResponse({"ok": False, "error": "Deduction sheet file is required."}, status=400)
    if not batch_reference:
        return JsonResponse({"ok": False, "error": "Batch reference is required."}, status=400)
    if not payroll_period:
        return JsonResponse({"ok": False, "error": "Payroll period is required."}, status=400)

    from core_system.secure_upload import SecureUploadError, validate_and_store

    try:
        saved_sheet = validate_and_store(
            sheet_file,
            subdir="secure_uploads/aid_deduction_sheets",
            allowed_extensions={"jpg", "jpeg", "png", "webp", "gif", "pdf", "xlsx", "xls", "csv"},
        )
    except SecureUploadError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
    old_sheet = post.deduction_sheet.name if post.deduction_sheet else ""
    post.deduction_sheet = saved_sheet["stored_name"]
    if old_sheet and old_sheet != saved_sheet["stored_name"]:
        try:
            default_storage.delete(old_sheet)
        except Exception:
            pass
    post.deduction_batch_reference = batch_reference
    post.deduction_payroll_period = payroll_period
    post.deduction_sheet_uploaded_at = timezone.now()
    post.save(update_fields=[
        "deduction_sheet",
        "deduction_batch_reference",
        "deduction_payroll_period",
        "deduction_sheet_uploaded_at",
        "updated_at",
    ])

    _record_audit_trail(
        table="AID_TRACKING_POST",
        record_id=post.post_id_PK,
        action="DEDUCTION_SHEET_UPLOADED",
        actor=officer,
        new={
            "batch_reference": batch_reference,
            "payroll_period": payroll_period,
            "file_name": sheet_file.name,
        },
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Deduction sheet uploaded for post {post.post_id_PK}: ref {batch_reference}, period {payroll_period}",
    )

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "auditor_dashboard",
        {
            "type": "deduction_sheet_uploaded",
            "post_id": post.post_id_PK,
            "batch_reference": batch_reference,
            "payroll_period": payroll_period,
        },
    )

    return JsonResponse({
        "ok": True,
        "message": "Deduction sheet uploaded successfully.",
        "batch_reference": batch_reference,
        "payroll_period": payroll_period,
    })


@require_POST
@transaction.atomic
def treasurer_aid_post_record_remittance(request: HttpRequest):
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard
    # ZT check removed during transition

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    post_id = (request.POST.get("post_id") or request.POST.get("post") or "").strip()
    if not post_id:
        return JsonResponse({"ok": False, "error": "Missing post_id."}, status=400)

    try:
        post = AidTrackingPost.objects.get(post_id_PK=int(post_id))
    except (ValueError, AidTrackingPost.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Post not found."}, status=404)

    remitted_amount = request.POST.get("remitted_amount", "").strip()
    remittance_reference = request.POST.get("remittance_reference", "").strip()
    remitted_date = request.POST.get("remitted_date", "").strip()

    if not remitted_amount:
        return JsonResponse({"ok": False, "error": "Remitted amount is required."}, status=400)
    if not remittance_reference:
        return JsonResponse({"ok": False, "error": "Remittance reference is required."}, status=400)
    if not remitted_date:
        return JsonResponse({"ok": False, "error": "Remitted date is required."}, status=400)

    try:
        amount = decimal.Decimal(str(remitted_amount))
        if amount <= 0:
            raise ValueError
    except (ValueError, decimal.InvalidOperation):
        return JsonResponse({"ok": False, "error": "Remitted amount must be a positive number."}, status=400)

    from datetime import date as date_type
    try:
        parsed_date = date_type.fromisoformat(remitted_date)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

    old_values = {}
    if post.deduction_remitted_amount is not None:
        old_values = {
            "old_remitted_amount": str(post.deduction_remitted_amount),
            "old_remittance_reference": post.deduction_remittance_reference,
            "old_remitted_date": str(post.deduction_remitted_date) if post.deduction_remitted_date else None,
        }

    post.deduction_remitted_amount = amount
    post.deduction_remittance_reference = remittance_reference
    post.deduction_remitted_date = parsed_date
    post.deduction_remitted_at = timezone.now()
    post.save(update_fields=[
        "deduction_remitted_amount",
        "deduction_remittance_reference",
        "deduction_remitted_date",
        "deduction_remitted_at",
        "updated_at",
    ])

    # NOTE: No FundTransaction is created here. The remittance is the same money
    # as the member contributions, which are booked as inflows (source_type
    # "contribution") at Auditor verify. Creating an additional inflow here would
    # double-count the funds. The remittance is kept as a deposit reference /
    # audit trail only.

    action = "DEDUCTION_REMITTANCE_UPDATED" if old_values else "DEDUCTION_REMITTANCE_RECORDED"
    audit_new = {
        "remitted_amount": str(amount),
        "remittance_reference": remittance_reference,
        "remitted_date": remitted_date,
    }
    audit_kwargs = {
        "table": "AID_TRACKING_POST",
        "record_id": post.post_id_PK,
        "action": action,
        "actor": officer,
        "new": audit_new,
        "ip": request.META.get("REMOTE_ADDR"),
        "notes": f"Remittance {'updated' if old_values else 'recorded'} — ref {remittance_reference}, amount {amount}, date {remitted_date}",
    }
    if old_values:
        audit_kwargs["old"] = old_values
    _record_audit_trail(**audit_kwargs)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "auditor_dashboard",
        {
            "type": "deduction_remittance_recorded",
            "post_id": post.post_id_PK,
            "remitted_amount": str(amount),
            "remittance_reference": remittance_reference,
        },
    )

    return JsonResponse({
        "ok": True,
        "message": "Remittance recorded successfully.",
        "remitted_amount": str(amount),
        "remittance_reference": remittance_reference,
        "remitted_date": remitted_date,
    })


# ==========================================================================
# MEMBER CLAIMS QUEUE — Treasurer Reviews
# ==========================================================================


@require_GET
def treasurer_claims_pending_list(request: HttpRequest):
    """Return pending medical/death aid claims awaiting treasurer review (member-submitted only)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # Exclude "Treasurer Direct" status - these are treasurer-created claims that go directly to Auditor
    statuses = ["Pending", "Pending Treasurer Review", "Pending Review"]
    claims = []

    medical_ct = ContentType.objects.get_for_model(MedicalAid)
    for ma in (
        MedicalAid.objects.filter(status__in=statuses)
        .exclude(status="Treasurer Direct")  # Exclude treasurer-created claims
        .select_related("member_id_FK")
        .order_by("request_date")
    ):
        proof_count = SupportingProof.objects.filter(
            content_type=medical_ct, object_id=ma.medical_aid_id_PK
        ).count()
        claims.append({
            "id": ma.medical_aid_id_PK,
            "claim_type": "medical_aid",
            "status": ma.status,
            "member_name": ma.member_id_FK.full_name,
            "member_employee_id": ma.member_id_FK.employee_id or "",
            "submitted_date": ma.request_date.isoformat(),
            "hospital_name": ma.hospital_name,
            "deceased_name": "",
            "amount": float(ma.requested_amount or ma.hospital_bill_amount or 0),
            "per_member": False,
            "date_of_death": "",
            "proof_count": proof_count,
        })

    death_ct = ContentType.objects.get_for_model(DeathAid)
    for da in (
        DeathAid.objects.filter(status__in=statuses)
        .exclude(status="Treasurer Direct")  # Exclude treasurer-created claims
        .select_related("member_id_FK")
        .order_by("claim_date")
    ):
        proof_count = SupportingProof.objects.filter(
            content_type=death_ct, object_id=da.death_aid_id_PK
        ).count()
        claims.append({
            "id": da.death_aid_id_PK,
            "claim_type": "death_aid",
            "status": da.status,
            "member_name": da.member_id_FK.full_name,
            "member_employee_id": da.member_id_FK.employee_id or "",
            "submitted_date": da.claim_date.isoformat(),
            "hospital_name": "",
            "deceased_name": da.deceased_name,
            "amount": float(da.benefit_amount or 0),
            "per_member": True,
            "date_of_death": da.date_of_death.isoformat() if da.date_of_death else "",
            "proof_count": proof_count,
        })

    claims.sort(key=lambda c: c["submitted_date"])

    return JsonResponse({"ok": True, "claims": claims})


@require_POST
def treasurer_claim_review(request: HttpRequest):
    """Treasurer approves, rejects, or returns a member claim."""
    guard = require_role(request, role="Treasurer")
    if guard is not None:
        return guard

    officer = resolve_officer_from_session(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session missing."}, status=401)

    try:
        body = json.loads(request.body)
    except (ValueError, AttributeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    claim_type = (body.get("claim_type") or "").strip()
    claim_id = body.get("claim_id")
    decision = (body.get("decision") or "").strip().lower()
    remarks = (body.get("remarks") or "").strip()

    if claim_type not in ("medical_aid", "death_aid"):
        return JsonResponse({"ok": False, "error": "Invalid claim_type."}, status=400)
    if not claim_id:
        return JsonResponse({"ok": False, "error": "claim_id required."}, status=400)
    if decision not in ("approve", "reject", "return"):
        return JsonResponse({"ok": False, "error": "decision must be approve/reject/return."}, status=400)

    Model = MedicalAid if claim_type == "medical_aid" else DeathAid
    try:
        claim = Model.objects.select_related("member_id_FK").get(pk=claim_id)
    except Model.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Claim not found."}, status=404)

    member = claim.member_id_FK

    if decision == "approve":
        claim.status = "Pending Auditor Verification"
        claim.treasurer_validated_by_user_id_FK = officer
        claim.save()

        message = f"Your {claim_type.replace('_', ' ').title()} claim has been approved by the Treasurer and forwarded to the Auditor."
        notify_member(
            member,
            notification_type="Claim Update",
            message=message + (f" Remarks: {remarks}" if remarks else ""),
            category="claim",
            sender_name=officer.full_name if officer else "Treasurer",
            sender_role="Treasurer",
            send_email=True,
        )
    else:
        set_treasurer_rejected(
            claim_type,
            claim_id,
            officer,
            remarks,
            request,
            member=member,
            is_rejected=(decision == "reject"),
            extra_updates={"treasurer_validated_by_user_id_FK": officer},
            details=(
                f"Your {claim_type.replace('_', ' ').title()} claim was rejected by the Treasurer."
                if decision == "reject"
                else f"Your {claim_type.replace('_', ' ').title()} claim was returned for revision by the Treasurer."
            ),
        )

    _broadcast_treasurer("claims_queue")

    return JsonResponse({"ok": True, "message": "Claim reviewed."})


# ============================================================================
# END TREASURER WORKSPACE VIEWS
# ============================================================================


@require_GET
def treasurer_financial_pending_counts(request: HttpRequest):
    guard = require_officer_session(request)
    if guard is not None:
        return guard

    from core_system.constants.status_constants import RegistrationStatus, Status
    from core_system.models import MemberRegistrationRequest, MedicalAid, DeathAid

    registration = MemberRegistrationRequest.objects.filter(
        status__in=[RegistrationStatus.PENDING_TREASURER_REVIEW, RegistrationStatus.RETURNED_FOR_REVISION]
    ).count()

    membership_fees = MembershipFee.objects.filter(payment_status="Pending").count()

    medical_aid = MedicalAid.objects.filter(status__in=["Pending", "Pending Treasurer Review"]).count()
    death_aid = DeathAid.objects.filter(status__in=["Pending", "Pending Treasurer Review"]).count()

    claims = (
        MedicalAid.objects.filter(status__in=["Pending", "Pending Treasurer Review", "Pending Review"])
        .exclude(status="Treasurer Direct")
        .count()
        + DeathAid.objects.filter(status__in=["Pending", "Pending Treasurer Review", "Pending Review"])
        .exclude(status="Treasurer Direct")
        .count()
    )
    dues = MonthlyDues.objects.filter(treasurer_status="Pending Treasurer Review").count()

    return JsonResponse({
        "ok": True,
        "registration": registration,
        "membership_fees": membership_fees,
        "medical_aid": medical_aid,
        "death_aid": death_aid,
        "claims": claims,
        "dues": dues,
        "total": registration + membership_fees + medical_aid + death_aid,
    })


@require_GET
def treasurer_position_rank_list(request: HttpRequest):
    """List all position ranks for management (active and inactive keep their
    rows so they can be re-activated; only the dropdowns filter to active)."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    ranks = PositionRank.objects.all().order_by("category", "name")
    
    items = []
    for rank in ranks:
        items.append({
            "id": rank.position_rank_id_PK,
            "name": rank.name,
            "category": rank.category,
            "is_active": rank.is_active,
            "created_at": rank.created_at.isoformat() if rank.created_at else "",
            "created_by": rank.created_by_user_id_FK.full_name if rank.created_by_user_id_FK else "System",
        })
    
    return JsonResponse({"ok": True, "ranks": items})


@require_GET
def treasurer_position_rank_options(request: HttpRequest):
    """Get position rank options for dropdowns (public endpoint)."""
    ranks = PositionRank.objects.filter(is_active=True).order_by("category", "name")
    
    items = []
    for rank in ranks:
        items.append({
            "id": rank.position_rank_id_PK,
            "name": rank.name,
            "category": rank.category,
        })
    
    return JsonResponse({"ok": True, "ranks": items})


def _ensure_position_category(name: str, actor):
    """Keep the managed category list in sync with a rank's category value."""
    if not name:
        return None
    category = PositionCategory.objects.filter(name__iexact=name).first()
    if category is not None:
        return category
    return PositionCategory.objects.create(
        name=name,
        is_active=True,
        created_by_user_id_FK=actor,
    )


@require_POST
@transaction.atomic
def treasurer_position_rank_add(request: HttpRequest):
    """Add a new position rank."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()

    if not name:
        return JsonResponse({"ok": False, "error": "Position name is required"}, status=400)
    if not category:
        return JsonResponse({"ok": False, "error": "Category is required"}, status=400)

    recorded_by = resolve_officer_from_session(request)
    if not recorded_by:
        return JsonResponse({"ok": False, "error": "Session missing"}, status=401)

    _ensure_position_category(category, recorded_by)

    try:
        rank = PositionRank.objects.create(
            name=name,
            category=category,
            is_active=True,
            created_by_user_id_FK=recorded_by,
        )
        
        _record_audit_trail(
            table="position_rank",
            record_id=rank.position_rank_id_PK,
            action="CREATED",
            actor=recorded_by,
            new={"name": name, "category": category},
            ip=request.META.get("REMOTE_ADDR"),
            notes=f"Position rank '{name}' added",
        )
        
        return JsonResponse({
            "ok": True,
            "rank": {
                "id": rank.position_rank_id_PK,
                "name": rank.name,
                "category": rank.category,
                "is_active": rank.is_active,
            }
        })
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@require_POST
@transaction.atomic
def treasurer_position_rank_update(request: HttpRequest, rank_id: int):
    """Update an existing position rank."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        rank = PositionRank.objects.get(position_rank_id_PK=rank_id)
    except PositionRank.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Position rank not found"}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()
    is_active = data.get("is_active", True)

    if not name:
        return JsonResponse({"ok": False, "error": "Position name is required"}, status=400)
    if not category:
        return JsonResponse({"ok": False, "error": "Category is required"}, status=400)

    recorded_by = resolve_officer_from_session(request)
    if not recorded_by:
        return JsonResponse({"ok": False, "error": "Session missing"}, status=401)

    _ensure_position_category(category, recorded_by)

    old_values = {"name": rank.name, "category": rank.category, "is_active": rank.is_active}
    
    rank.name = name
    rank.category = category
    rank.is_active = is_active
    rank.save()

    _record_audit_trail(
        table="position_rank",
        record_id=rank.position_rank_id_PK,
        action="UPDATED",
        actor=recorded_by,
        old=old_values,
        new={"name": name, "category": category, "is_active": is_active},
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Position rank '{name}' updated",
    )

    return JsonResponse({
        "ok": True,
        "rank": {
            "id": rank.position_rank_id_PK,
            "name": rank.name,
            "category": rank.category,
            "is_active": rank.is_active,
        }
    })


@require_POST
@transaction.atomic
def treasurer_position_rank_delete(request: HttpRequest, rank_id: int):
    """Delete (deactivate) a position rank."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        rank = PositionRank.objects.get(position_rank_id_PK=rank_id)
    except PositionRank.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Position rank not found"}, status=404)

    recorded_by = resolve_officer_from_session(request)
    if not recorded_by:
        return JsonResponse({"ok": False, "error": "Session missing"}, status=401)

    # Soft delete by setting is_active to False
    rank.is_active = False
    rank.save()

    _record_audit_trail(
        table="position_rank",
        record_id=rank.position_rank_id_PK,
        action="DELETED",
        actor=recorded_by,
        old={"name": rank.name, "category": rank.category},
        new={"is_active": False},
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Position rank '{rank.name}' deactivated",
    )

    return JsonResponse({"ok": True, "message": "Position rank deactivated successfully"})


@require_GET
def treasurer_position_category_list(request: HttpRequest):
    """List academic-rank categories with how many ranks use each."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    items = []
    for category in PositionCategory.objects.all().order_by("name"):
        items.append({
            "id": category.category_id_PK,
            "name": category.name,
            "is_active": category.is_active,
            "rank_count": PositionRank.objects.filter(category=category.name).count(),
            "created_at": category.created_at.isoformat() if category.created_at else "",
        })

    return JsonResponse({"ok": True, "categories": items})


@require_POST
@transaction.atomic
def treasurer_position_category_add(request: HttpRequest):
    """Add a new academic-rank category."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Category name is required"}, status=400)
    if PositionCategory.objects.filter(name__iexact=name).exists():
        return JsonResponse({"ok": False, "error": "That category already exists"}, status=400)

    recorded_by = resolve_officer_from_session(request)
    if not recorded_by:
        return JsonResponse({"ok": False, "error": "Session missing"}, status=401)

    category = PositionCategory.objects.create(
        name=name,
        is_active=True,
        created_by_user_id_FK=recorded_by,
    )

    _record_audit_trail(
        table="position_category",
        record_id=category.category_id_PK,
        action="CREATED",
        actor=recorded_by,
        new={"name": name},
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Position category '{name}' added",
    )

    return JsonResponse({
        "ok": True,
        "category": {
            "id": category.category_id_PK,
            "name": category.name,
            "is_active": category.is_active,
            "rank_count": 0,
        },
    })


@require_POST
@transaction.atomic
def treasurer_position_category_update(request: HttpRequest, category_id: int):
    """Rename a category (cascades to its ranks) and/or toggle it active."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        category = PositionCategory.objects.get(category_id_PK=category_id)
    except PositionCategory.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Category not found"}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    new_name = (data.get("name") or "").strip()
    is_active = data.get("is_active", category.is_active)

    if not new_name:
        return JsonResponse({"ok": False, "error": "Category name is required"}, status=400)
    if PositionCategory.objects.filter(name__iexact=new_name).exclude(category_id_PK=category_id).exists():
        return JsonResponse({"ok": False, "error": "That category already exists"}, status=400)

    recorded_by = resolve_officer_from_session(request)
    if not recorded_by:
        return JsonResponse({"ok": False, "error": "Session missing"}, status=401)

    old_name = category.name
    renamed_ranks = 0
    if new_name != old_name:
        renamed_ranks = PositionRank.objects.filter(category=old_name).update(category=new_name)

    category.name = new_name
    category.is_active = is_active
    category.save()

    _record_audit_trail(
        table="position_category",
        record_id=category.category_id_PK,
        action="UPDATED",
        actor=recorded_by,
        old={"name": old_name},
        new={"name": new_name, "is_active": is_active, "renamed_ranks": renamed_ranks},
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Position category '{old_name}' updated to '{new_name}'",
    )

    return JsonResponse({
        "ok": True,
        "category": {
            "id": category.category_id_PK,
            "name": category.name,
            "is_active": category.is_active,
            "rank_count": PositionRank.objects.filter(category=category.name).count(),
        },
        "renamed_ranks": renamed_ranks,
    })


@require_POST
@transaction.atomic
def treasurer_position_category_delete(request: HttpRequest, category_id: int):
    """Delete a category, but only when no rank still references it."""
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    try:
        category = PositionCategory.objects.get(category_id_PK=category_id)
    except PositionCategory.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Category not found"}, status=404)

    in_use = PositionRank.objects.filter(category=category.name).count()
    if in_use:
        return JsonResponse({
            "ok": False,
            "error": (
                f"Cannot delete '{category.name}': {in_use} rank(s) still use this "
                "category. Reassign or remove them first."
            ),
        }, status=400)

    recorded_by = resolve_officer_from_session(request)
    if not recorded_by:
        return JsonResponse({"ok": False, "error": "Session missing"}, status=401)

    name = category.name
    category.delete()

    _record_audit_trail(
        table="position_category",
        record_id=category_id,
        action="DELETED",
        actor=recorded_by,
        old={"name": name},
        ip=request.META.get("REMOTE_ADDR"),
        notes=f"Position category '{name}' deleted",
    )

    return JsonResponse({"ok": True, "message": "Category deleted"})


# ==========================================================================
# TREASURER DOCUMENT REPOSITORY API ENDPOINTS
# ==========================================================================

def _treasurer_document_queryset():
    """Documents owned by the Treasurer role (uploads + auto-filed reports)."""
    return Document.objects.select_related("uploaded_by_user_id_FK").filter(
        uploaded_by_user_id_FK__role="Treasurer"
    )


@require_GET
def treasurer_documents_list(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard

    document_type = request.GET.get("document_type")
    category = request.GET.get("category")
    year = request.GET.get("year")
    keyword = request.GET.get("keyword")
    search = request.GET.get("search")
    status_filter = request.GET.get("status")
    filetype_filter = request.GET.get("file_type")
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 10))

    queryset = _treasurer_document_queryset()

    if document_type:
        queryset = queryset.filter(document_type=document_type)
    if category:
        queryset = queryset.filter(category__icontains=category)
    if year:
        queryset = queryset.filter(uploaded_at__year=year)
    if keyword:
        queryset = queryset.filter(keywords__icontains=keyword)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(document_type__icontains=search)
            | Q(category__icontains=search)
            | Q(description__icontains=search)
            | Q(keywords__icontains=search)
            | Q(tags__icontains=search)
        )
    if status_filter:
        if status_filter == "Active":
            queryset = queryset.filter(is_archived=False)
        elif status_filter == "Archived":
            queryset = queryset.filter(is_archived=True)
    if filetype_filter:
        queryset = queryset.filter(file_type__icontains=filetype_filter)

    officer_id = request.session.get("officer_id")
    pinned_ids = set()
    if officer_id:
        pinned_ids = set(
            DocumentPin.objects.filter(officer_id_FK=officer_id).values_list("document_id_FK", flat=True)
        )

    total = queryset.count()
    start = (page - 1) * page_size
    page_docs = list(queryset.order_by("-uploaded_at")[start : start + page_size])

    documents = []
    for doc in page_docs:
        status = "Archived" if doc.is_archived else "Active"
        documents.append({
            "document_id": doc.document_id_PK,
            "title": doc.title,
            "description": doc.description,
            "document_type": doc.document_type,
            "category": doc.category or doc.document_type,
            "keywords": doc.keywords,
            "tags": doc.tags,
            "file_name": doc.file_name,
            "file_size": doc.file_size,
            "file_type": doc.file_type,
            "version": doc.version,
            "uploaded_by": doc.uploaded_by_user_id_FK.full_name if doc.uploaded_by_user_id_FK else "Unknown",
            "uploaded_at": timezone.localtime(doc.uploaded_at).strftime("%Y-%m-%d %I:%M %p"),
            "is_archived": doc.is_archived,
            "status": status,
            "is_pinned": doc.document_id_PK in pinned_ids,
            "is_public_visible": doc.is_public_visible,
        })

    return JsonResponse({
        "ok": True,
        "documents": documents,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    })


@require_GET
def treasurer_document_stats(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        docs = _treasurer_document_queryset()
        total = docs.count()
        active = docs.filter(is_archived=False).count()
        archived = docs.filter(is_archived=True).count()
        files = docs.exclude(file_size__isnull=True).values_list("file_size", flat=True)
        size_mb = round(sum(files) / (1024 * 1024), 1) if files else 0
        return JsonResponse({"ok": True, "total": total, "active": active, "archived": archived, "storage_mb": size_mb})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_document_upload(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        officer_id = request.session.get("officer_id")
        officer = OfficerUser.objects.get(user_id_PK=officer_id) if officer_id else None

        title = (request.POST.get("title") or "").strip()
        description = request.POST.get("description", "")
        document_type = request.POST.get("document_type") or "Other"
        category = (request.POST.get("category", "") or "")[:100]
        keywords = (request.POST.get("keywords", "") or "")[:500]

        file = request.FILES.get("file")
        if not title:
            return JsonResponse({"ok": False, "error": "Title is required."}, status=400)
        if not file:
            return JsonResponse({"ok": False, "error": "No file uploaded."}, status=400)

        from core_system.secure_upload import SecureUploadError, validate_and_store

        try:
            saved = validate_and_store(file, subdir="secure_uploads/documents")
        except SecureUploadError as exc:
            return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)

        document = Document.objects.create(
            title=title,
            description=description,
            document_type=document_type,
            category=category or document_type,
            keywords=keywords,
            file_path=saved["stored_name"],
            file_name=saved["original_name"],
            file_size=saved["size"],
            file_type=saved["mime"][:50],
            content_sha256=saved["sha256"],
            uploaded_by_user_id_FK=officer,
        )
        DocumentActivity.objects.create(
            document_id_FK=document,
            action="uploaded",
            officer_id_FK=officer,
            officer_name=officer.full_name if officer else "Treasurer",
            details=f"Uploaded {title}",
        )
        _record_audit_trail(
            table="document",
            record_id=document.document_id_PK,
            action="DOCUMENT_UPLOADED",
            actor=officer,
            ip=request.META.get("REMOTE_ADDR"),
            notes=f"Treasurer uploaded document '{title}'",
        )
        return JsonResponse({"ok": True, "message": "Document uploaded successfully", "document_id": document.document_id_PK})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_document_replace(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        document_id = request.POST.get("document_id")
        file = request.FILES.get("file")
        if not document_id or not file:
            return JsonResponse({"ok": False, "error": "document_id and file required"}, status=400)

        old_doc = Document.objects.get(document_id_PK=document_id)
        officer_id = request.session.get("officer_id")
        officer = OfficerUser.objects.get(user_id_PK=officer_id) if officer_id else None

        old_doc.is_archived = True
        old_doc.save()

        old_version = float(old_doc.version) if old_doc.version else 1.0
        new_version = f"{old_version + 0.1:.1f}"

        from core_system.secure_upload import SecureUploadError, validate_and_store

        try:
            saved = validate_and_store(file, subdir="secure_uploads/documents")
        except SecureUploadError as exc:
            return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)

        new_doc = Document.objects.create(
            title=old_doc.title,
            description=old_doc.description,
            document_type=old_doc.document_type,
            category=old_doc.category,
            keywords=old_doc.keywords,
            file_path=saved["stored_name"],
            file_name=saved["original_name"],
            file_size=saved["size"],
            file_type=saved["mime"][:50],
            content_sha256=saved["sha256"],
            version=new_version,
            uploaded_by_user_id_FK=old_doc.uploaded_by_user_id_FK or officer,
        )
        DocumentActivity.objects.create(
            document_id_FK=new_doc,
            action="replaced",
            officer_id_FK=officer,
            officer_name=officer.full_name if officer else "Treasurer",
            details=f"Replaced version {old_doc.version} with {new_version}",
        )
        return JsonResponse({"ok": True, "message": "Document replaced", "new_version": new_version, "document_id": new_doc.document_id_PK})
    except Document.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Document not found"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_document_toggle_favorite(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        data = json.loads(request.body)
        document_id = data.get("document_id")
        officer_id = request.session.get("officer_id")
        if not document_id or not officer_id:
            return JsonResponse({"ok": False, "error": "document_id required"}, status=400)
        officer = OfficerUser.objects.get(user_id_PK=officer_id)
        doc = Document.objects.get(document_id_PK=document_id)
        pin = DocumentPin.objects.filter(document_id_FK=doc, officer_id_FK=officer).first()
        if pin:
            pin.delete()
            return JsonResponse({"ok": True, "pinned": False})
        DocumentPin.objects.create(document_id_FK=doc, officer_id_FK=officer)
        return JsonResponse({"ok": True, "pinned": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_GET
def treasurer_document_preview(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        document_id = request.GET.get("document_id")
        if not document_id:
            return JsonResponse({"ok": False, "error": "document_id required"}, status=400)
        doc = Document.objects.get(document_id_PK=document_id)
        content, content_type, filename = document_file_bytes(doc)
        if content is None:
            return JsonResponse({"ok": False, "error": "File not found on disk"}, status=404)
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response
    except Document.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Document not found"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_GET
def treasurer_document_download(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        document_id = request.GET.get("document_id")
        if not document_id:
            return JsonResponse({"ok": False, "error": "document_id required"}, status=400)
        doc = Document.objects.get(document_id_PK=document_id)
        content, content_type, filename = document_file_bytes(doc)
        if content is None:
            return JsonResponse({"ok": False, "error": "File not found on disk"}, status=404)
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except Document.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Document not found"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_GET
def treasurer_document_activity(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        activities = DocumentActivity.objects.select_related("document_id_FK").filter(
            document_id_FK__uploaded_by_user_id_FK__role="Treasurer"
        )[:15]
        items = []
        for a in activities:
            items.append({
                "action": a.action,
                "officer_name": a.officer_name,
                "details": a.details,
                "timestamp": timezone.localtime(a.timestamp).strftime("%b %d, %Y %I:%M %p") if a.timestamp else "",
                "doc_title": a.document_id_FK.title if a.document_id_FK else "",
            })
        return JsonResponse({"ok": True, "activities": items})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_GET
def treasurer_category_list(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        cats = Category.objects.filter(role="Treasurer").values("category_id_PK", "name")
        return JsonResponse({"ok": True, "categories": list(cats)})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_category_create(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        if not name:
            return JsonResponse({"ok": False, "error": "Name is required"}, status=400)
        cat = Category.objects.create(name=name, role="Treasurer")
        return JsonResponse({"ok": True, "category_id": cat.category_id_PK, "name": cat.name})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_GET
def treasurer_document_version_history(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        title = request.GET.get("title")
        if not title:
            return JsonResponse({"ok": False, "error": "title required"}, status=400)
        docs = list(Document.objects.filter(title=title, uploaded_by_user_id_FK__role="Treasurer").order_by("uploaded_at"))
        versions = []
        for d in docs:
            versions.append({
                "document_id": d.document_id_PK,
                "version": d.version,
                "is_archived": d.is_archived,
                "file_name": d.file_name,
                "file_size": d.file_size,
                "uploaded_at": timezone.localtime(d.uploaded_at).strftime("%Y-%m-%d %I:%M %p"),
                "uploaded_by": d.uploaded_by_user_id_FK.full_name if d.uploaded_by_user_id_FK else "Unknown",
            })
        return JsonResponse({"ok": True, "versions": versions})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_document_toggle_public(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        data = json.loads(request.body)
        document_id = data.get("document_id")
        if not document_id:
            return JsonResponse({"ok": False, "error": "document_id required"}, status=400)
        doc = Document.objects.get(document_id_PK=document_id)
        doc.is_public_visible = not doc.is_public_visible
        doc.save(update_fields=["is_public_visible"])
        return JsonResponse({
            "ok": True,
            "is_public_visible": doc.is_public_visible,
            "message": "Visibility updated.",
        })
    except Document.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Document not found"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_category_rename(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        data = json.loads(request.body)
        category_id = data.get("category_id")
        name = data.get("name", "").strip()
        if not category_id or not name:
            return JsonResponse({"ok": False, "error": "category_id and name required"}, status=400)
        cat = Category.objects.get(category_id_PK=category_id, role="Treasurer")
        cat.name = name
        cat.save()
        return JsonResponse({"ok": True, "name": cat.name})
    except Category.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Category not found or not authorized"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def treasurer_category_delete(request: HttpRequest):
    guard = require_role(request, role=["Treasurer"])
    if guard is not None:
        return guard
    try:
        data = json.loads(request.body)
        category_id = data.get("category_id")
        if not category_id:
            return JsonResponse({"ok": False, "error": "category_id required"}, status=400)
        cat = Category.objects.get(category_id_PK=category_id, role="Treasurer")
        cat.delete()
        return JsonResponse({"ok": True, "message": "Category deleted"})
    except Category.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Category not found or not authorized"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)



# ==========================================================================
# FUND TIMELINE — month-by-month credits / fund position / debits
# ==========================================================================

DUES_FAMILY_SOURCE_TYPES = (
    "monthly_dues",
    "aid_setaside_medical",
    "aid_setaside_death",
)

_BATCH_COMPONENT_LABELS = (
    ("monthly_dues", "Monthly Dues collected"),
    ("aid_setaside_medical", "Medical Aid Set-Aside"),
    ("aid_setaside_death", "Death Aid Set-Aside"),
)

_SETASIDE_TO_AID_TYPE = {
    "aid_setaside_medical": "medical_aid",
    "aid_setaside_death": "death_aid",
}

_TIMELINE_MONTH_YM = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def _timeline_covered_ym(descriptions) -> str:
    """Covered "YYYY-MM" from booking descriptions shaped like
    "Monthly dues for March 2026 — member 12" (raw id or simplified name
    after the em dash — only the month part matters)."""
    for desc in descriptions or []:
        match = re.search(r" for ([A-Za-z]+)\s+(\d{4})\s+—", str(desc or ""))
        if match and match.group(1).lower() in _TIMELINE_MONTH_YM:
            return f"{match.group(2)}-{_TIMELINE_MONTH_YM[match.group(1).lower()]}"
    return ""


def _timeline_post_recipients() -> dict:
    """{(aid_type, target_month): [recipient names]} over every aid tracking
    post (active AND closed — historical months' cases are finished) so
    set-aside components can name the aid case they feed."""
    index: dict[tuple, list] = {}
    posts = AidTrackingPost.objects.select_related("archive_id_FK").all()
    for post in posts:
        ym = (post.target_month or "").strip()
        if not ym or not post.aid_type:
            continue
        archive = post.archive_id_FK
        if post.source_type == "external_aid" or post.external_campus or post.external_beneficiary:
            name = (post.external_display or "").strip() or (archive.member_name if archive else "")
        else:
            name = archive.member_name if archive else ""
        name = (name or "").strip()
        if not name:
            continue
        key = (post.aid_type, ym)
        if name not in index.setdefault(key, []):
            index[key].append(name)
    return index


def _timeline_units(rows: list, post_recipients: dict | None = None) -> list:
    """Fold the raw fund rows into timeline units.

    A President-approved monthly deduction batch books one row per member per
    purpose — dues portion + medical/death aid set-asides — all sharing the
    batch's ``COL-`` collection reference. Those rows are folded into ONE
    credit unit whose total is the whole money that actually went in, with a
    components breakdown (Dues / Medical Aid / Death Aid) for the accordion.
    Everything else (contributions, releases, other transactions) stays a
    single plain row.
    """
    units = []
    i = 0
    n = len(rows)
    while i < n:
        r = rows[i]
        ref = r.get("reference") or ""
        if (
            r["direction"] == "inflow"
            and r["source_key"] in DUES_FAMILY_SOURCE_TYPES
            and ref.startswith("COL-")
        ):
            family = [r]
            j = i + 1
            while (
                j < n
                and rows[j]["direction"] == "inflow"
                and rows[j]["source_key"] in DUES_FAMILY_SOURCE_TYPES
                and (rows[j].get("reference") or "") == ref
            ):
                family.append(rows[j])
                j += 1

            dues_rows = [x for x in family if x["source_key"] == "monthly_dues"]
            prefix = "Monthly dues"
            if dues_rows:
                prefix = dues_rows[0]["description"].split("—")[0].strip(" -–") or prefix

            covered_ym = _timeline_covered_ym([x["description"] for x in family])
            components = []
            for source_key, comp_label in _BATCH_COMPONENT_LABELS:
                comp_rows = [x for x in family if x["source_key"] == source_key]
                if not comp_rows:
                    continue
                # Set-aside components feed an aid case: name its recipient
                # (dues components have no single recipient — the count
                # already says how many members paid).
                recipient = ""
                aid_type = _SETASIDE_TO_AID_TYPE.get(source_key)
                if aid_type and covered_ym and post_recipients:
                    recipient = "; ".join(post_recipients.get((aid_type, covered_ym), []))
                components.append({
                    "source_key": source_key,
                    "label": comp_label,
                    "recipient": recipient,
                    "count": len(comp_rows),
                    "total": round(sum(x["amount"] for x in comp_rows), 2),
                    "fund_before": comp_rows[0]["fund_before"],
                    "fund_after": comp_rows[-1]["fund_after"],
                })

            units.append({
                "kind": "batch",
                "month": r["month"],
                "direction": "inflow",
                "key": "col:" + ref,
                "label": prefix,
                "count": len(family),
                "total": round(sum(x["amount"] for x in family), 2),
                "fund_before": family[0]["fund_before"],
                "fund_after": family[-1]["fund_after"],
                # The renderer sorts every month's units by ts — a batch
                # without one throws and the whole timeline stays "Loading…".
                "ts": max(x["ts"] for x in family),
                "has_aid": len(components) > 1,
                "components": components,
            })
            i = j
            continue

        single = dict(r)
        single["kind"] = "single"
        units.append(single)
        i += 1
    return units


@require_GET
def treasurer_fund_timeline(request: HttpRequest):
    """Powers the 3-column Fund Timeline panel (ISUCauFA, Inc. FUND).

    For the selected year, every month with fund activity is returned as:
      left   — credits (inflows) with a month total
      center — fund before / fund after (running position)
      right  — debits (outflows) with a month total
    `fund_before_year` carries the balance accumulated before January of
    the year, so the timeline starts from the true running position.
    """
    guard = require_role(request, role=["Treasurer", "Auditor", "President"])
    if guard is not None:
        return guard

    # MySQL's CONVERT_TZ is unavailable on this server (timezone tables not
    # loaded), so SQL-side year extraction returns NULL — derive years in
    # Python instead (transaction counts are small).
    year_choices = {
        timezone.localtime(ts).year
        for ts in FundTransaction.objects.values_list("recorded_at", flat=True)
        if ts is not None
    }
    today_year = timezone.localtime().year
    years = sorted(year_choices | {today_year}, reverse=True)

    try:
        year = int(request.GET.get("year", "0") or 0)
    except ValueError:
        year = 0
    if year <= 0:
        year = years[0] if years else today_year

    year_start = timezone.make_aware(datetime(year, 1, 1))
    year_end = timezone.make_aware(datetime(year + 1, 1, 1))

    base = FundTransaction.objects.filter(recorded_at__lt=year_start).aggregate(
        tin=Sum("amount", filter=Q(direction="inflow")),
        tout=Sum("amount", filter=Q(direction="outflow")),
    )
    fund_before_year = round(float(base["tin"] or 0) - float(base["tout"] or 0), 2)

    transactions = (
        FundTransaction.objects.filter(recorded_at__gte=year_start, recorded_at__lt=year_end)
        .order_by("recorded_at", "transaction_id_PK")
    )

    # Aid recipients, joined by id (never parsed out of descriptions): aid
    # payouts name their medical member / death claimant / tracked post, so
    # the timeline's debit side can say WHO received the aid.
    outflows = [t for t in transactions if t.direction == "outflow"]
    med_claims = {
        m.medical_aid_id_PK: (m.member_id_FK.full_name if m.member_id_FK else "")
        for m in MedicalAid.objects.filter(
            medical_aid_id_PK__in=[t.source_id for t in outflows if t.source_type == "medical_aid"]
        ).select_related("member_id_FK")
    }
    death_claims = {
        d.death_aid_id_PK: (
            (d.claimant_id_FK.full_name if d.claimant_id_FK else "") or d.deceased_name or ""
        )
        for d in DeathAid.objects.filter(
            death_aid_id_PK__in=[t.source_id for t in outflows if t.source_type == "death_aid"]
        ).select_related("claimant_id_FK")
    }
    release_posts = {
        p.post_id_PK: (
            (p.external_display or "").strip()
            or (p.archive_id_FK.member_name if p.archive_id_FK else "")
        )
        for p in AidTrackingPost.objects.filter(
            post_id_PK__in=[t.source_id for t in outflows if t.source_type == "aid_post_payment"]
        ).select_related("archive_id_FK")
    }

    def _outflow_recipient(tx) -> str:
        if tx.direction != "outflow":
            return ""
        if tx.source_type == "medical_aid":
            return med_claims.get(tx.source_id, "")
        if tx.source_type == "death_aid":
            return death_claims.get(tx.source_id, "")
        if tx.source_type == "aid_post_payment":
            return release_posts.get(tx.source_id, "")
        return ""

    # Chronological rows, EACH carrying the fund position immediately before
    # and after itself — the timeline's center column is per record.
    rows = []
    running = fund_before_year
    for t in transactions:
        local_ts = timezone.localtime(t.recorded_at)
        before = round(running, 2)
        amount = float(t.amount)
        after = round(before + amount if t.direction == "inflow" else before - amount, 2)
        running = after
        rows.append({
            "id": t.transaction_id_PK,
            "ts": t.recorded_at.isoformat(),
            "month": local_ts.month,
            "date": local_ts.strftime("%b %d"),
            "direction": t.direction,
            "description": t.description or "",
            "recipient": _outflow_recipient(t),
            "source_type": t.get_source_type_display() or "",
            "source_key": t.source_type,
            "reference": t.reference_number or "",
            "amount": amount,
            "fund_before": before,
            "fund_after": after,
        })

    units = _timeline_units(rows, _timeline_post_recipients())

    month_names = ["", "January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    months = []
    months_map = {}
    for u in units:
        m = u["month"]
        if m not in months_map:
            months_map[m] = {
                "month": m,
                "month_label": f"{month_names[m]} {year}",
                "rows": [],
                "total_in": 0.0,
                "total_out": 0.0,
            }
            months.append(months_map[m])
        months_map[m]["rows"].append(u)
        total = u["total"] if u["kind"] in ("group", "batch") else u["amount"]
        if u["direction"] == "inflow":
            months_map[m]["total_in"] = round(months_map[m]["total_in"] + total, 2)
        else:
            months_map[m]["total_out"] = round(months_map[m]["total_out"] + total, 2)

    return JsonResponse({
        "ok": True,
        "year": year,
        "years": years,
        "fund_before_year": fund_before_year,
        "months": months,
        "current_balance": round(float(FundTransaction.get_balance()), 2),
    })
