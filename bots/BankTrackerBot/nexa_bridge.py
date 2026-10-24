"""
BankTrackerBot ↔ Nexa Hisab.

- প্রতি ২০ সেকেন্ডে bot-এর database থেকে Payment cycle, receipt আর activity log site-এ mirror হয়
  (শুধু বদলানো row যায়; bot-এ মুছে ফেলা receipt site থেকেও মোছে)।
- Site থেকে দেওয়া কাজ (receipt upload, Complete payment, Reopen, মাস বদল, delete, Excel/PDF, backup,
  doctor…) bot নিজের code দিয়েই চালায়, তাই হিসাব সবসময় bot-এর নিয়মে থাকে।

NEXA_URL / NEXA_TOKEN না থাকলে কিছুই করে না।
ঐচ্ছিক: NEXA_LEDGER=expense  → প্রতিটি receipt Nexa Hisab-এর Transactions-এ খরচ হিসেবেও যাবে
        NEXA_CATEGORY=Dollar payment
"""
import hashlib
import json
import logging
import re
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import BACKUP_RETENTION, DATA_DIR, RECEIPTS_DIR, TIMEZONE

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)
_nexa = None
_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.getenv("NEXA_URL", "").strip() and (os.getenv("NEXA_TOKEN", "").strip() or os.getenv("NEXA_SYNC_TOKEN", "").strip()))


def client():
    global _nexa
    if _nexa is None:
        from nexa_sync import NexaSync
        _nexa = NexaSync(outbox_path=os.getenv("NEXA_OUTBOX") or str(DATA_DIR / "nexa_outbox.db"))
    return _nexa


# ---- mirror -------------------------------------------------------------------
def _iso_tx(date_text: str, time_text: str) -> str:
    """'2026-10-20' + '02:35:10 PM' → '2026-10-20T14:35:10+06:00'."""
    date_text = (date_text or "").strip()
    if not date_text:
        return ""
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime((time_text or "").strip(), fmt)
            return f"{date_text}T{t:%H:%M:%S}+06:00"
        except ValueError:
            continue
    return f"{date_text}T12:00:00+06:00"


def _utc_iso(value: str) -> str:
    """SQLite CURRENT_TIMESTAMP ('YYYY-MM-DD HH:MM:SS', UTC) → ISO with Z."""
    value = str(value or "").strip()
    if len(value) == 19 and value[10] == " ":
        return value.replace(" ", "T") + "Z"
    return value


def _records():
    from database import connect, list_payments
    ledger = os.getenv("NEXA_LEDGER", "").strip().lower()
    category = os.getenv("NEXA_CATEGORY", "Dollar payment").strip()
    cycles = []
    for p in list_payments():
        cycles.append({
            "id": p["payment_code"], "title": p["payment_code"], "amount": round(float(p["total_amount"] or 0), 2) or None,
            "status": p["status"], "at": p["started_at"],
            "data": {"month": p["payment_month"] or "", "started_at": p["started_at"], "completed_at": p["completed_at"] or "",
                     "count": int(p["transaction_count"] or 0), "total": round(float(p["total_amount"] or 0), 2)},
        })
    txs = []
    with connect() as c:
        rows = c.execute("""SELECT t.*, p.payment_code, p.payment_month FROM transactions t
                            LEFT JOIN payment_cycles p ON p.id=t.payment_id ORDER BY t.id""").fetchall()
        activity = c.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 300").fetchall()
    for t in rows:
        amount = round(float(t["amount"] or 0), 2)
        at = _iso_tx(t["transaction_date"], t["transaction_time"]) or _utc_iso(t["created_at"])
        rec = {
            "id": f"tx-{t['id']}", "title": t["receiver_name"] or t["account_number"] or f"Receipt #{t['id']}",
            "amount": amount if amount > 0 else None, "status": t["payment_code"] or "", "at": at,
            "data": {"tx_id": t["id"], "bank": t["bank_name"], "account": t["account_number"], "receiver": t["receiver_name"],
                     "reference": t["reference_id"], "date": t["transaction_date"], "time": t["transaction_time"],
                     "payment_code": t["payment_code"], "payment_month": t["payment_month"], "remarks": t["remarks"],
                     "has_image": bool(t["source_file"] or t["telegram_file_id"]), "created_at": _utc_iso(t["created_at"])},
        }
        if ledger == "expense" and amount > 0:
            rec.update(ledger="expense", category=category, account=t["bank_name"] or "Bank",
                       party=t["receiver_name"] or t["account_number"], note=f"{t['payment_code']} · {t['reference_id']}")
        txs.append(rec)
    acts = [{"id": f"act-{a['id']}", "title": a["action"], "at": _utc_iso(a["created_at"]), "data": {"details": a["details"]}}
            for a in activity]
    return cycles, txs, acts


