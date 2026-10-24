
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime

def flush_pending_central() -> dict[str, Any]:
    return flush_snapshot("Dollar_Payments", _replace_tab_online)

from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from central_offline import flush_snapshot, sync_snapshot

from config import BASE_DIR, DATA_DIR, DATABASE_PATH

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = [
    "Source ID", "Payment Code", "Payment Month", "Date", "Time", "Bank", "Receiver",
    "Account", "Amount", "Reference", "Remarks", "Updated At",
]


def enabled() -> bool:
    return bool(
        os.getenv("CENTRAL_SHEET_ID", "").strip()
        and (
            os.getenv("CENTRAL_GOOGLE_CREDENTIALS_JSON", "").strip()
            or os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
        )
    )


def _book():
    sid = os.getenv("CENTRAL_SHEET_ID", "").strip()
    raw = (
        os.getenv("CENTRAL_GOOGLE_CREDENTIALS_JSON", "").strip()
        or os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    )
    if not sid or not raw:
        raise RuntimeError("CENTRAL_SHEET_ID / credentials missing")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(sid)


def _retry(fn, *args, attempts=3, **kwargs):
    last = None
    for index in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last = exc
            if index + 1 < attempts:
                time.sleep(index + 1)
    raise last


def _column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _ws(title: str, headers: list[str]):
    book = _retry(_book)
    try:
        ws = book.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=title, rows=2000, cols=max(10, len(headers)))
    if ws.row_values(1)[: len(headers)] != headers:
        ws.clear()
        ws.update(
            range_name=f"A1:{_column_letter(len(headers))}1",
            values=[headers],
        )
    try:
        ws.freeze(rows=1)
    except Exception:
        pass
    return ws


def _touch(source: str, count: int):
    headers = ["Source", "Last Sync", "Rows"]
    ws = _ws("Sync_Status", headers)
    values = ws.get_all_values()
    now = datetime.now().isoformat(timespec="seconds")
    found = None
    for idx, row in enumerate(values[1:], start=2):
        if row and row[0] == source:
            found = idx
            break
    if found:
        ws.update(
            range_name=f"A{found}:C{found}",
            values=[[source, now, count]],
        )
    else:
        ws.append_row([source, now, count], value_input_option="USER_ENTERED")


def _replace_tab_online(title: str, headers: list[str], rows: list[list[Any]]) -> int:
    if not enabled():
        raise RuntimeError("Central Sheet variables are missing")
    ws = _ws(title, headers)
    ws.clear()
    ws.update(
        range_name=f"A1:{_column_letter(len(headers))}1",
        values=[headers],
    )
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    _touch(title, len(rows))
    return len(rows)


def _candidate_databases() -> list[Path]:
    candidates: list[Path] = []

    explicit = os.getenv("DATABASE_PATH", "").strip()
    if explicit:
        candidates.append(Path(explicit))

    candidates.extend(
        [
            Path(DATABASE_PATH),
            Path(DATA_DIR) / "transactions.db",
            Path(DATA_DIR) / "bot_data.db",
            Path(DATA_DIR) / "banktracker.db",
            Path(BASE_DIR) / "transactions.db",
            Path(BASE_DIR) / "bot_data.db",
        ]
    )

    for root in {
        Path(DATA_DIR),
        Path(BASE_DIR),
        Path("/data"),
        Path("/app"),
    }:
        if not root.exists():
            continue
        try:
            for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
                candidates.extend(root.rglob(pattern))
        except (PermissionError, OSError):
            continue

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _inspect_database(path: Path) -> tuple[int, float]:
    if not path.is_file():
        return (0, 0.0)
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "transactions" not in tables:
            connection.close()
            return (0, 0.0)
        row = connection.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS total "
            "FROM transactions"
        ).fetchone()
        connection.close()
        return (int(row["n"] or 0), float(row["total"] or 0))
    except (sqlite3.Error, OSError):
        return (0, 0.0)


def find_source_database() -> tuple[Path, int, float]:
    inspected: list[tuple[int, float, Path]] = []
    for path in _candidate_databases():
        count, total = _inspect_database(path)
        if count or path == Path(DATABASE_PATH):
            inspected.append((count, total, path))

    if not inspected:
        raise RuntimeError(
            f"কোনো BankTracker database পাওয়া যায়নি। Expected: {DATABASE_PATH}"
        )

    inspected.sort(key=lambda item: (item[0], item[1]), reverse=True)
    count, total, path = inspected[0]
    return path, count, total


def _read_rows(path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=20)
    connection.row_factory = sqlite3.Row

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    has_cycles = "payment_cycles" in tables
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(transactions)")
    }

    payment_id_expr = "t.payment_id" if "payment_id" in columns else "NULL"
    if has_cycles and "payment_id" in columns:
        query = """
            SELECT t.*,
                   COALESCE(p.payment_code, '') AS payment_code,
                   COALESCE(p.payment_month, '') AS payment_month
            FROM transactions t
            LEFT JOIN payment_cycles p ON p.id=t.payment_id
            ORDER BY t.id
        """
    else:
        query = """
            SELECT t.*, '' AS payment_code, '' AS payment_month
            FROM transactions t
            ORDER BY t.id
        """

    rows = list(connection.execute(query))
    connection.close()
    return rows


def sync_bank_snapshot() -> dict[str, Any]:
    source_path, source_count, source_total = find_source_database()
    source_rows = _read_rows(source_path)

    now = datetime.now().isoformat(timespec="seconds")
    rows: list[list[Any]] = []
    for row in source_rows:
        keys = set(row.keys())
        rows.append(
            [
                f"BANK-{row['id']}",
                row["payment_code"] if "payment_code" in keys else "",
                row["payment_month"] if "payment_month" in keys else "",
                row["transaction_date"] if "transaction_date" in keys else "",
                row["transaction_time"] if "transaction_time" in keys else "",
                row["bank_name"] if "bank_name" in keys else "",
                row["receiver_name"] if "receiver_name" in keys else "",
                row["account_number"] if "account_number" in keys else "",
                float(row["amount"] or 0),
                row["reference_id"] if "reference_id" in keys else "",
                row["remarks"] if "remarks" in keys else "",
                now,
            ]
        )

    result = sync_snapshot(
        "Dollar_Payments", "Dollar_Payments", HEADERS, rows, _replace_tab_online
    )
    return {
        "synced": int(result.get("synced") or 0),
        "queued": bool(result.get("queued")),
        "pending": int(result.get("pending") or 0),
        "sync_error": result.get("error") or "",
        "source_count": source_count,
        "source_total": source_total,
        "source_path": str(source_path),
    }
