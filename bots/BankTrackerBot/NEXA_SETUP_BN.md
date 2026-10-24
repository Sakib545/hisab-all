# BankTrackerBot → Nexa Hisab ("Dollar payments" page)

Bot আগের মতোই চলবে। নতুন যা হয়েছে:
- প্রতি ২০ সেকেন্ডে Payment cycle (BP-xxxx), সব receipt আর activity log Nexa Hisab-এ mirror হয়।
  শুধু বদলানো row যায়; bot-এ delete করা receipt site থেকেও মোছে।
- Site থেকে যা করা যায় — bot নিজের code দিয়েই করে:
  receipt-এর ছবি upload (OCR → Running Payment), Complete Payment, Reopen, হিসাবের মাস বদল,
  receipt delete, Excel/PDF Telegram-এ, receipt ছবি Telegram-এ, System Doctor, Maintenance, Full backup।
  Site থেকে করা গুরুত্বপূর্ণ কাজের খবর ADMIN_ID-কে Telegram-এ যায়।
- `/nexa` — এখনই সব data sync করে, status দেখায়।
- হাতে লেখা deposit slip ও ছবি ছাড়া manual entry — দেখুন `MANUAL_ENTRY_BN.md`।

## চালু করা
1. Nexa Hisab → Telegram bots → Connect a bot → নাম `BankTrackerBot`, ধরন *Payments & money*।
2. Railway/Render variables-এ দিন:
   ```
   NEXA_URL=https://your-nexa-hisab-domain
   NEXA_TOKEN=nxh_...
   ```
   ঐচ্ছিক: `NEXA_LEDGER=expense` (প্রতিটি receipt Transactions-এও খরচ হিসেবে যাবে, default বন্ধ),
   `NEXA_CATEGORY=Dollar payment`, `NEXA_INTERVAL=20` (সেকেন্ড)।
3. Redeploy। প্রথম ২০ সেকেন্ডেই পুরনো সব data site-এ চলে যাবে।

## বদলানো / নতুন ফাইল
- `bot.py` — sync job, `/nexa` command, আর একটি **bug fix**: `import logging` ছিল না।
  ফলে Central Sheet sync ব্যর্থ হলে receipt save হলেও bot "❌ Could not read receipt" বলত
  (album-এ failed গুনত)। এখন ঠিক।
- `nexa_bridge.py`, `nexa_sync.py`, `manual_entry.py` — নতুন।

`data/`, `.env`, receipts — কিছু replace করবেন না। NEXA_URL না দিলে bot ঠিক আগের মতো চলে।
