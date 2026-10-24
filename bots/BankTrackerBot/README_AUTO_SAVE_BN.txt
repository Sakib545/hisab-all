BankTrackerBot Auto Save Update
===============================

নতুন আচরণ:
- একটি receipt screenshot পাঠালেই OCR শেষে স্বয়ংক্রিয়ভাবে save হবে।
- Confirm/Cancel button আর থাকবে না।
- আগে save করা একই receipt আবার পাঠালে duplicate হিসেবে skip হবে।
- Amount detect না হলে save হবে না।
- Album/multiple screenshot আগের মতোই auto-process ও auto-save হবে।

Deploy:
python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
git add .
git commit -m "Enable automatic receipt saving"
git push

তারপর Render > Manual Deploy > Deploy latest commit
