import base64
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime


from pathlib import Path

from django.conf import settings
from django.utils import timezone

from core_system.constants.policy_constants import POLICY
from core_system.models import BackupJob, SystemSetting


def _backup_root() -> Path:
    """Canonical backup root: OUTSIDE the web-served MEDIA_ROOT.

    Legacy archives still live under MEDIA_ROOT/backups/ and remain
    restorable (see _ensure_inside_backups), but every NEW backup is written
    here so dumps are never URL-addressable, regardless of .htaccess/nginx.
    """
    root = getattr(settings, "SECURE_BACKUP_ROOT", "") or (Path(settings.BASE_DIR) / "CAUFA-backups")
    return Path(root)


def _legacy_backup_root() -> Path:
    return Path(settings.MEDIA_ROOT) / "backups"


def _allowed_backup_roots() -> list[Path]:
    return [_backup_root(), _legacy_backup_root()]


def _get_backup_fernet():
    """Fernet for dump/config encryption. Dedicated BACKUP_ENCRYPTION_KEY when
    set; otherwise derived from SECRET_KEY (documented fallback)."""
    from cryptography.fernet import Fernet

    raw = (getattr(settings, "BACKUP_ENCRYPTION_KEY", "") or "").strip()
    if raw:
        return Fernet(raw.encode())
    digest = hashlib.sha256(f"backup-envelope-v1:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_bytes(data: bytes) -> bytes:
    return _get_backup_fernet().encrypt(data)


def _decrypt_bytes(token: bytes) -> bytes:
    """Decrypt; pass through legacy PLAINTEXT bytes (InvalidToken) so archives
    written before encryption shipped still restore."""
    from cryptography.fernet import InvalidToken

    try:
        return _get_backup_fernet().decrypt(token)
    except InvalidToken:
        return token


@dataclass
class BackupPaths:
    base_dir: Path
    db_dir: Path
    media_dir: Path
    config_dir: Path
    system_dir: Path


def get_backup_paths() -> BackupPaths:
    # SECURE_BACKUP_ROOT (outside MEDIA_ROOT) — never URL-addressable.
    # See _ensure_inside_backups for legacy MEDIA_ROOT/backups read support.
    base_dir = _backup_root()
    db_dir = base_dir / "db"
    media_dir = base_dir / "files"
    config_dir = base_dir / "config"
    system_dir = base_dir / "system"

    for d in (db_dir, media_dir, config_dir, system_dir):
        d.mkdir(parents=True, exist_ok=True)

    return BackupPaths(
        base_dir=base_dir,
        db_dir=db_dir,
        media_dir=media_dir,
        config_dir=config_dir,
        system_dir=system_dir,
    )


def _now_stamp() -> str:
    return timezone.now().strftime("%Y%m%d_%H%M%S")


def _get_db_connection_env() -> dict:
    # Build best-effort parameters from Django settings. Empty password
    # fallback (never a committed literal) — dev reads it from .env.
    db = settings.DATABASES["default"]
    user = db.get("USER") or "root"
    password = db.get("PASSWORD") or ""
    host = db.get("HOST") or "127.0.0.1"
    port = str(db.get("PORT") or "3306")
    name = db.get("NAME") or ""
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "name": name,
    }


def _run_cmd(cmd: list[str], cwd: str | None = None) -> None:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")


