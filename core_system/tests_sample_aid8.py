"""AID8 data contract (REPORTS.MD :: Aid Financial Summary Report).

The AID8 sheet shows per-incident aid economics by type: contributions
collected from aid cases in range vs releases booked in range, opening at zero
(no standing fund), ending = collected − released.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AidTrackingPost,
    Contribution,
    FundTransaction,
    MedicalAid,
    Member,
    TransactionArchive,
)
from core_system.tests import TreasurerApiClientMixin


class SampleAid8DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.m1 = Member.objects.create(
            full_name="Navarro, Rosario H.", employee_id="MEM-0023", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        self.m2 = Member.objects.create(
            full_name="Valdez, Jericho G.", employee_id="MEM-0027", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        med = MedicalAid.objects.create(
            member_id_FK=self.m1, request_date=date(2026, 9, 14),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("13300"),
            requested_amount=Decimal("13300"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("13300"), status="Released",
        )
        archive = TransactionArchive.objects.create(
            transaction_type="medical_aid", record_id=med.medical_aid_id_PK,
            member_id_FK=self.m1, member_name=self.m1.full_name,
            amount=Decimal("13300"), validated_amount=Decimal("13300"),
            status="Released", payment_method="Cash", fiscal_term="2026-09",
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=archive, aid_type="medical_aid", target_month="2026-09",
            total_expected=Decimal("13300"), total_collected=Decimal("13300"),
            is_active=False, status="closed",
        )
        Contribution.objects.create(
            aid_tracking_post_id_FK=self.post, member_id_FK=self.m1,
            expected_amount=Decimal("100"), paid_amount=Decimal("100"),
            payment_date=date(2026, 9, 15), status="PAID",
        )
        Contribution.objects.create(
            aid_tracking_post_id_FK=self.post, member_id_FK=self.m2,
            expected_amount=Decimal("100"), paid_amount=Decimal("0"),
            payment_date=None, status="NOT_PAID",
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("13300"), source_type="medical_aid",
            source_id=med.medical_aid_id_PK,
            description=f"Aid disbursement — {self.m1.full_name} (medical_aid)",
            reference_number="DV-2026-051", recorded_by_user_id_FK=self.officer,
        )

    def test_contributions_sum_from_case_members(self):
        data = self.client.get(
            f"/api/treasurer/aid-post-members/{self.post.post_id_PK}/").json()
        collected = sum(float(m["paid_amount"]) for m in data["members"])
        self.assertEqual(collected, 100.0)

    def test_releases_sum_from_ledger(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        released = sum(float(e["amount"]) for e in data["items"]
                       if e["direction"] == "outflow" and e["source_type"] == "medical_aid")
        self.assertEqual(released, 13300.0)

    def test_ending_is_collected_minus_released(self):
        self.assertEqual(round(100.0 - 13300.0, 2), -13200.0)

    def test_post_counts_as_case_in_period(self):
        data = self.client.get("/api/treasurer/approved-aid-posts/?all=1").json()
        in_sep = [p for p in data["posts"] if str(p["target_month"])[:7] == "2026-09"]
        self.assertEqual(len(in_sep), 1)
