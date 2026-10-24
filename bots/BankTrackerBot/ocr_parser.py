import re
from datetime import datetime
from pathlib import Path

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from config import OCR_LANG, TESSERACT_CMD

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3,
    "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6,
    "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def extract_text(path):
    """OCR tuned for the clear Pubali/IFIC receipt layouts supplied by the user."""
    img = Image.open(Path(path))
    img = ImageOps.exif_transpose(img).convert("L")
    if img.width < 1800:
        scale = 1800 / img.width
        img = img.resize((1800, int(img.height * scale)))
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = img.filter(ImageFilter.SHARPEN)

    # PSM 6 keeps each receipt row together. A second pass helps when PDF screenshots
    # have wide gaps between labels and values.
    text1 = pytesseract.image_to_string(img, lang=OCR_LANG, config="--psm 6")
    text2 = pytesseract.image_to_string(img, lang=OCR_LANG, config="--psm 11")
    return text1 + "\n" + text2


def _first(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.M)
        if match:
            return (match.group(1) if match.groups() else match.group(0)).strip()
    return ""


def _clean_ocr_date(value):
    value = value.strip()
    value = value.replace("|", "1")
    # Common OCR substitutions only inside date/time strings.
    value = re.sub(r"(?<=\d)[Oo](?=\d|[./:-])|(?<=[./:-])[Oo](?=\d)", "0", value)
    value = re.sub(r"\bJu[Il1]\b", "Jul", value, flags=re.I)
    return re.sub(r"\s+", " ", value)


def _format_datetime(value, formats):
    value = _clean_ocr_date(value)
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.date().isoformat(), dt.strftime("%I:%M:%S %p")
        except ValueError:
            continue
    return "", ""


def detect_receipt_type(text):
    low = text.lower()

    # IFIC receipts can contain "PUBALI BANK PLC." as the recipient bank.
    # Therefore IFIC branding/layout cues must be checked before the word Pubali.
    if (
        re.search(r"\bific\b", low)
        or "source of payment" in low
        or "name of the recipient" in low
        or "transfer to other bank" in low
        or "transaction receipt generated on" in low
    ):
        return "IFIC"

    if (
        "pubali" in low
        or "date & time" in low
        or "fund transfer(npsb) successful" in low
    ):
        return "PUBALI"
    return ""


def _pubali_datetime(text):
    value = _first([
        r"Date\s*&\s*Time\s*[:\-]?\s*([0-3]?\d\s*[-/.]\s*[A-Za-z1]{3,9}\s*[-/.]\s*20\d{2}\s+[0-2]?\d:[0-5]\d(?::[0-5]\d)?\s*(?:AM|PM))",
        r"\b([0-3]?\d\s*[-/.]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[A-Za-z]*\s*[-/.]\s*20\d{2}\s+[0-2]?\d:[0-5]\d(?::[0-5]\d)?\s*(?:AM|PM))\b",
    ], text)
    return _format_datetime(value, [
        "%d-%b-%Y %I:%M:%S %p", "%d-%b-%Y %I:%M %p",
        "%d-%B-%Y %I:%M:%S %p", "%d-%B-%Y %I:%M %p",
        "%d/%b/%Y %I:%M:%S %p", "%d/%b/%Y %I:%M %p",
    ])


def _ific_datetime(text):
    # Prefer the actual transaction Date field near the bottom, not the
    # "receipt generated on" timestamp. OCR may keep the value on the same
    # line or move it to the following line.
    value = _first([
        r"(?im)^\s*Date\s*[:\-]?\s*([0-3]?\d\s*[./-]\s*[01]?\d\s*[./-]\s*20\d{2}\s+[0-2]?\d:[0-5]\d(?::[0-5]\d)?)\s*$",
        r"(?ims)^\s*Date\s*[:\-]?\s*\n+\s*([0-3]?\d\s*[./-]\s*[01]?\d\s*[./-]\s*20\d{2}\s+[0-2]?\d:[0-5]\d(?::[0-5]\d)?)\s*$",
        r"\b([0-3]?\d\s*[.]\s*[01]?\d\s*[.]\s*20\d{2}\s+[0-2]?\d:[0-5]\d(?::[0-5]\d)?)\b",
    ], text)
    value = re.sub(r"\s*([./-])\s*", r"\1", value)
    return _format_datetime(value, [
        "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
    ])