def _dump_database_to(dump_path: Path, *, note: str | None = None) -> None:
    """Run mysqldump into dump_path (gzipped + Fernet-encrypted).

    Shared by backup and pre-restore safety snapshot. The file at dump_path
    is always ciphertext; restore decrypts (with plaintext fallback for
    legacy archives — see _decrypt_bytes).
    """
    dbc = _get_db_connection_env()

    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp_sql:
        tmp_path = tmp_sql.name

    try:
        env = os.environ.copy()
        env["MYSQL_PWD"] = dbc["password"]

        cmd_dump = [
            "mysqldump",
            "--single-transaction",
            "--default-character-set=utf8mb4",
            "--routines",
            "-h",
            dbc["host"],
            "-P",
            dbc["port"],
            "-u",
            dbc["user"],
            dbc["name"],
        ]
        proc = subprocess.run(cmd_dump, capture_output=True, text=False, env=env)
        if proc.returncode != 0:
            raise RuntimeError(
                f"mysqldump failed ({proc.returncode}): {proc.stderr.decode(errors='replace')}"
            )

        with open(tmp_path, "wb") as f:
            f.write(proc.stdout)

        import gzip
        with open(tmp_path, "rb") as f_in:
            gzipped = gzip.compress(f_in.read())
        dump_path.write_bytes(_encrypt_bytes(gzipped))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _prune_retired_jobs(retired_ids: list, path_attr: str) -> None:
    """Delete retired rows AND their files (retention previously orphaned
    ciphertext on disk — the dump's PII survived its own retention)."""
    if not retired_ids:
        return
    for path in BackupJob.objects.filter(job_id__in=retired_ids).values_list(path_attr, flat=True):
        if not path:
            continue
        # config path lives inside metadata_json, not a column.
        candidate = path if isinstance(path, str) else None
        if candidate:
            try:
                p = Path(candidate)
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
    BackupJob.objects.filter(job_id__in=retired_ids).delete()


def create_db_backup(*, retention_count: int = 7, note: str | None = None) -> BackupJob:
    paths = get_backup_paths()
    stamp = _now_stamp()
    dump_path = paths.db_dir / f"db_{stamp}.sql.gz.enc"

    dbc = _get_db_connection_env()
    _dump_database_to(dump_path)

    # retention (keep last N; delete retired rows AND their ciphertext files)
    db_jobs = BackupJob.objects.filter(backup_type="db").order_by("-created_at")
    ids = list(db_jobs.values_list("job_id", flat=True))
    if len(ids) >= retention_count:
        # >= because the new row is not yet created; keep total at retention_count.
        extra = ids[retention_count - 1:]
        _prune_retired_jobs(extra, "db_dump_path")

    job = BackupJob.objects.create(
        backup_type="db",
        backup_status="Completed",
        db_dump_path=str(dump_path),
        created_at=timezone.now(),
        metadata_json={"host": dbc["host"], "db": dbc["name"], **({"note": note} if note else {})},
    )
    return job


def create_media_backup(*, retention_count: int = 4) -> BackupJob:
    paths = get_backup_paths()
    stamp = _now_stamp()
    archive_path = paths.media_dir / f"media_{stamp}.tar.gz"

    media_root = Path(settings.MEDIA_ROOT)

    def _is_backup(p: Path) -> bool:
        try:
            return str(p).lower().startswith(str(media_root / "backups").lower())
        except Exception:
            return False

    with tarfile.open(archive_path, "w:gz") as tar:
        for root, dirs, files in os.walk(media_root):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if not _is_backup(root_path / d)]
            for fn in files:
                fp = root_path / fn
                if _is_backup(fp):
                    continue
                arcname = str(fp.relative_to(media_root))
                tar.add(fp, arcname=arcname)

    # retention (keep last N media backups; remove retired archives too)
    jobs = BackupJob.objects.filter(backup_type="media").order_by("-created_at")
    ids = list(jobs.values_list("job_id", flat=True))
    if len(ids) >= retention_count:
        extra = ids[retention_count - 1:]
        _prune_retired_jobs(extra, "media_archive_path")

    job = BackupJob.objects.create(
        backup_type="media",
        backup_status="Completed",
        media_archive_path=str(archive_path),
        created_at=timezone.now(),
        metadata_json={"media_root": str(media_root)},
    )
    return job


def create_config_backup(*, retention_count: int = 4) -> BackupJob:
    paths = get_backup_paths()
    stamp = _now_stamp()
    config_path = paths.config_dir / f"config_{stamp}.json.enc"

    settings_qs = SystemSetting.objects.all().values("setting_key", "setting_value")
    payload = {
        "system_settings": list(settings_qs),
        "policy_constants": {k: getattr(POLICY, k) for k in dir(POLICY) if not k.startswith("_")},
        "generated_at": timezone.now().isoformat(),
    }

    config_path.write_bytes(_encrypt_bytes(json.dumps(payload, indent=2).encode("utf-8")))

    # retention (keep last N; config path lives in metadata_json)
    jobs = BackupJob.objects.filter(backup_type="config").order_by("-created_at")
    ids = list(jobs.values_list("job_id", flat=True))
    if len(ids) >= retention_count:
        extra = ids[retention_count - 1:]
        for meta in BackupJob.objects.filter(job_id__in=extra).values_list("metadata_json", flat=True):
            try:
                cfg = (meta or {}).get("config_path") if isinstance(meta, dict) else None
            except Exception:
                cfg = None
            if cfg:
                try:
                    p = Path(cfg)
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass
        BackupJob.objects.filter(job_id__in=extra).delete()

    job = BackupJob.objects.create(
        backup_type="config",
        backup_status="Completed",
        metadata_json={"config_path": str(config_path)},
        created_at=timezone.now(),
    )
    return job


