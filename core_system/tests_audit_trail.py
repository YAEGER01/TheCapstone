from datetime import date

from django.test import TestCase, override_settings
from django.utils import timezone

from core_system.audit_trail_utils import build_changes
from core_system.auth_utils import create_access_session, hash_password
from core_system.models import GlobalAuditTrail, Member, OfficerUser
from core_system.shared_view_utils import _record_audit_trail

LIST_URL = "/api/audit/trail/"


def detail_url(trail_id):
    return f"/api/audit/trail/{trail_id}/"


class AuditTrailScopeTests(TestCase):
    """The unified audit trail API must be strictly role scoped."""

    def _login(self, role, username):
        officer = OfficerUser.objects.create(
            full_name=f"{role} User",
            username=username,
            password_hash="unused",
            role=role,
            account_status="Active",
            mfa_enabled=False,
        )
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.trusted_device = True
        policy = session.session_policy or {}
        policy["zt_verified_at"] = timezone.now().isoformat()
        session.session_policy = policy
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def _entry(self, table, action, actor, record_id=1, result="Success"):
        _record_audit_trail(
            table=table,
            record_id=record_id,
            action=action,
            actor=actor,
            ip="127.0.0.1",
            device_info="tests",
            result=result,
        )

    def _get(self, url):
        return self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_member_is_denied(self):
        self._login("Member", "member_audit")
        response = self._get(LIST_URL)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    def test_anonymous_is_denied(self):
        response = self._get(LIST_URL)
        self.assertEqual(response.status_code, 403)

    def test_treasurer_sees_only_own_actions(self):
        treasurer_a = self._login("Treasurer", "treasurer_a")
        self._entry("contribution", "PAID", treasurer_a, record_id=10)

        treasurer_b = OfficerUser.objects.create(
            full_name="Treasurer B",
            username="treasurer_b",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        self._entry("contribution", "PAID", treasurer_b, record_id=11)

        response = self._get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["entries"])
        for entry in data["entries"]:
            self.assertEqual(entry["actor_id"], treasurer_a.user_id_PK)

    def test_auditor_sees_operational_but_not_security(self):
        treasurer = self._login("Treasurer", "treasurer_ops")
        self._entry("contribution", "PAID", treasurer, record_id=20)
        self._entry("officer_user", "LOGIN", treasurer, record_id=treasurer.user_id_PK)

        self._login("Auditor", "auditor_ops")
        data = self._get(LIST_URL).json()
        tables = {entry["table_name"] for entry in data["entries"]}
        self.assertIn("contribution", tables)
        self.assertNotIn("officer_user", tables)

    def test_president_sees_everything(self):
        treasurer = self._login("Treasurer", "treasurer_all")
        self._entry("contribution", "PAID", treasurer, record_id=30)
        self._entry("officer_user", "LOGIN", treasurer, record_id=treasurer.user_id_PK)

        self._login("President", "president_all")
        data = self._get(LIST_URL).json()
        tables = {entry["table_name"] for entry in data["entries"]}
        self.assertIn("contribution", tables)
        self.assertIn("officer_user", tables)

    def test_superadmin_sees_security_only(self):
        treasurer = self._login("Treasurer", "treasurer_sec")
        self._entry("contribution", "PAID", treasurer, record_id=40)
        self._entry("officer_user", "LOGIN", treasurer, record_id=treasurer.user_id_PK)

        self._login("Superadmin", "superadmin_sec")
        data = self._get(LIST_URL).json()
        tables = {entry["table_name"] for entry in data["entries"]}
        self.assertIn("officer_user", tables)
        self.assertNotIn("contribution", tables)

    def test_detail_enforces_scope(self):
        treasurer_a = self._login("Treasurer", "treasurer_detail_a")
        self._entry("contribution", "PAID", treasurer_a, record_id=50, result="Success")
        entry = GlobalAuditTrail.objects.latest("trail_id")

        detail = self._get(detail_url(entry.trail_id))
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()["entry"]
        self.assertEqual(payload["action_label"], "Paid")
        self.assertEqual(payload["module"], "Contributions")
        self.assertIn("old_values", payload)
        self.assertIn("new_values", payload)
        self.assertIn("changes", payload)

        self._login("Treasurer", "treasurer_detail_b")
        denied = self._get(detail_url(entry.trail_id))
        self.assertEqual(denied.status_code, 404)

    def test_status_filter(self):
        treasurer = self._login("Treasurer", "treasurer_status")
        self._entry("contribution", "PAID", treasurer, record_id=60, result="Success")
        self._entry("contribution", "PAID", treasurer, record_id=61, result="Failed")

        response = self._get(LIST_URL + "?status=Failed")
        data = response.json()
        self.assertTrue(data["entries"])
        for entry in data["entries"]:
            self.assertEqual(entry["status"], "Failed")


