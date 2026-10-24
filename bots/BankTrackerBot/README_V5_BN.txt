BANKTRACKERBOT v5 — BURAQ DOLLER PAYMENT

নতুন ফিচার:
- Payment ID: BP-0001, BP-0002...
- Pubali ও IFIC receipt auto-save
- Date, Time, Receiver Account এবং Amount না পেলে save হবে না
- Duplicate receipt skip
- Multiple screenshot/album support
- Running payment complete করলে নতুন BP Payment শুরু
- Export picker: Running, Completed এবং All Payments
- Excel title: BURAQ DOLLER PAYMENT
- Excel-এ database ID নয়; SL 1,2,3... থাকবে
- প্রতিটি cell-এ স্পষ্ট border/grid
- Columns: SL, Date, Time, Receiver Account, Amount
- Professional summary, grand total, A4 landscape print

পুরোনো blank date repair করতে Telegram-এ /repairdates দিন।

Install:
1. ZIP-এর files current project folder-এ replace করুন। .env রাখুন।
2. python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
3. git add .
4. git commit -m "Build BankTrackerBot v5"
5. git push
6. Render -> Manual Deploy -> Deploy latest commit
