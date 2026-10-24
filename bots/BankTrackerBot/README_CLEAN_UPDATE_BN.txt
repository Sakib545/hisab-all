BankTracker Clean Update

পরিবর্তন:
1. Bank নাম Bot preview/report থেকে সরানো হয়েছে।
2. Bot-এর নিচে স্থায়ী Menu button যোগ হয়েছে:
   Today, This Month, Total, Export Excel, Search, Delete, Delete All.
3. Excel এখন একটিমাত্র clean Transactions sheet তৈরি করে।
4. Excel column: ID, Date, Time, Account Number, Amount.
5. Summary sheet, chart, reference, remarks, bank/service এবং অন্য অপ্রয়োজনীয় তথ্য সরানো হয়েছে।
6. ID visible রাখা হয়েছে, যাতে /delete ID ব্যবহার করা যায়।
7. Grand Total, filter, freeze header ও professional formatting রাখা হয়েছে।

Install:
ফাইলগুলো project folder-এ replace করে চালান:
python3 -m py_compile bot.py database.py ocr_parser.py config.py excel_export.py
git add .
git commit -m "Simplify bot menu and Excel report"
git push

তারপর Render -> Manual Deploy -> Deploy latest commit.
