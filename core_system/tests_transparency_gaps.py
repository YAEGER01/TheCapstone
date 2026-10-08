from decimal import Decimal
from datetime import date, datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import (
    AidTrackingPost,
    FundTransaction,
    MedicalAid,
    Member,
    MemberAssessment,
    MonthlyAssessment,
    OfficerUser,
    TransactionArchive,
)
from core_system.fund_report_views import (
    _build_report_pdf_bytes,
    _fund_report_financials,
)
from core_system.models import OrganizationFundReport

PASSWORD = "Str0ng!Passw0rd"
DEPOSIT_URL = "/api/treasurer/deductions/deposit/"
SLIP = SimpleUploadedFile("slip.pdf", b"%PDF-1.4 test slip", content_type="application/pdf")


class PartialDepositTests(TestCase):
    """A month batch may now be deposited in parts; the batch only moves to
    the Auditor once cumulative deposits reach the recorded total."""

    def _officer(self, role="Treasurer", username="dep_treasurer"):
        return OfficerUser.objects.create(
            full_name="Treasurer User",
            username=username,
            password_hash=hash_password(PASSWORD),
            role=role,
            account_status="Active",
            mfa_enabled=False,
            email=f"{username}@isu.edu.ph",
        )

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()

    def _batch(self, officer, amounts=(500, 300)):
        assessment = MonthlyAssessment.objects.create(
            month=date(2031, 5, 1),
            total_amount=Decimal(sum(amounts)),
            status=MonthlyAssessment.STATUS_PENDING_DEPOSIT,
            created_by_id_FK=officer,
        )
        for name, amount in zip(("Alpha", "Beta"), amounts):
            MemberAssessment.objects.create(
                assessment_id_FK=assessment,
                member_id_FK=Member.objects.create(
                    full_name=name,
                    employee_id=f"emp-{name}-{amount}",
                    membership_status="Permanent",
                    employment_status="Active",
                    member_classification="Teaching",
                    date_joined=timezone.now().date(),
                ),
                standard_assessment=Decimal(amount),
                actual_deduction=Decimal(amount),
                recorded_by_id_FK=officer,
            )
        return assessment

    def _deposit(self, assessment, amount, ref="ORS-1"):
        return self.client.post(
            DEPOSIT_URL,
            {
                "assessment_id": str(assessment.assessment_id_PK),
                "deposit_reference": ref,
                "deposited_amount": str(amount),
                "proof": SimpleUploadedFile("slip.pdf", b"%PDF-1.4 slip", content_type="application/pdf"),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_partial_deposits_accumulate_until_complete(self):
        officer = self._officer()
        self._login(officer)
        assessment = self._batch(officer)  # recorded total 800

        r1 = self._deposit(assessment, 300)
        self.assertTrue(r1.json()["ok"])
        self.assertFalse(r1.json()["completed"])
        self.assertEqual(r1.json()["remaining_to_deposit"], 500.0)
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, MonthlyAssessment.STATUS_PENDING_DEPOSIT)
        self.assertEqual(assessment.deposited_amount, Decimal("300.00"))

        # Over-depositing the remainder is rejected.
        r2 = self._deposit(assessment, 900, ref="ORS-2")
        self.assertEqual(r2.status_code, 400)
        self.assertIn("exceeds the remaining", r2.json()["error"])

        r3 = self._deposit(assessment, 200, ref="ORS-2")
        self.assertFalse(r3.json()["completed"])
        self.assertEqual(r3.json()["remaining_to_deposit"], 300.0)

        # Final partial completes the batch.
        r4 = self._deposit(assessment, 300, ref="ORS-3")
        self.assertTrue(r4.json()["completed"])
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, MonthlyAssessment.STATUS_PENDING_AUDIT)
        self.assertEqual(assessment.deposited_amount, Decimal("800.00"))

    def test_full_deposit_still_works_in_one_call(self):
        officer = self._officer()
        self._login(officer)
        assessment = self._batch(officer)
        r = self._deposit(assessment, 800)
        self.assertTrue(r.json()["completed"])
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, MonthlyAssessment.STATUS_PENDING_AUDIT)


