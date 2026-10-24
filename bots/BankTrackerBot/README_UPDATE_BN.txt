এই আপডেটে যা ঠিক হয়েছে
=======================
1. Receipt-এর ভেতরে থাকা DD/MM/YY, DD-MM-YYYY, YYYY-MM-DD এবং English month date এখন পড়বে।
2. Date না পেলে আর চুপচাপ আজকের date বসাবে না; "Not detected" দেখাবে।
3. পুরোনো transaction-এর raw OCR থেকে date আবার বের করতে Telegram-এ /repairdates লিখুন।
4. /delete ID দিয়ে একটি transaction delete করা যাবে।
5. /deleteall দিয়ে confirmation-এর পরে সব transaction delete করা যাবে।
6. Professional Excel export:
   - Receiver ও Source File column নেই
   - Professional title, summary, filters, total row, proper widths
   - Separate Summary sheet + bank-wise chart
   - ID column report-এ hidden, তবে দরকার হলে Excel-এ unhide করা যাবে

Deploy
======
পুরোনো project folder-এ ফাইলগুলো replace করুন, তারপর:
python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
git add .
git commit -m "Fix receipt dates and professional Excel export"
git push

Render -> Manual Deploy -> Deploy latest commit

Deploy-এর পরে প্রথমে /repairdates চালান, তারপর /export চালিয়ে Excel দেখুন।
