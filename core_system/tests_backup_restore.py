"""Backup & restore tests: path guard, zip-slip, codebase backup/restore,
scheduler registration, and DB-restore bookkeeping (mysql mocked).
"""
import gzip
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

from core_system.models import BackupJob
from core_system.services import backup_service


class _FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class BackupPathGuardTests(TestCase):
    def test_restore_refuses_paths_outside_backups_folder(self):
        with self.assertRaises(ValueError):
            backup_service._ensure_inside_backups(Path(r"C:\Windows\evil.sql.gz"))

    def test_restore_accepts_paths_inside_backups_folder(self):
        inside = Path(settings.MEDIA_ROOT) / "backups" / "db" / "db_x.sql.gz"
        try:
            backup_service._ensure_inside_backups(inside)
        except ValueError:
            self.fail("Path inside backups folder was rejected")

    def test_restore_accepts_paths_inside_secure_backup_root(self):
        from django.test import override_settings as _os

        with TemporaryDirectory() as tmp:
            new_root = Path(tmp) / "secure"
            inside = new_root / "db" / "db_x.sql.gz.enc"
            with _os(SECURE_BACKUP_ROOT=str(new_root)):
                try:
                    backup_service._ensure_inside_backups(inside)
                except ValueError:
                    self.fail("Path inside SECURE_BACKUP_ROOT was rejected")


