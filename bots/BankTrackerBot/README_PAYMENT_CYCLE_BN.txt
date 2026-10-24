BankTrackerBot — Pubali + IFIC + Payment Cycle Update

নতুন সুবিধা:
1. শুধু Pubali ও IFIC receipt parser।
2. Receipt-এর Date, Time, Account ও Amount সব detect না হলে auto-save হবে না।
3. IFIC receipt-এ Amount field নেওয়া হবে, Total Amount নয়।
4. নতুন receipt active Payment ID-তে auto-save হবে।
5. Complete Payment করলে আগের হিসাব lock হয়ে নতুন Payment ID শুরু হবে।
6. Excel-এর প্রতিটি cell-এ পরিষ্কার border/grid থাকবে।

Commands:
/currentpayment
/completepayment
/payments
/payment PAY-0001
/exportpayment PAY-0001
/export
/delete ID

Deploy:
python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
git add .
git commit -m "Add Pubali IFIC parser and payment cycles"
git push
