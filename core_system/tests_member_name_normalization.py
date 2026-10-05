from django.test import TestCase, override_settings
from django.utils import timezone

from core_system.auth_utils import create_access_session
from core_system.models import Member, OfficerUser

CREATE_URL = "/api/treasurer/members/create/"
CREATE_OLD_URL = "/api/treasurer/members/create-old/"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MemberNameUppercaseTests(TestCase):
    """Names typed in lower/mixed case must be stored ALL CAPS at every
    treasurer entry point: Create Member, Create Member (Old), and the
    batch grid/file upload (which share create/ and create-old/)."""

    def _login(self):
        officer = OfficerUser.objects.create(
            full_name="Treasurer Test",
            username="treasurer_namecase",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
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

    def test_create_member_uppercases_names(self):
        self._login()
        response = self.client.post(
            CREATE_URL,
            {
                "first_name": "Justin",
                "middle_initial": "b",
                "last_name": "Reyes",
                "email": "justin.reyes@isu.edu.ph",
                "department": "CCS",
                "position": "Instructor",
                "classification": "Teaching",
                "membership_category": "Permanent",
                "contact": "09171234567",
                "amount": "100",
                "payment_method": "Cash",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        member = Member.objects.get(email="justin.reyes@isu.edu.ph")
        self.assertEqual(member.full_name, "JUSTIN B REYES")

    def test_create_old_member_uppercases_names(self):
        self._login()
        response = self.client.post(
            CREATE_OLD_URL,
            {
                "first_name": "maria",
                "middle_initial": "c",
                "last_name": "santos",
                "email": "maria.santos@isu.edu.ph",
                "department": "COE",
                "position": "Assistant Professor",
                "classification": "Teaching",
                "membership_category": "Permanent",
                "contact": "09181234567",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        member = Member.objects.get(email="maria.santos@isu.edu.ph")
        self.assertEqual(member.full_name, "MARIA C SANTOS")
