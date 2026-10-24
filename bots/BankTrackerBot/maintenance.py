"""Safe maintenance tasks for BankTrackerBot.

Only generated/cache files are cleaned. Receipt images and database records are never
removed by this module.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config import BACKUPS_DIR, DATA_DIR, DATABASE_PATH, EXPORTS_DIR, INCOMING_RESTORE_DIR, TIMEZONE

TZ = ZoneInfo(TIMEZONE)
LOGS_DIR = DATA_DIR / "logs"
TEMP_DIRS = (INCOMING_RESTORE_DIR, DATA_DIR / "tmp", DATA_DIR / "temp")
BACKUP_RETENTION = max(1, int(os.getenv("BACKUP_RETENTION", "7") or 7))
LOG_RETENTION_DAYS = max(1, int(os.getenv("LOG_RETENTION_DAYS", "30") or 30))
TEMP_RETENTION_HOURS = max(1, int(os.getenv("TEMP_RETENTION_HOURS", "24") or 24))
EXPORT_RETENTION_DAYS = max(0, int(os.getenv("EXPORT_RETENTION_DAYS", "0") or 0))


@dataclass
class TaskResult:
    name: str
    ok: bool
    detail: str


def _format_bytes(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _delete_old_files(folder: Path, older_than_seconds: int, patterns: tuple[str, ...] = ("*",)) -> tuple[int, int]:
    if not folder.exists():
        return 0, 0
    cutoff = time.time() - older_than_seconds
    files: set[Path] = set()
    for pattern in patterns:
        files.update(path for path in folder.rglob(pattern) if path.is_file())
    deleted = 0
    reclaimed = 0
    for path in files:
        try:
            stat = path.stat()
            if stat.st_mtime >= cutoff:
                continue
            size = stat.st_size
            path.unlink(missing_ok=True)
            deleted += 1
            reclaimed += size
        except OSError:
            continue
    # Remove empty directories only, never non-empty folders.
    for path in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    return deleted, reclaimed


def _database_maintenance() -> tuple[TaskResult, dict[str, Any]]:
    before = DATABASE_PATH.stat().st_size if DATABASE_PATH.is_file() else 0
    details: dict[str, Any] = {"before": before, "after": before, "integrity": "missing"}
    if not DATABASE_PATH.is_file():
        return TaskResult("Database optimize", False, "Database file not found"), details

    connection = sqlite3.connect(str(DATABASE_PATH), timeout=60)
    try:
        connection.execute("PRAGMA busy_timeout=60000")
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        details["integrity"] = integrity
        if integrity.lower() != "ok":
            return TaskResult("Database optimize", False, f"Integrity check failed: {integrity}"), details
        connection.execute("PRAGMA optimize")
        connection.execute("ANALYZE")
        connection.commit()
        # VACUUM requires no active transaction and may need temporary free disk space.
        connection.execute("VACUUM")
        connection.commit()
    finally:
        connection.close()
    after = DATABASE_PATH.stat().st_size
    details["after"] = after
    reclaimed = max(0, before - after)
    return TaskResult("Database optimize", True, f"Integrity OK • reclaimed {_format_bytes(reclaimed)}"), details


def _cleanup_backups() -> TaskResult:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        BACKUPS_DIR.glob("BankTrackerBot_Full_Backup_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted = 0
    reclaimed = 0
    for path in files[BACKUP_RETENTION:]:
        try:
            reclaimed += path.stat().st_size
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    return TaskResult("Backup retention", True, f"kept {min(len(files), BACKUP_RETENTION)} • removed {deleted} • {_format_bytes(reclaimed)} freed")


def _cleanup_logs() -> TaskResult:
    deleted, reclaimed = _delete_old_files(
        LOGS_DIR,
        LOG_RETENTION_DAYS * 86400,
        patterns=("*.log", "*.txt", "*.jsonl"),
    )
    return TaskResult("Log cleanup", True, f"removed {deleted} old file(s) • {_format_bytes(reclaimed)} freed")


def _cleanup_temp() -> TaskResult:
    deleted = 0
    reclaimed = 0
    for folder in TEMP_DIRS:
        d, r = _delete_old_files(folder, TEMP_RETENTION_HOURS * 3600, patterns=("*.zip", "*.tmp", "*.part", "*.restore_tmp"))
        deleted += d
        reclaimed += r
    return TaskResult("Temporary cleanup", True, f"removed {deleted} stale file(s) • {_format_bytes(reclaimed)} freed")


def _cleanup_exports() -> TaskResult:
    if EXPORT_RETENTION_DAYS <= 0:
        return TaskResult("Export cleanup", True, "disabled (exports are preserved)")
    deleted, reclaimed = _delete_old_files(
        EXPORTS_DIR,
        EXPORT_RETENTION_DAYS * 86400,
        patterns=("*.xlsx", "*.xls", "*.pdf", "*.csv"),
    )
    return TaskResult("Export cleanup", True, f"removed {deleted} file(s) older than {EXPORT_RETENTION_DAYS} days • {_format_bytes(reclaimed)} freed")


def run_maintenance() -> dict[str, Any]:
    """Run safe maintenance and return a serializable report."""
    started = time.monotonic()
    tasks: list[TaskResult] = []
    db_details: dict[str, Any] = {}

    try:
        result, db_details = _database_maintenance()
        tasks.append(result)
    except Exception as exc:
        tasks.append(TaskResult("Database optimize", False, f"{type(exc).__name__}: {exc}"))

    for operation in (_cleanup_backups, _cleanup_logs, _cleanup_temp, _cleanup_exports):
        try:
            tasks.append(operation())
        except Exception as exc:
            tasks.append(TaskResult(operation.__name__.replace("_", " ").title(), False, f"{type(exc).__name__}: {exc}"))

    try:
        usage = shutil.disk_usage(DATA_DIR)
        disk_detail = f"{_format_bytes(usage.free)} free ({usage.free / usage.total * 100:.1f}%)" if usage.total else "Unknown"
        tasks.append(TaskResult("Disk status", usage.free >= 512 * 1024 * 1024, disk_detail))
    except Exception as exc:
        tasks.append(TaskResult("Disk status", False, f"{type(exc).__name__}: {exc}"))

    elapsed = time.monotonic() - started
    success = sum(1 for task in tasks if task.ok)
    return {
        "generated_at": datetime.now(TZ).isoformat(),
        "elapsed_seconds": elapsed,
        "success": success,
        "failed": len(tasks) - success,
        "tasks": [asdict(task) for task in tasks],
        "database": db_details,
    }


def format_maintenance_report(report: dict[str, Any], automatic: bool = False) -> str:
    title = "🌙 Automatic Maintenance" if automatic else "🛠 System Maintenance"
    lines = [title, ""]
    for task in report["tasks"]:
        icon = "✅" if task["ok"] else "❌"
        lines.append(f"{icon} {task['name']}\n   {task['detail']}")
    lines.extend([
        "",
        f"Completed: {report['success']} • Failed: {report['failed']}",
        f"Time: {report['elapsed_seconds']:.2f} seconds",
        "",
        "Receipt images and transaction records were not deleted.",
    ])
    return "\n".join(lines)
