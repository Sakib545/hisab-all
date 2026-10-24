BANKTRACKERBOT — PORTABLE HOSTING v5.2
=====================================

নতুন সুবিধা
-----------
1. 💾 Backup button বা /backup command
   - transactions.db
   - সব archived receipt image
   - manifest.json
   এক ZIP file হিসেবে Telegram-এ পাঠাবে।

2. ♻️ Restore Backup button বা /restore command
   - Backup ZIP Telegram-এ document হিসেবে পাঠান
   - Caption লিখুন: /restore
   - Database ও receipt images আগের অবস্থায় restore হবে

3. Hosting-independent DATA_DIR
   - Render persistent disk: DATA_DIR=/var/data
   - Railway volume: DATA_DIR=/data
   - অন্য hosting: mounted persistent folder-এর path দিন

HOSTING বদলানোর নিরাপদ নিয়ম
---------------------------
1. পুরোনো bot-এ 💾 Backup চাপুন এবং ZIP download করে রাখুন।
2. নতুন hosting-এ GitHub code deploy করুন।
3. Persistent volume/disk attach করুন।
4. Environment variable DATA_DIR volume path-এ সেট করুন।
5. BOT_TOKEN, ADMIN_ID, TIMEZONE, OCR_LANG সেট করুন।
6. নতুন bot চালু হলে Backup ZIP document হিসেবে পাঠিয়ে caption /restore দিন।
7. Restore complete হলে /total, /payments এবং Export Excel পরীক্ষা করুন।

গুরুত্বপূর্ণ
-----------
- GitHub-এ database বা receipt upload করবেন না।
- Persistent volume ছাড়া hosting restart/redeploy-এ local data হারাতে পারে।
- প্রতিটি payment complete হওয়ার পরে একটি Backup ZIP রেখে দেওয়া ভালো।