# Directory names (any depth) never packed into a codebase archive.
_SYSTEM_EXCLUDE_DIRS = frozenset({
    "venv", ".venv", ".git", "node_modules", "staticfiles", "media",
    "__pycache__",
})
# File patterns never packed into a codebase archive.
_SYSTEM_EXCLUDE_SUFFIXES = (".zip", ".log", ".pyc")


def _system_backup_should_include(rel: Path) -> bool:
    for part in rel.parts:
        if part in _SYSTEM_EXCLUDE_DIRS:
            return False
    if rel.name.lower().endswith(_SYSTEM_EXCLUDE_SUFFIXES):
        return False
    return True


def create_system_backup(*, retention_count: int = 4) -> BackupJob:
    """Zip the project codebase with pure Python (no shell script needed).

    Same exclusion rules as scripts/backup_system.bat (kept for operators
    who prefer the console): no virtualenvs, VCS metadata, caches, media
    uploads (they have their own dedicated backup job), old zips or logs —
    so the archive stays small and can never recurse into itself. Running
    in-process works on Windows AND Linux, unlike the .bat which Windows
    cannot even launch headless (``'scripts' is not recognized…``, exit 1).
    """
    paths = get_backup_paths()
    stamp = _now_stamp()
    archive_path = paths.system_dir / f"system_{stamp}.zip"

    base_dir = Path(settings.BASE_DIR)
    file_count = 0
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(base_dir):
            root_path = Path(root)
            # Prune excluded directories so we never descend into them.
            dirs[:] = sorted(d for d in dirs if d not in _SYSTEM_EXCLUDE_DIRS)
            for fn in sorted(files):
                rel = (root_path / fn).relative_to(base_dir)
                if not _system_backup_should_include(rel):
                    continue
                zf.write(root_path / fn, arcname=rel.as_posix())
                file_count += 1

    if not archive_path.exists() or archive_path.stat().st_size == 0:
        raise RuntimeError("System backup produced an empty archive.")

    job = BackupJob.objects.create(
        backup_type="system",
        backup_status="Completed",
        system_archive_path=str(archive_path),
        created_at=timezone.now(),
        metadata_json={
            "size_bytes": archive_path.stat().st_size,
            "file_count": file_count,
            "source": str(base_dir),
            "method": "python-zipfile",
        },
    )

    # retention (keep last N system backups; remove retired archives too)
    jobs = BackupJob.objects.filter(backup_type="system").order_by("-created_at")
    ids = list(jobs.values_list("job_id", flat=True))
    if len(ids) >= retention_count:
        extra = ids[retention_count - 1:]
        _prune_retired_jobs(extra, "system_archive_path")

    return job


def _ensure_inside_backups(path: Path) -> None:
    """Refuse to restore from files outside the backup roots (tamper guard).

    Accepts the canonical SECURE_BACKUP_ROOT and the legacy
    MEDIA_ROOT/backups tree so archives written before the move still
    restore during transition.
    """
    try:
        resolved = path.resolve()
    except Exception:
        raise ValueError(f"Refusing to restore from outside the backups folder: {path}")
    for root in _allowed_backup_roots():
        try:
            resolved.relative_to(root.resolve())
            return
        except ValueError:
            continue
    raise ValueError(f"Refusing to restore from outside the backups folder: {path}")


def list_backup_jobs(*, limit: int = 50) -> list[BackupJob]:
    limit = max(1, min(int(limit), 200))
    return list(BackupJob.objects.order_by("-created_at")[:limit])


