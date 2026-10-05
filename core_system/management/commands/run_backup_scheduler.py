from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from core_system.services.backup_service import create_backup_bundle, create_config_backup, create_db_backup, create_media_backup
from core_system.services.dues_reminder import run_dues_reminders
from core_system.services.email_service import process_email_queue

logger = logging.getLogger(__name__)


def _drain_email_queue():
    """Flush queued mail.

    The request-time daemon thread only fires while the app is serving
    requests, so anything queued while idle sat there until the next click.
    """
    try:
        process_email_queue()
    except Exception:
        logger.exception("Email queue processing failed")


def _drain_otp_queue():
    """Fast OTP-only drain so verification codes go out within seconds even
    when the request-time worker died with a page close.

    OTP-first ordering in process_email_queue + small batch keeps this cheap
    (~one SMTP send); bulk mail waits for the 2-minute full drain.
    """
    try:
        process_email_queue(batch_size=10)
    except Exception:
        logger.exception("OTP queue drain failed")


def _purge_expired_rows():
    try:
        call_command("purge_expired_rows")
    except Exception:
        logger.exception("Row retention purge failed")


# Live status of the in-process scheduler, read by the system backup dashboard.
scheduler_state = {
    "running": False,
    "scheduler": None,
    "started_at": None,
}


def _register_jobs(scheduler: BackgroundScheduler, *, db_retention: int, media_retention: int, config_retention: int) -> None:
    # Daily DB backup at 12:00 AM (midnight), as required by the backup policy.
    scheduler.add_job(
        lambda: create_db_backup(retention_count=db_retention),
        trigger=CronTrigger(hour=0, minute=0),
        id="backup_db_daily_0000",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )

    # Weekly media backup: every Sunday 00:15, just after the midnight DB dump
    scheduler.add_job(
        lambda: create_media_backup(retention_count=media_retention),
        trigger=CronTrigger(day_of_week="sun", hour=0, minute=15),
        id="backup_media_weekly_sun_0015",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )

    # Config backup: weekly at the same slot (Sun 00:15)
    scheduler.add_job(
        lambda: create_config_backup(retention_count=config_retention),
        trigger=CronTrigger(day_of_week="sun", hour=0, minute=15),
        id="backup_config_weekly_sun_0015",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )

    # Monthly dues reminders: daily 08:00
    scheduler.add_job(
        lambda: run_dues_reminders(dry_run=False),
        trigger=CronTrigger(hour=8, minute=0),
        id="dues_reminders_daily_0800",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )

    # Queued email: every 2 minutes, so OTPs and reminders go out even
    # when nobody is clicking through the app.
    scheduler.add_job(
        _drain_email_queue,
        trigger=CronTrigger(minute="*/2"),
        id="email_queue_every_2min",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )

    # OTP fast lane: every 30s, bounded to 10 (OTP-first ordering), so a
    # verification code queued by a closed/abandoned page still sends in
    # seconds without waiting for the 2-minute full drain.
    scheduler.add_job(
        _drain_otp_queue,
        trigger=IntervalTrigger(seconds=30),
        id="otp_queue_every_30s",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    # Row retention: daily 02:30, well after the midnight backup is written.
    scheduler.add_job(
        _purge_expired_rows,
        trigger=CronTrigger(hour=2, minute=30),
        id="purge_expired_rows_daily_0230",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )

    # Connection hygiene: scheduler jobs run in worker threads with no
    # request cycle, so Django never closes their DB handles — every 30s
    # OTP drain leaked another connection until MySQL hit 1040
    # (Too many connections). Release after every job instead.
    try:
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

        def _close_job_connection(_event):
            try:
                from django.db import close_old_connections
                close_old_connections()
            except Exception:
                pass

        scheduler.add_listener(_close_job_connection, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    except Exception:
        logger.exception("Failed to attach scheduler DB-cleanup listener")


def start_background_scheduler(*, db_retention: int = 7, media_retention: int = 4, config_retention: int = 4) -> BackgroundScheduler:
    """Start the backup scheduler inside an already-running process.

    Called by apps.ready() when running under `runserver`, so the midnight
    DB backup works without a second console window. Idempotent: a second
    call while the scheduler is alive returns the existing instance.
    """
    if scheduler_state["running"] and scheduler_state["scheduler"] is not None:
        return scheduler_state["scheduler"]

    scheduler = BackgroundScheduler(timezone=timezone.get_current_timezone())
    _register_jobs(
        scheduler,
        db_retention=db_retention,
        media_retention=media_retention,
        config_retention=config_retention,
    )
    scheduler.start()
    scheduler_state.update(running=True, scheduler=scheduler, started_at=timezone.now())
    logger.info("In-process backup scheduler started (DB backup daily at 12:00 AM)")
    return scheduler


class Command(BaseCommand):
    help = "Run the backup scheduler (autobackup)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run backup tasks once immediately, then exit.",
        )

        parser.add_argument(
            "--db-retention",
            type=int,
            default=7,
            help="Retention count for DB backups.",
        )
        parser.add_argument(
            "--media-retention",
            type=int,
            default=4,
            help="Retention count for media backups.",
        )
        parser.add_argument(
            "--config-retention",
            type=int,
            default=4,
            help="Retention count for config backups.",
        )

    def handle(self, *args, **options):
        once: bool = bool(options.get("once"))
        db_retention: int = int(options.get("db_retention"))
        media_retention: int = int(options.get("media_retention"))
        config_retention: int = int(options.get("config_retention"))

        logger.info("Backup scheduler starting at %s", timezone.now().isoformat())

        if once:
            self.stdout.write("Running backup tasks once...")
            create_db_backup(retention_count=db_retention)
            create_media_backup(retention_count=media_retention)
            create_config_backup(retention_count=config_retention)
            self.stdout.write(self.style.SUCCESS("Backup tasks completed."))
            return

        scheduler = BackgroundScheduler(timezone=timezone.get_current_timezone())
        _register_jobs(
            scheduler,
            db_retention=db_retention,
            media_retention=media_retention,
            config_retention=config_retention,
        )

        scheduler.start()
        self.stdout.write(self.style.SUCCESS("Backup scheduler is running. Press Ctrl+C to stop."))

        try:
            # Keep process alive.
            import time

            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            scheduler.shutdown(wait=False)
            logger.info("Backup scheduler stopped")
