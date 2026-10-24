"""
হাতে লেখা (manual) entry ও Cash Deposit Slip.

হাতের লেখা Tesseract নির্ভরযোগ্যভাবে পড়তে পারে না, তাই deposit slip-এর amount
ব্যবহারকারী লিখে দেন; ছবিটা receipt হিসেবে সাথে থাকে। ছবি ছাড়াও শুধু লিখে entry করা যায়:

    1000
    100000 0220249853811
    100000 0220249853811 13/10/2026 IFIC Rahim
    ৳১,০০,০০০ 13/10/26 cash deposit

প্রথম সংখ্যা = amount। বাকি যেকোনো ক্রমে: account নম্বর (৬+ digit), তারিখ, bank, নাম/নোট।
"""
import re
from datetime import date, datetime

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
BANKS = {"ific": "IFIC", "pubali": "PUBALI", "bkash": "bKash", "nagad": "Nagad", "rocket": "Rocket", "cash": "CASH",
         "dbbl": "DBBL", "dutch": "DBBL", "brac": "BRAC", "city": "City", "islami": "Islami", "sonali": "Sonali"}
AMOUNT_RE = re.compile(r"^৳?\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:/-|tk|taka|টাকা|bdt)?$", re.I)

SLIP_CUES = ("deposit slip", "deposit branch", "cash denominations", "depositor", "cash received",
             "customer copy", "in words", "drawee bank", "a/c with branch")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(BN_DIGITS)).strip()


def is_deposit_slip(ocr_text: str) -> bool:
    low = (ocr_text or "").lower()
    return sum(cue in low for cue in SLIP_CUES) >= 2


def slip_hints(ocr_text: str) -> dict:
    """Printed/stamped parts OCR can sometimes catch. Only shown as hints — never saved without the user."""
    t = (ocr_text or "").translate(BN_DIGITS)
    hints = {}
    m = re.search(r"\b([0-3]?\d)\s*[-/. ]?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*[-/. ]?\s*(20\d\d)\b", t, re.I)
    if m:
        try:
            hints["date"] = date(int(m.group(3)), MONTHS[m.group(2).lower()[:3]], int(m.group(1))).isoformat()
        except ValueError:
            pass
    acc = re.search(r"\b(\d[\d -]{9,24}\d)\b", t)
    if acc and len(re.sub(r"\D", "", acc.group(1))) >= 10:
        hints["account"] = re.sub(r"\D", "", acc.group(1))
    if "ific" in t.lower():
        hints["bank"] = "IFIC"
    elif "pubali" in t.lower():
        hints["bank"] = "PUBALI"
    return hints


def parse_amount(token: str):
    m = AMOUNT_RE.match(normalize(token))
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    return value if 0 < value < 1_000_000_000 else None


def parse_date(token: str, today: date):
    t = normalize(token).lower()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", t)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            y = int(m.group(3)) if m.group(3) else today.year
            if y < 100:
                y += 2000
        else:
            m = re.fullmatch(r"(\d{1,2})[-/ ]?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:[-/ ]?(\d{2,4}))?", t)
            if not m:
                return None
            d, mo = int(m.group(1)), MONTHS[m.group(2)[:3]]
            y = int(m.group(3)) if m.group(3) else today.year
            if y < 100:
                y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def looks_manual(text: str) -> bool:
    """Message starts with an amount → treat as a manual entry."""
    first = normalize(text).split(" ", 1)[0] if text else ""
    return parse_amount(first) is not None


def parse_manual(text: str, today: date | None = None) -> dict:
    """Returns {'amount','date','account','bank','note'} or raises ValueError with a Bangla message."""
    today = today or date.today()
    tokens = normalize(text).split(" ")
    # allow "1 00 000"? no — first token must be the whole amount
    if not tokens or parse_amount(tokens[0]) is None:
        raise ValueError("প্রথমে amount লিখুন, যেমন: 1000 অথবা 100000 0220249853811 13/10/2026")
    amount = parse_amount(tokens[0])
    out = {"amount": amount, "date": None, "account": "", "bank": "", "note": ""}
    rest = tokens[1:]
    note = []
    i = 0
    while i < len(rest):
        tok = rest[i]
        # "13 oct 2026" written with spaces
        joined3 = " ".join(rest[i:i + 3])
        joined2 = " ".join(rest[i:i + 2])
        d = None
        for cand, size in ((joined3, 3), (joined2, 2), (tok, 1)):
            if size > 1 and not re.search(r"[a-z]", cand.lower()):
                continue
            d = parse_date(cand.replace(" ", "-"), today) if size > 1 else parse_date(cand, today)
            if d:
                i += size
                break
        if d:
            if out["date"]:
                raise ValueError("দুটো তারিখ দেওয়া হয়েছে — একটা দিন।")
            out["date"] = d
            continue
        if re.fullmatch(r"\d{1,4}[/.-]\d{1,2}(?:[/.-]\d{1,4})?", tok) and not re.fullmatch(r"[\d-]{6,}", tok):
            raise ValueError(f"তারিখ '{tok}' ঠিক নেই — যেমন 13/10/2026 লিখুন।")
        digits = re.sub(r"[-\s]", "", tok)
        if digits.isdigit() and len(digits) >= 6 and not out["account"]:
            out["account"] = digits
        elif tok.lower().strip(".,") in BANKS and not out["bank"]:
            out["bank"] = BANKS[tok.lower().strip(".,")]
        else:
            note.append(tok)
        i += 1
    out["note"] = " ".join(note)[:200]
    out["date"] = out["date"] or today
    if out["date"] > today:
        raise ValueError(f"তারিখ ভবিষ্যতের ({out['date']:%d/%m/%Y}) — ঠিক করে লিখুন।")
    return out


def to_transaction(entry: dict, *, slip: bool = False, now: datetime | None = None) -> dict:
    """Shape for database.add_transaction (which needs date, time, account and amount)."""
    now = now or datetime.now()
    d = entry["date"] if isinstance(entry["date"], date) else date.fromisoformat(str(entry["date"]))
    time_text = now.strftime("%I:%M:%S %p") if d == now.date() else "12:00:00 PM"
    kind = "Cash deposit slip (manual amount)" if slip else "Manual entry"
    return {
        "bank_name": entry.get("bank") or ("IFIC" if slip else "Manual"),
        "receiver_name": entry.get("note", "")[:120],
        "account_number": entry.get("account") or "CASH",
        "amount": float(entry["amount"]),
        "transaction_date": d.isoformat(),
        "transaction_time": time_text,
        "reference_id": "",
        "remarks": kind + (f" · {entry['note']}" if entry.get("note") else ""),
        "raw_text": "",
    }
