from datetime import date

from django.test import TestCase
from django.utils import timezone

from core_system.fund_report_views import (
    _build_report_pdf_bytes,
    _fund_report_financials,
    _period_words,
)
from core_system.models import (
    AidSetAside,
    AidTrackingPost,
    AssessmentItem,
    FundTransaction,
    MedicalAid,
    Member,
    MemberAssessment,
    MonthlyAssessment,
    OfficerUser,
    OrganizationFundReport,
    TransactionArchive,
)
from core_system.services.reporting import (
    compliance_periods,
    generate_organization_fund_report,
    merge_dept_summaries,
    months_covered_by,
    parse_report_period,
    report_type_label,
    resolve_report_range,
    resolve_report_range_from_period,
)


class ReportRangeTests(TestCase):
    def test_monthly_range_is_the_whole_month(self):
        start, end, label = resolve_report_range("monthly", 2026, 9)
        self.assertEqual(start, date(2026, 9, 1))
        self.assertEqual(end, date(2026, 9, 30))
        self.assertEqual(label, "2026-09")

    def test_weekly_range_is_a_seven_day_window(self):
        start, end, label = resolve_report_range("weekly", 2026, 9, 2)
        self.assertEqual(start, date(2026, 9, 8))
        self.assertEqual(end, date(2026, 9, 14))
        self.assertEqual(label, "2026-09-W2")

    def test_weekly_range_clips_at_the_end_of_a_short_month(self):
        start, end, label = resolve_report_range("weekly", 2026, 9, 5)
        self.assertEqual(start, date(2026, 9, 29))
        self.assertEqual(end, date(2026, 9, 30))
        self.assertEqual(label, "2026-09-W5")

    def test_weekly_defaults_to_week_one(self):
        start, end, _ = resolve_report_range("weekly", 2026, 9)
        self.assertEqual(start, date(2026, 9, 1))
        self.assertEqual(end, date(2026, 9, 7))

    def test_yearly_range_spans_the_calendar_year(self):
        start, end, label = resolve_report_range("yearly", 2026, 1)
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 12, 31))
        self.assertEqual(label, "2026")

    def test_report_type_label_defaults_to_monthly(self):
        self.assertEqual(report_type_label("weekly"), "Weekly")
        self.assertEqual(report_type_label("monthly"), "Monthly")
        self.assertEqual(report_type_label("yearly"), "Yearly")
        self.assertEqual(report_type_label(None), "Monthly")
        self.assertEqual(report_type_label("nonsense"), "Monthly")

    def test_period_round_trips(self):
        for report_type, year, month, week in [
            ("weekly", 2026, 9, 3),
            ("monthly", 2026, 9, None),
            ("yearly", 2026, 1, None),
        ]:
            _, _, label = resolve_report_range(report_type, year, month, week)
            self.assertEqual(parse_report_period(label), (report_type, year, month, week))
            self.assertEqual(
                resolve_report_range_from_period(label),
                resolve_report_range(report_type, year, month, week),
            )

    def test_unparseable_period_returns_none(self):
        self.assertIsNone(parse_report_period("nonsense"))
        self.assertIsNone(parse_report_period(""))
        self.assertIsNone(resolve_report_range_from_period("nonsense"))

    def test_months_covered_by_single_and_multi_month_windows(self):
        start, end, _ = resolve_report_range("monthly", 2026, 9)
        self.assertEqual(months_covered_by(start, end), ["2026-09"])

        start, end, _ = resolve_report_range("yearly", 2026, 1)
        months = months_covered_by(start, end)
        self.assertEqual(len(months), 12)
        self.assertEqual(months[0], "2026-01")
        self.assertEqual(months[-1], "2026-12")

    def test_compliance_periods_stay_monthly_except_yearly(self):
        self.assertEqual(compliance_periods("weekly", 2026, 9), [(2026, 9)])
        self.assertEqual(compliance_periods("monthly", 2026, 9), [(2026, 9)])
        self.assertEqual(compliance_periods("yearly", 2026, 9), [(2026, m) for m in range(1, 13)])

    def test_merge_dept_summaries_totals_across_months(self):
        merged = merge_dept_summaries([
            [{"department_id": 1, "department_name": "CCSICT", "total_members": 10,
              "paid_count": 8, "unpaid_count": 2, "percentage": 80.0}],
            [{"department_id": 1, "department_name": "CCSICT", "total_members": 10,
              "paid_count": 5, "unpaid_count": 5, "percentage": 50.0}],
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["total_members"], 20)
        self.assertEqual(merged[0]["paid_count"], 13)
        self.assertEqual(merged[0]["unpaid_count"], 7)
        self.assertEqual(merged[0]["percentage"], 65.0)

    def test_period_words_for_every_period_format(self):
        self.assertEqual(_period_words("2026-09"), "September 2026")
        self.assertEqual(_period_words("2026-09-W2"), "Week 2 of September 2026")
        self.assertEqual(_period_words("2026"), "2026")
        self.assertEqual(_period_words(""), "")
        self.assertEqual(_period_words("bad"), "bad")


class FundReportPeriodFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = OfficerUser.objects.create(
            full_name="Treasurer Test",
            username="treasurer_periods",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )

    def _tx(self, amount, at):
        tx = FundTransaction.objects.create(
            direction="inflow",
            amount=amount,
            source_type="monthly_dues",
            source_id=1,
            description="Period filter fixture",
            recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.filter(pk=tx.pk).update(recorded_at=at)
        return tx

    def _summary_rows(self, wb):
        ws = wb["Fund Summary"]
        return {row[0]: row[1] for row in ws.iter_rows(min_row=4, max_col=2, values_only=True) if row[0]}

    def setUp(self):
        import pytz
        from datetime import datetime

        def at(month, day, hour):
            return pytz.UTC.localize(datetime(2026, month, day, hour, 0, 0))

        # Week 1 (Sep 1-7), week 2 (Sep 8-14), late September, and outside
        # September entirely — so monthly and yearly totals differ.
        self._tx("100.00", at(9, 3, 9))
        self._tx("200.00", at(9, 10, 9))
        self._tx("400.00", at(9, 20, 9))
        self._tx("800.00", at(8, 12, 9))

    def test_weekly_report_only_includes_that_week(self):
        week1 = self._summary_rows(generate_organization_fund_report(2026, 9, "weekly", week=1))
        week2 = self._summary_rows(generate_organization_fund_report(2026, 9, "weekly", week=2))

        self.assertEqual(week1["Report Type"], "Weekly")
        self.assertEqual(week1["Date Range"], "2026-09-01 to 2026-09-07")
        self.assertEqual(float(week1["Total Inflows"]), 100.0)
        self.assertEqual(week1["Number of Transactions"], 1)

        self.assertEqual(week2["Period"], "2026-09-W2")
        self.assertEqual(float(week2["Total Inflows"]), 200.0)
        self.assertEqual(week2["Number of Transactions"], 1)

    def test_monthly_report_covers_the_whole_month(self):
        rows = self._summary_rows(generate_organization_fund_report(2026, 9, "monthly"))
        self.assertEqual(rows["Report Type"], "Monthly")
        self.assertEqual(rows["Date Range"], "2026-09-01 to 2026-09-30")
        self.assertEqual(float(rows["Total Inflows"]), 100 + 200 + 400)
        self.assertEqual(rows["Number of Transactions"], 3)

    def test_yearly_report_covers_every_month(self):
        rows = self._summary_rows(generate_organization_fund_report(2026, 9, "yearly"))
        self.assertEqual(rows["Report Type"], "Yearly")
        self.assertEqual(rows["Period"], "2026")
        self.assertEqual(rows["Date Range"], "2026-01-01 to 2026-12-31")
        self.assertEqual(float(rows["Total Inflows"]), 100 + 200 + 400 + 800)
        self.assertEqual(rows["Number of Transactions"], 4)


class FundReportHistorySheetsTests(TestCase):
    """Deposit/withdrawal history and outstanding balances are reported too."""

    @classmethod
    def setUpTestData(cls):
        cls.officer = OfficerUser.objects.create(
            full_name="Treasurer Sheets",
            username="treasurer_sheets",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        cls.member = Member.objects.create(
            full_name="Dela Cruz, Ana",
            employee_id="EMP-01",
            department="IT",
            employment_status="Active",
            membership_status="Permanent",
            date_joined=date(2020, 1, 1),
        )

    @classmethod
    def _tx(cls, direction, amount, at, reference):
        tx = FundTransaction.objects.create(
            direction=direction,
            amount=amount,
            source_type="other_transaction",
            source_id=0,
            description=f"{direction} fixture",
            reference_number=reference,
            recorded_by_user_id_FK=cls.officer,
        )
        FundTransaction.objects.filter(pk=tx.pk).update(recorded_at=at)
        return tx

    def setUp(self):
        import pytz
        from datetime import datetime

        def at(month, day, hour):
            return pytz.UTC.localize(datetime(2026, month, day, hour, 0, 0))

        self._tx("inflow", "500.00", at(9, 5, 9), "OR-1001")
        self._tx("outflow", "150.00", at(9, 6, 9), "DR-1001")

        self.assessment = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1),
            total_amount="300.00",
            status=MonthlyAssessment.STATUS_PENDING_DEPOSIT,
            deposit_reference="BD-555",
            deposited_amount="300.00",
            deposited_at=at(9, 20, 9),
            deposited_by_id_FK=self.officer,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.assessment,
            member_id_FK=self.member,
            standard_assessment="300.00",
            actual_deduction="225.00",
            outstanding_balance="75.00",
            status=MemberAssessment.STATUS_PENDING,
        )

        self.rejected = MonthlyAssessment.objects.create(
            month=date(2026, 8, 1),
            total_amount="999.00",
            status=MonthlyAssessment.STATUS_REJECTED,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.rejected,
            member_id_FK=self.member,
            standard_assessment="999.00",
            actual_deduction="0.00",
            outstanding_balance="999.00",
        )

    def _sheet_rows(self, wb, name):
        return list(wb[name].iter_rows(min_row=2, values_only=True))

    def _summary_rows(self, wb):
        ws = wb["Fund Summary"]
        return {row[0]: row[1] for row in ws.iter_rows(min_row=4, max_col=2, values_only=True) if row[0]}

    def test_summary_reports_deposits_and_outstanding_balance(self):
        rows = self._summary_rows(generate_organization_fund_report(2026, 9, "monthly"))
        self.assertEqual(rows["Deposits and Withdrawals"], 3)
        self.assertEqual(float(rows["Total Outstanding Balance"]), 75.0)

    def test_deposit_withdrawal_sheet_keeps_cash_movements_apart(self):
        wb = generate_organization_fund_report(2026, 9, "monthly")
        kinds = [r[1] for r in self._sheet_rows(wb, "Deposits and Withdrawals")]
        self.assertEqual(kinds, ["Deposit", "Withdrawal", "Dues Deposit"])

        refs = [r[2] for r in self._sheet_rows(wb, "Deposits and Withdrawals")]
        self.assertEqual(refs, ["OR-1001", "DR-1001", "BD-555"])

    def test_outstanding_balances_sheet_excludes_rejected_months(self):
        wb = generate_organization_fund_report(2026, 9, "monthly")
        rows = self._sheet_rows(wb, "Outstanding Balances")
        member_rows = [r for r in rows if r[0] == "Dela Cruz, Ana"]
        self.assertEqual(len(member_rows), 1)
        self.assertEqual(member_rows[0][3], "September 2026")
        self.assertEqual(float(member_rows[0][6]), 75.0)

        total_rows = [r for r in rows if r[0] == "TOTAL OUTSTANDING"]
        self.assertEqual(len(total_rows), 1)
        self.assertEqual(float(total_rows[0][6]), 75.0)
