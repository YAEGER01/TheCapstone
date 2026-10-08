import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import (
    AidSetAside,
    AssessmentItem,
    BudgetLine,
    Claimant,
    DeathAid,
    FundTransaction,
    GlobalAuditTrail,
    MedicalAid,
    Member,
    MemberAssessment,
    MemberCatchupDue,
    MonthlyAssessment,
    OfficerUser,
)
from core_system.services.association_reports import GA_BUILDERS, GA_TITLES


def _officer(username="ga_treasurer", role="Treasurer"):
    return OfficerUser.objects.create(
        full_name=f"{role} GA",
        username=username,
        password_hash=hash_password("GaPass123!"),
        role=role,
        account_status="Active",
        mfa_enabled=False,
    )


class AssociationReportsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = _officer()
        cls.ann = Member.objects.create(
            full_name="Ann Santos", employee_id="E001", department="CCSICT",
            employment_status="Active", membership_status="Permanent",
            member_classification="Teaching", member_type="Member",
            date_joined=date(2025, 6, 1), email="ann@isu.edu.ph",
        )
        cls.bob = Member.objects.create(
            full_name="Bob Reyes", employee_id="E002", department="COE",
            employment_status="Active", membership_status="Temporary",
            member_classification="Teaching", member_type="Member",
            date_joined=date(2026, 1, 10), email="bob@isu.edu.ph",
        )
        cls.jan = MonthlyAssessment.objects.create(
            month=date(2026, 1, 1), total_amount=Decimal("300.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
            created_by_id_FK=cls.officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=cls.jan, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"), priority_order=1,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=cls.jan, purpose=AssessmentItem.PURPOSE_MEDICAL_AID,
            amount=Decimal("200.00"), priority_order=2,
        )
        cls.feb = MonthlyAssessment.objects.create(
            month=date(2026, 2, 1), total_amount=Decimal("300.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
            created_by_id_FK=cls.officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=cls.feb, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"), priority_order=1,
        )
        # Ann: Jan fully paid, Feb partially paid
        MemberAssessment.objects.create(
            assessment_id_FK=cls.jan, member_id_FK=cls.ann,
            standard_assessment=Decimal("300.00"), actual_deduction=Decimal("300.00"),
            outstanding_balance=Decimal("0.00"), status="approved",
            recorded_by_id_FK=cls.officer,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=cls.feb, member_id_FK=cls.ann,
            standard_assessment=Decimal("300.00"), actual_deduction=Decimal("100.00"),
            outstanding_balance=Decimal("200.00"), status="pending",
            recorded_by_id_FK=cls.officer,
        )
        # Bob: Jan fully unpaid
        MemberAssessment.objects.create(
            assessment_id_FK=cls.jan, member_id_FK=cls.bob,
            standard_assessment=Decimal("300.00"), actual_deduction=Decimal("0.00"),
            outstanding_balance=Decimal("300.00"), status="pending",
            recorded_by_id_FK=cls.officer,
        )
        # Bob back dues
        MemberCatchupDue.objects.create(
            member_id_FK=cls.bob, month=date(2025, 12, 1),
            amount=Decimal("100.00"), created_by_id_FK=cls.officer,
        )
        # Claims
        cls.med = MedicalAid.objects.create(
            member_id_FK=cls.ann, request_date=date(2026, 2, 5),
            requested_amount=Decimal("5000.00"), hospital_name="H1",
            hospital_bill_amount=Decimal("8000.00"), claim_year=2026,
            document_status="Complete", policy_record_status="Eligible",
            validated_aid_amount=Decimal("4000.00"), status="Released",
            release_reference="REL-1",
        )
        claimant = Claimant.objects.create(
            member_id_FK=cls.bob,
            full_name="Claimant One", relationship_to_member="spouse",
        )
        cls.death = DeathAid.objects.create(
            member_id_FK=cls.bob, claimant_id_FK=claimant,
            claim_date=date(2026, 3, 2), claim_type="member",
            deceased_name="Bob Sr", relationship_to_member="parent_child",
            funeral_location="Cauayan", benefit_amount=Decimal("10000.00"),
            document_status="Complete", status="Pending",
        )
        # Money
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("600.00"),
            source_type="monthly_dues", source_id=1,
            description="Feb dues", recorded_by_user_id_FK=cls.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("4000.00"),
            source_type="medical_aid", source_id=cls.med.medical_aid_id_PK,
            description="Medical payout", reference_number="REL-1",
            recorded_by_user_id_FK=cls.officer,
        )
        BudgetLine.objects.create(fiscal_year=2026, category="monthly_dues", amount=Decimal("100000.00"))
        GlobalAuditTrail.objects.create(
            table_name="member", record_id=cls.ann.member_id_PK, action="CREATE",
            result="success", actor_type="officer", actor_id=cls.officer.pk,
            actor_name="GA", notes="test entry",
        )

    def setUp(self):
        session, token = create_access_session(
            officer=self.officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.save()
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = self.officer.user_id_PK
        s["role"] = self.officer.role
        s.save()

    # -- registry ------------------------------------------------------
    def test_registry_has_remaining_eight(self):
        self.assertEqual(len(GA_BUILDERS), 8)
        self.assertEqual(len(GA_TITLES), 8)
        resp = self.client.get(reverse("association_reports_meta"))
        self.assertEqual(resp.status_code, 200)
        groups = resp.json()["meta"]["groups"]
        total = sum(len(g["reports"]) for g in groups)
        self.assertEqual(total, 8)

    def test_unknown_key_rejected(self):
        self.assertEqual(
            self.client.get(reverse("association_report_preview", kwargs={"report_key": "nope"})).status_code, 400,
        )
        self.assertEqual(
            self.client.get(reverse("association_report_export", kwargs={"report_key": "nope"})).status_code, 400,
        )

    def _preview(self, key, **params):
        url = reverse("association_report_preview", kwargs={"report_key": key})
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, f"{key}: {resp.content[:200]}")
        report = resp.json()["report"]
        self.assertIn("columns", report)
        self.assertIn("rows", report)
        self.assertIn("summary", report)
        return report

    # -- collections ----------------------------------------------------

    def test_delinquency_threshold(self):
        report = self._preview("delinquency", min_amount="250")
        names = [r["member"] for r in report["rows"]]
        self.assertIn("Bob Reyes", names)  # 300 + 100 catchup
        self.assertNotIn("Ann Santos", names)  # only 200
        all_rows = self._preview("delinquency", min_amount="0")
        self.assertEqual(len(all_rows["rows"]), 2)
        by_name = {r["member"]: r for r in all_rows["rows"]}
        # Status is payment standing: latest owed month per member.
        self.assertEqual(by_name["Bob Reyes"]["status"], "Still Unpaid as of January 2026")
        self.assertEqual(by_name["Bob Reyes"]["oldest_month"], "December 2025")
        self.assertEqual(by_name["Ann Santos"]["status"], "Still Unpaid as of February 2026")

    def test_collection_efficiency(self):
        report = self._preview("collection_efficiency", months="12")
        by_month = {r["month"]: r for r in report["rows"]}
        self.assertEqual(by_month["January 2026"]["expected"], 600.0)
        self.assertEqual(by_month["January 2026"]["collected"], 300.0)
        self.assertEqual(by_month["February 2026"]["collected"], 100.0)


    def test_member_soa(self):
        report = self._preview("member_soa", member_id=str(self.ann.member_id_PK))
        billed = next(s for s in report["summary"] if s["label"] == "Total billed")
        self.assertEqual(billed["value"], 600.0)
        self.assertEqual(len(report["sections"]), 2)
        missing = self._preview("member_soa")
        self.assertIn("Select a member", missing["rows"][0]["item"])

    # -- aid --------------------------------------------------------------
    def test_aid_fund_utilization(self):
        report = self._preview("aid_fund_utilization")
        funds = {r["fund"]: r for r in report["rows"]}
        self.assertEqual(funds["Medical Aid"]["released"], 4000.0)
        self.assertEqual(funds["Medical Aid"]["released_count"], 1)
        self.assertEqual(funds["Death Aid"]["pending_count"], 1)

    def test_claims_register(self):
        report = self._preview("claims_register")
        self.assertEqual(len(report["rows"]), 2)
        med_only = self._preview("claims_register", aid_type="medical")
        self.assertEqual(len(med_only["rows"]), 1)
        released = self._preview("claims_register", status="Released")
        self.assertEqual(len(released["rows"]), 1)

    # -- money --------------------------------------------------------------





    def test_budget_vs_actual(self):
        report = self._preview("budget_vs_actual", year="2026")
        row = next(r for r in report["rows"] if r["category"] == "Monthly Dues Collections")
        self.assertEqual(row["budgeted"], 100000.0)
        self.assertEqual(row["actual"], 600.0)

    def test_aid_utilization_collected_uses_covered_month(self):
        """A January earmark booked today still belongs to January, not to the
        booking date — same covered-month rule as the Fund Overview Summary."""
        ann_jan = MemberAssessment.objects.get(
            assessment_id_FK=self.jan, member_id_FK=self.ann
        )
        med_item = AssessmentItem.objects.get(
            assessment_id_FK=self.jan, purpose=AssessmentItem.PURPOSE_MEDICAL_AID
        )
        tx = FundTransaction.objects.create(
            direction="inflow", amount=Decimal("200.00"),
            source_type="aid_setaside_medical",
            source_id=ann_jan.member_assessment_id_PK,
            description="Medical aid set-aside for January 2026",
            recorded_by_user_id_FK=self.officer,
        )
        AidSetAside.objects.create(
            member_assessment_id_FK=ann_jan, assessment_item_id_FK=med_item,
            fund_transaction_id_FK=tx, aid_type="medical_aid",
            amount=Decimal("200.00"),
        )
        jan = self._preview(
            "aid_fund_utilization",
            date_from="2026-01-01", date_to="2026-01-31",
        )
        funds = {r["fund"]: r for r in jan["rows"]}
        self.assertEqual(funds["Medical Aid"]["collected"], 200.0)
        feb = self._preview(
            "aid_fund_utilization",
            date_from="2026-02-01", date_to="2026-02-28",
        )
        funds = {r["fund"]: r for r in feb["rows"]}
        self.assertEqual(funds["Medical Aid"]["collected"], 0.0)

    def test_budget_dues_actual_uses_covered_year(self):
        """December dues booked in January count for the prior fiscal year."""
        dec = MonthlyAssessment.objects.create(
            month=date(2025, 12, 1), total_amount=Decimal("100.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
            created_by_id_FK=self.officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=dec, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("100.00"), priority_order=1,
        )
        dec_ma = MemberAssessment.objects.create(
            assessment_id_FK=dec, member_id_FK=self.ann,
            standard_assessment=Decimal("100.00"), actual_deduction=Decimal("100.00"),
            outstanding_balance=Decimal("0.00"), status="approved",
            recorded_by_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("500.00"),
            source_type="monthly_dues",
            source_id=dec_ma.member_assessment_id_PK,
            description="December 2025 dues booked late",
            recorded_by_user_id_FK=self.officer,
        )
        report_2026 = self._preview("budget_vs_actual", year="2026")
        row = next(r for r in report_2026["rows"] if r["category"] == "Monthly Dues Collections")
        self.assertEqual(row["actual"], 600.0)
        report_2025 = self._preview("budget_vs_actual", year="2025")
        row = next(r for r in report_2025["rows"] if r["category"] == "Monthly Dues Collections")
        self.assertEqual(row["actual"], 500.0)

    def test_collection_efficiency_honors_selected_period(self):
        """A February filter shows February — not just the latest N months."""
        report = self._preview(
            "collection_efficiency", months="12",
            date_from="2026-02-01", date_to="2026-02-28",
        )
        months = [r["month"] for r in report["rows"]]
        self.assertEqual(months, ["February 2026"])


    def test_membership_registry(self):
        report = self._preview("membership_registry")
        self.assertEqual(len(report["rows"]), 2)
        perm = self._preview("membership_registry", membership_status="Permanent")
        self.assertEqual(len(perm["rows"]), 1)

    def test_audit_trail_export(self):
        report = self._preview("audit_trail_export", table_name="member")
        self.assertTrue(any(r["actor"] == "GA" for r in report["rows"]))

    # -- export formats -------------------------------------------------------
    def test_export_xlsx_and_pdf(self):
        for key in ("delinquency", "member_soa", "budget_vs_actual", "claims_register"):
            base = reverse("association_report_export", kwargs={"report_key": key})
            xlsx = self.client.get(base + "?format=xlsx")
            self.assertEqual(xlsx.status_code, 200, key)
            self.assertIn("spreadsheetml", xlsx["Content-Type"])
            pdf = self.client.get(base + "?format=pdf")
            self.assertEqual(pdf.status_code, 200, key)
            self.assertEqual(pdf["Content-Type"], "application/pdf")
            self.assertTrue(pdf.content.startswith(b"%PDF"))

    # -- budget endpoints -------------------------------------------------------
    def test_budget_save_and_list(self):
        url = reverse("association_budget_save")
        resp = self.client.post(
            url, data=json.dumps({"year": 2027, "lines": [
                {"category": "monthly_dues", "amount": "50000"},
                {"category": "aid_medical", "amount": "20000", "notes": "cap"},
            ]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["saved"], 2)
        listed = self.client.get(reverse("association_budget_lines") + "?year=2027").json()
        self.assertEqual(len(listed["lines"]), 2)
        bad = self.client.post(
            url, data=json.dumps({"year": 2027, "lines": [{"category": "nope", "amount": "1"}]}),
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)
