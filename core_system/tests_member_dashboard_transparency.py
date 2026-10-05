"""Member Dashboard — Financial Transparency.

Covers the four feature areas end to end and, more importantly, the boundaries
that make the feature safe to ship:

* the Financial Overview is organisation-wide and always shows real figures
* everything else is member-only, and no client-supplied member id can change that
* the removed surfaces (reveal, reports, access history) are actually gone
* no officer endpoint was widened to get here
* every financial read lands in the audit trail
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import (
    FundTransaction,
    GlobalAuditTrail,
    Member,
    MemberAssessment,
    MemberLedger,
    MembershipFee,
    MonthlyAssessment,
    OfficerUser,
    SensitiveReadLog,
)

PASSWORD = "Str0ng!Passw0rd"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class TransparencyTestBase(TestCase):
    def _officer(self, role, username):
        return OfficerUser.objects.create(
            full_name=f"{role} User",
            username=username,
            password_hash=hash_password(PASSWORD),
            role=role,
            account_status="Active",
            mfa_enabled=False,
            email=f"{username}@isu.edu.ph",
        )

    def _login(self, officer, role=None):
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        client_session = self.client.session
        client_session["access_token"] = token
        client_session["officer_id"] = officer.user_id_PK
        client_session["role"] = role or officer.role
        client_session.save()
        return officer

    def _member(self, officer, name="Alpha Member", employee_id="mt-001", **kwargs):
        return Member.objects.create(
            full_name=name,
            employee_id=employee_id,
            membership_status=kwargs.get("membership_status", "Permanent"),
            employment_status=kwargs.get("employment_status", "Active"),
            member_classification=kwargs.get("member_classification", "Teaching"),
            date_joined=kwargs.get("date_joined", timezone.now().date()),
            officer_user_id_FK=officer,
        )

    def _tx(self, direction, amount, source_type, description, year=2031, month=1,
            source_id=1, ref=None):
        tx = FundTransaction.objects.create(
            direction=direction,
            source_type=source_type,
            source_id=source_id,
            amount=Decimal(amount),
            description=description,
            reference_number=ref,
            recorded_by_user_id_FK=self.recorder,
        )
        # recorded_at is auto_now_add, so backdate with an explicit update.
        FundTransaction.objects.filter(pk=tx.pk).update(
            recorded_at=timezone.make_aware(datetime(year, month, 15, 10, 30))
        )
        return tx


class FundSummaryTests(TransparencyTestBase):
    """1. Financial Overview — organisation-wide, always unmasked."""

    def setUp(self):
        self.member_user = self._officer("Member", "mt_member")
        self.recorder = self._officer("Treasurer", "mt_treasurer")
        self.member = self._member(self.member_user)
        self._login(self.member_user)
        self._tx("inflow", "1000.00", "monthly_dues", "Dues batch", 2031, 1, ref="COL-00001")
        self._tx("inflow", "250.00", "membership_fee", "Membership fee", 2031, 1, source_id=2)
        self._tx("inflow", "100.00", "other_transaction", "Donation", 2031, 2, source_id=3)
        self._tx("outflow", "400.00", "aid_post_payment", "Aid release", 2031, 2, source_id=4)

    def test_summary_figures_are_correct(self):
        resp = self.client.get("/api/member/fund/summary/", **AJAX)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        # Inflows 1350, outflows 400 -> balance 950.
        self.assertEqual(data["total_in"], 1350.0)
        self.assertEqual(data["total_out"], 400.0)
        self.assertEqual(data["balance"], 950.0)

    def test_total_collections_excludes_non_collection_inflows(self):
        """Total Collections is money collected from members (dues + fee +
        aid set-asides), not every peso that arrived — the 100 donation and
        the 400 disbursement must not be counted as collections."""
        data = self.client.get("/api/member/fund/summary/", **AJAX).json()
        self.assertEqual(data["total_collections"], 1250.0)

    def test_summary_is_organisation_scoped_and_unmasked(self):
        """The one panel a member reads as an association member: real numbers,
        no reveal step, no masking flag to flip."""
        data = self.client.get("/api/member/fund/summary/", **AJAX).json()
        self.assertEqual(data["scope"], "organization")
        for key in ("balance", "total_in", "total_out", "total_collections"):
            self.assertIsInstance(data[key], float, f"{key} must be a real figure")
        self.assertNotIn("masked", data)

    def test_summary_is_never_a_mask_placeholder(self):
        """No value anywhere in the response may be the masking placeholder."""
        data = self.client.get("/api/member/fund/summary/", **AJAX).json()
        self.assertNotIn("••••••", str(data))

    def test_trend_series_has_one_bucket_per_month(self):
        data = self.client.get("/api/member/fund/trend/?months=6", **AJAX).json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["series"]), 6)
        # Oldest first, so the labels walk forward through the calendar.
        keys = [row["key"] for row in data["series"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(data["scope"], "organization")

    def test_trend_bucket_totals_match_the_ledger(self):
        """The trend series must bucket the same money the ledger reports.

        Seeded relative to the current month, because the trend endpoint is
        deliberately windowed to the last N months and a fixed year would fall
        outside it.
        """
        now = timezone.localtime().date()
        this_month = now.replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)
        self._tx("inflow", "700.00", "monthly_dues", "This month dues", this_month.year, this_month.month, source_id=70)
        self._tx("inflow", "300.00", "monthly_dues", "Last month dues", last_month.year, last_month.month, source_id=71)
        self._tx("outflow", "120.00", "aid_post_payment", "Last month aid", last_month.year, last_month.month, source_id=72)
        # A movement well before the window, so the series has to open on a
        # real carried-forward position rather than zero.
        self._tx("inflow", "5000.00", "monthly_dues", "Old dues", 2020, 3, source_id=73)

        data = self.client.get("/api/member/fund/trend/?months=4", **AJAX).json()
        by_key = {row["key"]: row for row in data["series"]}

        this_key = this_month.strftime("%Y-%m")
        last_key = last_month.strftime("%Y-%m")
        self.assertEqual(by_key[this_key]["total_in"], 700.0)
        self.assertEqual(by_key[last_key]["total_in"], 300.0)
        self.assertEqual(by_key[last_key]["total_out"], 120.0)
        self.assertEqual(data["opening_balance"], 5000.0)


class TrendClosesOnTheLedgerTests(TransparencyTestBase):
    """The trend series must reconcile with the fund summary.

    Kept in its own class with no out-of-window rows: the series is scoped to
    the last N months while the summary is lifetime, so the two only agree when
    every movement falls inside the window.
    """

    def setUp(self):
        self.member_user = self._officer("Member", "tr_member")
        self.recorder = self._officer("Treasurer", "tr_treasurer")
        self.member = self._member(self.member_user)
        self._login(self.member_user)

        now = timezone.localtime().date().replace(day=1)
        prev = (now - timedelta(days=1)).replace(day=1)
        self._tx("inflow", "1000.00", "monthly_dues", "A", now.year, now.month, source_id=1)
        self._tx("outflow", "250.00", "aid_post_payment", "B", now.year, now.month, source_id=2)
        self._tx("inflow", "500.00", "contribution", "C", prev.year, prev.month, source_id=3)

    def test_series_closes_on_the_current_balance(self):
        trend = self.client.get("/api/member/fund/trend/?months=3", **AJAX).json()
        summary = self.client.get("/api/member/fund/summary/", **AJAX).json()
        self.assertEqual(trend["series"][-1]["balance"], summary["balance"])
        self.assertEqual(trend["current_balance"], summary["balance"])
        self.assertEqual(trend["opening_balance"], 0.0)


class CashFlowMemberOnlyTests(TransparencyTestBase):
    """3. Cash Flow — the member's own movements, one personal timeline."""

    def setUp(self):
        self.member_user = self._officer("Member", "cf_member")
        self.recorder = self._officer("Treasurer", "cf_treasurer")
        self.member = self._member(self.member_user)
        self._login(self.member_user)

        self.other_user = self._officer("Member", "cf_other")
        self.other = self._member(
            self.other_user, name="Other Member", employee_id="cf-002"
        )

        self.ledger_in = MemberLedger.objects.create(
            member_id_FK=self.member,
            transaction_type="monthly_dues",
            amount=Decimal("2000.00"),
            direction="credit",
            balance_after=Decimal("2000.00"),
            reference_id=1,
            reference_type="MonthlyDues",
            description="January dues",
            notes="Deducted from payroll",
            recorded_by_user_id_FK=self.recorder,
        )
        self.ledger_out = MemberLedger.objects.create(
            member_id_FK=self.member,
            transaction_type="medical_aid",
            amount=Decimal("500.00"),
            direction="debit",
            balance_after=Decimal("1500.00"),
            reference_id=2,
            reference_type="MedicalAid",
            description="Medical aid release",
            notes="Approved claim",
            recorded_by_user_id_FK=self.recorder,
        )
        # Somebody else's money: must never surface.
        MemberLedger.objects.create(
            member_id_FK=self.other,
            transaction_type="monthly_dues",
            amount=Decimal("9999.00"),
            direction="credit",
            balance_after=Decimal("9999.00"),
            reference_id=3,
            reference_type="MonthlyDues",
            description="Other member dues",
            recorded_by_user_id_FK=self.recorder,
        )

    def test_cash_flow_reports_the_members_own_movements(self):
        data = self.client.get("/api/member/fund/ledger/?page=1&per_page=5", **AJAX).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["scope"], "member")
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["total_pages"], 1)
        self.assertEqual(data["summary"]["total_in"], 2000.0)
        self.assertEqual(data["summary"]["total_out"], 500.0)
        self.assertEqual(data["summary"]["net"], 1500.0)

    def test_never_leaks_another_members_movement(self):
        data = self.client.get("/api/member/fund/ledger/", **AJAX).json()
        self.assertNotIn("9999", str(data))
        self.assertNotIn("Other member dues", str(data))

    def test_direction_filter(self):
        data = self.client.get("/api/member/fund/ledger/?direction=out", **AJAX).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["direction"], "out")

    def test_kind_filter(self):
        data = self.client.get("/api/member/fund/ledger/?kind=monthly_dues", **AJAX).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["description"], "January dues")

    def test_year_filter_excludes_other_years(self):
        data = self.client.get("/api/member/fund/ledger/?year=1999", **AJAX).json()
        self.assertEqual(data["total"], 0)

    def test_paginates_onto_a_second_page(self):
        for i in range(4):
            MemberLedger.objects.create(
                member_id_FK=self.member,
                transaction_type="contribution",
                amount=Decimal("10.00"),
                direction="credit",
                balance_after=Decimal("10.00"),
                reference_id=100 + i,
                reference_type="Contribution",
                description=f"Filler {i}",
                recorded_by_user_id_FK=self.recorder,
            )
        # per_page has a server-side floor of 5, so 6 rows fills two pages.
        data = self.client.get("/api/member/fund/ledger/?page=1&per_page=5", **AJAX).json()
        self.assertEqual(data["total"], 6)
        self.assertEqual(data["total_pages"], 2)
        self.assertEqual(len(data["items"]), 5)

        page2 = self.client.get("/api/member/fund/ledger/?page=2&per_page=5", **AJAX).json()
        self.assertEqual(page2["page"], 2)
        self.assertEqual(len(page2["items"]), 1)

    def test_figures_are_never_masked(self):
        data = self.client.get("/api/member/fund/ledger/", **AJAX).json()
        self.assertNotIn("••••••", str(data))
        for row in data["items"]:
            self.assertIsInstance(row["amount"], float)
            self.assertIsInstance(row["running_net"], float)

    def test_movement_detail_returns_remarks(self):
        data = self.client.get(
            f"/api/member/fund/movement/ledger_{self.ledger_out.ledger_id_PK}/", **AJAX
        ).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["direction"], "out")
        self.assertEqual(data["description"], "Medical aid release")
        self.assertEqual(data["kind_label"], "Medical Aid")
        self.assertEqual(data["amount"], 500.0)
        self.assertEqual(data["remarks"], "Approved claim")

    def test_movement_detail_404s_for_another_members_movement(self):
        other_movement = MemberLedger.objects.filter(member_id_FK=self.other).first()
        resp = self.client.get(
            f"/api/member/fund/movement/ledger_{other_movement.ledger_id_PK}/", **AJAX
        )
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn("9999", resp.content.decode())

    def test_movement_detail_404s_for_unknown_id(self):
        resp = self.client.get("/api/member/fund/movement/ledger_999999/", **AJAX)
        self.assertEqual(resp.status_code, 404)

    def test_no_member_id_parameter_is_honoured(self):
        data = self.client.get(
            f"/api/member/fund/ledger/?member_id={self.other.member_id_PK}", **AJAX
        ).json()
        self.assertEqual(data["total"], 2)


