import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreSystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core_system'

    def ready(self):
        # Register the FundTransaction live-update broadcasts.
        from core_system import signals  # noqa: F401

        # Start the backup scheduler inside the web process so the daily
        # 12:00 AM DB backup — and the OTP/email queue drains — fire with a
        # plain `runserver` AND under Passenger/cPanel, with no second
        # console window needed. RUN_MAIN is set only in the reloader's
        # serving child (keeps the autoreload parent scheduler-free);
        # --noreload has no child, so the check covers it via sys.argv.
        # Management commands (migrate/shell/test/...) and the standalone
        # scheduler command itself must stay scheduler-free.
        _scheduler_free_commands = {
            "migrate", "makemigrations", "sqlmigrate", "showmigrations",
            "shell", "shell_plus", "dbshell", "test", "collectstatic",
            "createsuperuser", "createsuperuser2", "process_emails",
            "run_backup_scheduler", "check", "validate_templates",
        }
        argv_command = sys.argv[1] if len(sys.argv) > 1 else ""
        if argv_command in _scheduler_free_commands:
            return
        # Reloader parent (runserver without --noreload, RUN_MAIN unset) must
        # stay scheduler-free — the serving child (RUN_MAIN=true) starts it.
        if (
            argv_command == "runserver"
            and "--noreload" not in sys.argv
            and os.environ.get("RUN_MAIN") != "true"
        ):
            return
        try:
            from core_system.management.commands.run_backup_scheduler import (
                start_background_scheduler,
            )

            start_background_scheduler()
        except Exception:
            logger.exception("In-process backup scheduler failed to start")
