# Smart Product Accounts Bot → Nexa Hisab ("Courier & COD" page)

Bot আগের মতোই চলবে। নতুন যা হয়েছে:
- প্রতি ২০ সেকেন্ডে সব parcel (Paid Invoice live-join status, fee, payout ও Return CSV status সহ),
  import history, Paid Invoice (INV-xxxxxx), duplicate history আর Return CSV import Nexa Hisab-এ mirror হয়।
  Site-এর Settlement হিসাব bot-এর settlement.py-এর সাথে হুবহু মেলে (test করা)।
- Site থেকে যা করা যায় — bot নিজের code দিয়েই করে:
  Deliveries CSV/Excel, Paid Invoice CSV, Return CSV upload; import delete; একটি বা সব Paid Invoice delete;
  duplicate history clear; import-এর Product Excel আবার Telegram-এ; Central Export।
  Deliveries import-এর Hair Oil 100ml / Pain Oil Excel আগের মতোই ADMIN_IDS-এ Telegram-এ আসে।
- `/nexa` — এখনই সব data sync করে, status দেখায়।

## চালু করা
1. Nexa Hisab → Telegram bots → Connect a bot → নাম `Smart Product Accounts`, ধরন *Orders & customers*।
2. Railway variables-এ দিন:
   ```
   NEXA_URL=https://your-nexa-hisab-domain
   NEXA_TOKEN=nxh_...
   ```
   ঐচ্ছিক: `NEXA_INTERVAL=20`।
3. Redeploy। প্রথমবার সব order পাঠাতে কয়েক মিনিট লাগতে পারে (২০টা করে যায়)।

Site থেকে file সর্বোচ্চ ~1.4 MB; বড় file আগের মতো সরাসরি bot-এ পাঠান।

## ⚠️ নিরাপত্তা
এই repo-তে `.env` commit করা ছিল, তাতে আসল `BOT_TOKEN` আছে। এই package থেকে `.env` বাদ দিয়েছি।
BotFather → /revoke দিয়ে token বদলান, নতুন token শুধু Railway variable-এ রাখুন, আর repo থেকে `.env` মুছে
`.gitignore`-এ যোগ করুন (git history-তেও থেকে যায়, তাই token বদলানোই আসল সমাধান)।

## বদলানো / নতুন ফাইল
- `bot.py` — sync loop ও `/nexa` command (বাকি সব আগের মতো)
- `nexa_bridge.py`, `nexa_sync.py` — নতুন
