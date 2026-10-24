"""
BusinessExpenseBot → Nexa Hisab sync.

NEXA_URL আর NEXA_TOKEN সেট না থাকলে কিছুই করে না (bot আগের মতোই চলে)।
Google Sheet-ই আসল হিসাব: প্রতিবার খরচ যোগ/delete হলে পুরো sheet-এর snapshot পাঠানো হয়,
তাই delete করা খরচ Nexa Hisab থেকেও মুছে যায়।
"""
import hashlib
import logging
import os
import threading
from collections import Counter

logger = logging.getLogger(__name__)
_nexa = None
_sync_lock = threading.Lock()  # one snapshot at a time, so an older one never undoes a newer one


def enabled() -> bool:
    return bool(os.getenv("NEXA_URL", "").strip() and (os.getenv("NEXA_TOKEN", "").strip() or os.getenv("NEXA_SYNC_TOKEN", "").strip()))


def client():
    global _nexa
    if _nexa is None:
        from nexa_sync import NexaSync
        data_dir = os.getenv("DATA_DIR", "").strip()
        _nexa = NexaSync(outbox_path=os.getenv("NEXA_OUTBOX") or (os.path.join(data_dir, "nexa_outbox.db") if data_dir else None))
    return _nexa


def stable_id(date_iso: str, category: str, amount: float, n: int) -> str:
    # Sheet row numbers shift when a row is deleted, so the id is built from the expense itself.
    # n = which copy of an identical expense on the same day (1st, 2nd…).
    cat = hashlib.sha1(category.strip().casefold().encode()).hexdigest()[:8]
    return f"exp-{date_iso}-{cat}-{amount:g}-{n}"


def to_records(rows: list[dict]) -> list[dict]:
    seen = Counter()
    out = []
    for r in rows:
        d = r["date"].isoformat()
        key = (d, r["category"].strip().casefold(), float(r["amount"]))
        seen[key] += 1
        out.append({
            "id": stable_id(d, r["category"], float(r["amount"]), seen[key]),
            "title": r["category"],
            "amount": float(r["amount"]),
            "at": d,
            "ledger": "expense",
            "category": r["category"],
            "account": os.getenv("NEXA_ACCOUNT", "Cash"),
            "data": {"sheet_row": r.get("row_number"), "source": "Google Sheet · All Expenses"},
        })
    return out


def sync_expenses(store) -> dict:
    """Never raises — the bot must keep working even if Nexa Hisab is down."""
    if not enabled():
        return {"skipped": "NEXA_URL / NEXA_TOKEN not set"}
    try:
        with _sync_lock:
            result = client().sync_snapshot("expense", to_records(store.get_all()))
        logger.info("Nexa Hisab sync: %s", result)
        return result
    except Exception as exc:
        logger.exception("Nexa Hisab sync failed")
        return {"error": f"{type(exc).__name__}: {exc}"}


def sync_in_background(store) -> None:
    """Telegram reply আটকে না রেখে sync চালায়।"""
    if enabled():
        threading.Thread(target=sync_expenses, args=(store,), daemon=True).start()


def flush() -> None:
    if enabled():
        try:
            client().flush()
        except Exception:
            logger.exception("Nexa Hisab retry failed")


def status_text() -> str:
    if not enabled():
        return "⚪ Nexa Hisab sync বন্ধ — NEXA_URL ও NEXA_TOKEN সেট করুন।"
    n = client()
    try:
        info = n.ping()
        line = f"✅ Nexa Hisab connected ('{info['bot']}') · site-এ {info['synced']}টি record"
    except Exception as exc:
        line = f"⚠️ Nexa Hisab-এ পৌঁছানো যাচ্ছে না: {exc}"
    pending = n.pending()
    rejected = n.errors(3)
    if pending:
        line += f"\n⏳ পাঠানোর অপেক্ষায়: {pending}টি"
    for rid, err in rejected:
        line += f"\n✗ {rid}: {err}"
    return line
