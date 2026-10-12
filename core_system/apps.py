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

        # START.ps1 live-reload: watch *.html/*.js/*.css and auto-refresh
        # the browser WITHOUT restarting the server. Dev-only: needs
        # DEBUG + CAUFA_DEV_WATCH=1 (set by START.ps1) + runserver command,
        # so Passenger/prod and all management commands are unaffected.
        try:
            if sys.argv[1:2] == ["runserver"]:
                from core_system.dev_reload_watcher import maybe_start_dev_watcher

                maybe_start_dev_watcher()
        except Exception:
            logger.exception("dev reload watcher failed to start")

        # Start the backup scheduler inside the web process on local dev so the
        # daily 12:00 AM DB backup — and the OTP/email queue drains — fire with
        # a plain `runserver` and no second console window needed.
        #
        # cPanel/Passenger: OFF by default. Passenger culls idle processes and
        # spawns multiples, so in-process jobs duplicate or never fire. Use
        # cPanel Cron (deploy/cpanel-cron.txt) instead. Disable via any of:
        #   CPANEL_MODE=True  (also flips SINGLE_WORKER_MODE + scheduler off
        #                      in settings.py), or
        #   DISABLE_BACKGROUND_SCHEDULER=True, or
        #   running under Passenger (PASSENGER_APP_ENV / passenger argv).
        # RUN_MAIN is set only in the reloader's serving child (keeps the
        # autoreload parent scheduler-free); --noreload has no child, so the
        # check covers it via sys.argv.
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
        # cPanel / Passenger kill-switch (env) + auto-detect (Passenger sets
        # PASSENGER_APP_ENV, and its argv[0] contains "passenger").
        try:
            from django.conf import settings as _dj_settings

            if getattr(_dj_settings, "DISABLE_BACKGROUND_SCHEDULER", False):
                return
            if getattr(_dj_settings, "CPANEL_MODE", False):
                return
        except Exception:
            pass
        if os.environ.get("PASSENGER_APP_ENV") or "passenger" in (sys.argv[0] or "").lower():
            return
        if os.environ.get("DISABLE_BACKGROUND_SCHEDULER", "").strip().lower() in {"1", "true", "yes", "on"}:
            return
        if os.environ.get("CPANEL_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
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