@override_settings(
    TURNSTILE_SITE_KEY="",
    TURNSTILE_SECRET_KEY="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class LoginAuditTests(TestCase):
    """Login attempts must be written into the audit trail."""

    def test_successful_login_records_entry(self):
        officer = OfficerUser.objects.create(
            full_name="Login Officer",
            username="login_officer",
            password_hash=hash_password("Secret123!"),
            role="Treasurer",
            account_status="Active",
            email="login.officer@example.com",
            mfa_enabled=False,
        )
        # Password-only sign-in is no longer enough: every sign-in now
        # requires email OTP verification.
        response = self.client.post(
            "/login/",
            {"username": "login_officer", "password": "Secret123!"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json().get("mfa_required"))

        officer.refresh_from_db()
        self.assertTrue(officer.mfa_secret)
        from core_system.services.mfa_service import generate_otp

        pre_auth_token = self.client.session.get("mfa_pre_auth_token")
        response = self.client.post(
            "/api/auth/mfa/verify/",
            {"otp": generate_otp(officer.mfa_secret), "pre_auth_token": pre_auth_token},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content)

        entry = GlobalAuditTrail.objects.filter(action="LOGIN").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor_id, officer.user_id_PK)
        self.assertEqual(entry.result, "Success")

    def test_failed_login_records_entry(self):
        response = self.client.post(
            "/login/",
            {"username": "ghost_user", "password": "nope"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 401)

        entry = GlobalAuditTrail.objects.filter(action="LOGIN_FAILED").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.result, "Failed")
        self.assertEqual(entry.actor_type, "Anonymous")
        self.assertEqual(entry.actor_name, "ghost_user")


class AuditTrailChangeResolutionTests(TestCase):
    """The Changes table must show names/labels, not raw column ids."""

    def test_relation_values_resolve_to_names(self):
        officer = OfficerUser.objects.create(
            full_name="Maria Santos",
            username="officer_resolve",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        member = Member.objects.create(
            full_name="Juan Dela Cruz",
            employment_status="Permanent",
            membership_status="Active",
            date_joined=date(2024, 1, 1),
        )

        changes = build_changes(
            "member",
            None,
            {
                "member_id": member.member_id_PK,
                "officer_user_id": officer.user_id_PK,
                "membership_category": "Permanent",
                "amount": "100.00",
            },
        )
        by_field = {c["field"]: c for c in changes}

        self.assertEqual(by_field["Member"]["new"], "Juan Dela Cruz")
        self.assertEqual(by_field["Officer"]["new"], "Maria Santos")
        self.assertEqual(by_field["Membership Category"]["new"], "Permanent")
        self.assertEqual(by_field["Amount"]["new"], "100.00")

    def test_boolean_and_missing_fk_are_readable(self):
        changes = build_changes(
            "member",
            {"member_id": 999999, "setup_complete": False},
            {"setup_complete": True},
        )
        by_field = {c["field"]: c for c in changes}

        self.assertEqual(by_field["Member"]["previous"], "#999999")
        self.assertEqual(by_field["Setup Complete"]["previous"], "No")
        self.assertEqual(by_field["Setup Complete"]["new"], "Yes")
        self.assertTrue(by_field["Setup Complete"]["changed"])