class CashFlowNoDoubleCountTests(TransparencyTestBase):
    """One payment must appear once, not once per table that records it.

    The approval views mirror every approved MembershipFee, MonthlyDues and
    MemberAssessment into MemberLedger keyed by (reference_type, reference_id),
    so merging the source tables in unconditionally counted the same peso twice.
    """

    def setUp(self):
        self.member_user = self._officer("Member", "dc_member")
        self.recorder = self._officer("Treasurer", "dc_treasurer")
        self.member = self._member(self.member_user)
        self._login(self.member_user)

    def _ledger_for(self, reference_type, reference_id, amount):
        return MemberLedger.objects.create(
            member_id_FK=self.member,
            transaction_type="membership_fee",
            amount=Decimal(amount),
            direction="credit",
            balance_after=Decimal(amount),
            reference_id=reference_id,
            reference_type=reference_type,
            description="Membership Fee Payment",
            recorded_by_user_id_FK=self.recorder,
        )

    def test_an_approved_fee_is_counted_once(self):
        fee = MembershipFee.objects.create(
            member_id_FK=self.member,
            amount=Decimal("100.00"),
            payment_method="OTC",
            payment_status="Paid",
            payment_date=date(2031, 1, 10),
            receipt_number="RCP-1",
            recorded_by_user_id_FK=self.recorder,
        )
        self._ledger_for("MembershipFee", fee.fee_id_PK, "100.00")

        data = self.client.get("/api/member/fund/ledger/", **AJAX).json()
        self.assertEqual(data["total"], 1, "the fee was counted twice")
        self.assertEqual(data["summary"]["total_in"], 100.0)
        self.assertEqual(data["items"][0]["id"], f"ledger_{MemberLedger.objects.first().ledger_id_PK}")

    def test_an_unmirrored_fee_still_appears(self):
        """The fee table is the backstop: a fee with no ledger row is not lost."""
        MembershipFee.objects.create(
            member_id_FK=self.member,
            amount=Decimal("100.00"),
            payment_method="OTC",
            payment_status="Paid",
            payment_date=date(2031, 1, 10),
            receipt_number="RCP-1",
            recorded_by_user_id_FK=self.recorder,
        )

        data = self.client.get("/api/member/fund/ledger/", **AJAX).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["summary"]["total_in"], 100.0)
        self.assertTrue(data["items"][0]["id"].startswith("fee_"))

    def test_a_mirrored_assessment_is_counted_once(self):
        batch = MonthlyAssessment.objects.create(
            month=date(2031, 5, 1),
            total_amount=Decimal("300.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
            created_by_id_FK=self.recorder,
        )
        ma = MemberAssessment.objects.create(
            assessment_id_FK=batch,
            member_id_FK=self.member,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("300.00"),
            outstanding_balance=Decimal("0.00"),
            status=MemberAssessment.STATUS_APPROVED,
            recorded_by_id_FK=self.recorder,
        )
        MemberLedger.objects.create(
            member_id_FK=self.member,
            transaction_type="monthly_dues",
            amount=Decimal("300.00"),
            direction="credit",
            balance_after=Decimal("300.00"),
            reference_id=ma.member_assessment_id_PK,
            reference_type="MemberAssessment",
            description="Monthly Deduction - May 2031",
            recorded_by_user_id_FK=self.recorder,
        )

        data = self.client.get("/api/member/fund/ledger/", **AJAX).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["summary"]["total_in"], 300.0)

    def test_an_unapproved_assessment_shows_as_outstanding(self):
        """A deduction that has not been approved is money the member owes and
        has not paid, so it must still be visible."""
        batch = MonthlyAssessment.objects.create(
            month=date(2031, 5, 1),
            total_amount=Decimal("300.00"),
            status=MonthlyAssessment.STATUS_DRAFT,
            created_by_id_FK=self.recorder,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=batch,
            member_id_FK=self.member,
            standard_assessment=Decimal("300.00"),
            actual_deduction=Decimal("100.00"),
            outstanding_balance=Decimal("200.00"),
            status=MemberAssessment.STATUS_PENDING,
            recorded_by_id_FK=self.recorder,
        )

        data = self.client.get("/api/member/fund/ledger/", **AJAX).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["summary"]["outstanding"], 200.0)

    def test_two_members_each_pay_the_same_fee_but_totals_do_not_merge(self):
        other_user = self._officer("Member", "dc_other")
        other = self._member(other_user, name="Other", employee_id="dc-002")
        for m in (self.member, other):
            fee = MembershipFee.objects.create(
                member_id_FK=m,
                amount=Decimal("100.00"),
                payment_method="OTC",
                payment_status="Paid",
                payment_date=date(2031, 1, 10),
                receipt_number="RCP",
                recorded_by_user_id_FK=self.recorder,
            )
            MemberLedger.objects.create(
                member_id_FK=m,
                transaction_type="membership_fee",
                amount=Decimal("100.00"),
                direction="credit",
                balance_after=Decimal("100.00"),
                reference_id=fee.fee_id_PK,
                reference_type="MembershipFee",
                description="Membership Fee Payment",
                recorded_by_user_id_FK=self.recorder,
            )

        data = self.client.get("/api/member/fund/ledger/", **AJAX).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["summary"]["total_in"], 100.0)