class SystemBackupRestoreTests(TestCase):
    def _make_zip(self, path: Path, names=("manage.py", "core_system/views.py")):
        with zipfile.ZipFile(path, "w") as zf:
            for name in names:
                zf.writestr("./" + name, "# fake")

    @override_settings(MEDIA_ROOT="", BASE_DIR=Path(""))
    def test_system_restore_rejects_zip_slip(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            media = tmp / "media"
            (media / "backups" / "system").mkdir(parents=True)
            archive = media / "backups" / "system" / "system_x.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escaped.txt", "evil")

            with override_settings(MEDIA_ROOT=str(media), BASE_DIR=tmp / "proj", SECURE_BACKUP_ROOT=str(tmp / "secure")):
                with self.assertRaises(ValueError):
                    backup_service.restore_system_from_archive(system_archive_path=str(archive))

    def test_system_restore_extracts_next_to_project(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj = tmp / "proj"
            media = proj / "media"
            (media / "backups" / "system").mkdir(parents=True)
            archive = media / "backups" / "system" / "system_x.zip"
            self._make_zip(archive)

            with override_settings(MEDIA_ROOT=str(media), BASE_DIR=proj, SECURE_BACKUP_ROOT=str(tmp / "secure")):
                target = backup_service.restore_system_from_archive(system_archive_path=str(archive))

            target = Path(target)
            self.assertTrue(target.exists())
            self.assertTrue((target / "manage.py").exists())
            self.assertTrue(str(target).startswith(str(tmp)))
            self.assertNotIn(str(proj), str(target.resolve())[: len(str(target))])

    def test_create_system_backup_zips_codebase_in_process(self):
        # No shell script involved: pure-Python zip works on Windows and Linux.
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj = tmp / "proj"
            (proj / "core_system").mkdir(parents=True)
            (proj / "manage.py").write_text("# fake")
            (proj / "core_system" / "views.py").write_text("# fake")
            (proj / "media" / "backups" / "system").mkdir(parents=True)
            (proj / "media" / "photo.jpg").write_bytes(b"upload")
            (proj / "venv" / "bin").mkdir(parents=True)
            (proj / "venv" / "bin" / "activate").write_text("# fake")
            (proj / "core_system" / "__pycache__").mkdir(parents=True)
            (proj / "core_system" / "__pycache__" / "x.pyc").write_bytes(b"0")
            (proj / "stale.zip").write_bytes(b"0")
            (proj / "debug.log").write_text("x")
            media = proj / "media"

            with override_settings(MEDIA_ROOT=str(media), BASE_DIR=proj, SECURE_BACKUP_ROOT=str(tmp / "secure")):
                job = backup_service.create_system_backup()

            self.assertEqual(job.backup_type, "system")
            self.assertEqual(job.backup_status, "Completed")
            archive = Path(job.system_archive_path)
            self.assertTrue(archive.exists())

            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
            self.assertIn("manage.py", names)
            self.assertIn("core_system/views.py", names)
            for name in names:
                self.assertNotIn("venv", name)
                self.assertNotIn("__pycache__", name)
                self.assertNotIn("media/", name)
                self.assertFalse(name.endswith((".zip", ".log", ".pyc")))
            self.assertEqual(job.metadata_json["file_count"], len(names))

    def test_restore_backup_job_system_type_reports_target(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj = tmp / "proj"
            media = proj / "media"
            (media / "backups" / "system").mkdir(parents=True)
            archive = media / "backups" / "system" / "system_x.zip"
            self._make_zip(archive)

            job = BackupJob.objects.create(
                backup_type="system",
                backup_status="Completed",
                system_archive_path=str(archive),
            )
            with override_settings(MEDIA_ROOT=str(media), BASE_DIR=proj, SECURE_BACKUP_ROOT=str(tmp / "secure")):
                result = backup_service.restore_backup_job(job_id=job.job_id)

            self.assertTrue(result["ok"])
            self.assertTrue(Path(result["restore_target"]).exists())
            job.refresh_from_db()
            self.assertEqual(job.backup_status, "Completed")


class DbBackupRestoreBookkeepingTests(TestCase):
    """The mysql/mysqldump binaries are mocked; file + row logic is real."""

    def _write_dump(self, path: Path):
        with gzip.open(path, "wb") as f:
            f.write(b"-- fake dump")

    def test_create_db_backup_writes_gzip_and_job_row(self):
        with TemporaryDirectory() as tmp:
            media = Path(tmp) / "media"

            def fake_run(cmd, **kwargs):
                if "mysqldump" in cmd:
                    return _FakeProc(stdout=b"-- fake dump")
                return _FakeProc()

            with override_settings(MEDIA_ROOT=str(media), SECURE_BACKUP_ROOT=str(Path(tmp) / "secure")):
                with patch.object(backup_service.subprocess, "run", side_effect=fake_run):
                    job = backup_service.create_db_backup()

            self.assertEqual(job.backup_type, "db")
            self.assertEqual(job.backup_status, "Completed")
            self.assertTrue(Path(job.db_dump_path).exists())

    def test_create_db_backup_writes_encrypted_dump(self):
        # Ciphertext must not contain the plaintext dump marker.
        with TemporaryDirectory() as tmp:
            media = Path(tmp) / "media"

            def fake_run(cmd, **kwargs):
                if "mysqldump" in cmd:
                    return _FakeProc(stdout=b"-- fake dump")
                return _FakeProc()

            with override_settings(MEDIA_ROOT=str(media), SECURE_BACKUP_ROOT=str(Path(tmp) / "secure")):
                with patch.object(backup_service.subprocess, "run", side_effect=fake_run):
                    job = backup_service.create_db_backup()

            raw = Path(job.db_dump_path).read_bytes()
            self.assertTrue(str(job.db_dump_path).endswith(".enc"))
            self.assertNotIn(b"-- fake dump", raw)

    def test_db_restore_registers_safety_snapshot_with_distinct_pk(self):
        with TemporaryDirectory() as tmp:
            media = Path(tmp) / "media"
            db_dir = media / "backups" / "db"
            db_dir.mkdir(parents=True)
            dump = db_dir / "db_test.sql.gz"
            self._write_dump(dump)

            def fake_run(cmd, **kwargs):
                name = cmd[0] if cmd else ""
                if "mysqldump" in name:
                    return _FakeProc(stdout=b"-- fake dump")
                if "mysql" in name:
                    return _FakeProc()
                return _FakeProc()

            job = BackupJob.objects.create(
                backup_type="db",
                backup_status="Completed",
                db_dump_path=str(dump),
            )

            with override_settings(MEDIA_ROOT=str(media), SECURE_BACKUP_ROOT=str(Path(tmp) / "secure")):
                with patch.object(backup_service.subprocess, "run", side_effect=fake_run):
                    result = backup_service.restore_backup_job(job_id=job.job_id)

            self.assertTrue(result["ok"])
            safety_id = result["safety_job_id"]
            self.assertNotEqual(safety_id, job.job_id)

            safety = BackupJob.objects.get(job_id=safety_id)
            self.assertEqual(safety.backup_type, "db")
            self.assertEqual(safety.backup_status, "Completed")
            self.assertIn("Pre-restore safety snapshot", str(safety.metadata_json))

            job.refresh_from_db()
            self.assertEqual(job.backup_status, "Completed")
            self.assertTrue(Path(safety.db_dump_path).exists())

    def test_db_restore_refuses_dump_outside_backups_folder(self):
        with TemporaryDirectory() as tmp:
            outside = Path(tmp) / "stolen.sql.gz"
            self._write_dump(outside)

            job = BackupJob.objects.create(
                backup_type="db",
                backup_status="Completed",
                db_dump_path=str(outside),
            )
            result = backup_service.restore_backup_job(job_id=job.job_id)

            self.assertFalse(result["ok"])
            self.assertIn("outside the backups folder", result["error"])
            job.refresh_from_db()
            self.assertEqual(job.backup_status, "Failed")


class SchedulerRegistrationTests(TestCase):
    def test_db_backup_job_scheduled_at_midnight(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        from core_system.management.commands.run_backup_scheduler import _register_jobs

        scheduler = BackgroundScheduler()
        _register_jobs(
            scheduler,
            db_retention=7,
            media_retention=4,
            config_retention=4,
        )
        try:
            job = scheduler.get_job("backup_db_daily_0000")
            self.assertIsNotNone(job, "midnight DB backup job missing")
            self.assertIsInstance(job.trigger, CronTrigger)
            self.assertIn("hour='0'", str(job.trigger))
            self.assertIn("minute='0'", str(job.trigger))

            self.assertIsNotNone(scheduler.get_job("backup_media_weekly_sun_0015"))
            self.assertIsNotNone(scheduler.get_job("email_queue_every_2min"))
        finally:
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                pass

    def test_start_background_scheduler_is_idempotent(self):
        from core_system.management.commands.run_backup_scheduler import (
            scheduler_state,
            start_background_scheduler,
        )

        first = start_background_scheduler()
        second = start_background_scheduler()
        self.assertIs(first, second)
        self.assertTrue(scheduler_state["running"])
        first.shutdown(wait=False)
        scheduler_state.update(running=False, scheduler=None, started_at=None)


class SuperadminBackupApiTests(TestCase):
    """Superadmin backup page APIs: list, manual (full + db-only), detail.

    Regression: the manual/codebase views used an undefined
    ``_resolve_officer`` helper, so every manual backup died with a
    NameError (HTTP 500) instead of running.
    """

    def _login(self, role="Superadmin", username="sa_backup_admin"):
        from core_system.auth_utils import create_access_session, hash_password
        from core_system.models import OfficerUser

        officer = OfficerUser.objects.create(
            full_name="Backup Admin",
            username=username,
            password_hash=hash_password("Str0ng!Pass"),
            role=role,
            account_status="Active",
            mfa_enabled=False,
            email="sa-backup@isu.edu.ph",
        )
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
        return officer

    def _xhr(self, method, url, data=None):
        do = self.client.post if method == "post" else self.client.get
        return do(
            url, data or {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    def test_list_ok_for_superadmin(self):
        self._login()
        BackupJob.objects.create(backup_type="db", backup_status="Completed")
        resp = self._xhr("get", "/api/president/backups/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(len(resp.json()["jobs"]), 1)

    def test_list_forbidden_for_treasurer(self):
        self._login(role="Treasurer", username="treas_no_backup")
        resp = self._xhr("get", "/api/president/backups/")
        self.assertEqual(resp.status_code, 403)

    def test_manual_full_scope_runs_bundle(self):
        from unittest.mock import patch

        self._login()
        db_job = BackupJob.objects.create(backup_type="db", backup_status="Completed")
        media_job = BackupJob.objects.create(backup_type="media", backup_status="Completed")
        with patch(
            "core_system.president_views.trigger_manual_backup",
            return_value=[db_job, media_job],
        ) as mocked:
            resp = self._xhr("post", "/api/president/backups/manual/")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["scope"], "full")
        mocked.assert_called_once_with()

    def test_manual_db_scope_creates_only_database_job(self):
        from unittest.mock import patch

        self._login()
        made = {}

        def fake_db_backup(**kwargs):
            made["note"] = kwargs.get("note")
            return BackupJob.objects.create(backup_type="db", backup_status="Completed")

        with patch(
            "core_system.services.backup_service.create_db_backup",
            side_effect=fake_db_backup,
        ):
            resp = self._xhr("post", "/api/president/backups/manual/", {"scope": "db"})
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["scope"], "db")
        self.assertEqual([j["backup_type"] for j in body["jobs"]], ["db"])
        self.assertIn("Manual", made.get("note") or "")

    def test_detail_reports_paths_and_disk_state(self):
        self._login()
        with TemporaryDirectory() as tmp:
            dump = Path(tmp) / "db_x.sql.gz"
            dump.write_bytes(b"x" * 2048)
            job = BackupJob.objects.create(
                backup_type="db",
                backup_status="Completed",
                db_dump_path=str(dump),
                metadata_json={"note": "Manual database backup"},
            )
            resp = self._xhr("get", f"/api/president/backups/{job.job_id}/")
        self.assertEqual(resp.status_code, 200)
        detail = resp.json()["job"]
        self.assertEqual(detail["backup_type"], "db")
        self.assertTrue(detail["db_dump"]["exists"])
        self.assertEqual(detail["db_dump"]["size_bytes"], 2048)
        self.assertFalse(detail["media_archive"]["exists"])
        self.assertEqual(detail["metadata"]["note"], "Manual database backup")

    def test_detail_404_for_missing_job(self):
        self._login()
        resp = self._xhr("get", "/api/president/backups/999999/")
        self.assertEqual(resp.status_code, 404)

    def test_superadmin_page_contains_backup_panel(self):
        self._login()
        resp = self.client.get("/superadmin/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('id="backup-panel"', content)
        self.assertIn("Back Up Database Now", content)
        self.assertIn("Back Up System Now", content)
