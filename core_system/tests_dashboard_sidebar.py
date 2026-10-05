"""Render smoke test for every dashboard that ships a collapsible sidebar.

Confirms the templates still render after the collapsed-by-default +
hover-peek sidebar changes.
"""
from django.test import TestCase
from django.urls import reverse

from core_system.models import OfficerUser
from core_system.tests import _create_zt_verified_session


DASHBOARDS = [
    ("Treasurer", "Treasurer", "treasurer_dashboard"),
    ("Auditor", "Auditor", "auditor_dashboard"),
    ("President", "President", "president_dashboard"),
    ("Superadmin", "Superadmin", "superadmin_dashboard"),
    ("Secretary", "Secretary", "secretary_dashboard"),
    ("System", "System", "systembackup_dashboard"),
    ("PIO", "Public Information Officer", "pio_dashboard"),
]


class DashboardSidebarRenderTests(TestCase):
    def test_all_sidebars_render(self):
        for key, role, url_name in DASHBOARDS:
            with self.subTest(url_name=url_name):
                officer = OfficerUser.objects.create(
                    full_name="%s Smoke" % role,
                    username="sidebar_smoke_%s" % key.lower(),
                    password_hash="unused",
                    role=role,
                    account_status="Active",
                )
                session, token = _create_zt_verified_session(officer)
                session_data = self.client.session
                session_data["access_token"] = token
                session_data["officer_id"] = officer.user_id_PK
                session_data["role"] = officer.role
                session_data.save()

                response = self.client.get(reverse(url_name))
                self.assertEqual(
                    response.status_code,
                    200,
                    "%s -> %s" % (url_name, response.status_code),
                )
                body = response.content.decode("utf-8", "replace")
                self.assertIn("sidebar_peek.js", body)
                officer.delete()