def snapshot(force: bool = False) -> dict:
    if not enabled():
        return {"skipped": "NEXA_URL / NEXA_TOKEN not set"}
    with _lock:
        cycles, txs, acts = _records()
        n = client()
        out = {"cycle": n.sync_snapshot("cycle", cycles, force=force),
               "bank_tx": n.sync_snapshot("bank_tx", txs, allow_empty=True, force=force)}
        if acts:
            out["activity"] = n.sync_snapshot("activity", acts, force=force)
        return out


# ---- commands from the site -------------------------------------------------------
def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _central_sync():
    try:
        from central_sync import sync_bank_snapshot
        sync_bank_snapshot()
    except Exception:
        logger.exception("Central bank auto-sync failed")


def cmd_add_receipt(payload, file):
    from database import add_transaction, log_activity, update_source_file
    from ocr_parser import extract_text, parse_receipt
    if not file:
        raise ValueError("receipt image missing")
    name, data = file
    suffix = Path(name).suffix.lower() if Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"
    inbox = RECEIPTS_DIR / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / f"site_{datetime.now(TZ):%Y%m%d_%H%M%S_%f}{suffix}"
    path.write_bytes(data)
    parsed = parse_receipt(extract_text(path))
    parsed["source_file"] = str(path)
    parsed["receipt_hash"] = _sha(path)
    if not parsed.get("is_valid"):
        # e.g. a handwritten IFIC cash deposit slip: keep the photo and ask the site for the amount
        from manual_entry import is_deposit_slip, slip_hints
        pending_dir = RECEIPTS_DIR / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        pending_id = path.stem
        shutil.move(str(path), str(pending_dir / path.name))
        (pending_dir / f"{pending_id}.json").write_text(json.dumps({"file": path.name, "hash": parsed["receipt_hash"]}))
        return {"saved": False, "reason": "needs_details", "pending_id": pending_id, "file": name,
                "slip": is_deposit_slip(parsed.get("raw_text", "")), "hints": slip_hints(parsed.get("raw_text", "")),
                "missing": parsed.get("missing_fields", [])}
    ok, row_id, payment_code = add_transaction(parsed)
    if not ok:
        path.unlink(missing_ok=True)
        return {"saved": False, "reason": "duplicate", "payment_code": payment_code, "file": name}
    target_dir = RECEIPTS_DIR / payment_code
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"receipt_{row_id:06d}{suffix}"
    shutil.move(str(path), str(target))
    update_source_file(row_id, target)
    log_activity("SITE_RECEIPT", f"{payment_code} #{row_id} {parsed['amount']}")
    _central_sync()
    summary = {k: parsed.get(k) for k in ("bank_name", "account_number", "receiver_name", "amount", "transaction_date", "transaction_time", "reference_id")}
    return {"saved": True, "tx_id": row_id, "payment_code": payment_code, "file": name, **summary,
            "_notify": {"text": f"🌐 Site থেকে receipt যোগ হয়েছে\n{payment_code} · #{row_id}\n{summary['bank_name']} → {summary['account_number']}\n৳{float(summary['amount']):,.2f}"}}


