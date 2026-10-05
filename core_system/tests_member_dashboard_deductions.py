"""Member-facing monthly deduction data must show the real assessed breakdown.

The member dashboard previously showed each approved month only as a lump-sum
ledger amount, while Overview's outstanding/paid totals used the legacy direct
payment records. These tests require final-approved months to expose
classification-aware, per-item applied/remaining rows, carry a prior-month
balance forward accurately, and drive the Overview numbers.
"""
import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.models import (
    Member,
    MemberLedger,
    MembershipFee,
    Notification,
    OfficerUser,
)
from core_system.tests import _create_zt_verified_session, deposit_monthly_batch


class MemberDashboardDeductionTests(TestCase):
    def setUp(self):
        self.carry_member = Member.objects.create(
            full_name="Dashboard Carry Member",
            employee_id="EMP-MD-CARRY",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dashboard_carry@test.local",
            date_joined=date(2025, 1, 15),
        )
        self.full_member = Member.objects.create(
            full_name="Dashboard Full Member",
            employee_id="EMP-MD-FULL",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dashboard_full@test.local",
            date_joined=date(2025, 1, 15),
        )

    def _login(self, role, suffix):
        officer = OfficerUser.objects.create(
            full_name=f"{role} Dashboard Deduction Test {suffix}",
            username=f"{role.lower()}_dashboard_deduction_{suffix}_{timezone.now().timestamp()}",
            password_hash="unused",
            role=role,
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def _post(self, url, payload):
        response = self.client.post(
            url,
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _approve_month(self, month, actuals, items=None):
        self._login("President", f"{month}-setup")
        assessment = self._post(
            "/api/president/monthly-assessment/save/",
            {
                "month": month,
                "items": items
                or [
                    {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                    {
                        "purpose": "medical_aid_fund",
                        "amount": 100,
                        "priority_order": 2,
                        "recipient": "Aid Recipient",
                    },
                ],
            },
        )["assessment"]
        self._login("Treasurer", f"{month}-record")
        self._post(
            "/api/treasurer/deductions/record/",
            {
                "assessment_id": assessment["assessment_id"],
                "members": [
                    {"member_id": member, "actual_deduction": actual}
                    for member, actual in actuals
                ],
            },
        )
        deposit_monthly_batch(self.client, assessment["assessment_id"])
        self._login("Auditor", f"{month}-verify")
        self._post(
            "/api/auditor/deductions/verify/",
            {"assessment_id": assessment["assessment_id"], "action": "approve", "notes": "ok"},
        )
        self._login("President", f"{month}-final")
        self._post(
            "/api/president/deductions/approve/",
            {"assessment_id": assessment["assessment_id"], "action": "approve", "notes": "Approved."},
        )
        return assessment["assessment_id"]

    def _login_as_member(self, member):
        officer = self._login("Member", f"member{member.member_id_PK}")
        member.officer_user_id_FK = officer
        member.save(update_fields=["officer_user_id_FK"])

    def _create_membership_fee(self, member, amount="100.00", status="Paid"):
        recorder = self._login("Treasurer", f"fee{member.member_id_PK}")
        return MembershipFee.objects.create(
            member_id_FK=member,
            amount=Decimal(amount),
            payment_method="Cash",
            payment_status=status,
            payment_date=date(2025, 1, 20),
            receipt_number=f"DASH-FEE-{member.member_id_PK}",
            recorded_by_user_id_FK=recorder,
        )

    def _ledger_data(self, member):
        self._login_as_member(member)
        response = self.client.get("/api/member/ledger/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        return data

    def _ledger_entry(self, member, month_label):
        data = self._ledger_data(member)
        entries = [
            entry
            for entry in data["entries"]
            if entry["transaction_type"] == "monthly_dues"
            and (entry.get("breakdown") or {}).get("month_label") == month_label
        ]
        self.assertEqual(len(entries), 1, data["entries"])
        return entries[0]

    def _dashboard_numbers(self, member):
        self._login_as_member(member)
        response = self.client.get("/api/member/dashboard/data/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        return data["total_dues_paid"], data["outstanding_balance"]

    def test_approved_months_expose_item_breakdown_and_carry_over(self):
        carry = self.carry_member.member_id_PK
        full = self.full_member.member_id_PK
        self._approve_month(
            "2026-09",
            [(carry, 250), (full, 400)],
        )
        self._approve_month("2026-10", [(carry, 250)])

        september = self._ledger_entry(self.carry_member, "September 2026")
        self.assertEqual(september["amount"], 250.0)
        breakdown = september["breakdown"]
        self.assertEqual(breakdown["status"], "partial")
        self.assertEqual(breakdown["total_required"], 300.0)
        self.assertEqual(breakdown["actual"], 250.0)
        self.assertEqual(breakdown["outstanding"], 50.0)
        by_purpose = {row["purpose"]: row for row in breakdown["rows"]}
        self.assertEqual(by_purpose["Monthly Due"]["applied"], 200.0)
        self.assertEqual(by_purpose["Monthly Due"]["remaining"], 0.0)
        self.assertEqual(by_purpose["Medical Aid Fund"]["applied"], 0.0)
        self.assertEqual(by_purpose["Medical Aid Fund"]["remaining"], 100.0)
        # Token Incentive is no longer an assessment purpose.
        self.assertNotIn("Token Incentive", by_purpose)

        october = self._ledger_entry(self.carry_member, "October 2026")
        self.assertEqual(october["amount"], 250.0)
        breakdown = october["breakdown"]
        self.assertEqual(breakdown["status"], "partial")
        self.assertEqual(breakdown["total_required"], 350.0)
        self.assertEqual(breakdown["actual"], 250.0)
        self.assertEqual(breakdown["outstanding"], 100.0)
        prior_rows = [row for row in breakdown["rows"] if row["kind"] == "prior"]
        self.assertEqual(len(prior_rows), 1)
        self.assertIn("September 2026", prior_rows[0]["purpose"])
        self.assertEqual(prior_rows[0]["required"], 50.0)
        self.assertEqual(prior_rows[0]["applied"], 0.0)
        self.assertEqual(prior_rows[0]["remaining"], 50.0)

        full_september = self._ledger_entry(self.full_member, "September 2026")
        self.assertEqual(full_september["breakdown"]["status"], "full")
        self.assertEqual(full_september["breakdown"]["outstanding"], 0.0)
        self.assertEqual(full_september["breakdown"]["change"], 100.0)

    def test_retired_member_keeps_history_but_has_no_current_obligation(self):
        member = Member.objects.create(
            full_name="Dashboard Retired Member",
            employee_id="EMP-MD-RETIRED",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dashboard_retired@test.local",
            date_joined=date(2025, 1, 15),
        )
        self._approve_month("2026-09", [(member.member_id_PK, 250)])
        member.member_classification = "Retired"
        member.membership_status = "Retired"
        member.save(update_fields=["member_classification", "membership_status"])

        data = self._ledger_data(member)
        september = self._ledger_entry(member, "September 2026")
        # The active-month allocation remains intact after retirement.
        by_purpose = {row["purpose"]: row for row in september["breakdown"]["rows"]}
        self.assertEqual(by_purpose["Monthly Due"]["required"], 200.0)
        self.assertEqual(by_purpose["Monthly Due"]["applied"], 200.0)
        self.assertEqual(september["outstanding_after"], 50.0)
        # Retirement ends the current obligation without deleting history.
        self.assertEqual(data["monthly_total_paid"], 250.0)
        self.assertEqual(data["monthly_outstanding"], 0.0)
        self.assertEqual(self._dashboard_numbers(member), (250.0, 0.0))

    def test_approved_month_without_ledger_posting_still_appears(self):
        member = self.carry_member.member_id_PK
        self._approve_month("2026-09", [(member, 250)])
        MemberLedger.objects.filter(
            reference_type="MemberAssessment",
            reference_id__in=Member.objects.filter(member_id_PK=member).values_list(
                "monthly_assessment_deductions__member_assessment_id_PK", flat=True
            ),
        ).delete()

        data = self._ledger_data(self.carry_member)
        self.assertEqual(len(data["entries"]), 1)
        self.assertTrue(data["entries"][0]["id"].startswith("assessment_"))
        self.assertEqual(data["entries"][0]["outstanding_after"], 50.0)
        self.assertEqual(data["monthly_total_paid"], 250.0)
        self.assertEqual(data["monthly_outstanding"], 50.0)

    def test_membership_fee_only_member_gets_a_separate_fee_card(self):
        member = Member.objects.create(
            full_name="Dashboard Fee Only Member",
            employee_id="EMP-MD-FEE",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dashboard_fee@test.local",
            date_joined=timezone.now().date(),
        )
        self._create_membership_fee(member)
        data = self._ledger_data(member)

        self.assertEqual(data["entries"], [])
        self.assertEqual(data["monthly_total_paid"], 0.0)
        self.assertEqual(data["monthly_outstanding"], 0.0)
        self.assertTrue(data["membership_fee"]["paid"])
        self.assertEqual(data["membership_fee"]["amount"], 100.0)

    def test_old_member_without_fee_record_hides_fee_card(self):
        member = Member.objects.create(
            full_name="Dashboard Old Member",
            employee_id="EMP-MD-OLD",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dashboard_old@test.local",
            date_joined=date(2024, 6, 15),
        )
        data = self._ledger_data(member)

        self.assertIsNone(data["membership_fee"])
        self._login_as_member(member)
        response = self.client.get(reverse("member_dashboard"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.context["has_membership_fee"])
        # Membership Fee card was removed from the member dashboard entirely,
        # so OLD members (and NEW members) never render a fee card — no
        # Pending status can appear in Overview or Monthly Deductions History.
        self.assertNotIn('membershipFeeCard', response.content.decode())
        self.assertNotIn('Membership Fee</div>', response.content.decode())

    def test_membership_fee_has_a_separate_overview_card(self):
        member = Member.objects.create(
            full_name="Dashboard Overview Fee Member",
            employee_id="EMP-MD-OVFEE",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Teaching",
            email="dashboard_overview_fee@test.local",
            date_joined=date(2025, 1, 15),
        )
        self._create_membership_fee(member)
        self._approve_month("2026-09", [(member.member_id_PK, 350)])

        self._login_as_member(member)
        response = self.client.get(reverse("member_dashboard"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.context["has_membership_fee"])
        content = response.content.decode()
        # Membership Fee card was removed from the member dashboard entirely.
        # The fee record still exists in the backend, but no card is rendered
        # in Overview or Monthly Deductions History.
        self.assertNotIn('membershipFeeCard', content)
        self.assertNotIn('Membership Fee</div>', content)
        self.assertIn("₱350.00", content)

    def test_overview_uses_final_approved_months_not_legacy_math(self):
        carry = self.carry_member.member_id_PK
        full = self.full_member.member_id_PK
        self._approve_month(
            "2026-09",
            [(carry, 250), (full, 400)],
        )
        self._approve_month("2026-10", [(carry, 250)])

        # These old join dates would otherwise generate a large legacy
        # outstanding balance from months with no direct-payment records.
        self.assertEqual(self._dashboard_numbers(self.carry_member), (500.0, 100.0))
        self.assertEqual(self._dashboard_numbers(self.full_member), (400.0, 0.0))

    def test_server_rendered_overview_matches_deduction_months(self):
        carry = self.carry_member.member_id_PK
        full = self.full_member.member_id_PK
        self._approve_month("2026-09", [(carry, 250), (full, 400)])
        self._approve_month("2026-10", [(carry, 250)])

        self._login_as_member(self.carry_member)
        response = self.client.get(reverse("member_dashboard"))
        self.assertEqual(response.status_code, 200, response.content)
        content = response.content.decode()
        self.assertIn("₱500.00", content)
        self.assertIn("₱100.00", content)
        self.assertIn("breakdown-toggle", content)
        self.assertIn('{ full: "Paid"', content)
        self.assertNotIn('<th style="width:105px;">Entry</th>', content)
        self.assertNotIn("dir-badge", content)

    def test_deduction_notice_amounts_use_consistent_peso_format(self):
        carry = self.carry_member.member_id_PK
        self._approve_month("2026-09", [(carry, 250)])
        notice = (
            Notification.objects.filter(
                recipient_type="member",
                recipient_id=carry,
                notification_type="Monthly Deduction",
                message__contains="September 2026",
            )
            .order_by("-sent_at", "-notification_id_PK")
            .first()
        )
        self.assertIsNotNone(notice)
        self.assertIn("₱250.00", notice.message)
        self.assertIn("outstanding: ₱50.00", notice.message)