class PersonalRecordsTests(TransparencyTestBase):
    """4. My Records — member-only, always unmasked."""

    def setUp(self):
        self.member_user = self._officer("Member", "pr_member")
        self.recorder = self._officer("Treasurer", "pr_treasurer")
        self.member = self._member(self.member_user)
        self._login(self.member_user)
        self.other_user = self._officer("Member", "pr_other")
        self.other = self._member(
            self.other_user, name="Other Member", employee_id="pr-002"
        )

        self.fee = MembershipFee.objects.create(
            member_id_FK=self.member,
            amount=Decimal("500.00"),
            payment_method="OTC",
            payment_status="Paid",
            payment_date=date(2031, 1, 10),
            receipt_number="RCP-1",
            recorded_by_user_id_FK=self.recorder,
        )
        MembershipFee.objects.create(
            member_id_FK=self.other,
            amount=Decimal("500.00"),
            payment_method="OTC",
            payment_status="Paid",
            payment_date=date(2031, 1, 10),
            receipt_number="RCP-2",
            recorded_by_user_id_FK=self.recorder,
        )

    def test_payments_are_scoped_to_the_signed_in_member(self):
        data = self.client.get("/api/member/records/payments/", **AJAX).json()
        self.assertTrue(data["ok"])
        refs = [row["reference"] for row in data["items"]]
        self.assertIn("RCP-1", refs)
        self.assertNotIn("RCP-2", refs)

    def test_payment_figures_are_real(self):
        data = self.client.get("/api/member/records/payments/", **AJAX).json()
        self.assertEqual(data["items"][0]["amount"], 500.0)
        self.assertNotIn("••••••", str(data))

    def test_dues_matrix_marks_unpaid_months(self):
        data = self.client.get("/api/member/records/dues-matrix/?months=6", **AJAX).json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["grid"]), 6)
        self.assertFalse(data["is_retired"])
        self.assertTrue(any(g["status"] == "Unpaid" for g in data["grid"]))

    def test_dues_matrix_never_bills_a_retired_member(self):
        """Retirement ends the current obligation while preserving history, so
        the matrix must not show a retired member a wall of unpaid months."""
        retired_user = self._officer("Member", "pr_retired")
        self._member(
            retired_user,
            name="Retired Member",
            employee_id="pr-003",
            membership_status="Retired",
            member_classification="Retired",
        )
        self._login(retired_user)

        data = self.client.get("/api/member/records/dues-matrix/?months=6", **AJAX).json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["is_retired"])
        self.assertFalse(
            [g for g in data["grid"] if g["status"] == "Unpaid"],
            "a retired member must not be shown unpaid dues months",
        )

    def test_contributions_endpoint_returns_empty_not_error(self):
        data = self.client.get("/api/member/records/contributions/", **AJAX).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["items"], [])

    def test_dues_matrix_window_ends_at_the_current_month(self):
        """The strip must span the last N months ending at the present one."""
        data = self.client.get("/api/member/records/dues-matrix/?months=6", **AJAX).json()
        today = timezone.localtime().date()
        first_of_this_month = today.replace(day=1)
        expected_start = first_of_this_month
        for _ in range(5):
            expected_start = (expected_start - timedelta(days=1)).replace(day=1)

        self.assertEqual(len(data["grid"]), 6)
        self.assertEqual(data["grid"][0]["key"], expected_start.strftime("%Y-%m"))
        self.assertEqual(data["grid"][-1]["key"], first_of_this_month.strftime("%Y-%m"))

    def test_no_member_id_parameter_is_honoured(self):
        """An IDOR probe must not be able to redirect a member's request at
        somebody else's records."""
        data = self.client.get(
            f"/api/member/records/payments/?member_id={self.other.member_id_PK}", **AJAX
        ).json()
        refs = [row["reference"] for row in data["items"]]
        self.assertNotIn("RCP-2", refs)