def cmd_add_manual(payload, file):
    """Manual entry from the site — optionally completing a photo the bot could not read."""
    from database import add_transaction, log_activity, update_source_file
    from manual_entry import parse_manual, to_transaction
    today = datetime.now(TZ).date()
    amount = str(payload.get("amount", "")).strip()
    parts = [amount, str(payload.get("account", "")).strip(), str(payload.get("date", "")).strip()]
    entry = parse_manual(" ".join(p for p in parts if p), today)
    if payload.get("bank"):
        entry["bank"] = str(payload["bank"])[:40]
    entry["note"] = str(payload.get("note", "")).strip()[:200]
    pending_id = re.sub(r"[^\w.-]", "", str(payload.get("pending_id", "")))
    image, meta = None, {}
    if pending_id:
        meta_path = RECEIPTS_DIR / "pending" / f"{pending_id}.json"
        if not meta_path.is_file():
            raise ValueError("এই ছবিটা আর bot-এ নেই — আবার upload করুন")
        meta = json.loads(meta_path.read_text())
        image = RECEIPTS_DIR / "pending" / meta["file"]
    tx = to_transaction(entry, slip=bool(payload.get("slip")), now=datetime.now(TZ).replace(tzinfo=None))
    if image:
        tx.update(receipt_hash=meta.get("hash", ""), source_file=str(image))
    ok, row_id, payment_code = add_transaction(tx)
    if not ok:
        return {"saved": False, "reason": "duplicate", "payment_code": payment_code}
    if image and image.is_file():
        target_dir = RECEIPTS_DIR / payment_code
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"receipt_{row_id:06d}{image.suffix}"
        shutil.move(str(image), str(target))
        update_source_file(row_id, target)
        (RECEIPTS_DIR / "pending" / f"{pending_id}.json").unlink(missing_ok=True)
    log_activity("MANUAL_ENTRY", f"{payment_code} #{row_id} {tx['amount']} (site{' slip' if image else ''})")
    _central_sync()
    return {"saved": True, "tx_id": row_id, "payment_code": payment_code, "amount": tx["amount"], "date": tx["transaction_date"],
            "account": tx["account_number"], "bank_name": tx["bank_name"], "with_image": bool(image),
            "_notify": {"text": f"🌐 Site থেকে manual entry\n{payment_code} · #{row_id}\n{tx['bank_name']} · {tx['account_number']}\n৳{tx['amount']:,.2f} · {tx['transaction_date']}"}}


def cmd_complete_payment(payload, file):
    from database import complete_active_payment, log_activity
    old, new = complete_active_payment()
    if not old:
        raise ValueError("কোনো running payment নেই")
    log_activity("COMPLETE_PAYMENT", f"{old['payment_code']} (site)")
    _central_sync()
    return {"completed": old["payment_code"], "count": int(old["transaction_count"] or 0), "total": float(old["total_amount"] or 0),
            "new_code": new["payment_code"],
            "_notify": {"text": f"🌐 Site থেকে {old['payment_code']} Complete হয়েছে · মোট ৳{float(old['total_amount'] or 0):,.2f}\n🟢 নতুন Running Payment: {new['payment_code']}"}}


def cmd_reopen_payment(payload, file):
    from database import log_activity, reopen_payment
    ok, result = reopen_payment(str(payload.get("code", "")).upper())
    if not ok:
        raise ValueError(result)
    log_activity("REOPEN_PAYMENT", f"{result} (site)")
    return {"active": result, "_notify": {"text": f"🌐 Site থেকে {result} আবার Running Payment করা হয়েছে।"}}


def cmd_set_month(payload, file):
    from database import log_activity, set_payment_month
    code, month = set_payment_month(str(payload.get("code", "")).upper(), str(payload.get("month", "")))
    log_activity("SET_PAYMENT_MONTH", f"{code} {month} (site)")
    _central_sync()
    return {"code": code, "month": month}


def cmd_delete_tx(payload, file):
    from database import delete_row, get_transaction, log_activity
    tx_id = int(payload.get("tx_id"))
    row = get_transaction(tx_id)
    if not row or not delete_row(tx_id):
        raise ValueError(f"Receipt #{tx_id} পাওয়া যায়নি")
    log_activity("DELETE", f"#{tx_id} {row['payment_code']} {row['amount']} (site)")
    _central_sync()
    return {"deleted": tx_id, "payment_code": row["payment_code"], "amount": float(row["amount"] or 0)}


def _rows(code):
    from database import all_rows, rows_for_payment
    rows = rows_for_payment(code) if code else all_rows()
    if not rows:
        raise ValueError(f"{code or 'All Payments'}-এ কোনো record নেই")
    return rows


def cmd_send_excel(payload, file):
    from excel_export import make_excel
    code = (payload.get("code") or "").upper() or None
    rows = _rows(code)
    path = make_excel(rows, code)
    return {"file": Path(path).name, "rows": len(rows),
            "_notify": {"documents": [str(path)], "text": f"📊 {code or 'All Payments'} • {len(rows)} receipts (site থেকে চাওয়া)"}}


