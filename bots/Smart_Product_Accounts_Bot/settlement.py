from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from database import DB_PATH, init_db, session

PAID_INVOICE_REQUIRED = {"consignment_id", "invoice type", "merchant_order_id"}
FINAL_TYPES = {"delivery", "return"}


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().replace('"', "")
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text


def _key(value: Any) -> str:
    return re.sub(r"[\s\-_/\\]+", "", _text(value).upper())


def _money(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        return round(float(str(value).replace(",", "").replace("৳", "").strip() or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _parse_datetime(value: Any) -> Any:
    """DD/MM/YYYY কে day-first ধরে parse করে (ISO হলে day-first নয়)।"""
    text = _text(value)
    if not text:
        return pd.NaT
    day_first = not re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", text)
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=day_first)
    if pd.isna(parsed):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=not day_first)
    return parsed


def _date_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    parsed = _parse_datetime(text)
    if pd.isna(parsed):
        return text
    return parsed.strftime("%Y-%m-%d")


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
            try:
                return pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.read_excel(path, dtype=str, keep_default_na=False)


def _column_map(frame: pd.DataFrame) -> dict[str, str]:
    return {str(c).strip().casefold(): str(c) for c in frame.columns}


def is_paid_invoice_file(path: Path) -> bool:
    try:
        cols = set(_column_map(read_table(path)))
    except Exception:
        return False
    return PAID_INVOICE_REQUIRED.issubset(cols)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_hash(file_hash: str, position: int, values: list[Any]) -> str:
    payload = "\x1f".join([file_hash, str(position), *(_text(v) for v in values)])
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def _create_backup_once() -> dict[str, Any]:
    init_db()
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    with session() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settlement_v8_meta(meta_key TEXT PRIMARY KEY, meta_value TEXT NOT NULL, updated_at TEXT NOT NULL)")
        row = conn.execute("SELECT meta_value FROM settlement_v8_meta WHERE meta_key='pre_v8_backup'").fetchone()
        if row and Path(str(row["meta_value"])).exists():
            return {"created": False, "path": str(row["meta_value"])}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"bot_data_before_v8_{stamp}.db"
    source = sqlite3.connect(DB_PATH)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
        check = target.execute("PRAGMA integrity_check").fetchone()
        if not check or str(check[0]).lower() != "ok":
            raise RuntimeError("Backup integrity check failed")
    finally:
        target.close()
        source.close()
    with session() as conn:
        conn.execute("INSERT OR REPLACE INTO settlement_v8_meta(meta_key,meta_value,updated_at) VALUES('pre_v8_backup',?,?)", (str(backup), datetime.now().isoformat(timespec="seconds")))
    return {"created": True, "path": str(backup)}


_SCHEMA_READY = False


def _ensure_schema() -> None:
    # প্রতিটি অপারেশনে আবার DDL চালানোর দরকার নেই।
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    init_db()
    with session() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settlement_v8_meta(
            meta_key TEXT PRIMARY KEY, meta_value TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settlement_v8_imports(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_code TEXT UNIQUE NOT NULL,
            source_file TEXT NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            total_rows INTEGER NOT NULL DEFAULT 0,
            delivery_rows INTEGER NOT NULL DEFAULT 0,
            return_rows INTEGER NOT NULL DEFAULT 0,
            other_rows INTEGER NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settlement_v8_rows(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_id INTEGER NOT NULL,
            row_hash TEXT UNIQUE NOT NULL,
            row_position INTEGER NOT NULL,
            consignment_id TEXT,
            consignment_key TEXT,
            merchant_order_id TEXT,
            merchant_key TEXT,
            invoice_type TEXT NOT NULL,
            created_date TEXT,
            collected_amount REAL NOT NULL DEFAULT 0,
            collectable_amount REAL NOT NULL DEFAULT 0,
            cod_fee REAL NOT NULL DEFAULT 0,
            delivery_fee REAL NOT NULL DEFAULT 0,
            final_fee REAL NOT NULL DEFAULT 0,
            payout REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(import_id) REFERENCES settlement_v8_imports(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_v8_rows_import ON settlement_v8_rows(import_id);
        CREATE INDEX IF NOT EXISTS ix_v8_rows_merchant ON settlement_v8_rows(merchant_key);
        CREATE INDEX IF NOT EXISTS ix_v8_rows_consignment ON settlement_v8_rows(consignment_key);
        """)
    _SCHEMA_READY = True


def _next_invoice_code(conn: sqlite3.Connection) -> str:
    # AUTOINCREMENT-এর কারণে delete করার পর MAX(id)+1 আর আসল id মেলে না,
    # তাই খালি একটি code খুঁজে নেওয়া হয়।
    used = {str(r["invoice_code"]) for r in conn.execute("SELECT invoice_code FROM settlement_v8_imports")}
    n = int(conn.execute("SELECT COALESCE(MAX(id),0)+1 n FROM settlement_v8_imports").fetchone()["n"])
    while f"INV-{n:06d}" in used:
        n += 1
    return f"INV-{n:06d}"


def _order_maps(conn: sqlite3.Connection) -> tuple[dict[str, sqlite3.Row], dict[str, sqlite3.Row]]:
    merchant: dict[str, sqlite3.Row] = {}
    consignment: dict[str, sqlite3.Row] = {}
    for row in conn.execute("SELECT id,consignment,merchant_id,product,cod,courier_charge,order_date FROM orders ORDER BY id"):
        mk, ck = _key(row["merchant_id"]), _key(row["consignment"])
        if mk and mk not in merchant:
            merchant[mk] = row
        if ck and ck not in consignment:
            consignment[ck] = row
    return merchant, consignment


def _match_row(row: sqlite3.Row, merchant: dict[str, sqlite3.Row], consignment: dict[str, sqlite3.Row]) -> tuple[sqlite3.Row | None, str | None]:
    mk, ck = str(row["merchant_key"] or ""), str(row["consignment_key"] or "")
    if mk and mk in merchant:
        return merchant[mk], "merchant_order_id"
    if ck and ck in consignment:
        return consignment[ck], "consignment_id"
    return None, None


def _import_snapshot(conn: sqlite3.Connection, import_id: int) -> dict[str, Any] | None:
    imp = conn.execute("SELECT * FROM settlement_v8_imports WHERE id=?", (import_id,)).fetchone()
    if not imp:
        return None
    merchant, consignment = _order_maps(conn)
    matched_delivery = matched_return = unmatched = 0
    matched_by_merchant = matched_by_consignment = 0
    ignored_other = 0
    fee = payout = 0.0
    invoice_dates: list[str] = []
    for row in conn.execute("SELECT * FROM settlement_v8_rows WHERE import_id=? ORDER BY row_position,id", (import_id,)):
        if row["created_date"]:
            invoice_dates.append(str(row["created_date"]))
        if row["invoice_type"] not in FINAL_TYPES:
            ignored_other += 1
            continue
        order, matched_by = _match_row(row, merchant, consignment)
        if not order:
            unmatched += 1
            continue
        if matched_by == "merchant_order_id":
            matched_by_merchant += 1
        elif matched_by == "consignment_id":
            matched_by_consignment += 1
        if row["invoice_type"] == "return":
            matched_return += 1
        else:
            matched_delivery += 1
        fee += float(row["final_fee"] or 0)
        payout += float(row["payout"] or 0)
    result = dict(imp)
    result.update({
        "rows": int(imp["total_rows"] or 0),
        "insta_fee_rows": int(imp["other_rows"] or 0),
        "matched_delivery": matched_delivery,
        "matched_return": matched_return,
        "unmatched": unmatched,
        "unmatched_rows": unmatched,
        "ignored_other": ignored_other,
        "matched_by_merchant": matched_by_merchant,
        "matched_by_consignment": matched_by_consignment,
        "invoice_date_from": min(invoice_dates) if invoice_dates else "",
        "invoice_date_to": max(invoice_dates) if invoice_dates else "",
        "available_delivery_orders": len(merchant) if merchant else len(consignment),
        "total_fee": round(fee, 2),
        "total_payout": round(payout, 2),
        "matched_fee": round(fee, 2),
        "matched_payout": round(payout, 2),
        "ledger_rows": int(imp["total_rows"] or 0),
        "payout": round(payout, 2),
    })
    return result


def import_paid_invoice(path: Path, source_file: str) -> dict[str, Any]:
    _ensure_schema()
    frame = read_table(path)
    columns = _column_map(frame)
    if not PAID_INVOICE_REQUIRED.issubset(columns):
        raise ValueError("Paid Invoice CSV-এর প্রয়োজনীয় column পাওয়া যায়নি।")
    digest = _file_hash(path)
    with session() as conn:
        existing = conn.execute("SELECT id FROM settlement_v8_imports WHERE file_hash=?", (digest,)).fetchone()
        if existing:
            snap = _import_snapshot(conn, int(existing["id"])) or {}
            snap["already_imported"] = True
            return snap
        invoice_code = _next_invoice_code(conn)
        now = datetime.now().isoformat(timespec="seconds")
        types = frame[columns["invoice type"]].map(lambda v: _text(v).casefold())
        delivery_rows = int((types == "delivery").sum())
        return_rows = int((types == "return").sum())
        other_rows = int(len(frame) - delivery_rows - return_rows)
        cur = conn.execute(
            "INSERT INTO settlement_v8_imports(invoice_code,source_file,file_hash,total_rows,delivery_rows,return_rows,other_rows,imported_at) VALUES(?,?,?,?,?,?,?,?)",
            (invoice_code, source_file, digest, len(frame), delivery_rows, return_rows, other_rows, now),
        )
        import_id = int(cur.lastrowid)

        # আগে প্রতিটি row-এর জন্য ১০ বার নতুন Series তৈরি হতো।
        def col(name: str, default: str = "") -> list[Any]:
            actual = columns.get(name.casefold())
            return list(frame[actual]) if actual else [default] * len(frame)

        col_consignment = col("consignment_id")
        col_merchant = col("merchant_order_id")
        col_type = col("invoice type")
        col_created = col("created_date")
        col_collected = col("collected_amount")
        col_collectable = col("collectable_amount")
        col_cod_fee = col("cod_fee")
        col_delivery_fee = col("delivery_fee")
        col_final_fee = col("final_fee")
        col_payout = col("payout")

        for pos in range(len(frame)):
            c = _text(col_consignment[pos])
            m = _text(col_merchant[pos])
            t = _text(col_type[pos]).casefold()
            values = [
                c, m, t, col_created[pos], col_collected[pos],
                col_collectable[pos], col_cod_fee[pos],
                col_delivery_fee[pos], col_final_fee[pos], col_payout[pos],
            ]
            conn.execute(
                """INSERT INTO settlement_v8_rows(
                    import_id,row_hash,row_position,consignment_id,consignment_key,
                    merchant_order_id,merchant_key,invoice_type,created_date,
                    collected_amount,collectable_amount,cod_fee,delivery_fee,final_fee,payout
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (import_id, _row_hash(digest, pos, values), pos + 1, c, _key(c), m, _key(m), t,
                 _date_text(values[3]), _money(values[4]), _money(values[5]), _money(values[6]),
                 _money(values[7]), _money(values[8]), _money(values[9])),
            )
        snap = _import_snapshot(conn, import_id) or {}
        snap["already_imported"] = False
        return snap


def list_paid_invoice_imports(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_schema()
    with session() as conn:
        ids = [int(r["id"]) for r in conn.execute("SELECT id FROM settlement_v8_imports ORDER BY id DESC LIMIT ?", (limit,))]
        result = []
        for import_id in ids:
            snap = _import_snapshot(conn, import_id)
            if snap:
                result.append(snap)
        return result


def get_paid_invoice_import(import_id: int) -> dict[str, Any] | None:
    _ensure_schema()
    with session() as conn:
        return _import_snapshot(conn, import_id)


def _live_order_states(conn: sqlite3.Connection) -> tuple[dict[int, dict[str, Any]], int]:
    merchant, consignment = _order_maps(conn)
    states: dict[int, dict[str, Any]] = {}
    unmatched = 0
    for row in conn.execute("SELECT * FROM settlement_v8_rows ORDER BY import_id,row_position,id"):
        if row["invoice_type"] not in FINAL_TYPES:
            continue
        order, _ = _match_row(row, merchant, consignment)
        if not order:
            unmatched += 1
            continue
        oid = int(order["id"])
        state = states.setdefault(oid, {"status": "PENDING", "fee": 0.0, "payout": 0.0, "collected": 0.0})
        state["fee"] += float(row["final_fee"] or 0)
        state["payout"] += float(row["payout"] or 0)
        state["collected"] += float(row["collected_amount"] or 0)
        if row["invoice_type"] == "return":
            state["status"] = "RETURNED"
        elif state["status"] != "RETURNED":
            state["status"] = "DELIVERED"
    return states, unmatched


def _global_counts(conn: sqlite3.Connection) -> dict[str, int]:
    states, _ = _live_order_states(conn)
    return {
        "matched_delivery": sum(1 for s in states.values() if s["status"] == "DELIVERED"),
        "matched_return": sum(1 for s in states.values() if s["status"] == "RETURNED"),
    }


def delete_paid_invoice_import(import_id: int) -> dict[str, Any] | None:
    _ensure_schema()
    with session() as conn:
        snap = _import_snapshot(conn, import_id)
        if not snap:
            return None
        deleted_rows = int(conn.execute("SELECT COUNT(*) n FROM settlement_v8_rows WHERE import_id=?", (import_id,)).fetchone()["n"])
        conn.execute("DELETE FROM settlement_v8_imports WHERE id=?", (import_id,))
        return {
            "invoice_code": snap["invoice_code"],
            "source_file": snap["source_file"],
            "deleted_rows": deleted_rows,
            "reconciliation": _global_counts(conn),
        }


def delete_all_paid_invoice_imports() -> dict[str, Any]:
    _ensure_schema()
    with session() as conn:
        imports = int(conn.execute("SELECT COUNT(*) n FROM settlement_v8_imports").fetchone()["n"])
        rows = int(conn.execute("SELECT COUNT(*) n FROM settlement_v8_rows").fetchone()["n"])
        conn.execute("DELETE FROM settlement_v8_imports")
        return {"deleted_imports": imports, "deleted_rows": rows}


def _parse_order_month(value: Any) -> tuple[int, int] | None:
    parsed = _parse_datetime(value)
    if pd.isna(parsed):
        return None
    return int(parsed.year), int(parsed.month)


def available_settlement_months(limit: int = 24) -> list[tuple[int, int, int]]:
    init_db()
    totals: dict[tuple[int, int], int] = {}
    with session() as conn:
        for row in conn.execute("SELECT order_date FROM orders"):
            ym = _parse_order_month(row["order_date"])
            if ym:
                totals[ym] = totals.get(ym, 0) + 1
    return [(y, m, c) for (y, m), c in sorted(totals.items(), reverse=True)[:limit]]


def detect_order_months(rows: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    totals: dict[tuple[int, int], int] = {}
    for row in rows:
        ym = _parse_order_month(row.get("order_date"))
        if ym:
            totals[ym] = totals.get(ym, 0) + 1
    return [(y, m, c) for (y, m), c in sorted(totals.items(), reverse=True)]


def _summarize(orders: list[sqlite3.Row], states: dict[int, dict[str, Any]], unmatched: int) -> dict[str, Any]:
    products: dict[str, dict[str, Any]] = {}
    total_cod = delivered_cod = return_cod = pending_cod = 0.0
    delivered = returned = pending = 0
    total_charge = matched_payout = matched_collected = 0.0

    for order in orders:
        oid = int(order["id"])
        cod = float(order["cod"] or 0)
        product = str(order["product"] or "Unknown Product")
        state = states.get(oid, {"status": "PENDING", "fee": 0.0, "payout": 0.0, "collected": 0.0})
        status = state["status"]
        total_cod += cod
        p = products.setdefault(product, {"product": product, "delivered": 0, "returned": 0, "pending": 0})
        if status == "RETURNED":
            returned += 1
            return_cod += cod
            p["returned"] += 1
        elif status == "DELIVERED":
            delivered += 1
            delivered_cod += cod
            p["delivered"] += 1
        else:
            pending += 1
            pending_cod += cod
            p["pending"] += 1
        total_charge += float(state["fee"] or 0)
        matched_payout += float(state["payout"] or 0)
        matched_collected += float(state["collected"] or 0)

    expected = round(total_cod - return_cod - total_charge, 2)
    remaining = round(expected - matched_payout, 2)
    return {
        "total_parcels": len(orders),
        "total_cod": round(total_cod, 2),
        "delivered_parcels": delivered,
        "delivered_cod": round(delivered_cod, 2),
        "return_parcels": returned,
        "return_cod": round(return_cod, 2),
        "pending_parcels": pending,
        "pending_cod": round(pending_cod, 2),
        "total_charge": round(total_charge, 2),
        "expected_settlement": expected,
        "matched_payout": round(matched_payout, 2),
        "matched_collected": round(matched_collected, 2),
        "remaining": remaining,
        "unmatched_invoice_rows": unmatched,
        "products": sorted(products.values(), key=lambda x: x["product"].casefold()),
    }


def settlement_summary(year: int | None = None, month: int | None = None) -> dict[str, Any]:
    _ensure_schema()
    with session() as conn:
        states, unmatched = _live_order_states(conn)
        orders = [
            row
            for row in conn.execute("SELECT id,product,cod,courier_charge,order_date FROM orders ORDER BY id")
            if (ym := _parse_order_month(row["order_date"]))
            and (year is None or month is None or ym == (year, month))
        ]
        return _summarize(orders, states, unmatched)


def settlement_summaries(months: list[tuple[int, int]]) -> dict[tuple[int, int], dict[str, Any]]:
    """একবারে অনেক মাসের summary — একটি মাত্র scan-এ।

    আগে central sync প্রতিটি মাসের জন্য আলাদা করে settlement_summary()
    ডাকত, ফলে ১২০ মাসে ১২০ বার পুরো orders + invoice table scan হতো।
    """
    _ensure_schema()
    wanted = set(months)
    with session() as conn:
        states, unmatched = _live_order_states(conn)
        buckets: dict[tuple[int, int], list[sqlite3.Row]] = {ym: [] for ym in wanted}
        for row in conn.execute("SELECT id,product,cod,courier_charge,order_date FROM orders ORDER BY id"):
            ym = _parse_order_month(row["order_date"])
            if ym in buckets:
                buckets[ym].append(row)
        return {ym: _summarize(rows, states, unmatched) for ym, rows in buckets.items()}


def initialize_settlement_system() -> dict[str, Any]:
    backup = _create_backup_once()
    _ensure_schema()
    with session() as conn:
        conn.execute("INSERT OR REPLACE INTO settlement_v8_meta(meta_key,meta_value,updated_at) VALUES('v8_initialized','1',?)", (datetime.now().isoformat(timespec="seconds"),))
    return {"backup": backup, "engine": "v8_live_join", "migrated_rows": 0}