def extract_reference_id(text, receipt_type):
    patterns = [
        r"(?im)^\s*Transaction\s*ID\s*[:#-]?\s*([A-Z0-9][A-Z0-9/_-]{5,40})\s*$",
        r"Transaction\s*ID\s*[:#-]?\s*([A-Z0-9][A-Z0-9/_-]{5,40})",
    ]
    return _first(patterns, text).replace(" ", "").upper()


def _parse_amount(raw):
    if not raw:
        return 0.0
    raw = raw.replace(" ", "").replace(",", "")
    try:
        value = float(raw)
        return value if 0 < value < 1000000000 else 0.0
    except ValueError:
        return 0.0


def _pubali_amount(text):
    # Pubali's Amount row; avoid Available Balance and Bank Charges.
    raw = _first([
        r"(?im)^\s*Amount\s*[:\-]?\s*(?:BDT\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:BDT)?\s*$",
        r"Amount\s*[:\-]?\s*(?:BDT\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)\s*BDT",
    ], text)
    return _parse_amount(raw)


def _ific_amount(text):
    # Use Amount, never Total Amount (which includes fee/VAT).
    raw = _first([
        r"(?im)^\s*Amount\s*[:\-]?\s*(?:BDT\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)\s*$",
        r"\bAmount\s+(?:BDT\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)\b",
    ], text)
    return _parse_amount(raw)


def _account(text, receipt_type):
    if receipt_type == "PUBALI":
        raw = _first([
            r"(?im)^\s*Receiver\s*[:\-]?\s*([0-9][0-9 ]{7,24})\s*$",
            r"Receiver\s*[:\-]?\s*([0-9]{8,24})",
        ], text)
    else:
        raw = _first([
            r"(?im)^\s*Account\s*number\s*[:\-]?\s*([0-9][0-9 ]{7,24})\s*$",
            r"(?ims)^\s*Account\s*number\s*[:\-]?\s*\n+\s*([0-9][0-9 ]{7,24})\s*$",
            r"Account\s*(?:number|no\.?|#)\s*[:\-]?\s*([0-9]{8,24})",
            r"(?:Beneficiary|Recipient|Receiver)\s*(?:Account|A/?C)\s*(?:number|no\.?|#)?\s*[:\-]?\s*([0-9]{8,24})",
        ], text)
    return re.sub(r"\D", "", raw)


def parse_receipt(text):
    receipt_type = detect_receipt_type(text)

    if receipt_type == "PUBALI":
        date_value, time_value = _pubali_datetime(text)
        amount = _pubali_amount(text)
    elif receipt_type == "IFIC":
        date_value, time_value = _ific_datetime(text)
        amount = _ific_amount(text)
    else:
        date_value, time_value, amount = "", "", 0.0

    account = _account(text, receipt_type) if receipt_type else ""
    reference_id = extract_reference_id(text, receipt_type)
    receiver_name = ""
    if receipt_type == "IFIC":
        receiver_name = _first([
            r"(?im)^\s*Name\s+of\s+the\s+recipient\s*[:\-]?\s*(.+?)\s*$",
            r"(?ims)^\s*Name\s+of\s+the\s+recipient\s*[:\-]?\s*\n+\s*([^\n]+)",
        ], text)

    missing = []
    if not receipt_type:
        missing.append("unsupported receipt (only Pubali and IFIC are supported)")
    if not date_value:
        missing.append("date")
    if not time_value:
        missing.append("time")
    if not account:
        missing.append("receiver account")
    if not amount:
        missing.append("amount")

    return {
        "bank_name": receipt_type or "Unknown",
        "receiver_name": receiver_name,
        "account_number": account,
        "amount": amount,
        "transaction_date": date_value,
        "transaction_time": time_value,
        "reference_id": reference_id,
        "remarks": "Missing: " + ", ".join(missing) if missing else "",
        "raw_text": text,
        "is_valid": not missing,
        "missing_fields": missing,
    }
