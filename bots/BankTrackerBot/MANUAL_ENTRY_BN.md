# হাতে লেখা slip ও Manual Entry

## হাতে লেখা IFIC Cash Deposit Slip
1. Slip-এর ছবি bot-এ পাঠান (আগের মতোই)।
2. Bot slip চিনে বলবে: "Cash Deposit Slip পেয়েছি — amount লিখে পাঠান"।
   হাতের লেখা (amount, account) ছবি থেকে নির্ভরযোগ্যভাবে পড়া যায় না, তাই bot আন্দাজে কিছু save করে না।
3. Amount লিখুন, চাইলে account / তারিখ / bank / নাম সহ:
   `100000` অথবা `100000 0220249853811 13/10/2026 IFIC`
4. Bot preview দেখাবে → ✅ Save। ছবিটা ওই receipt-এর সাথে থাকবে (/receipt ID দিয়ে দেখা যায়)।
   একই ছবি দ্বিতীয়বার দিলে duplicate হিসেবে আটকাবে। বাদ দিতে /cancel।

## ছবি ছাড়া শুধু লিখে
যেকোনো সময় amount দিয়ে শুরু করে message পাঠান, বা ✍️ Manual Entry button / `/add`:
```
1000
100000 0220249853811
100000 0220249853811 13/10/2026 IFIC Rahim
৳১,০০,০০০ 13 oct cash
```
প্রথম সংখ্যা = amount; বাকিগুলো যেকোনো ক্রমে: account (৬+ digit), তারিখ (13/10/2026, 13/10/26, 13 oct, 2026-10-13),
bank (IFIC, Pubali, bKash, Nagad, Cash…), নাম/নোট। তারিখ না দিলে আজ। Save-এর আগে ✅/❌ দিয়ে নিশ্চিত করতে হয়;
একই দিনে একই amount আগে থাকলে সতর্ক করে। Account না দিলে "CASH" লেখা হয়।

Nexa Hisab site-এও একই কাজ: Dollar payments → "হাতে লিখে যোগ", আর site থেকে দেওয়া slip পড়া না গেলে
সেখানেই amount লেখার ঘর আসে।

নতুন ফাইল: `manual_entry.py` (+ `test_manual_entry.py`: `python -m unittest test_manual_entry`)।
