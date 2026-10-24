"""System health checks for BankTrackerBot.

This module has no Telegram dependency, so the checks can be tested independently.
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config import BACKUPS_DIR, DATABASE_PATH, DATA_DIR, EXPORTS_DIR, RECEIPTS_DIR, TESSERACT_CMD, TIMEZONE

TZ = ZoneInfo(TIMEZONE)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class Check:
    name: str
    ok: bool
    value: str
    severity: str = "error"  # error or warning


def _format_bytes(size: int | float) -> str:
    value = float(size or 0)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def _format_age(seconds: float | None) -> str:
    if seconds is None:
        return "Never"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _count_files(folder: Path, suffixes: set[str] | None = None) -> int:
    if not folder.exists():
        return 0
    return sum(
        1
        for path in folder.rglob("*")
        if path.is_file() and (suffixes is None or path.suffix.lower() in suffixes)
    )


def _resolve_receipt_path(raw_path: str) -> Path | None:
    raw_path = (raw_path or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    if path.is_file():
        return path

    # Backups restored on a different host can contain old absolute paths.
    # Try matching the payment-folder/file tail inside the current receipt root.
    parts = path.parts
    for depth in (2, 1):
        if len(parts) >= depth:
            candidate = RECEIPTS_DIR.joinpath(*parts[-depth:])
            if candidate.is_file():
                return candidate
    return None


def _database_report() -> dict[str, Any]:
    result: dict[str, Any] = {
        "exists": DATABASE_PATH.is_file(),
        "integrity": False,
        "integrity_text": "Database file missing",
        "records": 0,
        "payments": 0,
        "missing_receipts": 0,
        "size": DATABASE_PATH.stat().st_size if DATABASE_PATH.is_file() else 0,
    }
    if not DATABASE_PATH.is_file():
        return result

    connection = sqlite3.connect(str(DATABASE_PATH), timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        result["integrity"] = str(integrity).lower() == "ok"
        result["integrity_text"] = str(integrity)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "transactions" in tables:
            result["records"] = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            rows = connection.execute(
                "SELECT source_file, telegram_file_id FROM transactions"
            ).fetchall()
            missing = 0
            for row in rows:
                source_file = (row["source_file"] or "").strip()
                telegram_file_id = (row["telegram_file_id"] or "").strip()
                # Telegram file ID is a valid recovery source even when local image is missing.
                if source_file and _resolve_receipt_path(source_file) is None and not telegram_file_id:
                    missing += 1
                elif not source_file and not telegram_file_id:
                    missing += 1
            result["missing_receipts"] = missing
        if "payment_cycles" in tables:
            result["payments"] = connection.execute("SELECT COUNT(*) FROM payment_cycles").fetchone()[0]
    finally:
        connection.close()
    return result


def _latest_backup() -> tuple[Path | None, float | None]:
    if not BACKUPS_DIR.exists():
        return None, None
    backups = sorted(
        BACKUPS_DIR.glob("BankTrackerBot_Full_Backup_*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        return None, None
    latest = backups[0]
    age = datetime.now(TZ).timestamp() - latest.stat().st_mtime
    return latest, age


def _tesseract_status() -> tuple[bool, str]:
    configured = (TESSERACT_CMD or "").strip()
    if configured:
        path = Path(configured)
        return path.is_file(), str(path)
    found = shutil.which("tesseract")
    return bool(found), found or "Not found in PATH"


def run_doctor() -> dict[str, Any]:
    """Run all checks and return data ready for Telegram formatting."""
    checks: list[Check] = []
    errors: list[str] = []

    try:
        db = _database_report()
    except Exception as exc:  # keep /doctor alive even if SQLite is damaged/locked
        db = {
            "exists": DATABASE_PATH.is_file(), "integrity": False,
            "integrity_text": f"{type(exc).__name__}: {exc}", "records": 0,
            "payments": 0, "missing_receipts": 0,
            "size": DATABASE_PATH.stat().st_size if DATABASE_PATH.is_file() else 0,
        }
        errors.append(f"Database check: {type(exc).__name__}: {exc}")

    checks.append(Check("Database file", bool(db["exists"]), _format_bytes(db["size"])))
    checks.append(Check("Database integrity", bool(db["integrity"]), str(db["integrity_text"])))

    receipt_files = _count_files(RECEIPTS_DIR, IMAGE_SUFFIXES)
    missing_receipts = int(db["missing_receipts"])
    checks.append(Check(
        "Missing receipt images",
        missing_receipts == 0,
        str(missing_receipts),
        severity="warning",
    ))

    export_files = _count_files(EXPORTS_DIR)
    latest_backup, backup_age = _latest_backup()
    backup_ok = latest_backup is not None and backup_age is not None and backup_age <= 48 * 3600
    checks.append(Check(
        "Recent backup",
        backup_ok,
        _format_age(backup_age),
        severity="warning",
    ))

    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_percent = (usage.free / usage.total * 100) if usage.total else 0
        disk_ok = free_percent >= 10 and usage.free >= 512 * 1024 * 1024
        checks.append(Check("Free disk space", disk_ok, f"{_format_bytes(usage.free)} ({free_percent:.1f}% free)"))
    except Exception as exc:
        usage = None
        checks.append(Check("Free disk space", False, f"{type(exc).__name__}: {exc}"))
        errors.append(f"Disk check: {type(exc).__name__}: {exc}")

    tesseract_ok, tesseract_value = _tesseract_status()
    checks.append(Check("OCR engine", tesseract_ok, tesseract_value))

    # Weighted score: errors cost more than warnings.
    penalty = sum(20 if not item.ok and item.severity == "error" else 8 if not item.ok else 0 for item in checks)
    score = max(0, 100 - penalty)
    if score >= 90:
        health = "🟢 Healthy"
    elif score >= 70:
        health = "🟡 Needs attention"
    else:
        health = "🔴 Unhealthy"

    return {
        "generated_at": datetime.now(TZ).isoformat(),
        "database": db,
        "receipt_files": receipt_files,
        "export_files": export_files,
        "latest_backup": latest_backup,
        "backup_age": backup_age,
        "disk": usage,
        "tesseract_ok": tesseract_ok,
        "tesseract_value": tesseract_value,
        "checks": checks,
        "score": score,
        "health": health,
        "errors": errors,
    }


def format_doctor_report(report: dict[str, Any]) -> str:
    db = report["database"]
    latest = report["latest_backup"]
    disk = report["disk"]
    integrity_icon = "✅" if db["integrity"] else "❌"
    missing_icon = "✅" if db["missing_receipts"] == 0 else "⚠️"
    backup_icon = "✅" if latest and report["backup_age"] <= 48 * 3600 else "⚠️"
    ocr_icon = "✅" if report["tesseract_ok"] else "❌"

    lines = [
        "🩺 System Doctor",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🗄 Database",
        "━━━━━━━━━━━━━━━━━━",
        f"Integrity: {integrity_icon} {db['integrity_text']}",
        f"Records: {db['records']}",
        f"Payments: {db['payments']}",
        f"Size: {_format_bytes(db['size'])}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🧾 Receipts",
        "━━━━━━━━━━━━━━━━━━",
        f"Stored images: {report['receipt_files']}",
        f"Missing recovery source: {missing_icon} {db['missing_receipts']}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📦 Backup & Exports",
        "━━━━━━━━━━━━━━━━━━",
        f"Latest backup: {backup_icon} {_format_age(report['backup_age'])}",
        f"Backup file: {latest.name if latest else 'None'}",
        f"Export files: {report['export_files']}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "⚙️ System",
        "━━━━━━━━━━━━━━━━━━",
        f"OCR engine: {ocr_icon} {'Available' if report['tesseract_ok'] else 'Not found'}",
    ]
    if disk:
        free_percent = disk.free / disk.total * 100 if disk.total else 0
        lines.extend([
            f"Disk free: {_format_bytes(disk.free)} ({free_percent:.1f}%)",
            f"Disk used: {_format_bytes(disk.used)}",
        ])
    else:
        lines.append("Disk: ❌ Check failed")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "❤️ Overall Health",
        "━━━━━━━━━━━━━━━━━━",
        f"{report['health']} — {report['score']}%",
    ])

    failed = [item for item in report["checks"] if not item.ok]
    if failed:
        lines.extend(["", "Attention:"])
        for item in failed:
            icon = "⚠️" if item.severity == "warning" else "❌"
            lines.append(f"{icon} {item.name}: {item.value}")
    return "\n".join(lines)
