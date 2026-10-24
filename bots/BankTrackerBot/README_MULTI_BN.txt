BankTrackerBot Multi Screenshot Version

নতুন সুবিধা:
1. Telegram-এ একসাথে অনেক ছবি Album হিসেবে পাঠালে সব ছবি auto-process হবে।
2. একই screenshot আবার দিলে Duplicate হিসেবে skip হবে।
3. একই Transaction/Reference ID হলেও Duplicate হিসেবে skip হবে।
4. Album শেষে Saved, Duplicate, Failed এবং Saved Total দেখাবে।
5. একটি ছবি আলাদাভাবে পাঠালে আগের মতো Confirm/Cancel button আসবে।
6. /delete ID দিয়ে record delete হবে।

ইনস্টল:
- এই folder-এর ফাইলগুলো আপনার পুরোনো BankTrackerBot folder-এ Replace করুন।
- আপনার পুরোনো .env ফাইল Replace বা Upload করবেন না।
- Render Environment-এ DATABASE_DIR=/app/data থাকতে হবে।
- Render Disk mount path /app/data হতে হবে।

Terminal commands:
python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
git add .
git commit -m "Add multi screenshot processing"
git push

তারপর Render: Manual Deploy > Deploy latest commit

ব্যবহার:
Telegram attachment icon > Gallery > কয়েকটি receipt নির্বাচন > Send as Album
Album-এর সব receipt Confirm ছাড়াই process ও save হবে।