def cmd_send_pdf(payload, file):
    from professional import make_pdf
    code = (payload.get("code") or "").upper() or None
    rows = _rows(code)
    out = DATA_DIR / f"{code or 'All_Payments'}_Report.pdf"
    make_pdf(rows, out, f"BURAQ DOLLER PAYMENT — {code or 'ALL PAYMENTS'}")
    return {"file": out.name, "rows": len(rows), "_notify": {"documents": [str(out)]}}


def cmd_send_receipt(payload, file):
    from database import get_transaction
    row = get_transaction(int(payload.get("tx_id")))
    if not row:
        raise ValueError("Receipt পাওয়া যায়নি")
    caption = f"🧾 Receipt #{row['id']}\nPayment: {row['payment_code']}\nAccount: {row['account_number']}\nAmount: ৳{float(row['amount'] or 0):,.2f}\nDate: {row['transaction_date']} {row['transaction_time']}"
    p = Path(row["source_file"] or "")
    photo = str(p) if p.is_file() else (row["telegram_file_id"] or "")
    if not photo:
        raise ValueError("Original receipt ছবি bot-এ পাওয়া যায়নি")
    return {"sent": True, "_notify": {"photos": [(photo, caption)]}}


def cmd_doctor(payload, file):
    from database import log_activity
    from doctor import format_doctor_report, run_doctor
    result = run_doctor()
    log_activity("SYSTEM_DOCTOR", f"health={result['score']}% (site)")
    return {"score": result.get("score"), "report": format_doctor_report(result)}


def cmd_maintenance(payload, file):
    from database import log_activity
    from maintenance import format_maintenance_report, run_maintenance
    result = run_maintenance()
    log_activity("SYSTEM_MAINTENANCE", f"success={result['success']} failed={result['failed']} (site)")
    return {"success": result.get("success"), "failed": result.get("failed"), "report": format_maintenance_report(result)}


def cmd_backup(payload, file):
    from disaster_recovery import create_full_backup
    path, manifest = create_full_backup(BACKUP_RETENTION)
    size = Path(path).stat().st_size
    return {"file": Path(path).name, "size_mb": round(size / 1048576, 2),
            "_notify": {"documents": [str(path)], "text": "🗄 Full backup (site থেকে চাওয়া)"}}


def cmd_resync(payload, file):
    return {"resync": snapshot(force=True)}


HANDLERS = {
    "add_receipt": cmd_add_receipt, "add_manual": cmd_add_manual, "complete_payment": cmd_complete_payment, "reopen_payment": cmd_reopen_payment,
    "set_month": cmd_set_month, "delete_tx": cmd_delete_tx, "send_excel": cmd_send_excel, "send_pdf": cmd_send_pdf,
    "send_receipt": cmd_send_receipt, "doctor": cmd_doctor, "maintenance": cmd_maintenance, "backup": cmd_backup,
    "resync": cmd_resync,
}


def tick() -> list[dict]:
    """Run site commands, then mirror. Returns Telegram notifications for the caller to send. Never raises."""
    if not enabled():
        return []
    notes = []
    try:
        for cmd, ok, result in client().run_commands(HANDLERS, after=snapshot):
            if ok and isinstance(result, dict) and result.get("_notify"):
                notes.append(result["_notify"])
            elif not ok:
                notes.append({"text": f"⚠️ Site-এর কাজ '{cmd['action']}' হয়নি: {result.get('error')}"})
        snapshot()
    except Exception:
        logger.exception("Nexa Hisab tick failed")
    return notes


def status_text() -> str:
    if not enabled():
        return "⚪ Nexa Hisab sync বন্ধ — NEXA_URL ও NEXA_TOKEN সেট করুন।"
    n = client()
    try:
        info = n.ping()
        line = f"✅ Nexa Hisab connected ('{info['bot']}') · site-এ {info['synced']}টি record"
    except Exception as exc:
        line = f"⚠️ Nexa Hisab-এ পৌঁছানো যাচ্ছে না: {exc}"
    if n.pending():
        line += f"\n⏳ পাঠানোর অপেক্ষায়: {n.pending()}টি"
    for rid, err in n.errors(3):
        line += f"\n✗ {rid}: {err}"
    return line
