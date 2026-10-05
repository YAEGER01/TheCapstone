from django.core.cache import cache
from django.test import TestCase

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import OfficerUser, SystemSetting
from core_system.services import zt_service
from core_system.services.mfa_service import generate_mfa_secret
from core_system import zt_settings

DASHBOARD_URL = "/superadmin/"
UNLOCK_URL = "/api/auth/zt/unlock/"
PASSWORD = "Str0ng!Passw0rd"


class ZeroTrustTimerSettingsTests(TestCase):
    """Superadmin-editable ZT & lockout timers: panel renders, values persist,
    validation guards relationships, and the engine picks the values up live."""

    def setUp(self):
        cache.clear()  # timer values are cached; keep tests isolated

    def _officer(self, role, username):
        return OfficerUser.objects.create(
            full_name=f"{role} User",
            username=username,
            password_hash=hash_password(PASSWORD),
            role=role,
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
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
        return session

    def _payload(self, **overrides):
        payload = {"form_type": "zt_timers"}
        payload.update({
            f["key"]: str(f["default"]) for f in zt_settings.timer_fields()
        })
        payload[zt_settings.ROLES_FIELD] = zt_settings.ROLES_DEFAULT
        payload.update({k: str(v) for k, v in overrides.items()})
        return payload

    # -- panel -------------------------------------------------------------

    def test_panel_renders_for_superadmin(self):
        self._login(self._officer("Superadmin", "sa_set"))
        resp = self.client.get(DASHBOARD_URL)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("sa-card-zt-timers", content)
        self.assertIn("Zero Trust &amp; Lockout Timers", content)
        # Default values are shown in the inputs
        self.assertIn('name="zt_lock_idle_minutes"', content)
        self.assertIn('value="2"', content)

    def test_non_superadmin_cannot_save(self):
        self._login(self._officer("President", "pres_set"))
        resp = self.client.post(
            DASHBOARD_URL, self._payload(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(SystemSetting.objects.filter(setting_key="zt_lock_idle_minutes").exists())

    # -- saving --------------------------------------------------------------

    def test_save_persists_and_engine_reads_it(self):
        officer = self._officer("Superadmin", "sa_save")
        self._login(officer)
        resp = self.client.post(DASHBOARD_URL, self._payload(zt_unlock_max_failures=3))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            SystemSetting.objects.filter(setting_key="zt_unlock_max_failures", setting_value="3").exists()
        )
        self.assertEqual(zt_settings.get_zt_timers()["unlock_max_failures"], 3)

        # Saving again to the same value is reflected too
        resp2 = self.client.post(DASHBOARD_URL, self._payload(zt_lock_idle_minutes=7))
        self.assertEqual(zt_settings.get_zt_timers()["lock_idle"].total_seconds(), 420)

    def test_validation_rejects_relationship_violations(self):
        self._login(self._officer("Superadmin", "sa_valid"))
        resp = self.client.post(
            DASHBOARD_URL,
            self._payload(zt_idle_soft_minutes=20, zt_idle_medium_minutes=15),
        )
        content = resp.content.decode()
        self.assertIn("Soft check idle time must be shorter", content)
        self.assertFalse(SystemSetting.objects.filter(setting_key="zt_idle_soft_minutes").exists())

    def test_validation_rejects_out_of_range(self):
        self._login(self._officer("Superadmin", "sa_range"))
        resp = self.client.post(DASHBOARD_URL, self._payload(zt_lock_idle_minutes=999))
        self.assertIn("must be between", resp.content.decode())
        self.assertFalse(SystemSetting.objects.filter(setting_key="zt_lock_idle_minutes").exists())

    # -- the engine actually uses the saved values ----------------------------

    def test_revoke_threshold_is_dynamic(self):
        # President exercises the password-failure path (no role forces OTP
        # on unlock by default; escalation comes from lock age, risk level,
        # or failed attempts).
        president = self._officer("President", "pres_dyn")
        pres_session, pres_token = create_access_session(
            officer=president, ip_address="127.0.0.1", device_info="tests",
        )
        pres_session.trusted_device = True
        pres_session.save()

        self._login(self._officer("Superadmin", "sa_dyn_admin"))
        self.client.post(DASHBOARD_URL, self._payload(zt_unlock_max_failures=3))

        # Switch the client back to the president's session, lock it, then
        # fail the unlock: 2 wrong passwords + 1 wrong OTP = 3 = revoked.
        test_session = self.client.session
        test_session["access_token"] = pres_token
        test_session["officer_id"] = president.user_id_PK
        test_session["role"] = president.role
        test_session.save()

        zt_service.lock_session(pres_session, "idle")
        for _ in range(2):
            self.client.post(
                UNLOCK_URL, {"password": "wrong"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
            )
        resp = self.client.post(
            UNLOCK_URL, {"otp": "000000"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertTrue(resp.json().get("session_revoked"))
        pres_session.refresh_from_db()
        self.assertEqual(pres_session.session_status, "Revoked")

    def test_lock_idle_setting_reaches_the_client(self):
        officer = self._officer("Superadmin", "sa_client")
        session = self._login(officer)
        self.client.post(DASHBOARD_URL, self._payload(zt_lock_idle_minutes=5))

        status_url = "/api/auth/zero-trust/status/"
        resp = self.client.get(
            status_url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.json()["lock_idle_seconds"], 300)

        session.refresh_from_db()
        _ = session  # silence unused warnings in some linters
