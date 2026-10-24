import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
BASE_DIR=Path(__file__).resolve().parent
DATA_DIR=Path(os.getenv("DATA_DIR") or os.getenv("DATABASE_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or str(BASE_DIR/"data"))
RECEIPTS_DIR=DATA_DIR/"receipts"
EXPORTS_DIR=DATA_DIR/"exports"
BACKUPS_DIR=DATA_DIR/"backups"
for p in (DATA_DIR,RECEIPTS_DIR,EXPORTS_DIR,BACKUPS_DIR): p.mkdir(parents=True,exist_ok=True)
DATABASE_PATH=Path(os.getenv("DATABASE_PATH", str(DATA_DIR/"transactions.db")))
BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
ADMIN_ID=int(os.getenv("ADMIN_ID","0") or 0)
TIMEZONE=os.getenv("TIMEZONE","Asia/Dhaka")
OCR_LANG=os.getenv("OCR_LANG","eng")
TESSERACT_CMD=os.getenv("TESSERACT_CMD","").strip()
if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN missing")
BACKUP_RETENTION=int(os.getenv("BACKUP_RETENTION","7") or 7)
AUTO_BACKUP_ENABLED=os.getenv("AUTO_BACKUP_ENABLED","true").strip().lower() in {"1","true","yes","on"}
AUTO_BACKUP_HOUR=int(os.getenv("AUTO_BACKUP_HOUR","3") or 3)
AUTO_BACKUP_MINUTE=int(os.getenv("AUTO_BACKUP_MINUTE","0") or 0)
INCOMING_RESTORE_DIR=DATA_DIR/"incoming_restore"
INCOMING_RESTORE_DIR.mkdir(parents=True,exist_ok=True)
