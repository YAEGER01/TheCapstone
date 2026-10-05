"""Escape hatch for the Zero Trust screen lock.

Use when email delivery is down and officers are stuck on the unlock screen:
    python manage.py zt_clear_locks                # clear every active lock
    python manage.py zt_clear_locks --username juan.admin
"""

from django.core.management.base import BaseCommand

from core_system.models import AccessSession


class Command(BaseCommand):
    help = (
        "Clear Zero Trust screen locks on active officer sessions so they can "
        "unlock with their password (use when OTP email delivery is down)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Only clear the lock for this officer username (default: all).",
        )

    def handle(self, *args, **options):
        username = (options.get("username") or "").strip().lower()
        cleared = 0

        for sess in AccessSession.objects.select_related("user_id_FK").filter(
            session_status="Active"
        ):
            if username and (getattr(sess.user_id_FK, "username", "") or "").lower() != username:
                continue
            policy = sess.session_policy if isinstance(sess.session_policy, dict) else {}
            if not policy.get("zt_locked"):
                continue
            policy["zt_locked"] = False
            policy["zt_lock_reason"] = ""
            sess.session_policy = policy
            sess.save(update_fields=["session_policy"])
            cleared += 1
            self.stdout.write(
                f"Cleared lock for {sess.user_id_FK.full_name} "
                f"({getattr(sess.user_id_FK, 'username', '')})"
            )

        if cleared == 0:
            self.stdout.write("No active screen locks found.")
        self.stdout.write(self.style.SUCCESS(f"Done. {cleared} lock(s) cleared."))
