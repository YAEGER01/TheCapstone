from django.test import TestCase

from core_system import zt_settings
from core_system.auth_utils import create_access_session, hash_password
from core_system.models import OfficerUser, SystemSetting
from core_system.services.mfa_service import generate_mfa_secret

DASHBOARD_URL = "/superadmin/"
PASSWORD = "Str0ng!Passw0rd"


class ConsolidatedSettingsTests(TestCase):
    """Consolidated System Settings view: one Update saves all cards,
    each card resets to its code default independently."""
    def _officer(self):
        return OfficerUser.objects.create(
            full_name="SA User",
            username="sa_consolidated",
            password_hash=hash_password(PASSWORD),
            role="Superadmin",
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
            email="sa_consolidated@isu.edu.ph",
        )

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = officer.user_id_PK
        s["role"] = officer.role
        s.save()

    def _payload(self, **overrides):
        p = {"form_type": "system_settings_save_all"}
        p.update({
            "nav_sidebar": "on",
            "isu_email_guard": "on",
            "safety_threshold_amount": "5000",
            "safety_threshold_enabled": "on",
            "banner_duration_seconds": "10",
        })
        p.update({f["key"]: str(f["default"]) for f in zt_settings.timer_fields()})
        p[zt_settings.ROLES_FIELD] = zt_settings.ROLES_DEFAULT
        p.update(overrides)
        return p

    def test_view_renders_cards_and_update_bar(self):
        self._login(self._officer())
        resp = self.client.get(DASHBOARD_URL)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        for marker in (
            'id="system-settings-view"',
            'id="sa-settings-form"',
            'name="form_type" value="system_settings_save_all"',
            'id="sa-card-navigation"',
            'id="sa-card-email-guard"',
            'id="sa-card-duplicate-email"',
            'id="sa-card-back-dues"',
            'id="sa-card-zt-timers"',
            'id="sa-card-threshold"',
            'id="sa-card-banner"',
            "Update All Settings",
            "sa-switch",
            "sa-state-badge",
            "Reset to default",
            "System Settings",
        ):
            self.assertIn(marker, content, f"missing: {marker}")

    def test_save_all_roundtrip(self):
        self._login(self._officer())
        resp = self.client.post(DASHBOARD_URL, self._payload(
            nav_header_strip="on",
            membership_duplicate_email="on",
            dues_require_back_dues_on_join="on",
        ))
        self.assertEqual(resp.status_code, 200)
        get = lambda k: SystemSetting.objects.filter(setting_key=k).first()
        self.assertEqual(get("nav_sidebar_enabled").setting_value, "true")
        self.assertEqual(get("nav_header_strip_enabled").setting_value, "true")
        self.assertEqual(get("isu_email_guard_enabled").setting_value, "true")
        self.assertEqual(get("membership_allow_duplicate_email").setting_value, "true")
        self.assertEqual(get("dues_require_back_dues_on_join").setting_value, "true")
        self.assertEqual(get("safety_threshold_amount").setting_value, "5000.0")
        self.assertEqual(get("safety_threshold_enabled").setting_value, "true")
        self.assertEqual(get("banner_duration_seconds").setting_value, "10")
        self.assertEqual(get("zt_lock_idle_minutes").setting_value, "2")

    def test_unchecked_pills_save_as_off(self):
        self._login(self._officer())
        payload = self._payload()
        # unchecked pills are absent from POST entirely
        for key in ("nav_header_strip", "membership_duplicate_email",
                    "dues_require_back_dues_on_join", "safety_threshold_enabled"):
            payload.pop(key, None)
        resp = self.client.post(DASHBOARD_URL, payload)
        self.assertEqual(resp.status_code, 200)
        get = lambda k: SystemSetting.objects.filter(setting_key=k).first()
        # absent from POST -> OFF
        self.assertEqual(get("nav_header_strip_enabled").setting_value, "false")
        self.assertEqual(get("membership_allow_duplicate_email").setting_value, "false")
        self.assertEqual(get("dues_require_back_dues_on_join").setting_value, "false")
        self.assertEqual(get("safety_threshold_enabled").setting_value, "false")
        # sidebar forced on (at least one navigation required)
        self.assertEqual(get("nav_sidebar_enabled").setting_value, "true")

    def test_invalid_card_skipped_rest_saved(self):
        self._login(self._officer())
        resp = self.client.post(DASHBOARD_URL, self._payload(
            banner_duration_seconds="999",
            safety_threshold_amount="-5",
        ))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Not saved", content)
        self.assertIsNone(SystemSetting.objects.filter(setting_key="banner_duration_seconds").first())
        self.assertIsNone(SystemSetting.objects.filter(setting_key="safety_threshold_amount").first())
        # valid cards still saved
        self.assertEqual(
            SystemSetting.objects.filter(setting_key="isu_email_guard_enabled").first().setting_value,
            "true",
        )

    def test_reset_groups(self):
        self._login(self._officer())
        self.client.post(DASHBOARD_URL, self._payload(
            nav_header_strip="on",
            membership_duplicate_email="on",
            dues_require_back_dues_on_join="on",
        ))
        for group in ("navigation", "email_guard", "duplicate_email", "back_dues",
                       "zt_timers", "safety_threshold", "banner"):
            resp = self.client.post(DASHBOARD_URL, {
                "form_type": "system_settings_reset",
                "reset_group": group,
            })
            self.assertEqual(resp.status_code, 200, group)
        self.assertFalse(SystemSetting.objects.filter(setting_key="nav_sidebar_enabled").exists())
        self.assertFalse(SystemSetting.objects.filter(setting_key="isu_email_guard_enabled").exists())
        self.assertFalse(SystemSetting.objects.filter(setting_key="membership_allow_duplicate_email").exists())
        self.assertFalse(SystemSetting.objects.filter(setting_key="dues_require_back_dues_on_join").exists())
        self.assertFalse(SystemSetting.objects.filter(setting_key__startswith="zt_").exists())
        self.assertFalse(SystemSetting.objects.filter(setting_key="safety_threshold_amount").exists())
        self.assertFalse(SystemSetting.objects.filter(setting_key="banner_duration_seconds").exists())
        # unknown group rejected
        resp = self.client.post(DASHBOARD_URL, {
            "form_type": "system_settings_reset",
            "reset_group": "nope",
        })
        self.assertIn("Unknown settings group", resp.content.decode())
