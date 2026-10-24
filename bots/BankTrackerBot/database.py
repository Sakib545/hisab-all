import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import DATABASE_PATH

DHAKA = ZoneInfo('Asia/Dhaka')


def connect():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _payment_code(number):
    return f"BP-{number:04d}"


def init_db():
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("""
            CREATE TABLE IF NOT EXISTS payment_cycles(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_code TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                payment_month TEXT DEFAULT '',
                started_at TEXT NOT NULL,
                completed_at TEXT DEFAULT ''
            )
        """)
        payment_columns = {
            row[1] for row in c.execute("PRAGMA table_info(payment_cycles)")
        }
        if "payment_month" not in payment_columns:
            c.execute(
                "ALTER TABLE payment_cycles ADD COLUMN payment_month TEXT DEFAULT ''"
            )

        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id INTEGER,
                bank_name TEXT DEFAULT 'Unknown',
                receiver_name TEXT DEFAULT '',
                account_number TEXT DEFAULT '',
                amount REAL NOT NULL DEFAULT 0,
                transaction_date TEXT NOT NULL DEFAULT '',
                transaction_time TEXT DEFAULT '',
                reference_id TEXT DEFAULT '',
                receipt_hash TEXT DEFAULT '',
                remarks TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                raw_text TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(payment_id) REFERENCES payment_cycles(id)
            )
        """)
        columns = {row[1] for row in c.execute("PRAGMA table_info(transactions)")}
        if "receipt_hash" not in columns:
            c.execute("ALTER TABLE transactions ADD COLUMN receipt_hash TEXT DEFAULT ''")
        if "payment_id" not in columns:
            c.execute("ALTER TABLE transactions ADD COLUMN payment_id INTEGER")
        if "telegram_file_id" not in columns:
            c.execute("ALTER TABLE transactions ADD COLUMN telegram_file_id TEXT DEFAULT ''")
        if "telegram_file_unique_id" not in columns:
            c.execute("ALTER TABLE transactions ADD COLUMN telegram_file_unique_id TEXT DEFAULT ''")

        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_reference_nonempty
            ON transactions(reference_id) WHERE TRIM(reference_id) <> ''
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_receipt_hash_nonempty
            ON transactions(receipt_hash) WHERE TRIM(receipt_hash) <> ''
        """)

        # Migrate old PAY-0001 style names to BP-0001 without touching IDs/data.
        for row in c.execute("SELECT id, payment_code FROM payment_cycles ORDER BY id"):
            expected = _payment_code(row["id"])
            if row["payment_code"] != expected:
                c.execute("UPDATE payment_cycles SET payment_code=? WHERE id=?", (expected, row["id"]))

        # Existing payment cycles keep one accounting month.
        # Prefer the earliest receipt date; fall back to cycle start month.
        for payment in c.execute(
            "SELECT id, payment_month, started_at FROM payment_cycles ORDER BY id"
        ).fetchall():
            if str(payment["payment_month"] or "").strip():
                continue
            first_date = c.execute(
                """
                SELECT MIN(NULLIF(TRIM(transaction_date), '')) AS first_date
                FROM transactions WHERE payment_id=?
                """,
                (payment["id"],),
            ).fetchone()["first_date"]
            month = str(first_date or "")[:7]
            if len(month) != 7:
                started = str(payment["started_at"] or "")
                month = started[:7] if len(started) >= 7 else datetime.now(DHAKA).strftime("%Y-%m")
            c.execute(
                "UPDATE payment_cycles SET payment_month=? WHERE id=?",
                (month, payment["id"]),
            )

        active = c.execute(
            "SELECT id FROM payment_cycles WHERE status='ACTIVE' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not active:
            next_id = c.execute("SELECT COALESCE(MAX(id),0)+1 n FROM payment_cycles").fetchone()["n"]
            cur = c.execute(
                "INSERT INTO payment_cycles(payment_code,status,payment_month,started_at) VALUES(?,?,?,?)",
                (
                    _payment_code(next_id),
                    "ACTIVE",
                    datetime.now(DHAKA).strftime("%Y-%m"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            active_id = cur.lastrowid
        else:
            active_id = active["id"]
        c.execute("UPDATE transactions SET payment_id=? WHERE payment_id IS NULL", (active_id,))
        c.execute("""
            CREATE TABLE IF NOT EXISTS schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        c.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('schema_version','6')")
        c.execute("""
            CREATE TABLE IF NOT EXISTS activity_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def get_active_payment():
    with connect() as c:
        return c.execute("""
            SELECT p.*, COUNT(t.id) AS transaction_count,
                   COALESCE(SUM(t.amount),0) AS total_amount
            FROM payment_cycles p
            LEFT JOIN transactions t ON t.payment_id=p.id
            WHERE p.status='ACTIVE'
            GROUP BY p.id ORDER BY p.id DESC LIMIT 1
        """).fetchone()


def add_transaction(d):
    required = ("transaction_date", "transaction_time", "account_number", "amount")
    if any(not d.get(key) for key in required):
        raise ValueError("Date, time, receiver account and amount are required")
    active = get_active_payment()
    if not active:
        raise RuntimeError("No active payment cycle")
    try:
        with connect() as c:
            cur = c.execute("""
                INSERT INTO transactions(
                    payment_id, bank_name, receiver_name, account_number, amount,
                    transaction_date, transaction_time, reference_id,
                    receipt_hash, remarks, source_file, raw_text,
                    telegram_file_id, telegram_file_unique_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                active["id"], d.get("bank_name", "Unknown"), d.get("receiver_name", ""),
                d.get("account_number", ""), float(d.get("amount", 0) or 0),
                d.get("transaction_date", ""), d.get("transaction_time", ""),
                d.get("reference_id", ""), d.get("receipt_hash", ""),
                d.get("remarks", ""), d.get("source_file", ""), d.get("raw_text", ""),
                d.get("telegram_file_id", ""), d.get("telegram_file_unique_id", ""),
            ))
            return True, cur.lastrowid, active["payment_code"]
    except sqlite3.IntegrityError:
        return False, None, active["payment_code"]


def complete_active_payment():
    with connect() as c:
        current = c.execute("""
            SELECT p.*, COUNT(t.id) transaction_count, COALESCE(SUM(t.amount),0) total_amount
            FROM payment_cycles p LEFT JOIN transactions t ON t.payment_id=p.id
            WHERE p.status='ACTIVE' GROUP BY p.id ORDER BY p.id DESC LIMIT 1
        """).fetchone()
        if not current:
            return None, None
        c.execute("UPDATE payment_cycles SET status='COMPLETED', completed_at=? WHERE id=?",
                  (datetime.now(timezone.utc).isoformat(), current["id"]))
        next_id = c.execute("SELECT COALESCE(MAX(id),0)+1 n FROM payment_cycles").fetchone()["n"]
        cur = c.execute(
            "INSERT INTO payment_cycles(payment_code,status,payment_month,started_at) VALUES(?,?,?,?)",
            (
                _payment_code(next_id),
                "ACTIVE",
                datetime.now(DHAKA).strftime("%Y-%m"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        new_cycle = c.execute("SELECT * FROM payment_cycles WHERE id=?", (cur.lastrowid,)).fetchone()
        return current, new_cycle



def set_active_payment_month(month):
    month = str(month or "").strip()
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Month format must be YYYY-MM") from exc
    with connect() as c:
        active = c.execute(
            "SELECT id, payment_code FROM payment_cycles "
            "WHERE status='ACTIVE' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not active:
            raise RuntimeError("No active payment cycle")
        c.execute(
            "UPDATE payment_cycles SET payment_month=? WHERE id=?",
            (month, active["id"]),
        )
        return active["payment_code"], month


def set_payment_month(payment_code, month):
    month = str(month or "").strip()
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Month format must be YYYY-MM") from exc
    with connect() as c:
        row = c.execute(
            "SELECT id, payment_code FROM payment_cycles "
            "WHERE UPPER(payment_code)=UPPER(?)",
            (payment_code,),
        ).fetchone()
        if not row:
            raise ValueError("Payment cycle not found")
        c.execute(
            "UPDATE payment_cycles SET payment_month=? WHERE id=?",
            (month, row["id"]),
        )
        return row["payment_code"], month


def list_payments():
    with connect() as c:
        return list(c.execute("""
            SELECT p.*, COUNT(t.id) transaction_count, COALESCE(SUM(t.amount),0) total_amount
            FROM payment_cycles p LEFT JOIN transactions t ON t.payment_id=p.id
            GROUP BY p.id ORDER BY p.id DESC
        """))


def payment_by_code(code):
    with connect() as c:
        return c.execute("""
            SELECT p.*, COUNT(t.id) transaction_count, COALESCE(SUM(t.amount),0) total_amount
            FROM payment_cycles p LEFT JOIN transactions t ON t.payment_id=p.id
            WHERE UPPER(p.payment_code)=UPPER(?) GROUP BY p.id
        """, (code,)).fetchone()


def rows_for_payment(code):
    with connect() as c:
        return list(c.execute("""
            SELECT t.*, p.payment_code, p.payment_month FROM transactions t
            JOIN payment_cycles p ON p.id=t.payment_id
            WHERE UPPER(p.payment_code)=UPPER(?) ORDER BY t.transaction_date, t.transaction_time, t.id
        """, (code,)))


def rows_for_date(day):
    with connect() as c:
        return list(c.execute("""
            SELECT t.*, p.payment_code, p.payment_month FROM transactions t
            LEFT JOIN payment_cycles p ON p.id=t.payment_id
            WHERE t.transaction_date=? ORDER BY t.transaction_time, t.id
        """, (day,)))


def rows_for_month(month):
    with connect() as c:
        return list(c.execute("""
            SELECT t.*, p.payment_code, p.payment_month FROM transactions t
            LEFT JOIN payment_cycles p ON p.id=t.payment_id
            WHERE substr(t.transaction_date,1,7)=? ORDER BY t.transaction_date, t.transaction_time, t.id
        """, (month,)))


def all_rows():
    with connect() as c:
        return list(c.execute("""
            SELECT t.*, p.payment_code, p.payment_month FROM transactions t
            LEFT JOIN payment_cycles p ON p.id=t.payment_id
            ORDER BY p.id, t.transaction_date, t.transaction_time, t.id
        """))


def search_rows(term):
    q = f"%{term}%"
    with connect() as c:
        return list(c.execute("""
            SELECT t.*, p.payment_code, p.payment_month FROM transactions t
            LEFT JOIN payment_cycles p ON p.id=t.payment_id
            WHERE t.account_number LIKE ? OR t.reference_id LIKE ?
               OR t.transaction_date LIKE ? OR CAST(t.amount AS TEXT) LIKE ?
               OR p.payment_code LIKE ?
            ORDER BY t.id DESC LIMIT 100
        """, (q, q, q, q, q)))


def total_summary():
    with connect() as c:
        row = c.execute("SELECT COUNT(*) n, COALESCE(SUM(amount),0) t FROM transactions").fetchone()
        return row["n"], row["t"]


def delete_row(row_id):
    with connect() as c:
        return c.execute("DELETE FROM transactions WHERE id=?", (row_id,)).rowcount > 0


def delete_all_rows():
    with connect() as c:
        return c.execute("DELETE FROM transactions").rowcount


def update_parsed_fields(row_id, transaction_date, transaction_time, account_number, bank_name):
    with connect() as c:
        c.execute("""
            UPDATE transactions SET transaction_date=?, transaction_time=?,
                account_number=?, bank_name=? WHERE id=?
        """, (transaction_date, transaction_time, account_number, bank_name, row_id))


def update_source_file(row_id, source_file):
    with connect() as c:
        c.execute("UPDATE transactions SET source_file=? WHERE id=?", (str(source_file), row_id))


def rows_needing_repair():
    with connect() as c:
        return list(c.execute("""
            SELECT t.*, p.payment_code, p.payment_month FROM transactions t
            LEFT JOIN payment_cycles p ON p.id=t.payment_id
            WHERE TRIM(COALESCE(t.transaction_date,''))=''
               OR TRIM(COALESCE(t.transaction_time,''))=''
               OR TRIM(COALESCE(t.account_number,''))=''
            ORDER BY t.id
        """))


def update_transaction_repair(row_id, parsed, source_file=None):
    with connect() as c:
        current = c.execute("SELECT * FROM transactions WHERE id=?", (row_id,)).fetchone()
        if not current:
            return False
        date_value = parsed.get("transaction_date") or current["transaction_date"]
        time_value = parsed.get("transaction_time") or current["transaction_time"]
        account = parsed.get("account_number") or current["account_number"]
        amount = float(parsed.get("amount") or current["amount"] or 0)
        bank_name = parsed.get("bank_name") or current["bank_name"]
        reference_id = parsed.get("reference_id") or current["reference_id"]
        raw_text = parsed.get("raw_text") or current["raw_text"]
        path_value = str(source_file) if source_file else current["source_file"]
        c.execute("""
            UPDATE transactions SET transaction_date=?, transaction_time=?,
                account_number=?, amount=?, bank_name=?, reference_id=?,
                raw_text=?, source_file=? WHERE id=?
        """, (date_value, time_value, account, amount, bank_name, reference_id, raw_text, path_value, row_id))
        return True


def create_database_snapshot(destination):
    """Create a consistent SQLite snapshot, including any WAL changes."""
    destination = str(destination)
    with connect() as source:
        source.execute("PRAGMA wal_checkpoint(FULL)")
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
            target.execute("PRAGMA integrity_check")
            target.commit()
        finally:
            target.close()
    return destination


def validate_database_file(path):
    conn = sqlite3.connect(str(path))
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        required = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return result == "ok" and {"transactions", "payment_cycles"}.issubset(required)
    finally:
        conn.close()


def log_activity(action, details=""):
    with connect() as c:
        c.execute("INSERT INTO activity_log(action,details) VALUES(?,?)", (str(action), str(details)))

def recent_activity(limit=30):
    with connect() as c:
        return list(c.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (int(limit),)))

def reopen_payment(code):
    with connect() as c:
        target = c.execute("SELECT * FROM payment_cycles WHERE UPPER(payment_code)=UPPER(?)", (code,)).fetchone()
        if not target:
            return False, "Payment not found"
        if target["status"] == "ACTIVE":
            return True, target["payment_code"]
        active = c.execute("SELECT * FROM payment_cycles WHERE status='ACTIVE' ORDER BY id DESC LIMIT 1").fetchone()
        if active:
            c.execute("UPDATE payment_cycles SET status='COMPLETED', completed_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), active["id"]))
        c.execute("UPDATE payment_cycles SET status='ACTIVE', completed_at='' WHERE id=?", (target["id"],))
        return True, target["payment_code"]

def get_transaction(row_id):
    with connect() as c:
        return c.execute("""SELECT t.*, p.payment_code, p.payment_month FROM transactions t LEFT JOIN payment_cycles p ON p.id=t.payment_id WHERE t.id=?""", (row_id,)).fetchone()

def analytics_summary():
    with connect() as c:
        totals=c.execute("SELECT COUNT(*) n, COALESCE(SUM(amount),0) total, COALESCE(AVG(amount),0) avg FROM transactions").fetchone()
        top=c.execute("""SELECT account_number, COUNT(*) n, COALESCE(SUM(amount),0) total FROM transactions WHERE TRIM(account_number)<>'' GROUP BY account_number ORDER BY total DESC LIMIT 5""").fetchall()
        banks=c.execute("""SELECT bank_name, COUNT(*) n, COALESCE(SUM(amount),0) total FROM transactions GROUP BY bank_name ORDER BY total DESC""").fetchall()
        payments=c.execute("SELECT COUNT(*) n FROM payment_cycles").fetchone()["n"]
        return totals, list(top), list(banks), payments
