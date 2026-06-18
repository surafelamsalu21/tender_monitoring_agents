"""
SQLite database backup service.

Uses the SQLite Online Backup API (sqlite3.Connection.backup) which is the
ONLY safe way to copy a SQLite database while the application is running.
A naive file copy of the .db plus -wal/-shm would risk a corrupt snapshot.

Backups are written to ``settings.BACKUP_DIR`` (default: ``./backups``) as
timestamped self-contained .db files (no -wal/-shm companions needed).
"""
from __future__ import annotations

import logging
import sqlite3
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy.engine.url import make_url

from app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class BackupFile:
    filename: str
    size_bytes: int
    created_at: str  # ISO-8601 UTC
    path: str        # absolute path

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "size_human": _human_size(self.size_bytes),
            "created_at": self.created_at,
        }


def _human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{num} {unit}"
        num /= 1024  # type: ignore[assignment]
    return f"{num:.1f} GB"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_backup_dir() -> Path:
    """Resolve the backup directory and ensure it exists."""
    raw = (getattr(settings, "BACKUP_DIR", None) or "backups").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = (_project_root() / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_secondary_backup_dir() -> Path:
    """Resolve the secondary backup directory and ensure it exists."""
    raw = (getattr(settings, "BACKUP_DIR_SECONDARY", None) or "backups_secondary").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = (_project_root() / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_live_sqlite_path() -> Optional[Path]:
    """Public helper for the live SQLite path; None for non-SQLite URLs."""
    return _live_sqlite_path()


def _live_sqlite_path() -> Optional[Path]:
    """Resolve the live SQLite database file path. Returns None for non-SQLite."""
    url = settings.DATABASE_URL or ""
    if not url.startswith("sqlite"):
        return None
    try:
        parsed = make_url(url)
    except Exception:
        return None
    db = parsed.database or ""
    if not db or db == ":memory:":
        return None
    p = Path(db)
    if not p.is_absolute():
        p = (_project_root() / p).resolve()
    return p


def _safe_filename(prefix: str = "tender_monitoring") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{prefix}_{ts}.db"


def _sqlite_has_application_tables(path: Path) -> bool:
    """Return True when a SQLite file is readable and contains app tables."""
    if not path.exists() or path.stat().st_size <= 0:
        return False
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(str(path), timeout=10)
        cur = conn.cursor()
        row = cur.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        return bool(row and int(row[0]) > 0)
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _latest_backup_across_dirs() -> Optional[BackupFile]:
    """Pick newest backup from primary and secondary directories."""
    candidates: List[BackupFile] = []
    for backup_dir in (get_backup_dir(), get_secondary_backup_dir()):
        for p in backup_dir.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
                continue
            if p.name.endswith(".tmp"):
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            candidates.append(
                BackupFile(
                    filename=p.name,
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat().replace("+00:00", "Z"),
                    path=str(p.resolve()),
                )
            )
    if not candidates:
        return None
    candidates.sort(key=lambda b: b.created_at, reverse=True)
    return candidates[0]


def auto_restore_live_db_from_latest_backup_if_needed() -> dict:
    """
    Startup safety: when live SQLite DB is missing/empty/invalid, restore newest backup.
    Returns a status dict for logs/diagnostics.
    """
    if not bool(getattr(settings, "BACKUP_AUTO_RESTORE_ON_STARTUP", True)):
        return {"checked": False, "restored": False, "reason": "disabled"}

    live = _live_sqlite_path()
    if live is None:
        return {"checked": False, "restored": False, "reason": "non_sqlite"}

    # Healthy DB already present -> keep it untouched.
    if _sqlite_has_application_tables(live):
        return {"checked": True, "restored": False, "reason": "live_db_ok", "live_path": str(live)}

    latest = _latest_backup_across_dirs()
    if latest is None:
        return {
            "checked": True,
            "restored": False,
            "reason": "no_backups_found",
            "live_path": str(live),
        }

    src = Path(latest.path)
    live.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale WAL/SHM if they exist near target.
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(live) + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass

    # Use SQLite backup API for restore as well (avoids bind-mount replace/busy issues).
    src_conn: Optional[sqlite3.Connection] = None
    dst_conn: Optional[sqlite3.Connection] = None
    try:
        src_conn = sqlite3.connect(str(src), timeout=30)
        dst_conn = sqlite3.connect(str(live), timeout=30)
        with dst_conn:
            src_conn.backup(dst_conn, pages=-1, progress=None)
    finally:
        if dst_conn is not None:
            try:
                dst_conn.close()
            except Exception:
                pass
        if src_conn is not None:
            try:
                src_conn.close()
            except Exception:
                pass

    if not _sqlite_has_application_tables(live):
        raise RuntimeError(
            f"Auto-restore copied {src} but restored DB still looks invalid: {live}"
        )

    logger.warning(
        "Live DB auto-restored from latest backup: %s -> %s",
        src,
        live,
    )
    return {
        "checked": True,
        "restored": True,
        "reason": "restored_from_backup",
        "from_backup": str(src),
        "live_path": str(live),
    }


def backup_database(target_path: Optional[Path] = None) -> BackupFile:
    """Write a consistent online backup of the live SQLite database.

    Raises RuntimeError when the live database is not SQLite or its file is missing.
    """
    live = _live_sqlite_path()
    if live is None:
        raise RuntimeError(
            "Backups are only implemented for SQLite databases. "
            "DATABASE_URL is not a sqlite:// URL."
        )
    if not live.exists():
        raise RuntimeError(f"Live SQLite database not found: {live}")

    backup_dir = get_backup_dir()
    if target_path is None:
        target_path = backup_dir / _safe_filename()
    target_path = Path(target_path)
    if not target_path.is_absolute():
        target_path = (backup_dir / target_path).resolve()

    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    src: Optional[sqlite3.Connection] = None
    dst: Optional[sqlite3.Connection] = None
    try:
        src = sqlite3.connect(str(live), timeout=30)
        dst = sqlite3.connect(str(tmp_path))
        # pages=-1 copies everything in a single batch under one read txn,
        # safe even while writers are active (online backup API).
        with dst:
            src.backup(dst, pages=-1, progress=None)
    finally:
        if dst is not None:
            try:
                dst.close()
            except Exception:
                pass
        if src is not None:
            try:
                src.close()
            except Exception:
                pass

    # Atomic-ish rename so partial files are never observed by callers.
    tmp_path.replace(target_path)

    size = target_path.stat().st_size
    info = BackupFile(
        filename=target_path.name,
        size_bytes=size,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        path=str(target_path),
    )
    logger.info(
        "DB backup written: %s (%s) from %s",
        info.filename, _human_size(size), live,
    )

    # Always mirror the backup to a second folder so two copies are kept.
    secondary_dir = get_secondary_backup_dir()
    secondary_target = (secondary_dir / target_path.name).resolve()
    shutil.copy2(target_path, secondary_target)
    logger.info("DB backup mirrored to secondary folder: %s", secondary_target)

    return info


def list_backups() -> List[BackupFile]:
    """List existing backups in the configured directory, newest first."""
    backup_dir = get_backup_dir()
    items: List[BackupFile] = []
    for p in backup_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
            continue
        if p.name.endswith(".tmp"):
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        items.append(
            BackupFile(
                filename=p.name,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat().replace("+00:00", "Z"),
                path=str(p.resolve()),
            )
        )
    items.sort(key=lambda b: b.created_at, reverse=True)
    return items


def prune_old_backups(retention: Optional[int] = None) -> int:
    """Delete oldest backups beyond ``retention`` count. Returns deleted count."""
    keep = retention if retention is not None else int(
        getattr(settings, "BACKUP_RETENTION", 30) or 30
    )
    keep = max(1, keep)

    deleted = 0

    # Apply retention independently to both backup folders.
    for backup_dir in (get_backup_dir(), get_secondary_backup_dir()):
        items: List[BackupFile] = []
        for p in backup_dir.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
                continue
            if p.name.endswith(".tmp"):
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            items.append(
                BackupFile(
                    filename=p.name,
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat().replace("+00:00", "Z"),
                    path=str(p.resolve()),
                )
            )
        items.sort(key=lambda b: b.created_at, reverse=True)

        if len(items) <= keep:
            continue

        for item in items[keep:]:
            try:
                Path(item.path).unlink()
                deleted += 1
                logger.info("Pruned old backup (%s): %s", backup_dir.name, item.filename)
            except OSError as e:
                logger.warning("Failed to prune %s from %s: %s", item.filename, backup_dir, e)
    return deleted


def delete_backup(filename: str) -> bool:
    """Delete a single backup file by filename. Returns True on success."""
    if "/" in filename or "\\" in filename or filename.startswith(".."):
        # Defense against path traversal.
        logger.warning("Refused suspicious backup filename: %s", filename)
        return False
    backup_dir = get_backup_dir()
    target = (backup_dir / filename).resolve()
    if backup_dir not in target.parents:
        logger.warning("Refused backup path outside backup_dir: %s", target)
        return False
    if not target.exists() or not target.is_file():
        return False
    try:
        target.unlink()
        logger.info("Deleted backup: %s", filename)
        return True
    except OSError as e:
        logger.warning("Failed to delete %s: %s", filename, e)
        return False


def run_scheduled_backup() -> Optional[BackupFile]:
    """Run a backup + prune. Returns the new backup info or None if disabled."""
    if not bool(getattr(settings, "BACKUP_ENABLED", True)):
        logger.info("DB backup skipped: BACKUP_ENABLED is False")
        return None
    info = backup_database()
    prune_old_backups()
    return info


def get_backup_status() -> dict:
    """Return summary stats for the backup UI."""
    items = list_backups()
    latest = items[0] if items else None
    backup_dir = get_backup_dir()
    secondary_backup_dir = get_secondary_backup_dir()

    secondary_items: List[BackupFile] = []
    for p in secondary_backup_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
            continue
        if p.name.endswith(".tmp"):
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        secondary_items.append(
            BackupFile(
                filename=p.name,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat().replace("+00:00", "Z"),
                path=str(p.resolve()),
            )
        )
    secondary_items.sort(key=lambda b: b.created_at, reverse=True)
    secondary_latest = secondary_items[0] if secondary_items else None

    return {
        "enabled": bool(getattr(settings, "BACKUP_ENABLED", True)),
        # Kept for backward compatibility with existing frontend typings.
        "interval_hours": 0,
        "trigger": "post_extraction_weekdays",
        "post_extraction_enabled": bool(
            getattr(settings, "BACKUP_AFTER_EXTRACTION_ENABLED", True)
        ),
        "schedule_weekdays": str(
            getattr(settings, "BACKUP_AFTER_EXTRACTION_WEEKDAYS", "monday,thursday")
        ),
        "retention": int(getattr(settings, "BACKUP_RETENTION", 30) or 30),
        "directory": str(backup_dir),
        "count": len(items),
        "total_bytes": sum(i.size_bytes for i in items),
        "latest": latest.to_dict() if latest else None,
        "secondary_directory": str(secondary_backup_dir),
        "secondary_count": len(secondary_items),
        "secondary_total_bytes": sum(i.size_bytes for i in secondary_items),
        "secondary_latest": secondary_latest.to_dict() if secondary_latest else None,
    }