def create_backup_bundle(*, include_config: bool = True) -> list[BackupJob]:
    """
    Create a manual “bundle” backup set:
      - db dump backup
      - media archive backup
      - config snapshot backup (optional)

    Returns the created BackupJob rows in [db, media, (config?)] order.
    """
    jobs: list[BackupJob] = []
    jobs.append(create_db_backup())
    jobs.append(create_media_backup())
    if include_config:
        jobs.append(create_config_backup())
    return jobs


def trigger_manual_backup(*, include_config: bool = True) -> list[BackupJob]:
    # Manual backup is a “bundle”: db + media + (optionally) config
    return create_backup_bundle(include_config=include_config)


def restore_db_from_dump(*, db_dump_path: str) -> Path:
    """Import a saved dump back into the database.

    Before touching a single row, the CURRENT database (corrupted or not) is
    dumped to a safety snapshot ON DISK, so a restore that goes wrong is
    itself reversible. Returns the safety dump path. No DB rows are written
    here: the import below replaces the whole backup_job table, so any
    bookkeeping rows must be created by the caller AFTER the import.
    """
    dbc = _get_db_connection_env()

    dump_file = Path(db_dump_path)
    if not dump_file.exists():
        raise FileNotFoundError(f"DB dump not found: {db_dump_path}")
    _ensure_inside_backups(dump_file)

    paths = get_backup_paths()
    safety_path = paths.db_dir / f"db_prerestore_{_now_stamp()}.sql.gz.enc"
    _dump_database_to(safety_path)

    # mysql command needs uncompressed SQL: decrypt (legacy plaintext passes
    # through) then gunzip.
    import gzip
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp_sql:
        tmp_sql_path = tmp_sql.name

    try:
        raw = dump_file.read_bytes()
        gzipped = _decrypt_bytes(raw)
        with open(tmp_sql_path, "wb") as f_out:
            f_out.write(gzip.decompress(gzipped))

        env = os.environ.copy()
        env["MYSQL_PWD"] = dbc["password"]

        cmd_mysql = [
            "mysql",
            "--default-character-set=utf8mb4",
            "-h",
            dbc["host"],
            "-P",
            dbc["port"],
            "-u",
            dbc["user"],
            dbc["name"],
        ]
        # Stream the file through stdin instead of reading it all into memory.
        with open(tmp_sql_path, "rb") as f:
            proc = subprocess.run(cmd_mysql, stdin=f, capture_output=True, env=env)
        if proc.returncode != 0:
            raise RuntimeError(
                f"mysql restore failed ({proc.returncode}): {proc.stderr.decode(errors='replace')}"
            )
    finally:
        try:
            if os.path.exists(tmp_sql_path):
                os.remove(tmp_sql_path)
        except Exception:
            pass

    return safety_path


def restore_media_from_archive(*, media_archive_path: str) -> None:
    archive = Path(media_archive_path)
    if not archive.exists():
        raise FileNotFoundError(f"Media archive not found: {media_archive_path}")
    _ensure_inside_backups(archive)

    media_root = Path(settings.MEDIA_ROOT)
    backups_root = media_root / "backups"

    # Remove everything in media_root except backups directory
    for entry in media_root.iterdir():
        if entry.name == "backups":
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            try:
                entry.unlink()
            except Exception:
                pass

    with tarfile.open(archive, "r:gz") as tar:
        try:
            tar.extractall(path=media_root, filter="data")
        except TypeError:
            # Python < 3.12 has no extraction filter; extract unfiltered.
            tar.extractall(path=media_root)


def restore_system_from_archive(*, system_archive_path: str) -> str:
    """Extract a codebase zip NEXT TO the live project, never over it.

    Restoring code on top of a running server would break the running
    process, so the archive is unpacked into a sibling folder the operator
    can review first. Returns that folder path. Entry paths are validated
    against zip-slip before extraction.
    """
    archive = Path(system_archive_path)
    if not archive.exists():
        raise FileNotFoundError(f"System archive not found: {system_archive_path}")
    _ensure_inside_backups(archive)

    target = Path(settings.BASE_DIR).parent / f"caufasystem_restore_{_now_stamp()}"
    target.mkdir(parents=True, exist_ok=True)
    target_resolved = target.resolve()

    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            try:
                (target / member.filename).resolve().relative_to(target_resolved)
            except ValueError:
                raise ValueError(f"Unsafe path in archive: {member.filename}")
        zf.extractall(target)

    return str(target)


