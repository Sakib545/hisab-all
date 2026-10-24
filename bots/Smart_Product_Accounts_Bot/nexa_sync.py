"""
nexa_sync.py — Python Telegram bot ↔ Nexa Hisab.
শুধু Python standard library লাগে (pip install লাগে না)।

ENV (Nexa Hisab → Telegram bots → Connect a bot থেকে কপি করুন):
  NEXA_URL      https://your-nexa-hisab-domain
  NEXA_TOKEN    nxh_...   (প্রতিটা bot-এর নিজস্ব key)
  NEXA_OUTBOX   optional, default ./nexa_outbox.db  (Railway/Render-এ volume path দিন)

তিনভাবে ব্যবহার:
  1) একটা একটা record:      nexa.record(id="R-77", title="…", amount=1250.5, ledger="expense")
  2) পুরো table mirror:      nexa.sync_snapshot("order", rows)   # শুধু বদলানো row যায়, মুছে ফেলা row site থেকেও মোছে
  3) site থেকে আসা কাজ:      nexa.run_commands({"complete_payment": fn, ...})

Command line:
  python nexa_sync.py test | status | flush
  python nexa_sync.py import-sqlite bot.db payments [--ledger expense --account Pubali]

App down থাকলে record হারায় না: local outbox-এ থাকে, পরে পাঠায়।
"""
import argparse, base64, hashlib, json, os, re, sqlite3, sys, threading, time, urllib.error, urllib.request

BATCH = 20  # small batches stay under Cloudflare D1's per-request query limit (free plan)
LEDGER_TYPES = ("income", "expense", "receivable", "payable")


