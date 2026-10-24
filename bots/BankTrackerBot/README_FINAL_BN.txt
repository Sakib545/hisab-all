BankTrackerBot Final Update
===========================

যা ঠিক করা হয়েছে:
1. একই screenshot আবার দিলে duplicate ধরে save করবে না।
2. একই Reference/Transaction ID আবার দিলে duplicate ধরে।
3. Receipt-এর Date এবং Time OCR থেকে নেয়।
4. Receiver name ব্যবহার না করে Receiver Account Number দেখায়।
5. /today ও /month-এ প্রতিটি হিসাব এবং মোট টাকা দেখায়।
6. /total-এ সব হিসাবের মোট Count এবং All Total দেখায়।
7. Excel-এর শেষে ALL TOTAL যোগ করা হয়েছে।
8. Pending receipt database-এ থাকে, restart হলেও সহজে হারায় না।
9. পুরোনো database স্বয়ংক্রিয়ভাবে receipt_hash column যোগ করে upgrade হবে।

Render Environment:
DATABASE_DIR=/app/data

Render Disk Mount Path:
/app/data

আপলোড করার নিয়ম:
1. এই ফোল্ডারের ফাইলগুলো আপনার পুরোনো BankTrackerBot folder-এ Replace করুন।
2. .env ফাইল পুরোনোটাই রাখুন; ZIP-এ নিরাপত্তার জন্য .env দেওয়া হয়নি।
3. Terminal-এ চালান:

python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
git add .
git commit -m "Fix duplicate date time account and totals"
git push

4. Render deploy শেষ হলে একই screenshot দুবার দিয়ে test করুন।