def restore_config_from_snapshot(*, payload: dict) -> None:
    system_settings = payload.get("system_settings") or []

    # Replace all SystemSetting rows in snapshot for deterministic restore.
    # Keep unrelated keys? Here we restore exactly what exists in snapshot.
    keys = {row.get("setting_key") for row in system_settings if row.get("setting_key")}
    keys = {k for k in keys if isinstance(k, str) and k.strip()}

    if keys:
        SystemSetting.objects.exclude(setting_key__in=list(keys)).delete()

    for row in system_settings:
        k = row.get("setting_key")
        v = row.get("setting_value")
        if not k:
            continue
        SystemSetting.objects.update_or_create(
            setting_key=k,
            defaults={"setting_value": str(v)},
        )


def _upsert_restored_job(job: BackupJob) -> None:
    """Save a job row whose table may have been replaced by a DB restore."""
    if not BackupJob.objects.filter(job_id=job.job_id).exists():
        job._state.adding = True
        job.save()
    else:
        job.save(update_fields=["backup_status"])


def restore_backup_job(*, job_id: int, actor_officer=None, ip: str | None = None) -> dict:
    job = BackupJob.objects.filter(job_id=job_id).first()
    if not job:
        return {"ok": False, "error": "Backup job not found."}

    # Update status
    job.backup_status = "Pending"
    job.save(update_fields=["backup_status"])

    extras: dict = {}
    try:
        if job.backup_type == "db":
            if not job.db_dump_path:
                raise ValueError("Missing db_dump_path")
            safety_path = restore_db_from_dump(db_dump_path=job.db_dump_path)
            # The import replaced the whole DB, including backup_job rows
            # created after the dump was taken. Re-insert this job's row
            # FIRST (its PK postdates the dump, so no collision), then
            # register the safety snapshot — both must happen after the
            # import to survive it, and in that order so the two rows get
            # distinct PKs.
            if not BackupJob.objects.filter(job_id=job.job_id).exists():
                job._state.adding = True
                job.save()
            safety_job = BackupJob.objects.create(
                backup_type="db",
                backup_status="Completed",
                db_dump_path=str(safety_path),
                created_at=timezone.now(),
                metadata_json={
                    "note": "Pre-restore safety snapshot (undo point for restore of job "
                            f"#{job.job_id})",
                },
            )
            extras["safety_job_id"] = safety_job.job_id
        elif job.backup_type == "media":
            if not job.media_archive_path:
                raise ValueError("Missing media_archive_path")
            restore_media_from_archive(media_archive_path=job.media_archive_path)
        elif job.backup_type == "config":
            meta = job.metadata_json
            if isinstance(meta, str):
                meta = json.loads(meta)
            config_path = (meta or {}).get("config_path")
            if not config_path:
                raise ValueError("Missing config_path in metadata_json")
            cfg_file = Path(config_path)
            if not cfg_file.exists():
                raise FileNotFoundError(f"Config snapshot not found: {config_path}")
            payload = json.loads(_decrypt_bytes(cfg_file.read_bytes()).decode("utf-8"))
            restore_config_from_snapshot(payload=payload)
        elif job.backup_type == "system":
            if not job.system_archive_path:
                raise ValueError("Missing system_archive_path")
            extras["restore_target"] = restore_system_from_archive(
                system_archive_path=job.system_archive_path
            )
        else:
            raise ValueError(f"Unknown backup_type: {job.backup_type}")

        job.backup_status = "Completed"
        _upsert_restored_job(job)
        return {
            "ok": True,
            "job": {"job_id": job.job_id, "backup_type": job.backup_type, "backup_status": job.backup_status},
            **extras,
        }
    except Exception as e:
        job.backup_status = "Failed"
        try:
            _upsert_restored_job(job)
        except Exception:
            pass
        return {"ok": False, "error": str(e), "job": {"job_id": job.job_id, "backup_type": job.backup_type, "backup_status": job.backup_status}}

