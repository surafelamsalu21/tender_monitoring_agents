"""
Database backup API routes.

Endpoints (mounted at /api/v1/backup by app/api/main.py):
  GET    /                  - list backups + status
  POST   /run               - trigger a backup right now
  GET    /download/{name}   - download a specific backup file
  DELETE /{name}            - delete a specific backup file
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.db_backup import (
    backup_database,
    delete_backup,
    get_backup_dir,
    get_backup_status,
    list_backups,
    prune_old_backups,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def get_backups():
    """List all backups + summary status (count, total size, retention, latest)."""
    try:
        items = list_backups()
        status = get_backup_status()
        return {
            "success": True,
            "status": status,
            "backups": [b.to_dict() for b in items],
        }
    except Exception as e:
        logger.exception("Failed to list backups")
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {e}")


@router.post("/run")
async def run_backup_now():
    """Run a one-off online SQLite backup and prune old files per retention."""
    try:
        info = await asyncio.to_thread(backup_database)
        await asyncio.to_thread(prune_old_backups)
        return {
            "success": True,
            "message": "Backup created successfully",
            "backup": info.to_dict(),
        }
    except RuntimeError as e:
        # E.g. non-SQLite DB or missing live file.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Manual backup failed")
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")


@router.get("/download/{filename}")
async def download_backup(filename: str):
    """Download a specific backup file."""
    if "/" in filename or "\\" in filename or filename.startswith(".."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    backup_dir: Path = get_backup_dir()
    target = (backup_dir / filename).resolve()
    if backup_dir not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        path=str(target),
        filename=filename,
        media_type="application/octet-stream",
    )


@router.delete("/{filename}")
async def remove_backup(filename: str):
    """Delete a specific backup file by name."""
    if not delete_backup(filename):
        raise HTTPException(
            status_code=404,
            detail=f"Backup not found or could not be deleted: {filename}",
        )
    return {"success": True, "message": f"Deleted {filename}"}