class MemberFundTransparencyTests(TestCase):
    """Members can see the association fund balance and recent transactions."""

    def _member_session(self):
        member_user = OfficerUser.objects.create(
            full_name="Member User",
            username="fund_member",
            password_hash=hash_password(PASSWORD),
            role="Member",
            account_status="Active",
            mfa_enabled=False,
            email="fund_member@isu.edu.ph",
        )
        session, token = create_access_session(
            officer=member_user, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = member_user.user_id_PK
        test_session["role"] = "Member"
        test_session.save()
        return member_user

    def test_balance_and_ledger_reachable_by_member(self):
        member_user = self._member_session()
        FundTransaction.objects.create(
            direction="inflow", source_type="monthly_dues", source_id=1,
            amount=Decimal("1000.00"), description="Dues batch",
            recorded_by_user_id_FK=member_user,
        )
        FundTransaction.objects.create(
            direction="outflow", source_type="aid_post_payment", source_id=2,
            amount=Decimal("250.00"), description="Aid release",
            recorded_by_user_id_FK=member_user,
        )
        resp = self.client.get("/api/fund-balance/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(float(resp.json()["balance"]), 750.0)

        resp2 = self.client.get("/api/fund-ledger/?per_page=10", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp2.status_code, 200)
        data = resp2.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["items"]), 2)


