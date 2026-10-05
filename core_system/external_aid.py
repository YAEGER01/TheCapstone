"""Cross-campus (other-campus) aid consolidation module.

Single source of truth for external aid so the President, Treasurer and
Auditor can never drift apart:

    President declares  -> AssessmentItem(recipient_type='external')
    Final approval      -> ensure_external_posts_for_assessment()
                           (TransactionArchive 'external_aid' +
                            AidTrackingPost source_type='external_aid' +
                            Contribution rows for every active member)
    Monthly booking     -> set-asides link by assessment ITEM (not by member
                           name) so external cash is never mistaken for a
                           member's claim
    Treasurer release   -> turnover via ONE Other-Transaction outflow
                           (source_id = post PK), proof receipt mandatory

Policy: turn over ONLY what was collected by default. A manual amount above
the held set-aside needs explicit fund-deduction acknowledgement and still
cannot exceed the fund balance. External aid never uses the member benefit
ceiling (no tier applies to another campus).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Q

CENT = Decimal("0.01")

EXTERNAL_SOURCE = "external_aid"
ARCHIVE_TYPE = "external_aid"

# Suggested campuses for the President's datalist (free text still allowed).
EXTERNAL_CAMPUSES = [
    "ISU Echague Campus",
    "ISU Ilagan Campus",
    "ISU Jones Campus",
    "ISU San Mariano Campus",
    "ISU Cauayan Campus",
    "ISUFFAI Federation",
]


def is_external_item(item) -> bool:
    return bool(item is not None and getattr(item, "recipient_type", "member") == "external")


def external_display(campus: str | None, beneficiary: str | None) -> str:
    campus = (campus or "").strip()
    beneficiary = (beneficiary or "").strip()
    if campus and beneficiary:
        return f"{campus} — {beneficiary}"
    return campus or beneficiary or ""


def active_contributors():
    """Every non-retired member funds external aid — nobody is excluded."""
    from core_system.models import Member
    from core_system.member_views import is_retired_member  # local import: views import this module

    return [m for m in Member.objects.all().order_by("full_name") if not is_retired_member(m)]


def _target_month_for_assessment(assessment) -> str:
    try:
        return assessment.month.strftime("%Y-%m")
    except Exception:
        from django.utils import timezone
        return timezone.now().strftime("%Y-%m")


def ensure_external_posts_for_assessment(assessment, officer):
    """Create (idempotently) one tracking post per external aid item.

    Called once at President final approval, after fund rows are booked.
    Returns the list of posts ensured (existing + newly created).
    """
    from core_system.models import (
        AidTrackingPost,
        AssessmentItem,
        Contribution,
        Member,
        TransactionArchive,
    )
    from core_system.aid_setaside import (
        link_set_asides_to_external_post,
        sync_post_contributions_from_setasides,
    )

    ensured = []
    items = list(
        assessment.items.filter(
            purpose__in=(AssessmentItem.PURPOSE_MEDICAL_AID, AssessmentItem.PURPOSE_DEATH_AID),
            recipient_type=AssessmentItem.RECIPIENT_EXTERNAL,
        )
    )
    if not items:
        return ensured

    contributors = active_contributors()
    if not contributors:
        return ensured

    for item in items:
        existing = AidTrackingPost.objects.filter(
            source_type=EXTERNAL_SOURCE,
            assessment_item_id_FK=item,
        ).first()
        if existing is not None:
            link_set_asides_to_external_post(existing, item)
            sync_post_contributions_from_setasides(existing)
            ensured.append(existing)
            continue

        aid_type = (
            "medical_aid"
            if item.purpose == AssessmentItem.PURPOSE_MEDICAL_AID
            else "death_aid"
        )
        per_member = item.amount or Decimal("0.00")
        total_expected = (per_member * len(contributors)).quantize(CENT)
        display = item.external_display or item.recipient or "External campus aid"

        with transaction.atomic():
            archive = TransactionArchive.objects.create(
                transaction_type=ARCHIVE_TYPE,
                record_id=item.item_id_PK,
                member_id_FK=None,
                member_name=display[:255],
                amount=per_member,
                validated_amount=per_member,
                status="Approved",
                payment_method="Salary Deduction",
                fiscal_term=_target_month_for_assessment(assessment),
                released_by_user_id_FK=None,
            )
            # record_id must point at the archive row for traceability.
            archive.record_id = archive.archive_id_PK
            archive.save(update_fields=["record_id"])
            post = AidTrackingPost.objects.create(
                archive_id_FK=archive,
                aid_type=aid_type,
                target_month=_target_month_for_assessment(assessment),
                total_expected=total_expected,
                total_collected=Decimal("0.00"),
                status="tracking",
                source_type=EXTERNAL_SOURCE,
                source_id=item.item_id_PK,
                assessment_item_id_FK=item,
                external_campus=item.external_campus,
                external_beneficiary=item.external_beneficiary,
                finish_status="pending_release",
                created_by_user_id_FK=officer,
            )
            Contribution.objects.bulk_create([
                Contribution(
                    aid_tracking_post_id_FK=post,
                    member_id_FK=member,
                    expected_amount=per_member,
                    paid_amount=Decimal("0.00"),
                    status=Contribution.STATUS_NOT_PAID,
                )
                for member in contributors
            ])
            link_set_asides_to_external_post(post, item)
            sync_post_contributions_from_setasides(post)
            ensured.append(post)
    return ensured


def turnover_description(post, assessment_label: str = "") -> str:
    campus = (post.external_campus or "").strip() or "Other campus"
    beneficiary = (post.external_beneficiary or "").strip()
    aid_label = "Medical Aid" if post.aid_type == "medical_aid" else "Death Aid"
    who = f"{campus} — {beneficiary}" if beneficiary else campus
    base = f"To {who} ({aid_label} turnover{', ' + assessment_label if assessment_label else ''})"
    return base[:255]


def find_turnover_outflow(post):
    """The single canonical outflow for an external post, if already turned over."""
    from core_system.models import FundTransaction
    return (
        FundTransaction.objects.filter(
            Q(source_type="other_transaction", source_id=post.post_id_PK)
            | Q(source_type="aid_post_payment", source_id=post.post_id_PK),
            direction="outflow",
        )
        .order_by("-recorded_at")
        .first()
    )
