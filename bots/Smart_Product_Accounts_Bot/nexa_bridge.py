"""
Smart Product Accounts Bot ↔ Nexa Hisab.

Mirror (প্রতি ২০ সেকেন্ডে, শুধু বদলানো row):
  order        — প্রতিটি parcel + Paid Invoice live-join status/fee/payout + courier_status (Return CSV)
  import       — Deliveries import history (batch)
  invoice      — Paid Invoice imports (INV-xxxxxx) ও match হিসাব
  duplicate    — duplicate history
  return_import— Return CSV imports
Site থেকে আসা কাজ bot নিজের code দিয়েই চালায় (Deliveries/Paid Invoice/Return CSV upload,
import delete, invoice delete, duplicate clear, saved file পাঠানো, Central Export)।

NEXA_URL / NEXA_TOKEN না থাকলে কিছুই করে না।
"""
import logging
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from database import DATA_DIR, session, init_db

logger = logging.getLogger(__name__)
SAVED_EXPORTS_DIR = DATA_DIR / "saved_exports"   # same folder bot.py uses
SUPPORTED = {".xlsx", ".xls", ".csv"}
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


def _num(v):
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# ---- mirror ---------------------------------------------------------------------
def _records():
    from settlement import _ensure_schema as settle_schema, _live_order_states, list_paid_invoice_imports
    from return_reconciliation import _ensure_schema as return_schema
    init_db(); settle_schema(); return_schema()
    with session() as conn:
        states, _ = _live_order_states(conn)
        orders = conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
        imports = conn.execute("SELECT * FROM import_history ORDER BY id").fetchall()
        dups = conn.execute("SELECT * FROM duplicate_history ORDER BY id DESC LIMIT 3000").fetchall()
        returns = conn.execute("SELECT * FROM return_csv_imports ORDER BY id").fetchall()
    out_orders = []
    for o in orders:
        st = states.get(int(o["id"]), {"status": "PENDING", "fee": 0.0, "payout": 0.0, "collected": 0.0})
        cod = _num(o["cod"])
        out_orders.append({
            "id": f"ord-{o['id']}", "title": o["product"] or "Unknown Product", "amount": cod if cod > 0 else None,
            "status": st["status"], "at": o["order_date"],
            "data": {"c": o["consignment"] or "", "m": o["merchant_id"] or "", "ph": o["phone"] or "",
                     "p": o["product"] or "Unknown Product", "desc": (o["description"] or "")[:400], "cod": cod,
                     "b": o["batch_id"] or "", "f": o["source_file"] or "", "imp": o["imported_at"] or "",
                     "cs": (o["courier_status"] or "UNKNOWN").upper(), "ccod": o["courier_cod"],
                     "fee": round(st["fee"], 2), "payout": round(st["payout"], 2), "col": round(st["collected"], 2),
                     "ra": o["returned_at"] or ""},
        })
    out_imports = [{
        "id": i["batch_id"], "title": i["source_file"], "amount": _num(i["added_cod"]) or None, "at": i["imported_at"],
        "data": {"total": i["total_rows"], "inserted": i["inserted_rows"], "duplicates": i["duplicate_rows"],
                 "invalid": i["invalid_rows"], "duplicate_cod": _num(i["duplicate_cod"]),
                 "files": [Path(n).name.split("__", 1)[-1] for n in str(i["export_files"] or "").split("|") if n]},
    } for i in imports if i["batch_id"]]
    out_invoices = []
    for v in list_paid_invoice_imports(limit=5000):
        out_invoices.append({
            "id": v["invoice_code"], "title": v["source_file"], "amount": _num(v["total_payout"]) or None, "at": v["imported_at"],
            "data": {k: v.get(k) for k in ("id", "rows", "delivery_rows", "return_rows", "insta_fee_rows", "matched_delivery",
                                            "matched_return", "unmatched", "ignored_other", "matched_by_merchant",
                                            "matched_by_consignment", "invoice_date_from", "invoice_date_to", "total_fee", "total_payout")},
        })
    out_dups = [{
        "id": f"dup-{d['id']}", "title": d["product"] or "", "amount": _num(d["cod"]) or None, "at": d["duplicate_at"],
        "status": d["duplicate_reason"],
        "data": {"c": d["consignment"] or "", "m": d["merchant_id"] or "", "ph": d["phone"] or "", "od": d["order_date"] or "",
                 "orig": d["original_file"] or "", "file": d["duplicate_file"] or "", "b": d["batch_id"] or ""},
    } for d in dups]
    out_returns = [{
        "id": f"ret-{r['id']}", "title": r["source_file"], "at": r["imported_at"],
        "data": {"total": r["total_rows"], "returns": r["return_rows"], "paid_returns": r["paid_return_rows"]},
    } for r in returns]
    return out_orders, out_imports, out_invoices, out_dups, out_returns


