BankTrackerBot v7.0.1 — Doctor Patch

Replace only:
1. bot.py
2. doctor.py (new file)

Do NOT replace/delete:
- .env
- data/
- receipts/
- exports/
- transactions.db

After deploy, test:
/doctor

Also available from menu:
🩺 System Doctor

Checks included:
- SQLite integrity
- transaction/payment counts
- stored receipt image count
- missing receipt recovery source
- latest backup age
- export count
- disk free/used space
- Tesseract OCR availability
- overall health score

No new Python dependency is required.
