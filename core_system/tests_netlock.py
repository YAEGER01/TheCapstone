"""Network-change lockout: debounced detector, lock copy, password re-baseline."""
from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from core_system.auth_utils import hash_password
from core_system.models import AccessSession, OfficerUser
from core_system.services import zt_service


def _officer(username="net_officer"):
    return OfficerUser.objects.create(
        full_name="Net Officer", username=username,
        password_hash=hash_password("Str0ng!Pass1"),
        role="Secretary", account_status="Active", email="net@isu.edu.ph",
    )


def _session(officer, ip="192.168.1.10"):
    return AccessSession.objects.create(
        user_id_FK=officer, token_id=f"tok_{officer.username}_{ip}",
        ip_address=ip, expires_at=timezone.now() + timedelta(hours=8),
        session_status="Active", last_activity_at=timezone.now(),
        session_policy={
            "zt_snapshot": {
                "ua_family": "Chrome", "ua_platform": "Windows",
                "ip": ip, "ip_net": zt_service.ip_network_key(ip),
            },
            "zt_ip_baseline": zt_service.ip_network_key(ip),
        },
    )


def _req(ip, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120"):
    rf = RequestFactory()
    req = rf.get("/treasurer/", REMOTE_ADDR=ip, HTTP_USER_AGENT=ua)
    return req


class NetlockDetectorTests(TestCase):
    def test_stable_network_is_none(self):
        s = _session(_officer())
        out = zt_service.track_network_drift(s, _req("192.168.1.55"))
        self.assertEqual(out["state"], "none")

    def test_first_sighting_only_arms_candidate(self):
        s = _session(_officer("o2"))
        out = zt_service.track_network_drift(s, _req("10.20.30.40"))
        self.assertEqual(out["state"], "pending")
        self.assertFalse(zt_service.is_locked(s))

    def test_persistent_new_network_confirms(self):
        s = _session(_officer("o3"))
        zt_service.track_network_drift(s, _req("10.20.30.40"))
        # age the candidate past the stability window
        policy = dict(s.session_policy)
        cand = dict(policy["zt_net_candidate"])
        cand["first_seen"] = (timezone.now() - timedelta(seconds=60)).isoformat()
        policy["zt_net_candidate"] = cand
        s.session_policy = policy
        s.save(update_fields=["session_policy"])
        out = zt_service.track_network_drift(s, _req("10.20.30.41"))
        self.assertEqual(out["state"], "confirmed")
        self.assertEqual(out["from_net"], "192.168.1")
        self.assertEqual(out["to_net"], "10.20.30")

    def test_flap_back_disarms_silently(self):
        s = _session(_officer("o4"))
        zt_service.track_network_drift(s, _req("10.20.30.40"))
        out = zt_service.track_network_drift(s, _req("192.168.1.99"))
        self.assertEqual(out["state"], "none")
        s.refresh_from_db()
        self.assertNotIn("zt_net_candidate", s.session_policy)

    def test_lock_note_names_what_changed(self):
        s = _session(_officer("o5"))
        zt_service.track_network_drift(s, _req("10.20.30.40"))
        policy = dict(s.session_policy)
        cand = dict(policy["zt_net_candidate"])
        cand["first_seen"] = (timezone.now() - timedelta(seconds=60)).isoformat()
        policy["zt_net_candidate"] = cand
        s.session_policy = policy
        s.save(update_fields=["session_policy"])
        track = zt_service.track_network_drift(s, _req("10.20.30.41"))
        zt_service.apply_network_lock(s, _req("10.20.30.41"), track)
        s.refresh_from_db()
        self.assertTrue(zt_service.is_locked(s))
        note = zt_service.lock_note(s)
        self.assertIn("Is this you?", note)
        self.assertIn("192.168.1.xxx", note)
        self.assertIn("10.20.30.xxx", note)
        self.assertIn("password", note.lower())

    def test_password_unlock_adopts_new_baseline(self):
        s = _session(_officer("o6"))
        zt_service.track_network_drift(s, _req("10.20.30.40"))
        policy = dict(s.session_policy)
        cand = dict(policy["zt_net_candidate"])
        cand["first_seen"] = (timezone.now() - timedelta(seconds=60)).isoformat()
        policy["zt_net_candidate"] = cand
        s.session_policy = policy
        s.save(update_fields=["session_policy"])
        track = zt_service.track_network_drift(s, _req("10.20.30.41"))
        zt_service.apply_network_lock(s, _req("10.20.30.41"), track)
        zt_service.clear_lock(s, _req("10.20.30.41"), "password")
        s.refresh_from_db()
        self.assertFalse(zt_service.is_locked(s))
        self.assertEqual(s.session_policy.get("zt_ip_baseline"), "10.20.30")
        # next request on the new network is quiet — no instant re-lock
        out = zt_service.track_network_drift(s, _req("10.20.30.77"))
        self.assertEqual(out["state"], "none")
