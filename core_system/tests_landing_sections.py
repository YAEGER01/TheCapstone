"""Landing-page visibility toggles: store round-trip + template gating."""
from django.test import TestCase

from core_system.landing_sections import (
    get_landing_sections,
    reset_landing_sections,
    set_landing_sections,
)
from core_system.models import SystemSetting


class LandingSectionStoreTests(TestCase):
    def test_defaults_all_visible(self):
        self.assertTrue(all(get_landing_sections().values()))

    def test_set_false_persists_and_reset_restores(self):
        set_landing_sections({"announcements": False, "nav_about": False})
        flags = get_landing_sections()
        self.assertFalse(flags["announcements"])
        self.assertFalse(flags["nav_about"])
        self.assertTrue(flags["news_highlights"])  # untouched stays default
        reset_landing_sections()
        self.assertTrue(all(get_landing_sections().values()))
        self.assertFalse(
            SystemSetting.objects.filter(setting_key__startswith="landing_").exists()
        )


class LandingTemplateGatingTests(TestCase):
    def test_cards_and_nav_visible_by_default(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(">Announcements</h3>", html)
        self.assertIn('id="placeholder-card"', html)
        self.assertIn(">Live Location</h3>", html)
        self.assertIn(">Officers <i", html)

    def test_hidden_card_and_nav_omitted(self):
        set_landing_sections({"announcements": False, "placeholder_card": False,
                              "nav_officers": False})
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertNotIn(">Announcements</h3>", html)
        self.assertNotIn('id="placeholder-card"', html)
        self.assertNotIn(">Officers <i", html)
        # everything else still there
        self.assertIn(">Quick Links</h3>", html)
        self.assertIn(">About Us <i", html)