def snapshot(force: bool = False) -> dict:
    if not enabled():
        return {"skipped": "NEXA_URL / NEXA_TOKEN not set"}
    with _lock:
        orders, imports, invoices, dups, returns = _records()
        n = client()
        return {
            "order": n.sync_snapshot("order", orders, allow_empty=True, force=force),
            "import": n.sync_snapshot("import", imports, allow_empty=True, force=force),
            "invoice": n.sync_snapshot("invoice", invoices, allow_empty=True, force=force),
            "duplicate": n.sync_snapshot("duplicate", dups, allow_empty=True, force=force),
            "return_import": n.sync_snapshot("return_import", returns, allow_empty=True, force=force),
        }


# ---- helpers shared with bot.py ---------------------------------------------------
def _central():
    try:
        from central_sync import sync_courier_snapshot
        sync_courier_snapshot()
    except Exception:
        logger.exception("Central courier auto-sync failed")


def _with_file(file, fn):
    if not file:
        raise ValueError("file missing")
    name, data = file
    ext = Path(name).suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError("শুধু .xlsx, .xls অথবা .csv ফাইল")
    with tempfile.TemporaryDirectory(prefix="nexa_upload_") as td:
        temp = Path(td)
        path = temp / f"input{ext}"
        path.write_bytes(data)
        return fn(path, temp, name)


# ---- commands -----------------------------------------------------------------------
def _deliveries(path, temp, filename):
    """Same steps as bot.py's handle_document for a Deliveries file, minus the chat replies."""
    from database import insert_orders_with_results, log_import, save_duplicate_rows
    from processor import create_analysis_outputs, create_outputs_from_rows, process_file
    from settlement import detect_order_months
    batch_id = uuid.uuid4().hex
    result = process_file(path, temp, filename)
    save_duplicate_rows(result.get("file_duplicate_rows", []), batch_id, filename)
    inserted_rows, duplicate_rows = insert_orders_with_results(result["db_rows"], batch_id)
    sheet_synced = 0
    try:
        from google_sheets import append_orders
        sheet_synced = append_orders(inserted_rows)
    except Exception:
        logger.exception("Google Sheets append sync failed for batch %s", batch_id)
    _central()
    outputs = create_outputs_from_rows(inserted_rows, temp)
    analysis = create_analysis_outputs(inserted_rows, temp)
    SAVED_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    saved_names, auto_docs = [], []
    for item in outputs + analysis["outputs"]:
        saved_name = f"{batch_id}__{Path(item['filename']).name}"
        shutil.copy2(item["path"], SAVED_EXPORTS_DIR / saved_name)
        saved_names.append(saved_name)
        if item in outputs and item.get("delivery") == "auto":
            auto_docs.append((str(SAVED_EXPORTS_DIR / saved_name), item["filename"],
                              f"✅ {item['product']}\nঅর্ডার: {item['count']}\nCOD: ৳{float(item['cod']):,.0f}"))
    file_dups = int(result.get("file_duplicates", 0))
    invalid = int(result.get("invalid_consignment_rows", 0))
    added_cod = sum(float(r.get("cod") or 0) for r in inserted_rows)
    dup_cod = sum(float(r.get("cod") or 0) for r in duplicate_rows) + sum(float(r.get("cod") or 0) for r in result.get("file_duplicate_rows", []))
    log_import(batch_id, filename, int(result.get("original_rows", result["input_rows"])), len(inserted_rows),
               file_dups + len(duplicate_rows), invalid, added_cod, dup_cod, "|".join(saved_names))
    products = [{"product": i["product"], "count": i["count"], "cod": float(i["cod"]),
                 "auto": i.get("delivery") == "auto"} for i in outputs]
    return {
        "type": "deliveries", "file": filename, "batch_id": batch_id,
        "original_rows": int(result.get("original_rows", 0)), "unique_rows": int(result.get("input_rows", 0)),
        "inserted": len(inserted_rows), "file_duplicates": file_dups, "db_duplicates": len(duplicate_rows),
        "invalid": invalid, "mixed_or_qty": sum(1 for r in inserted_rows if not bool(r.get("export_eligible", True))),
        "added_cod": round(added_cod, 2), "sheet_synced": sheet_synced, "products": products,
        "months": [{"month": f"{y:04d}-{m:02d}", "count": c} for y, m, c in detect_order_months(inserted_rows)],
        "cod_mismatches": int(analysis.get("cod_mismatches", 0)),
        "files": [Path(n).name.split("__", 1)[-1] for n in saved_names],
        "_notify": {"text": f"🌐 Site থেকে Deliveries import: {filename}\nনতুন: {len(inserted_rows)} · Duplicate: {file_dups + len(duplicate_rows)} · COD ৳{added_cod:,.0f}",
                    "documents": auto_docs},
    }


