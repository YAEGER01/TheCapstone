"""Member dashboard must never show the same aid collection twice.

Root cause (fixed): assessment-item recipients are stored formatted
('SURNAME, Given' via the President's autocomplete) while claim/post
resolution yields the raw `full_name` ('Given M SURNAME'). The de-dup
comparisons used plain equality, which never matched across that boundary,
so one collection was appended once per source — in month drawers, print
reports, the Aid page and Outstanding. External aids (assessment item +
linked tracking post by design) had no skip path at all.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AidTrackingPost,
    AssessmentItem,
    Contribution,
    MedicalAid,
    Member,
    MemberAssessment,
    MemberAssessmentAllocation,
    MonthlyAssessment,
    TransactionArchive,
)
from core_system.services import member_transparency as mt


class AidDedupTests(TestCase):
    def setUp(self):
        self.payer = Member.objects.create(
            full_name="Juan Dela Cruz",
            employee_id="EMP-DEDUP-PAYER",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dedup_payer@test.local",
            date_joined=date(2025, 1, 15),
        )
        # Suffix-style name: the formatted recipient spelling differs from
        # the raw full_name beyond word order, so naive equality doubles it.
        self.claimant = Member.objects.create(
            full_name="Alfredo G Mateo Jr",
            employee_id="EMP-DEDUP-CLM",
            department="HR",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dedup_claimant@test.local",
            date_joined=date(2025, 1, 15),
        )
        self.claim = MedicalAid.objects.create(
            member_id_FK=self.claimant,
            request_date=date(2026, 3, 5),
            hospital_bill_amount=Decimal("25000.00"),
            claim_year=2026,
            document_status="Complete",
            policy_record_status="Eligible",
            validated_aid_amount=Decimal("100.00"),
            status="Approved",
        )
        # Assessment carries the aid with the FORMATTED recipient spelling,
        # exactly as the President's autocomplete stores it.
        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 3, 1), total_amount=Decimal("150.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
        )
        self.due_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"), priority_order=1,
        )
        self.aid_item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment, purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("50.00"), recipient="MATEO JR., Alfredo G", priority_order=2,
        )
        self.member_assessment = MemberAssessment.objects.create(
            assessment_id_FK=self.assessment, member_id_FK=self.payer,
            standard_assessment=Decimal("150.00"), actual_deduction=Decimal("150.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.member_assessment,
            assessment_item_id_FK=self.due_item,
            amount_applied=Decimal("100.00"), amount_remaining=Decimal("0.00"),
        )
        MemberAssessmentAllocation.objects.create(
            member_assessment_id_FK=self.member_assessment,
            assessment_item_id_FK=self.aid_item,
            amount_applied=Decimal("50.00"), amount_remaining=Decimal("0.00"),
        )
        # The SAME collection also tracked OTC (raw full_name resolution).
        self.archive = TransactionArchive.objects.create(
            transaction_type="medical_aid", record_id=self.claim.medical_aid_id_PK,
            member_id_FK=self.claimant, member_name="Alfredo G Mateo Jr",
            amount=Decimal("50.00"), status="Approved",
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive, aid_type="medical_aid",
            target_month="2026-03", total_expected=Decimal("50.00"),
            total_collected=Decimal("50.00"),
            source_type="medical_aid", source_id=self.claim.medical_aid_id_PK,
        )
        Contribution.objects.create(
            aid_tracking_post_id_FK=self.post, member_id_FK=self.payer,
            expected_amount=Decimal("50.00"), paid_amount=Decimal("50.00"),
            status=Contribution.STATUS_PAID,
        )

    def test_drawer_lists_collection_once(self):
        month = mt._due_month_breakdown(self.payer, 2026, 3)
        medical = [a for a in month["aids"] if a.get("aid_type_label") == "Medical Aid"]
        self.assertEqual(len(medical), 1, month["aids"])
        self.assertEqual(month["totals"]["aid_paid"], 50.0)

    def test_aid_page_lists_collection_once(self):
        data = mt.contributions(self.payer)
        mine = [i for i in data["items"] if i.get("target_month") == "2026-03"]
        self.assertEqual(len(mine), 1, data["items"])
        self.assertEqual(data["total_paid"], 50.0)

    def test_drawer_external_aid_lists_once(self):
        item = AssessmentItem.objects.create(
            assessment_id_FK=self.assessment, purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("20.00"), recipient_type=AssessmentItem.RECIPIENT_EXTERNAL,
            external_campus="ISU Echague Campus", external_beneficiary="Relief Drive",
            priority_order=3,
        )
        archive = TransactionArchive.objects.create(
            transaction_type="external_aid", record_id=item.item_id_PK,
            member_name="ISU Echague Campus — Relief Drive",
            amount=Decimal("20.00"), status="Approved",
        )
        AidTrackingPost.objects.create(
            archive_id_FK=archive, aid_type="medical_aid",
            target_month="2026-03", total_expected=Decimal("20.00"),
            total_collected=Decimal("20.00"),
            source_type="external_aid", source_id=item.item_id_PK,
            assessment_item_id_FK=item,
            external_campus="ISU Echague Campus", external_beneficiary="Relief Drive",
        )
        month = mt._due_month_breakdown(self.payer, 2026, 3)
        external = [a for a in month["aids"] if "Echague" in (a.get("recipient_name") or "")]
        self.assertEqual(len(external), 1, month["aids"])

    def test_name_matcher(self):
        self.assertTrue(mt._same_aid_party("SANTOS, Maria", "Maria Santos"))
        self.assertTrue(mt._same_aid_party("DELA CRUZ, Juan", "Juan Dela Cruz"))
        self.assertTrue(mt._same_aid_party("MATEO JR., Alfredo G", "Alfredo G Mateo Jr"))
        self.assertFalse(mt._same_aid_party("SANTOS, Maria", "Juan Dela Cruz"))
        self.assertFalse(mt._same_aid_party("MATEO JR., Alfredo G", "Maria Santos"))
        self.assertFalse(mt._same_aid_party("Member", "Member"))
        self.assertFalse(mt._same_aid_party("—", "SANTOS, Maria"))
