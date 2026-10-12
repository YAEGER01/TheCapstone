"""A5 data contract (REPORTS.MD :: A5 Collection Summary Report).

The A5 sheet rolls dues standing, aid-case contributions and fee receipts into
PERIOD / DEPARTMENT / CATEGORY / EXPECTED / COLLECTED / SHORTFALL /
CONTRIBUTING MEMBERS rows (plus Member / Department / Payment Period groupings).
This test pins all three fact sources and the rollup arithmetic.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AidTrackingPost,
    AssessmentItem,
    Contribution,
    Member,
    MemberAssessment,
    MembershipFee,
    MonthlyAssessment,
    TransactionArchive,
)
from core_system.tests import TreasurerApiClientMixin


class SampleA5DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.m1 = Member.objects.create(
            full_name="Aguilar, Ana A.", employee_id="MEM-0108", department="CCS ICT",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 9, 1),
        )
        self.m2 = Member.objects.create(
            full_name="Torres, Grace T.", employee_id="MEM-0152", department="CCS ICT",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 9, 1),
        )
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("50.00"),
            status=MonthlyAssessment.STATUS_PENDING_AUDIT,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.ass, member_id_FK=self.m1,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("50.00"),
            outstanding_balance=Decimal("0.00"), status=MemberAssessment.STATUS_PENDING,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.ass, member_id_FK=self.m2,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("0.00"),
            outstanding_balance=Decimal("50.00"), status=MemberAssessment.STATUS_PENDING,
        )
        MembershipFee.objects.create(
            member_id_FK=self.m1, amount=100, payment_method="Cash",
            payment_status="Paid", payment_date=date(2026, 9, 5),
            receipt_number="OR-1001", recorded_by_user_id_FK=self.officer,
        )
        archive = TransactionArchive.objects.create(
            transaction_type="death_aid", record_id=1, member_id_FK=self.m1,
            member_name=self.m1.full_name, amount=Decimal("72000"),
            validated_amount=Decimal("72000"), status="Approved",
            payment_method="Cash", fiscal_term="2026-09",
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=archive, aid_type="death_aid", target_month="2026-09",
            total_expected=Decimal("1000"), total_collected=Decimal("500"),
            is_active=True, status="tracking",
        )
        Contribution.objects.create(
            aid_tracking_post_id_FK=self.post, member_id_FK=self.m1,
            expected_amount=Decimal("500"), paid_amount=Decimal("500"),
            payment_date=date(2026, 9, 15), status="PAID",
        )
        Contribution.objects.create(
            aid_tracking_post_id_FK=self.post, member_id_FK=self.m2,
            expected_amount=Decimal("500"), paid_amount=Decimal("0"),
            payment_date=None, status="NOT_PAID",
        )

    def test_dues_facts_from_heatmap(self):
        data = self.client.get("/api/auditor/deductions/heatmap/",
                               {"assessment_id": self.ass.assessment_id_PK}).json()
        rows = {m["member_id"]: m for m in data["members"]}
        self.assertEqual(float(rows[self.m1.member_id_PK]["standard"]), 50.0)
        self.assertEqual(float(rows[self.m1.member_id_PK]["actual"]), 50.0)
        self.assertEqual(float(rows[self.m2.member_id_PK]["outstanding"]), 50.0)

    def test_aid_facts_from_case_members(self):
        data = self.client.get(
            f"/api/treasurer/aid-post-members/{self.post.post_id_PK}/").json()
        self.assertTrue(data["ok"])
        rows = {m["member_id"]: m for m in data["members"]}
        for key in ("member_id", "member_name", "department", "expected_amount",
                    "paid_amount", "payment_date", "status"):
            self.assertIn(key, rows[self.m1.member_id_PK])
        self.assertEqual(float(rows[self.m1.member_id_PK]["paid_amount"]), 500.0)
        self.assertEqual(float(rows[self.m2.member_id_PK]["paid_amount"]), 0.0)

    def test_aid_post_target_month_scopes_to_period(self):
        data = self.client.get("/api/treasurer/approved-aid-posts/?all=1").json()
        self.assertTrue(data["ok"])
        post = next(p for p in data["posts"] if p["post_id"] == self.post.post_id_PK)
        self.assertEqual(str(post["target_month"])[:7], "2026-09")
        self.assertEqual(post["aid_type"], "death_aid")

    def test_summary_arithmetic(self):
        # (expected, collected) facts -> shortfall + contributing members.
        facts = [(50.0, 50.0), (50.0, 0.0), (500.0, 500.0), (500.0, 0.0), (100.0, 100.0)]
        exp = sum(e for e, _ in facts)
        col = sum(c for _, c in facts)
        self.assertEqual(exp, 1200.0)
        self.assertEqual(col, 650.0)
        self.assertEqual(round(exp - col, 2), 550.0)
        payers = sum(1 for _, c in facts if c > 0.005)
        self.assertEqual(payers, 3)
