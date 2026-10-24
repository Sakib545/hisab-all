BankTrackerBot v4 — Export Payment Picker
=========================================

নতুন ফিচার:
1. নিচের main menu-এর সব function আগের মতো থাকবে।
2. "📊 Export Excel" চাপলে Payment নির্বাচন করার inline menu আসবে।
3. Running Payment এবং সব Completed/Older Payment তালিকায় দেখাবে।
4. Payment বেশি হলে Previous/Next pagination থাকবে।
5. "📚 All Payments" দিয়ে সব Payment এক Excel-এ export হবে।
6. "📚 Payments" চাপলে Payment History button list আসবে।
7. Payment select করলে status, receipt count, total, dates, export এবং transaction view থাকবে।
8. /exportpayment PAY-0001 এবং /exportall command-ও রাখা হয়েছে।
9. Pubali + IFIC parser, auto-save, duplicate protection, payment cycle, delete/search/report সব রাখা হয়েছে।

Install:
- ZIP extract করে project folder-এর files replace করুন।
- .env পরিবর্তন বা delete করবেন না।
- python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
- git add .
- git commit -m "Add v4 payment export picker"
- git push
- Render > Manual Deploy > Deploy latest commit
