BANKTRACKERBOT v5.1 — RECEIPT ARCHIVE & REPAIR

নতুন ফিচার:
1. নতুন valid receipt save হলে original screenshot data/receipts/BP-XXXX/ ফোল্ডারে সংরক্ষিত হবে।
2. Database-এ local image path, Telegram file_id এবং file_unique_id থাকবে।
3. Date/Time/Account detect না হওয়া receipt data/receipts/review/ ফোল্ডারে রাখা হবে।
4. Menu: 🔧 Repair Receipts
5. Command: /repairreceipts (পুরোনো /repairdates-ও একই কাজ করবে)
6. Export-এর আগে incomplete records থাকলে bot নিজে repair চেষ্টা করবে।
7. Local image না থাকলে ভবিষ্যতের receipts Telegram file_id দিয়ে আবার download করার চেষ্টা করবে।

গুরুত্বপূর্ণ:
পুরোনো record-এর screenshot path বা Telegram file_id যদি database-এ কখনও save না হয়ে থাকে,
সেগুলো স্বয়ংক্রিয়ভাবে repair করা সম্ভব নয়। নতুন v5.1 receipts ভবিষ্যতে repair করা যাবে।