class RemovedSurfacesTests(TransparencyTestBase):
    """The disclosure, report and access-history surfaces are gone for good.

    A removed feature that is merely unlinked would be one URL rename away from
    coming back, so these assert the routes 404 rather than that a button is
    hidden.
    """

    def setUp(self):
        self.member_user = self._officer("Member", "rm_member")
        self.recorder = self._officer("Treasurer", "rm_treasurer")
        self.member = self._member(self.member_user)
        self._login(self.member_user)
        self._tx("inflow", "1000.00", "monthly_dues", "Dues", 2031, 1, source_id=1)

    def test_reveal_endpoint_is_gone(self):
        resp = self.client.post("/api/member/fund/reveal/", {"action": "reveal"}, **AJAX)
        self.assertEqual(resp.status_code, 404)

    def test_report_endpoints_are_gone(self):
        self.assertEqual(
            self.client.get("/api/member/fund/reports/", **AJAX).status_code, 404
        )
        self.assertEqual(
            self.client.get("/api/member/fund/reports/1/download/", **AJAX).status_code, 404
        )

    def test_access_history_endpoint_is_gone(self):
        self.assertEqual(
            self.client.get("/api/member/fund/activity/", **AJAX).status_code, 404
        )

    def test_duplicate_personal_transaction_endpoint_is_gone(self):
        """Cash Flow is now the single personal timeline."""
        self.assertEqual(
            self.client.get("/api/member/records/transactions/", **AJAX).status_code, 404
        )

    def test_collections_endpoint_is_gone(self):
        """Collections duplicated the monthly dues matrix and the Cash Flow
        movements, and the three could be made to disagree."""
        self.assertEqual(
            self.client.get("/api/member/collections/", **AJAX).status_code, 404
        )

    def test_no_response_carries_a_masking_flag(self):
        for url in [
            "/api/member/fund/summary/",
            "/api/member/fund/trend/",
            "/api/member/fund/ledger/",
            "/api/member/records/contributions/",
            "/api/member/records/dues-matrix/",
            "/api/member/records/payments/",
        ]:
            data = self.client.get(url, **AJAX).json()
            self.assertNotIn("masked", data, f"{url} still advertises masking")
            self.assertNotIn("revealed", data, f"{url} still advertises a reveal flag")

    def test_no_reveal_grant_is_stored_in_the_session(self):
        self.client.get("/api/member/fund/summary/", **AJAX)
        self.assertNotIn("member_fund_reveal_until", self.client.session)


