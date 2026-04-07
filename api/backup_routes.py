"""Database backup and restore endpoints.

Critical for kirana stores where data loss = business loss.
Supports SQLite file backup and JSON data export/import.
"""

import json
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from auth.dependencies import require_role
from db.models import User
from db.session import engine

router = APIRouter(prefix="/api/backup", tags=["backup"])

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BACKUP_DIR = DATA_DIR / "backups"


def _ensure_backup_dir():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/create")
async def create_backup(
    user: User = Depends(require_role("owner")),
):
    """Create a full database backup.

    For SQLite: copies the DB file.
    Returns the backup filename for later download/restore.
    """
    _ensure_backup_dir()

    db_url = str(engine.url)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    if "sqlite" in db_url:
        # Extract the SQLite file path
        db_path = db_url.split("///")[-1]
        if not Path(db_path).exists():
            raise HTTPException(status_code=404, detail="Database file not found")

        backup_name = f"retailos_backup_{timestamp}.db"
        backup_path = BACKUP_DIR / backup_name
        shutil.copy2(db_path, backup_path)

        size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)
        return {
            "status": "created",
            "filename": backup_name,
            "size_mb": size_mb,
            "timestamp": timestamp,
            "type": "sqlite",
        }
    else:
        # For PostgreSQL, export as JSON
        backup_name = f"retailos_backup_{timestamp}.json"
        backup_path = BACKUP_DIR / backup_name
        data = await _export_all_tables()
        with open(backup_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)
        return {
            "status": "created",
            "filename": backup_name,
            "size_mb": size_mb,
            "timestamp": timestamp,
            "type": "json",
        }


@router.get("/list")
async def list_backups(
    user: User = Depends(require_role("owner")),
):
    """List all available backups."""
    _ensure_backup_dir()
    backups = []
    for f in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if f.name.startswith("retailos_backup_"):
            backups.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created_at": f.stat().st_mtime,
            })
    return {"backups": backups, "count": len(backups)}


@router.get("/download/{filename}")
async def download_backup(
    filename: str,
    user: User = Depends(require_role("owner")),
):
    """Download a backup file."""
    # Prevent path traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    backup_path = BACKUP_DIR / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        path=str(backup_path),
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post("/restore/{filename}")
async def restore_backup(
    filename: str,
    user: User = Depends(require_role("owner")),
):
    """Restore from a backup file.

    WARNING: This replaces the current database. A pre-restore backup is
    automatically created first.
    """
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    backup_path = BACKUP_DIR / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    db_url = str(engine.url)

    if "sqlite" in db_url and filename.endswith(".db"):
        db_path = db_url.split("///")[-1]

        # Create pre-restore backup
        pre_restore = BACKUP_DIR / f"pre_restore_{time.strftime('%Y%m%d_%H%M%S')}.db"
        if Path(db_path).exists():
            shutil.copy2(db_path, pre_restore)

        # Dispose connections before replacing
        await engine.dispose()

        # Replace the database
        shutil.copy2(backup_path, db_path)

        return {
            "status": "restored",
            "from": filename,
            "pre_restore_backup": pre_restore.name,
            "note": "Restart the server to apply the restored database",
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Restore format mismatch. SQLite backups must be .db files.",
        )


@router.delete("/{filename}")
async def delete_backup(
    filename: str,
    user: User = Depends(require_role("owner")),
):
    """Delete a backup file."""
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    backup_path = BACKUP_DIR / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    backup_path.unlink()
    return {"status": "deleted", "filename": filename}


@router.post("/export-json")
async def export_json(
    user: User = Depends(require_role("owner")),
):
    """Export all data as JSON (portable format, works across DB engines)."""
    _ensure_backup_dir()
    data = await _export_all_tables()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"retailos_export_{timestamp}.json"
    filepath = BACKUP_DIR / filename

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/json",
    )


async def _export_all_tables() -> dict:
    """Export all table data as a dict of lists."""
    from sqlalchemy import text, inspect
    from db.session import async_session_factory

    async with async_session_factory() as session:
        # Get table names via sync inspection
        def get_tables(conn):
            inspector = inspect(conn)
            return inspector.get_table_names()

        async with engine.connect() as conn:
            tables = await conn.run_sync(get_tables)

        data = {}
        for table in tables:
            if table.startswith("alembic_"):
                continue
            result = await session.execute(text(f"SELECT * FROM {table}"))
            rows = result.fetchall()
            columns = result.keys()
            data[table] = [dict(zip(columns, row)) for row in rows]

        return data
