# Telegram bots → Nexa Hisab

Nexa Hisab-এর **Telegram bots** page-এ সব bot-এর data এক জায়গায় দেখা যায়।
প্রতিটা bot-এর নিজস্ব key থাকে; payment-জাতীয় record চাইলে সরাসরি Transactions-এও যায়।

## Bot connect (৩ ধাপ)
1. App → **Telegram bots → Connect a bot** → নাম আর ধরন দিন → key তৈরি হবে।
2. দেখানো দুই লাইন (`NEXA_URL`, `NEXA_TOKEN`) bot-এর `.env` / Railway / Render variables-এ দিন।
   `nexa_sync.py` bot-এর folder-এ কপি করুন (নতুন package লাগে না)।
3. Bot restart করুন বা `python nexa_sync.py test` চালান — page নিজেই "connected" দেখাবে।

## Bot code
```python
from nexa_sync import NexaSync
nexa = NexaSync()
nexa.start_background_flush()          # offline থাকলে পরে নিজে পাঠাবে

# payment bot (BankTrackerBot)
nexa.record(id=row_id, title="Pubali → Rahim", amount=1250.5, at="2026-10-20",
            ledger="expense", account="Pubali", data={"trx": trx_id})

# অন্য যেকোনো bot (Account Cleaner, order bot…)
nexa.record(id=f"clean-{user_id}-{ts}", title="Left 34 channels", kind="cleanup",
            data={"user": user_id, "left": 34})
```

## Snapshot sync (Google Sheet-ভিত্তিক bot)
Bot-এর data যদি কোনো Sheet/DB-তে থাকে আর সেখান থেকে delete হতে পারে, তাহলে প্রতিবার পুরো list পাঠান:
```python
nexa.sync_snapshot("expense", [ {"id": stable_id, "title": cat, "amount": 500, "at": "2026-10-20", "ledger": "expense"}, ... ])
```
নতুনগুলো যোগ হয়, bot-এ যেগুলো আর নেই সেগুলো site থেকেও মুছে যায় (ওই bot-এর বানানো ledger entry সহ)।
ID অবশ্যই stable হতে হবে — Sheet-এর row নম্বর নয় (delete করলে বদলে যায়)। উদাহরণ: `BusinessExpenseBot/nexa_bridge.py`।
খালি list পাঠালে server কিছুই মোছে না (Sheet পড়তে ব্যর্থ হলে সব হারানোর ভয় নেই)।

## Site থেকে bot-কে কাজ দেওয়া (command queue)
Site-এর বাটন (receipt upload, Complete payment, import delete…) `/api/bots/commands`-এ কাজ রাখে।
Bot `GET /api/bot/commands` দিয়ে কাজ নেয়, নিজের code দিয়ে চালায়, তারপর `POST /api/bot/commands {id, ok, result}`।
Python-এ সব একটা call-এ:
```python
done = nexa.run_commands({"complete_payment": fn, ...}, after=snapshot)
```
`after` (যেমন snapshot sync) result জানানোর আগে চলে, তাই site "হয়েছে" দেখানোর সময় data-ও নতুন থাকে।
Result-এর `_` দিয়ে শুরু key (যেমন `_notify`) site-এ যায় না — Telegram notification-এর জন্য রাখুন।
১০ মিনিটে শেষ না হওয়া কাজ আবার queue-তে ফেরে। ফাইল সর্বোচ্চ ~1.4 MB।

তৈরি bridge: `BankTrackerBot/nexa_bridge.py`, `Smart_Product_Accounts_Bot/nexa_bridge.py`, `BusinessExpenseBot/nexa_bridge.py`।

## পুরনো data
- **SQLite থেকে:** `python nexa_sync.py import-sqlite bot.db payments --ledger expense --account Pubali`
  (column নিজে বুঝে নেয়; না মিললে `--id --date --amount --title` দিয়ে বলে দিন)
- **CSV / JSON থেকে:** App → Telegram bots → **Import data** → file drop → column মিলিয়ে Import।

একই record দুবার import/send করলে skip হয়, তাই আবার চালানো নিরাপদ।

## HTTP API (অন্য ভাষার bot)
```
POST /api/bot/ingest
Authorization: Bearer nxh_...
{"records":[{"id":"r-1","title":"…","amount":"1250.50","at":"2026-10-20","kind":"payment",
  "status":"paid","data":{…},"ledger":{"type":"expense","account":"Pubali"}}]}
GET  /api/bot/ingest   → connection test
```
সর্বোচ্চ ১০০ record প্রতি request (Python client ২০টা করে পাঠায়, যাতে Cloudflare free plan-এর query limit না ছাড়ায়)।
`POST /api/bot/reconcile {"kind":"expense","ids":[…]}` — snapshot reconcile। পুরনো `/api/bot/entries` endpoint এখনো কাজ করে।
Shared `BOT_SYNC_TOKEN` (master key) দিলে body-তে `"bot":"name"` দিতে হয়।

## সতর্কতা
Bot (Railway/Render) পৌঁছাতে হলে app internet-এ থাকতে হবে। Bot API key দিয়ে সুরক্ষিত,
কিন্তু app-এর UI-তে login নেই — public করার আগে Cloudflare Access দিয়ে পুরো app ঢাকুন
এবং শুধু `/api/bot/*` path bypass রাখুন।
