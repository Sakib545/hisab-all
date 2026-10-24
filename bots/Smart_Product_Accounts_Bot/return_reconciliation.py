from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from database import connect, init_db, session
from settlement import read_table

RETURN_CSV_REQUIRED = {"order consignment id", "order status"}
RETURN_STATUSES = {"return", "paid return"}
PENDING_STATUSES = {"PENDING", "IN_TRANSIT", "UNKNOWN", ""}


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().replace('"', "")


def _key(value: Any) -> str:
    return re.sub(r"[\s\-_/\\\\]+", "", _text(value).upper())


def _columns(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).strip().casefold(): str(column) for column in frame.columns}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_hash(file_hash: str, position: int, values: list[str]) -> str:
    return hashlib.sha256("\x1f".join([file_hash, str(position), *values]).encode("utf-8", errors="replace")).hexdigest()


def _identity(consignment_key: str, merchant_key: str) -> str:
    return f"c:{consignment_key}" if consignment_key else f"m:{merchant_key}" if merchant_key else ""


def is_return_csv_file(path: Path) -> bool:
    try:
        return RETURN_CSV_REQUIRED.issubset(_columns(read_table(path)))
    except Exception:
        return False


_SCHEMA_READY = False


def _ensure_schema() -> None:
    # প্রতিটি অপারেশনে আবার DDL চালানোর দরকার নেই।
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    init_db()
    with session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS return_csv_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                total_rows INTEGER NOT NULL DEFAULT 0,
                return_rows INTEGER NOT NULL DEFAULT 0,
                paid_return_rows INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS return_csv_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id INTEGER NOT NULL,
                row_hash TEXT UNIQUE NOT NULL,
                consignment_key TEXT,
                merchant_key TEXT,
                status TEXT NOT NULL,
                FOREIGN KEY(import_id) REFERENCES return_csv_imports(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_return_csv_consignment ON return_csv_rows(consignment_key);
            CREATE INDEX IF NOT EXISTS ix_return_csv_merchant ON return_csv_rows(merchant_key);
            """
        )
    _SCHEMA_READY = True


def _invoice_return_ids(conn) -> set[str]:
    rows = conn.execute("SELECT consignment_key, merchant_key FROM settlement_v8_rows WHERE invoice_type='return'").fetchall()
    return {
        _identity(str(row["consignment_key"] or ""), str(row["merchant_key"] or ""))
        for row in rows
    } - {""}


def _return_csv_ids(conn) -> set[str]:
    rows = conn.execute("SELECT consignment_key, merchant_key FROM return_csv_rows").fetchall()
    return {
        _identity(str(row["consignment_key"] or ""), str(row["merchant_key"] or ""))
        for row in rows
    } - {""}


def reconciliation_summary(conn=None) -> dict[str, int]:
    owns_connection = conn is None
    if owns_connection:
        _ensure_schema()
        conn = connect()
    try:
        direct_rows = conn.execute("SELECT consignment_key, merchant_key FROM return_csv_rows").fetchall()
        invoice_rows = conn.execute("SELECT consignment_key, merchant_key FROM settlement_v8_rows WHERE invoice_type='return'").fetchall()
        direct_ids = [_identity(str(row["consignment_key"] or ""), str(row["merchant_key"] or "")) for row in direct_rows]
        invoice_ids = [_identity(str(row["consignment_key"] or ""), str(row["merchant_key"] or "")) for row in invoice_rows]
        direct_ids = [value for value in direct_ids if value]
        invoice_ids = [value for value in invoice_ids if value]
        direct_unique, invoice_unique = set(direct_ids), set(invoice_ids)
        return {
            "return_csv_rows": len(direct_rows),
            "return_csv_unique_ids": len(direct_unique),
            "invoice_return_rows": len(invoice_rows),
            "invoice_return_unique_ids": len(invoice_unique),
            "all_return_unique_ids": len(direct_unique | invoice_unique),
            "found_in_both_sources": len(direct_unique & invoice_unique),
            "duplicate_rows_in_return_csv": len(direct_ids) - len(direct_unique),
            "duplicate_rows_in_invoice": len(invoice_ids) - len(invoice_unique),
        }
    finally:
        if owns_connection:
            conn.close()


def _order_index(conn) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for row in conn.execute("SELECT id, consignment, merchant_id, courier_status FROM orders"):
        consignment_key, merchant_key = _key(row["consignment"]), _key(row["merchant_id"])
        for key in (_identity(consignment_key, ""), _identity("", merchant_key)):
            if key and key not in index:
                index[key] = row
    return index


def import_return_csv(path: Path, source_file: str) -> dict[str, int | bool]:
    _ensure_schema()
    frame = read_table(path)
    columns = _columns(frame)
    if not RETURN_CSV_REQUIRED.issubset(columns):
        raise ValueError("Return CSV-এর প্রয়োজনীয় column পাওয়া যায়নি।")
    status_column = columns["order status"]
    statuses = frame[status_column].map(lambda value: _text(value).casefold())
    return_frame = frame.loc[statuses.isin(RETURN_STATUSES)].copy()
    file_hash = _file_hash(path)

    with session() as conn:
        if conn.execute("SELECT 1 FROM return_csv_imports WHERE file_hash=?", (file_hash,)).fetchone():
            result = reconciliation_summary(conn)
            result.update({"already_imported": True, "updated_pending_orders": 0, "skipped_already_returned": 0, "skipped_not_pending": 0, "unmatched_pending_orders": 0, "duplicate_rows_in_uploaded_csv": 0})
            return result

        invoice_return_ids = _invoice_return_ids(conn)
        existing_return_ids = _return_csv_ids(conn)
        orders = _order_index(conn)
        cur = conn.execute(
            "INSERT INTO return_csv_imports(source_file,file_hash,total_rows,return_rows,paid_return_rows,imported_at) VALUES(?,?,?,?,?,?)",
            (source_file, file_hash, len(frame), len(return_frame), int((statuses == "paid return").sum()), datetime.now().isoformat(timespec="seconds")),
        )
        import_id = int(cur.lastrowid)
        consignment_column, merchant_column = columns["order consignment id"], columns.get("merchant order id")
        seen_in_file: set[str] = set()
        updated = already_returned = not_pending = unmatched = duplicate_in_file = 0
        now = datetime.now().isoformat(timespec="seconds")
        for position, (_, row) in enumerate(return_frame.iterrows(), start=1):
            consignment_key = _key(row.get(consignment_column, ""))
            merchant_key = _key(row.get(merchant_column, "")) if merchant_column else ""
            status = _text(row.get(status_column, "")).casefold()
            identity = _identity(consignment_key, merchant_key)
            conn.execute(
                "INSERT INTO return_csv_rows(import_id,row_hash,consignment_key,merchant_key,status) VALUES(?,?,?,?,?)",
                (import_id, _row_hash(file_hash, position, [consignment_key, merchant_key, status]), consignment_key, merchant_key, status),
            )
            if not identity or identity in seen_in_file:
                duplicate_in_file += 1
                continue
            seen_in_file.add(identity)
            order = orders.get(_identity(consignment_key, "")) or orders.get(_identity("", merchant_key))
            if identity in invoice_return_ids or identity in existing_return_ids or (order and str(order["courier_status"] or "").upper() == "RETURNED"):
                already_returned += 1
                continue
            if not order:
                unmatched += 1
                continue
            if str(order["courier_status"] or "").upper() not in PENDING_STATUSES:
                not_pending += 1
                continue
            conn.execute(
                "UPDATE orders SET courier_status='RETURNED', returned_at=?, courier_synced_at=?, courier_raw=? WHERE id=?",
                (now, now, f"Return CSV: {source_file}", int(order["id"])),
            )
            updated += 1
        result = reconciliation_summary(conn)
        result.update({
            "already_imported": False,
            "updated_pending_orders": updated,
            "skipped_already_returned": already_returned,
            "skipped_not_pending": not_pending,
            "unmatched_pending_orders": unmatched,
            "duplicate_rows_in_uploaded_csv": duplicate_in_file,
        })
        return result