def _hash(rec):
    return hashlib.sha1(json.dumps(rec, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:20]


class NexaSync:
    def __init__(self, url=None, token=None, outbox_path=None, timeout=30, bot=None):
        self.base = (url or os.environ["NEXA_URL"]).rstrip("/")
        self.url = self.base + "/api/bot/ingest"
        self.token = token or os.environ.get("NEXA_TOKEN") or os.environ["NEXA_SYNC_TOKEN"]
        self.bot = bot or os.environ.get("NEXA_BOT_NAME")  # only needed with the shared master token
        self.timeout = timeout
        self._lock = threading.RLock()
        self._checked_server = False
        path = outbox_path or os.environ.get("NEXA_OUTBOX") or os.environ.get("NEXA_OUTBOX_PATH", "nexa_outbox.db")
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                attempts INTEGER DEFAULT 0, last_error TEXT, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS rejected(id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                error TEXT, rejected_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sent(kind TEXT NOT NULL, id TEXT NOT NULL, hash TEXT NOT NULL,
                PRIMARY KEY(kind, id));
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self._db.commit()

    # ---- records ------------------------------------------------------------
    def record(self, id, title="", amount=None, at=None, kind="", status="", data=None,
               ledger=None, account="", category="", party="", note="", send=True):
        """যেকোনো bot data পাঠায়।
        id: bot-এর নিজস্ব unique id · amount: টাকায় · at: 'YYYY-MM-DD' / ISO / unix
        ledger: 'expense'/'income'/… দিলে Transactions-এও যোগ হয় · data: যেকোনো extra dict"""
        rec = {"id": str(id), "title": str(title or ""), "kind": kind, "status": str(status or ""),
               "data": data or {}}
        if amount not in (None, ""):
            rec["amount"] = str(amount)
        if at not in (None, ""):
            rec["at"] = str(at)
        if ledger:
            if ledger not in LEDGER_TYPES:
                raise ValueError(f"ledger must be one of {LEDGER_TYPES}")
            rec["ledger"] = {"type": ledger, "account": account, "category": category,
                             "party": party or title, "note": note}
        rec["hash"] = _hash(rec)
        with self._lock:
            self._db.execute("DELETE FROM rejected WHERE id=?", (rec["id"],))
            self._db.execute("INSERT OR REPLACE INTO outbox(id,payload,created_at) VALUES(?,?,?)",
                             (rec["id"], json.dumps(rec, ensure_ascii=False, default=str), time.time()))
            self._db.commit()
        return self.flush() if send else None

    def send(self, id, type, amount, date, category="", party="", account="", note=""):
        """v1 compatibility (ledger entry)."""
        return self.record(id=id, title=party or category, amount=amount, at=date, kind="payment",
                           ledger=type, account=account, category=category, party=party, note=note)

    def queue(self, **kw):
        return self.send(**kw) if "type" in kw else self.record(send=False, **kw)

    def flush(self):
        """Outbox পাঠায়। Exception ছোঁড়ে না। return {'created','updated','duplicate','failed','pending'}"""
        out = {"created": 0, "updated": 0, "duplicate": 0, "failed": 0}
        with self._lock:
            rows = self._db.execute("SELECT id,payload FROM outbox ORDER BY created_at").fetchall()
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            recs = [json.loads(p) for _, p in chunk]
            body = {"records": recs, "upsert": True}
            if self.bot:
                body["bot"] = self.bot
            try:
                res = self._req("POST", "/api/bot/ingest", body)
            except Exception as e:
                with self._lock:
                    self._db.executemany("UPDATE outbox SET attempts=attempts+1,last_error=? WHERE id=?",
                                         [(str(e)[:300], r[0]) for r in chunk])
                    self._db.commit()
                out["error"] = str(e)[:300]
                break
            by_id = {r["id"]: r for r in recs}
            with self._lock:
                for r in res.get("results", []):
                    rec = by_id.get(r["id"])
                    if r["status"] in ("created", "updated", "duplicate"):
                        self._db.execute("DELETE FROM outbox WHERE id=?", (r["id"],))
                        if rec and rec.get("kind"):
                            self._db.execute("INSERT OR REPLACE INTO sent(kind,id,hash) VALUES(?,?,?)",
                                             (rec["kind"], rec["id"], rec["hash"]))
                        out[r["status"]] += 1
                    else:  # data problem: retrying won't help → move to rejected
                        self._db.execute("INSERT OR REPLACE INTO rejected(id,payload,error,rejected_at) "
                                         "SELECT id,payload,?,? FROM outbox WHERE id=?",
                                         (r.get("error", "")[:300], time.time(), r["id"]))
                        self._db.execute("DELETE FROM outbox WHERE id=?", (r["id"],))
                        out["failed"] += 1
                self._db.commit()
        out["pending"] = self.pending()
        return out

    # ---- mirror a whole table ---------------------------------------------------
    def sync_snapshot(self, kind, records, allow_empty=False, force=False):
        """Bot-এর ওই ধরনের *সব* record দিন। শুধু নতুন/বদলানো record পাঠানো হয়;
        bot-এ যেগুলো আর নেই সেগুলো Nexa Hisab থেকেও মুছে যায় (ওই bot-এর ledger entry সহ)।"""
        records = list(records)
        if not records and not allow_empty:
            return {"skipped": "empty snapshot — nothing removed (read error?)"}
        if not self._checked_server:
            self._verify_server_copy()
        if force:
            with self._lock:
                self._db.execute("DELETE FROM sent WHERE kind=?", (kind,))
                self._db.commit()
        with self._lock:
            known = dict(self._db.execute("SELECT id,hash FROM sent WHERE kind=?", (kind,)).fetchall())
        changed = 0
        for r in records:
            r = dict(r, kind=kind)
            preview = dict(r)
            preview.pop("send", None)
            rec_hash = _hash(self._shape(**preview))
            if known.get(str(r["id"])) != rec_hash:
                self.record(send=False, **{k: v for k, v in r.items() if k != "send"})
                changed += 1
        out = self.flush() if changed else {"created": 0, "updated": 0, "duplicate": 0, "failed": 0, "pending": self.pending()}
        out["changed"] = changed
        if out.get("error"):
            return out
        ids = sorted(str(r["id"]) for r in records)
        id_hash = hashlib.sha1("\n".join(ids).encode()).hexdigest()
        meta_key = f"ids:{kind}"
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key=?", (meta_key,)).fetchone()
        out["removed"] = 0
        if force or not row or row[0] != id_hash or len(known) > len(ids):
            if ids:
                res = self._req("POST", "/api/bot/reconcile", {"kind": kind, "ids": ids, **({"bot": self.bot} if self.bot else {})})
                out["removed"] = res.get("removed", 0)
            with self._lock:
                keep = set(ids)
                gone = [k for k in known if k not in keep]
                self._db.executemany("DELETE FROM sent WHERE kind=? AND id=?", [(kind, g) for g in gone])
                self._db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (meta_key, id_hash))
                self._db.commit()
        return out

    @staticmethod
    def _shape(id, title="", amount=None, at=None, kind="", status="", data=None, ledger=None,
               account="", category="", party="", note=""):
        rec = {"id": str(id), "title": str(title or ""), "kind": kind, "status": str(status or ""), "data": data or {}}
        if amount not in (None, ""):
            rec["amount"] = str(amount)
        if at not in (None, ""):
            rec["at"] = str(at)
        if ledger:
            rec["ledger"] = {"type": ledger, "account": account, "category": category,
                             "party": party or title, "note": note}
        return rec

    def _verify_server_copy(self):
        """Site-এর database reset হলে local 'already sent' তালিকা মুছে সব আবার পাঠানো হয়।"""
        try:
            info = self.ping()
            with self._lock:
                local = self._db.execute("SELECT count(*) FROM sent").fetchone()[0]
                if info.get("synced", 0) < local * 0.9:
                    self._db.execute("DELETE FROM sent")
                    self._db.execute("DELETE FROM meta WHERE key LIKE 'ids:%'")
                    self._db.commit()
            self._checked_server = True
        except Exception:
            pass

    # ---- commands from the site -------------------------------------------------
    def fetch_commands(self):
        q = f"?bot={self.bot}" if self.bot else ""
        return self._req("GET", "/api/bot/commands" + q).get("commands", [])

    def finish_command(self, cmd_id, ok, result):
        body = {"id": cmd_id, "ok": bool(ok), "result": result}
        if self.bot:
            body["bot"] = self.bot
        self._req("POST", "/api/bot/commands", body)

    def run_commands(self, handlers, after=None):
        """handlers: {action: fn(payload: dict, file: (name, bytes) | None) -> dict}
        after: optional fn() run after commands (e.g. snapshot sync) before results are reported,
        so the site sees updated data as soon as the command shows 'done'.
        Returns the list of (command, ok, result) for the caller (e.g. to notify Telegram)."""
        try:
            cmds = self.fetch_commands()
        except Exception:
            return []
        done = []
        for c in cmds:
            fn = handlers.get(c["action"])
            file = None
            if c.get("file_data"):
                file = (c.get("file_name") or "upload", base64.b64decode(c["file_data"]))
            try:
                if not fn:
                    raise ValueError(f"এই bot '{c['action']}' কাজ চেনে না — bot update করুন।")
                result = fn(c.get("payload") or {}, file) or {}
                done.append((c, True, result))
            except Exception as e:
                done.append((c, False, {"error": f"{type(e).__name__}: {e}"[:1000]}))
        if done and after:
            try:
                after()
            except Exception:
                pass
        for c, ok, result in done:
            try:
                public = {k: v for k, v in result.items() if not str(k).startswith("_")} if isinstance(result, dict) else result
                self.finish_command(c["id"], ok, _jsonable(public))
            except Exception:
                pass
        return done

    # ---- status -----------------------------------------------------------------
    def pending(self):
        with self._lock:
            return self._db.execute("SELECT count(*) FROM outbox").fetchone()[0]

    def errors(self, limit=20):
        with self._lock:
            return self._db.execute("SELECT id,error FROM rejected ORDER BY rejected_at DESC LIMIT ?",
                                    (limit,)).fetchall()

    def last_network_error(self):
        with self._lock:
            r = self._db.execute("SELECT last_error FROM outbox WHERE last_error IS NOT NULL "
                                 "ORDER BY created_at DESC LIMIT 1").fetchone()
        return r[0] if r else None

    def ping(self):
        q = f"?bot={self.bot}" if self.bot else ""
        return self._req("GET", "/api/bot/ingest" + q)

    def start_background_flush(self, every_seconds=300):
        def loop():
            while True:
                time.sleep(every_seconds)
                if self.pending():
                    try:
                        self.flush()
                    except Exception:
                        pass
        threading.Thread(target=loop, daemon=True).start()

    def _req(self, method, path, body=None):
        data = json.dumps(body, ensure_ascii=False, default=str).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json",
                                              "User-Agent": "nexa-sync/3"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read()[:300].decode(errors="ignore")
            raise RuntimeError("Key ভুল বা মুছে ফেলা হয়েছে (401)" if e.code == 401 else f"HTTP {e.code}: {msg}")


def _jsonable(v):
    return json.loads(json.dumps(v, ensure_ascii=False, default=str))


def start_background_flush(sync, every_seconds=300):  # v1 compatibility
    sync.start_background_flush(every_seconds)


# ---- SQLite import (old bot data) ---------------------------------------------
GUESS = {
    "id": r"^(id|ref|reference|txn|trx|transaction_?id|receipt_?id|order_?id)$",
    "date": r"(date|time|created|timestamp)",
    "amount": r"(amount|total|taka|tk|bdt|price)",
    "title": r"(name|title|receiver|party|customer|description|details|purpose|bank)",
    "status": r"^(status|state)$",
}


def guess_columns(cols):
    picked = {}
    for key, pat in GUESS.items():
        picked[key] = next((c for c in cols if re.search(pat, c, re.I) and c not in picked.values()), None)
    return picked


def import_sqlite(nexa, db_path, table, ledger=None, account="", kind="import", **override):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
    if not cols:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        raise SystemExit(f"Table '{table}' পাওয়া যায়নি। এই database-এ আছে: {', '.join(tables)}")
    m = guess_columns(cols)
    m.update({k: v for k, v in override.items() if v})
    print("Columns:", ", ".join(cols))
    print("Using  :", ", ".join(f"{k}={v or '—'}" for k, v in m.items()))
    id_expr = f'"{m["id"]}"' if m["id"] and m["id"] != "rowid" else "rowid"
    n = 0
    for row in con.execute(f'SELECT {id_expr} AS __id, * FROM "{table}"'):
        d = {k: row[k] for k in row.keys() if k != "__id" and row[k] is not None}
        amt = row[m["amount"]] if m["amount"] else None
        nexa.record(id=f"{table}-{row['__id']}", title=str(row[m["title"]]) if m["title"] and row[m["title"]] else "",
                    amount=amt if amt not in (None, "", 0) else None, at=row[m["date"]] if m["date"] else None,
                    status=str(row[m["status"]]) if m["status"] and row[m["status"]] else "", kind=kind, data=d,
                    ledger=ledger if ledger and amt not in (None, "", 0) else None, account=account, send=False)
        n += 1
    print(f"{n} rows queued. Sending…")
    res = nexa.flush()
    print(f"Done: {res['created']} new, {res['duplicate']} already there, {res['failed']} rejected, {res['pending']} still pending")
    for e in nexa.errors(5):
        print("  ✗", e[0], "→", e[1])


def main():
    ap = argparse.ArgumentParser(description="Nexa Hisab bot sync")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("test"); sub.add_parser("status"); sub.add_parser("flush")
    imp = sub.add_parser("import-sqlite")
    imp.add_argument("db"); imp.add_argument("table")
    imp.add_argument("--ledger", choices=LEDGER_TYPES); imp.add_argument("--account", default="")
    imp.add_argument("--kind", default="import")
    for c in ("id", "date", "amount", "title", "status"):
        imp.add_argument(f"--{c}")
    a = ap.parse_args()
    nexa = NexaSync()
    if a.cmd == "test":
        try:
            r = nexa.ping()
            print(f"✅ Connected as '{r['bot']}' · {r['synced']} records stored")
        except Exception as e:
            sys.exit(f"❌ {e}")
    elif a.cmd == "status":
        print(f"waiting to send: {nexa.pending()}" + (f"  (last problem: {nexa.last_network_error()})" if nexa.pending() else ""))
        rej = nexa.errors()
        print(f"rejected by server: {len(rej)}")
        for e in rej:
            print("  ✗", e[0], "→", e[1])
    elif a.cmd == "flush":
        print(nexa.flush())
    else:
        import_sqlite(nexa, a.db, a.table, a.ledger, a.account, a.kind,
                      id=a.id, date=a.date, amount=a.amount, title=a.title, status=a.status)


if __name__ == "__main__":
    main()