class MemberProfilesPaginationTests(TestCase):
    """The Treasurer member directory is filtered and paginated server-side."""

    @classmethod
    def setUpTestData(cls):
        cls.treasurer = OfficerUser.objects.create(
            full_name="Treasurer User",
            username="prof_treasurer",
            password_hash=hash_password(PASSWORD),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()

    def test_pagination_search_and_classification(self):
        self._login(self.treasurer)
        for i in range(12):
            Member.objects.create(
                full_name=f"Member {i:02d}",
                employee_id=f"mp-{i:03d}",
                membership_status="Permanent",
                employment_status="Active",
                member_classification="Teaching",
                date_joined=timezone.now().date(),
            )
        Member.objects.create(
            full_name="Zed Retired",
            employee_id="mp-nt-001",
            membership_status="Retired",
            employment_status="Active",
            member_classification="Retired",
            date_joined=timezone.now().date(),
        )

        resp = self.client.get("/api/treasurer/member-profiles/list/?page=2&per_page=5",
                               HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data = resp.json()
        self.assertEqual(data["total"], 13)
        self.assertEqual(data["total_pages"], 3)
        self.assertEqual(len(data["members"]), 5)

        resp_q = self.client.get("/api/treasurer/member-profiles/list/?q=Zed",
                                 HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp_q.json()["total"], 1)

        resp_c = self.client.get("/api/treasurer/member-profiles/list/?classification=Retired",
                                 HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp_c.json()["total"], 1)

        resp_page_oob = self.client.get("/api/treasurer/member-profiles/list/?page=99&per_page=5",
                                        HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp_page_oob.json()["page"], 3)

    def test_surname_order_display_name_and_comma_search(self):
        """Directory sorts by surname and shows 'LASTNAME, Firstname M.I.'."""
        self._login(self.treasurer)
        names = ["JUAN A DELA CRUZ", "MARIA CLARA DE LOS SANTOS", "JOSE RIZAL JR"]
        for i, name in enumerate(names):
            Member.objects.create(
                full_name=name,
                employee_id=f"surname-{i:03d}",
                membership_status="Permanent",
                employment_status="Active",
                member_classification="Teaching",
                date_joined=timezone.now().date(),
            )

        asc = self.client.get("/api/treasurer/member-profiles/list/?per_page=100",
                              HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        desc = self.client.get("/api/treasurer/member-profiles/list/?per_page=100&order=desc",
                               HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        asc_shown = [m["display_name"] for m in asc["members"]]
        desc_shown = [m["display_name"] for m in desc["members"]]
        self.assertEqual(asc_shown, [
            "DE LOS SANTOS, MARIA CLARA",
            "DELA CRUZ, JUAN A",
            "RIZAL, JOSE JR",
        ])
        self.assertEqual(desc_shown, list(reversed(asc_shown)))

        comma = self.client.get("/api/treasurer/member-profiles/list/?q=Dela+Cruz%2C+Juan",
                                HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        self.assertEqual(comma["total"], 1)
        self.assertEqual(comma["members"][0]["display_name"], "DELA CRUZ, JUAN A")


class FundReportOutstandingTests(TestCase):
    """The fund report surfaces member outstanding balances (PDF + preview data)."""

    def test_financials_and_pdf_include_outstanding(self):
        treasurer = OfficerUser.objects.create(
            full_name="Treasurer User",
            username="rep_treasurer",
            password_hash=hash_password(PASSWORD),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )
        member = Member.objects.create(
            full_name="Owed Member",
            employee_id="owed-001",
            membership_status="Permanent",
            employment_status="Active",
            member_classification="Teaching",
            date_joined=timezone.now().date(),
        )
        assessment = MonthlyAssessment.objects.create(
            month=date(2031, 6, 1),
            total_amount=Decimal("600.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
            created_by_id_FK=treasurer,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=assessment,
            member_id_FK=member,
            standard_assessment=Decimal("600.00"),
            actual_deduction=Decimal("400.00"),
            outstanding_balance=Decimal("200.00"),
            recorded_by_id_FK=treasurer,
        )

        report = OrganizationFundReport(report_period="2031-06", report_type="monthly")
        report.prepared_by_user_id_FK = treasurer
        report.auditor_verified_by_user_id_FK = treasurer
        report.approved_by_user_id_FK = treasurer
        data = _fund_report_financials(report)
        self.assertIsNotNone(data)
        self.assertEqual(data["total_outstanding"], 200.0)
        self.assertEqual(len(data["outstanding"]), 1)
        self.assertEqual(data["outstanding"][0]["member"], "Owed Member")

        pdf = _build_report_pdf_bytes(report)
        self.assertIsNotNone(pdf)
        self.assertTrue(pdf.startswith(b"%PDF"))


class FundTimelineTests(TestCase):
    """3-column Fund Timeline: credits in, running fund position, debits out."""

    def _login_treasurer(self):
        officer = OfficerUser.objects.create(
            full_name="Treasurer User",
            username="tl_treasurer",
            password_hash=hash_password(PASSWORD),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def _tx(self, direction, amount, year, month, description, source_type="other_transaction", ref=None, source_id=1):
        # recorded_at is auto_now_add, so the historical date is applied with
        # an update after creation.
        tx = FundTransaction.objects.create(
            direction=direction,
            source_type=source_type,
            source_id=source_id,
            amount=Decimal(amount),
            description=description,
            reference_number=ref,
            recorded_by_user_id_FK=OfficerUser.objects.get(username="tl_treasurer"),
        )
        FundTransaction.objects.filter(pk=tx.pk).update(
            recorded_at=timezone.make_aware(datetime(year, month, 15, 10, 30))
        )
        return tx

    def test_timeline_running_balance_by_month(self):
        self._login_treasurer()
        # Seed year: 20,000 in before the timeline year.
        self._tx("inflow", "20000", 2030, 12, "Initial collections", source_type="monthly_dues")

        # January 2031 - a 5-member dues batch WITH aid assessments, booked
        # exactly like the approval does: one dues row + set-aside rows per
        # member, all sharing the batch's COL- collection reference. The
        # whole money that went in = dues 500 + medical 150 + death 50 = 700.
        self._tx("inflow", "100", 2031, 1, "Monthly dues for January 2031 \u2014 member 1", source_type="monthly_dues", ref="COL-00001")
        self._tx("inflow", "50", 2031, 1, "Medical aid set-aside for January 2031 \u2014 member 1", source_type="aid_setaside_medical", ref="COL-00001")
        self._tx("inflow", "100", 2031, 1, "Monthly dues for January 2031 \u2014 member 2", source_type="monthly_dues", ref="COL-00001")
        self._tx("inflow", "50", 2031, 1, "Medical aid set-aside for January 2031 \u2014 member 2", source_type="aid_setaside_medical", ref="COL-00001")
        self._tx("inflow", "100", 2031, 1, "Monthly dues for January 2031 \u2014 member 3", source_type="monthly_dues", ref="COL-00001")
        self._tx("inflow", "100", 2031, 1, "Monthly dues for January 2031 \u2014 member 4", source_type="monthly_dues", ref="COL-00001")
        self._tx("inflow", "30", 2031, 1, "Death aid set-aside for January 2031 \u2014 member 4", source_type="aid_setaside_death", ref="COL-00001")
        self._tx("inflow", "100", 2031, 1, "Monthly dues for January 2031 \u2014 member 5", source_type="monthly_dues", ref="COL-00001")
        self._tx("inflow", "50", 2031, 1, "Medical aid set-aside for January 2031 \u2014 member 5", source_type="aid_setaside_medical", ref="COL-00001")
        self._tx("inflow", "20", 2031, 1, "Death aid set-aside for January 2031 \u2014 member 5", source_type="aid_setaside_death", ref="COL-00001")

        # February: one contribution in, one aid release out; March: a
        # no-aid dues batch (collapsed row, no breakdown drawer).
        self._tx("inflow", "500", 2031, 2, "Member contribution", source_type="contribution")
        self._tx("outflow", "3000", 2031, 2, "Aid release", source_type="aid_post_payment")
        self._tx("inflow", "100", 2031, 3, "Monthly dues for March 2031 \u2014 member 1", source_type="monthly_dues", ref="COL-00002")
        self._tx("inflow", "100", 2031, 3, "Monthly dues for March 2031 \u2014 member 2", source_type="monthly_dues", ref="COL-00002")
        self._tx("inflow", "100", 2031, 3, "Monthly dues for March 2031 \u2014 member 3", source_type="monthly_dues", ref="COL-00002")

        resp = self.client.get("/api/treasurer/fund-timeline/?year=2031",
                               HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["fund_before_year"], 20000.0)
        self.assertEqual(len(data["months"]), 3)

        jan, feb, mar = data["months"]
        self.assertEqual(jan["month_label"], "January 2031")
        # The WHOLE collected money: dues 500 + medical 150 + death 50.
        self.assertEqual(jan["total_in"], 700.0)

        self.assertEqual(len(jan["rows"]), 1)
        batch = jan["rows"][0]
        self.assertEqual(batch["kind"], "batch")
        # The renderer sorts every month's units by ts — a batch without one
        # throws in the browser and the whole timeline stays "Loading…".
        self.assertTrue(batch.get("ts"))
        self.assertEqual(batch["label"], "Monthly dues for January 2031")
        self.assertEqual(batch["count"], 10)
        self.assertEqual(batch["total"], 700.0)
        self.assertEqual(batch["fund_before"], 20000.0)
        self.assertEqual(batch["fund_after"], 20700.0)
        self.assertTrue(batch["has_aid"])
        comps = {c["source_key"]: c for c in batch["components"]}
        self.assertEqual(comps["monthly_dues"]["count"], 5)
        self.assertEqual(comps["monthly_dues"]["total"], 500.0)
        self.assertEqual(comps["aid_setaside_medical"]["count"], 3)
        self.assertEqual(comps["aid_setaside_medical"]["total"], 150.0)
        self.assertEqual(comps["aid_setaside_death"]["count"], 2)
        self.assertEqual(comps["aid_setaside_death"]["total"], 50.0)

        self.assertEqual(feb["total_in"], 500.0)
        self.assertEqual(feb["total_out"], 3000.0)
        self.assertEqual(len(feb["rows"]), 2)
        c_row, d_row = feb["rows"]
        self.assertEqual(c_row["kind"], "single")
        self.assertEqual(c_row["fund_before"], 20700.0)
        self.assertEqual(c_row["fund_after"], 21200.0)
        self.assertEqual(d_row["kind"], "single")
        self.assertEqual(d_row["description"], "Aid release")
        self.assertEqual(d_row["fund_before"], 21200.0)
        self.assertEqual(d_row["fund_after"], 18200.0)

        # March: no-aid batch - one collapsed credit of the collected total,
        # no breakdown drawer.
        self.assertEqual(len(mar["rows"]), 1)
        no_aid = mar["rows"][0]
        self.assertEqual(no_aid["kind"], "batch")
        self.assertFalse(no_aid["has_aid"])
        self.assertEqual(no_aid["total"], 300.0)
        self.assertEqual(no_aid["fund_before"], 18200.0)
        self.assertEqual(no_aid["fund_after"], 18500.0)

        self.assertEqual(data["current_balance"], 18500.0)
        self.assertIn(2031, data["years"])

    def test_timeline_defaults_to_latest_year(self):
        self._login_treasurer()
        self._tx("inflow", "5000", 2029, 3, "Old dues", source_type="monthly_dues")
        resp = self.client.get("/api/treasurer/fund-timeline/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data = resp.json()
        self.assertEqual(data["year"], 2029)
        self.assertEqual(len(data["months"]), 1)

    def test_timeline_aid_recipients(self):
        """Aid on the timeline names its recipient: set-aside components via
        the aid case for their covered month, payouts via the claim itself."""
        self._login_treasurer()
        patient = Member.objects.create(
            full_name="Ana Santos", employee_id="E901", department="C",
            employment_status="Active", membership_status="Permanent",
            member_classification="Teaching", member_type="Member",
            date_joined=date(2030, 1, 1), email="ana@isu.edu.ph",
        )
        claim = MedicalAid.objects.create(
            member_id_FK=patient, request_date=date(2031, 1, 5),
            requested_amount=Decimal("5000.00"), hospital_name="H1",
            hospital_bill_amount=Decimal("8000.00"), claim_year=2031,
            document_status="Complete", policy_record_status="Eligible",
            validated_aid_amount=Decimal("4000.00"), status="Approved",
        )
        archive = TransactionArchive.objects.create(
            transaction_type="medical_aid", record_id=claim.medical_aid_id_PK,
            member_id_FK=patient, member_name=patient.full_name,
            amount=Decimal("4000.00"), validated_amount=Decimal("4000.00"),
            status="Approved",
        )
        AidTrackingPost.objects.create(
            archive_id_FK=archive, aid_type="medical_aid", target_month="2031-01",
            total_expected=Decimal("4000.00"), total_collected=Decimal("0.00"),
            is_active=True,
        )
        # January dues batch with a medical set-aside for the same month.
        self._tx("inflow", "100", 2031, 1, "Monthly dues for January 2031 — member 1", source_type="monthly_dues", ref="COL-00009")
        self._tx("inflow", "50", 2031, 1, "Medical aid set-aside for January 2031 — member 1", source_type="aid_setaside_medical", ref="COL-00009")
        # February payout against the claim (description names nobody).
        self._tx("outflow", "4000", 2031, 2, "Medical payout", source_type="medical_aid", source_id=claim.medical_aid_id_PK)

        resp = self.client.get("/api/treasurer/fund-timeline/?year=2031",
                               HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data = resp.json()
        self.assertTrue(data["ok"])
        jan, feb = data["months"]

        batch = jan["rows"][0]
        self.assertEqual(batch["kind"], "batch")
        comps = {c["source_key"]: c for c in batch["components"]}
        self.assertEqual(comps["aid_setaside_medical"]["recipient"], "Ana Santos")
        self.assertEqual(comps["monthly_dues"]["recipient"], "")

        payout = [r for r in feb["rows"] if r["kind"] == "single"][0]
        self.assertEqual(payout["recipient"], "Ana Santos")