class ReadAuditTests(TransparencyTestBase):
    """Every financial read lands in the audit trail."""

    def setUp(self):
        self.member_user = self._officer("Member", "au_member")
        self.recorder = self._officer("Treasurer", "au_treasurer")
        self.member = self._member(self.member_user)
        self._login(self.member_user)
        self._tx("inflow", "1000.00", "monthly_dues", "Dues", 2031, 1, source_id=1)

    def test_every_financial_read_is_logged(self):
        officer_id = self.member_user.user_id_PK
        for url in [
            "/api/member/fund/summary/",
            "/api/member/fund/trend/",
            "/api/member/fund/ledger/",
            "/api/member/records/contributions/",
            "/api/member/records/dues-matrix/",
            "/api/member/records/payments/",
        ]:
            before = SensitiveReadLog.objects.filter(reader_id=officer_id).count()
            resp = self.client.get(url, **AJAX)
            self.assertEqual(resp.status_code, 200, url)
            after = SensitiveReadLog.objects.filter(reader_id=officer_id).count()
            self.assertGreater(after, before, f"{url} did not log a sensitive read")

    def test_reads_appear_in_the_global_audit_trail(self):
        self.client.get("/api/member/fund/summary/", **AJAX)
        self.assertTrue(
            GlobalAuditTrail.objects.filter(
                table_name="fund_transaction", action="READ"
            ).exists()
        )