def cmd_upload(payload, file):
    from settlement import import_paid_invoice, is_paid_invoice_file
    from return_reconciliation import import_return_csv, is_return_csv_file
    kind = payload.get("type", "auto")

    def run(path, temp, name):
        if kind == "return_csv":
            if not is_return_csv_file(path):
                raise ValueError("এটি Return CSV নয় (Order consignment id ও Order status column লাগবে)। কোনো data বদলায়নি।")
            r = import_return_csv(path, name)
            _central()
            return {"type": "return_csv", "file": name, **{k: v for k, v in r.items()}}
        if kind in ("auto", "paid_invoice") and is_paid_invoice_file(path):
            inv = import_paid_invoice(path, name)
            _central()
            keys = ("invoice_code", "already_imported", "rows", "delivery_rows", "return_rows", "insta_fee_rows", "matched_delivery",
                    "matched_return", "unmatched", "ignored_other", "matched_by_merchant", "matched_by_consignment",
                    "total_fee", "total_payout", "invoice_date_from", "invoice_date_to")
            out = {"type": "paid_invoice", "file": name, **{k: inv.get(k) for k in keys}}
            if not inv.get("matched_delivery") and not inv.get("matched_return") and (inv.get("rows") or 0) > 0:
                out["warning"] = "একটিও order match হয়নি — সম্ভবত ভুল সময়ের Deliveries CSV আগে upload হয়েছে।"
            return out
        if kind == "paid_invoice":
            raise ValueError("এটি Paid Invoice CSV নয় (consignment_id, invoice type, merchant_order_id column লাগবে)।")
        return _deliveries(path, temp, name)
    return _with_file(file, run)


def cmd_delete_import(payload, file):
    from database import all_orders, delete_import
    batch_id = str(payload.get("batch_id", ""))
    result = delete_import(batch_id)
    if not result["deleted"]:
        raise ValueError("Import পাওয়া যায়নি")
    sheet = "ok"
    try:
        from google_sheets import delete_orders, replace_all
        rows = result.get("deleted_rows", [])
        if delete_orders(rows) < len(rows):
            replace_all([dict(r) for r in all_orders()])
            sheet = "full resync"
    except Exception:
        logger.exception("Google Sheets delete failed for batch %s", batch_id)
        sheet = "pending — bot-এ /resync দিন"
    for name in filter(None, str(result.get("export_files", "")).split("|")):
        (SAVED_EXPORTS_DIR / Path(name).name).unlink(missing_ok=True)
    _central()
    return {"orders": result["orders"], "cod": result["cod"], "sheet": sheet}


def cmd_delete_invoice(payload, file):
    from settlement import delete_paid_invoice_import
    r = delete_paid_invoice_import(int(payload.get("import_id")))
    if not r:
        raise ValueError("Invoice পাওয়া যায়নি")
    _central()
    return {k: r.get(k) for k in ("invoice_code", "source_file", "deleted_rows")}


def cmd_delete_all_invoices(payload, file):
    from settlement import delete_all_paid_invoice_imports
    r = delete_all_paid_invoice_imports()
    _central()
    return r


def cmd_clear_duplicates(payload, file):
    from database import clear_duplicates
    return {"cleared": clear_duplicates()}


def cmd_send_files(payload, file):
    batch_id = str(payload.get("batch_id", ""))
    docs = [(str(p), p.name.split("__", 1)[-1], None) for p in sorted(SAVED_EXPORTS_DIR.glob(f"{batch_id}__*"))]
    if not docs:
        raise ValueError("এই import-এর saved file নেই (৩০ দিনের পুরনো file মুছে যায়)")
    return {"files": len(docs), "_notify": {"documents": docs}}


def cmd_central_export(payload, file):
    from central_sync import export_central_xlsx
    out = DATA_DIR / "BURAQ_Central_Export.xlsx"
    export_central_xlsx(out)
    return {"file": out.name, "_notify": {"documents": [(str(out), out.name, "📦 Central Export (site থেকে চাওয়া)")]}}


def cmd_resync(payload, file):
    return {"resync": snapshot(force=True)}


HANDLERS = {
    "upload": cmd_upload, "delete_import": cmd_delete_import, "delete_invoice": cmd_delete_invoice,
    "delete_all_invoices": cmd_delete_all_invoices, "clear_duplicates": cmd_clear_duplicates,
    "send_files": cmd_send_files, "central_export": cmd_central_export, "resync": cmd_resync,
}


def tick() -> list[dict]:
    """Run site commands, then mirror. Returns Telegram notifications for the caller. Never raises."""
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
