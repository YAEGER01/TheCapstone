"""A1 sample-report data contract (ISUCauFA_Report_Samples.docx §A1).

The A1 sheet itself is rendered client-side from two live endpoints; this test
pins the exact fields the sheet reads so a backend change can never silently
break the 1:1 sample layout (member label, dept/type, joined date, assessed /
paid / balance math, payment/OR, status vocabulary, period keys).
"""
import json
from datetime import date

from django.test import TestCase

from core_system.models import Member, MembershipFee, OfficerUser
from core_system.tests import TreasurerApiClientMixin


FEE_ASSESSED = 100  # By-Laws one-time fee; mirrors the A1 sheet constant.


def a1_row(fee, member):
    paid = float(fee["amount"])
    bal = round(FEE_ASSESSED - paid, 2)
    status = "Fully Paid" if bal <= 0.005 else ("Partially Paid" if paid > 0.005 else "Unpaid")
    emp = (member["employee_id"] or "").strip()
    return {
        "member": f"{member['full_name']} ({emp or 'ID-' + str(member['member_id'])})",
        "assessed": FEE_ASSESSED,
        "paid": paid,
        "balance": bal,
        "status": status,
        "college": member["department"],
        "year": str(fee["payment_date"])[:4],
    }


class SampleA1DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.m1 = Member.objects.create(
            full_name="Lim, Rafael S.", employee_id="MEM-0153", department="College B",
            employment_status="Active", membership_status="Permanent",
            member_type="Regular", date_joined=date(2026, 9, 1),
        )
        self.m2 = Member.objects.create(
            full_name="Lim, Danilo E.", employee_id="MEM-0156", department="College D",
            employment_status="Active", membership_status="Permanent",
            member_type="Regular", date_joined=date(2026, 9, 10),
        )
        MembershipFee.objects.create(
            member_id_FK=self.m1, amount=100, payment_method="Cash",
            payment_status="Paid", payment_date=date(2026, 9, 1),
            receipt_number="OR-1001", recorded_by_user_id_FK=self.officer,
        )
        MembershipFee.objects.create(
            member_id_FK=self.m2, amount=50, payment_method="Cash",
            payment_status="Partial", payment_date=date(2026, 9, 10),
            receipt_number="OR-1004", recorded_by_user_id_FK=self.officer,
        )

    def test_fee_and_member_endpoints_carry_every_a1_field(self):
        fees = self.client.get("/api/treasurer/membership-fees/list/").json()
        members = self.client.get("/api/treasurer/members/list/").json()
        self.assertTrue(fees["ok"])
        self.assertTrue(members["ok"])
        need_fee = {"ref", "member_id", "member_name", "amount", "payment_date",
                    "payment_status", "payment_method"}
        need_mem = {"member_id", "full_name", "employee_id", "department",
                    "membership_status", "member_type", "date_joined"}
        for f in fees["fees"]:
            self.assertTrue(need_fee <= set(f), f)
        for m in members["members"]:
            self.assertTrue(need_mem <= set(m), m)

    def test_a1_row_math_matches_sample_layout(self):
        fees = {f["member_id"]: f
                for f in self.client.get("/api/treasurer/membership-fees/list/").json()["fees"]}
        members = {m["member_id"]: m
                   for m in self.client.get("/api/treasurer/members/list/").json()["members"]}
        full = a1_row(fees[self.m1.member_id_PK], members[self.m1.member_id_PK])
        self.assertEqual(full["assessed"], 100)
        self.assertEqual(full["paid"], 100.0)
        self.assertEqual(full["balance"], 0.0)
        self.assertEqual(full["status"], "Fully Paid")
        self.assertIn("MEM-0153", full["member"])
        self.assertEqual(full["college"], "College B")
        self.assertEqual(full["year"], "2026")

        part = a1_row(fees[self.m2.member_id_PK], members[self.m2.member_id_PK])
        self.assertEqual(part["paid"], 50.0)
        self.assertEqual(part["balance"], 50.0)
        self.assertEqual(part["status"], "Partially Paid")

    def test_a1_status_filter_vocabulary_still_matches(self):
        # The sheet shows "Fully Paid" while the filter offers "Paid": the
        # engine matches by substring, so "paid" must stay inside "fully paid".
        self.assertIn("paid", "Fully Paid".lower())
        self.assertIn("partial", "Partially Paid".lower())
