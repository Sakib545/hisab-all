import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from config import BACKUPS_DIR, BASE_DIR, DATA_DIR, DATABASE_PATH, EXPORTS_DIR, RECEIPTS_DIR, TIMEZONE
from database import create_database_snapshot, validate_database_file
from zoneinfo import ZoneInfo

TZ = ZoneInfo(TIMEZONE)
APP_NAME = "BankTrackerBot"
BACKUP_FORMAT = 7
SOURCE_EXCLUDES = {".git", ".venv", "venv", "__pycache__", "data", "backups", ".env"}
SOURCE_EXTENSIONS = {".py", ".txt", ".md", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg"}
ROOT_FILES = {"Dockerfile", "requirements.txt", ".gitignore", ".env.example", "Procfile", "railway.json", "render.yaml"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(zf: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in zf.infolist():
        target = (destination / member.filename).resolve()
        if destination not in target.parents and target != destination:
            raise ValueError("Unsafe ZIP path")
    zf.extractall(destination)


def _iter_source_files():
    for path in BASE_DIR.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(BASE_DIR)
        if any(part in SOURCE_EXCLUDES for part in relative.parts):
            continue
        if path.name == ".env":
            continue
        if path.name in ROOT_FILES or path.suffix.lower() in SOURCE_EXTENSIONS:
            yield path, relative


def _count_files(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(1 for item in folder.rglob("*") if item.is_file())


def _write_restore_guide(path: Path) -> None:
    path.write_text(
        """BANKTRACKERBOT ZERO-TOUCH RECOVERY GUIDE\n\n"
        "1. Deploy the included source/ folder to Render, Railway, VPS, or another Python host.\n"
        "2. Configure BOT_TOKEN, ADMIN_ID, TIMEZONE, and DATA_DIR in the host environment.\n"
        "3. Start the bot and upload this ZIP to the bot privately.\n"
        "4. The bot detects the backup and shows Restore/Cancel buttons.\n"
        "5. Tap Restore. Database, receipts, exports, logs, and portable settings are restored automatically.\n\n"
        "SECURITY: .env and secret tokens are intentionally excluded.\n"
        "NOTE: A running cloud container cannot redeploy its own source code reliably. The source/ copy is included\n"
        "for GitHub/account disaster recovery; data restore inside the running bot is automatic.\n"
        """,
        encoding="utf-8",
    )


def create_full_backup(retention: int = 7) -> tuple[Path, dict]:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S-%f")
    recovery_id = f"BTB-{datetime.now(TZ).strftime('%Y%m%d-%H%M%S-%f')}"
    output = BACKUPS_DIR / f"BankTrackerBot_Full_Backup_{stamp}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "package"
        source_dir = root / "source"
        data_dir = root / "data"
        settings_dir = root / "settings"
        restore_dir = root / "restore"
        for directory in (source_dir, data_dir, settings_dir, restore_dir):
            directory.mkdir(parents=True, exist_ok=True)

        # Consistent SQLite snapshot.
        db_snapshot = data_dir / "transactions.db"
        create_database_snapshot(db_snapshot)
        if not validate_database_file(db_snapshot):
            raise ValueError("Database snapshot failed integrity validation")

        for source, relative in _iter_source_files():
            destination = source_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        for folder, name in ((RECEIPTS_DIR, "receipts"), (EXPORTS_DIR, "exports"), (DATA_DIR / "logs", "logs")):
            if folder.exists():
                shutil.copytree(folder, data_dir / name, dirs_exist_ok=True)

        settings = {
            "app": APP_NAME,
            "backup_format": BACKUP_FORMAT,
            "created_at": datetime.now(TZ).isoformat(),
            "timezone": TIMEZONE,
            "database_filename": "transactions.db",
            "required_environment_variables": ["BOT_TOKEN", "ADMIN_ID", "TIMEZONE", "DATA_DIR"],
            "secrets_included": False,
        }
        (settings_dir / "portable_settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        _write_restore_guide(restore_dir / "RESTORE_GUIDE.txt")

        files = [p for p in root.rglob("*") if p.is_file()]
        checksums = {}
        for file_path in files:
            rel = file_path.relative_to(root).as_posix()
            checksums[rel] = _sha256(file_path)

        manifest = {
            "app": APP_NAME,
            "backup_format": BACKUP_FORMAT,
            "recovery_id": recovery_id,
            "created_at": datetime.now(TZ).isoformat(),
            "database": "data/transactions.db",
            "receipts": _count_files(data_dir / "receipts"),
            "exports": _count_files(data_dir / "exports"),
            "source_files": _count_files(source_dir),
            "file_count": len(checksums),
            "checksums_file": "checksums.sha256.json",
            "automatic_restore_supported": True,
            "secrets_included": False,
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (root / "checksums.sha256.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
        (root / "BACKUP_INFO.txt").write_text(
            f"{APP_NAME} Full Backup\nRecovery ID: {recovery_id}\nCreated: {manifest['created_at']}\n"
            f"Source files: {manifest['source_files']}\nReceipts: {manifest['receipts']}\nExports: {manifest['exports']}\n"
            "Secrets included: NO\n",
            encoding="utf-8",
        )

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for file_path in root.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(root).as_posix())

    # Keep only the latest backups.
    backups = sorted(BACKUPS_DIR.glob("BankTrackerBot_Full_Backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[max(1, retention):]:
        old.unlink(missing_ok=True)
    return output, manifest


def inspect_backup(zip_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "extracted"
        root.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract(zf, root)
        manifest_path = root / "manifest.json"
        checksums_path = root / "checksums.sha256.json"
        if not manifest_path.exists() or not checksums_path.exists():
            raise ValueError("This is not a BankTrackerBot full backup")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("app") != APP_NAME or int(manifest.get("backup_format", 0)) < 7:
            raise ValueError("Unsupported backup format")
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        for relative, expected in checksums.items():
            file_path = root / relative
            if not file_path.is_file() or _sha256(file_path) != expected:
                raise ValueError(f"Backup integrity check failed: {relative}")
        db_path = root / manifest.get("database", "data/transactions.db")
        if not db_path.is_file() or not validate_database_file(db_path):
            raise ValueError("Backup database is invalid")
        return manifest


def _database_stats(db_path: Path) -> dict:
    """Read portable comparison statistics without changing the database."""
    stats = {"transactions": 0, "payments": 0, "amount": 0.0}
    if not db_path.is_file():
        return stats
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=10)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "transactions" in tables:
            row = connection.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions").fetchone()
            stats["transactions"] = int(row[0] or 0)
            stats["amount"] = float(row[1] or 0)
        if "payment_cycles" in tables:
            stats["payments"] = int(connection.execute("SELECT COUNT(*) FROM payment_cycles").fetchone()[0] or 0)
    finally:
        connection.close()
    return stats


def _parse_backup_time(value: str):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TZ)
        return parsed.astimezone(TZ)
    except (TypeError, ValueError):
        return None


def analyze_backup(zip_path: Path) -> dict:
    """Verify a backup and compare it with the currently running data."""
    manifest = inspect_backup(zip_path)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "extracted"
        root.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract(zf, root)
        backup_db = root / manifest.get("database", "data/transactions.db")
        backup_stats = _database_stats(backup_db)

    current_stats = _database_stats(DATABASE_PATH)
    backup_created = _parse_backup_time(manifest.get("created_at", ""))
    now = datetime.now(TZ)
    age_hours = None
    if backup_created:
        age_hours = max(0.0, (now - backup_created).total_seconds() / 3600)

    record_difference = current_stats["transactions"] - backup_stats["transactions"]
    amount_difference = current_stats["amount"] - backup_stats["amount"]
    warnings = []
    if record_difference > 0:
        warnings.append(f"Backup-এ বর্তমান database-এর চেয়ে {record_difference}টি কম transaction আছে।")
    if backup_created and age_hours is not None and age_hours > 24:
        days = int(age_hours // 24)
        warnings.append(f"Backupটি প্রায় {days} দিন পুরোনো।")
    if backup_stats["payments"] < current_stats["payments"]:
        warnings.append("Backup-এ বর্তমান system-এর তুলনায় কম payment cycle আছে।")

    return {
        "manifest": manifest,
        "current": current_stats,
        "backup": backup_stats,
        "record_difference": record_difference,
        "amount_difference": amount_difference,
        "age_hours": age_hours,
        "warnings": warnings,
        "is_older_or_smaller": bool(warnings),
    }


def restore_full_backup(zip_path: Path) -> tuple[dict, Path, dict]:
    manifest = inspect_backup(zip_path)
    safety_path, _ = create_full_backup()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "extracted"
        root.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract(zf, root)

        incoming_db = root / manifest.get("database", "data/transactions.db")
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_db = DATABASE_PATH.with_suffix(DATABASE_PATH.suffix + ".restore_tmp")
        shutil.copy2(incoming_db, temp_db)
        if not validate_database_file(temp_db):
            temp_db.unlink(missing_ok=True)
            raise ValueError("Restored database failed integrity validation")
        # A previous WAL/SHM can replay newer pages into the restored database.
        # Remove the sidecar files before atomically replacing the main DB.
        for suffix in ("-wal", "-shm"):
            Path(str(DATABASE_PATH) + suffix).unlink(missing_ok=True)
        os.replace(temp_db, DATABASE_PATH)
        for suffix in ("-wal", "-shm"):
            Path(str(DATABASE_PATH) + suffix).unlink(missing_ok=True)

        incoming_data = root / "data"
        for destination, name in ((RECEIPTS_DIR, "receipts"), (EXPORTS_DIR, "exports"), (DATA_DIR / "logs", "logs")):
            source = incoming_data / name
            if destination.exists():
                shutil.rmtree(destination)
            if source.exists():
                shutil.copytree(source, destination)
            else:
                destination.mkdir(parents=True, exist_ok=True)
    verification = {
        "database_valid": validate_database_file(DATABASE_PATH),
        "database": _database_stats(DATABASE_PATH),
        "receipts": _count_files(RECEIPTS_DIR),
        "exports": _count_files(EXPORTS_DIR),
    }
    expected = analyze_backup(zip_path)["backup"]
    if not verification["database_valid"]:
        raise ValueError("Post-restore database integrity verification failed")
    if verification["database"]["transactions"] != expected["transactions"]:
        raise ValueError("Post-restore transaction count verification failed")
    return manifest, safety_path, verification