class AuditTrailAccessTests(TransparencyTestBase):
    """Dropping the member-facing access history must not widen or narrow the
    officer audit trail."""

    def setUp(self):
        self.member_user = self._officer("Member", "at_member")
        self.member = self._member(self.member_user)
        self.treasurer = self._officer("Treasurer", "at_treasurer")

    def test_member_cannot_read_the_officer_audit_trail(self):
        self._login(self.member_user)
        resp = self.client.get("/api/audit/trail/", **AJAX)
        self.assertEqual(resp.status_code, 403)

    def test_officer_audit_trail_still_works(self):
        self._login(self.treasurer)
        resp = self.client.get("/api/audit/trail/", **AJAX)
        self.assertEqual(resp.status_code, 200)


class ScopeFailsClosedTests(TransparencyTestBase):
    """An account with no linked Member row gets nothing, not everything."""

    def setUp(self):
        self.orphan = self._officer("Member", "orphan")
        self._login(self.orphan)
        self.recorder = self._officer("Treasurer", "orphan_treasurer")
        self._tx("inflow", "999.00", "monthly_dues", "Dues", 2031, 1, source_id=1)

    def test_every_endpoint_denies_an_unlinked_account(self):
        for url in [
            "/api/member/fund/summary/",
            "/api/member/fund/trend/",
            "/api/member/fund/ledger/",
            "/api/member/records/contributions/",
            "/api/member/records/dues-matrix/",
            "/api/member/records/payments/",
        ]:
            resp = self.client.get(url, **AJAX)
            self.assertEqual(resp.status_code, 403, f"{url} leaked to an unlinked account")
            self.assertNotIn("999", resp.content.decode())

    def test_movement_detail_denies_an_unlinked_account(self):
        resp = self.client.get("/api/member/fund/movement/ledger_1/", **AJAX)
        self.assertEqual(resp.status_code, 403)


class OfficerEndpointsNotWidenedTests(TransparencyTestBase):
    """The Member role gained new URLs, not new powers on officer URLs."""

    def setUp(self):
        self.member_user = self._officer("Member", "ow_member")
        self.member = self._member(self.member_user)
        self._login(self.member_user)
        self.recorder = self._officer("Treasurer", "ow_treasurer")
        self._tx("inflow", "100.00", "monthly_dues", "Dues", 2031, 1, source_id=1)

    def test_treasurer_only_views_stay_closed(self):
        for url in [
            "/api/treasurer/fund-timeline/",
            "/api/treasurer/dashboard/inflow-outflow/",
            "/api/treasurer/dashboard/monthly-flow/",
            "/api/treasurer/fund-reports/",
            "/api/treasurer/other-transactions/list/",
        ]:
            resp = self.client.get(url, **AJAX)
            self.assertEqual(resp.status_code, 403, f"{url} is no longer officer-only")

    def test_shared_fund_endpoints_still_reachable(self):
        """These two were already open to every authenticated role before this
        work; the transparency feature must not have closed them."""
        self.assertEqual(self.client.get("/api/fund-balance/", **AJAX).status_code, 200)
        self.assertEqual(self.client.get("/api/fund-ledger/", **AJAX).status_code, 200)


class FundBalanceContractTests(TransparencyTestBase):
    """Regression guard for the ₱0.00 card bug.

    The dashboard's Total Inflows / Total Outflows cards read `total_in` and
    `total_out`. The API used to return only `month_in` / `month_out`, and the
    client coerced the missing keys to zero — so the cards showed ₱0.00 instead
    of failing loudly.
    """

    def setUp(self):
        self.user = self._officer("Member", "fb_member")
        self._member(self.user)
        self._login(self.user)
        self.recorder = self._officer("Treasurer", "fb_treasurer")
        self._tx("inflow", "1500.00", "monthly_dues", "Dues", 2031, 1, source_id=1)
        self._tx("outflow", "500.00", "aid_post_payment", "Aid", 2031, 2, source_id=2)

    def test_lifetime_totals_are_present(self):
        data = self.client.get("/api/fund-balance/", **AJAX).json()
        self.assertEqual(data["total_in"], 1500.0)
        self.assertEqual(data["total_out"], 500.0)
        self.assertEqual(data["balance"], 1000.0)

    def test_month_to_date_keys_are_still_present(self):
        """The officer dashboard and HTMX partial still read these."""
        data = self.client.get("/api/fund-balance/", **AJAX).json()
        for key in ("month_in", "month_out", "safety_threshold", "available"):
            self.assertIn(key, data)
