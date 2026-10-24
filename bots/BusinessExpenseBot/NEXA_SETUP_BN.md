# BusinessExpenseBot → Nexa Hisab

এই version-এ bot-এর সব খরচ Nexa Hisab site-এ চলে যায়। Bot আগের মতোই চলবে:
Google Sheet, Central Sync, export — কিছুই বদলায়নি।

## চালু করা
1. Nexa Hisab → **Telegram bots → Connect a bot** → নাম `BusinessExpenseBot`, ধরন *Payments & money*।
2. দেখানো দুই লাইন Railway / Render variables-এ দিন:
   ```
   NEXA_URL=https://your-nexa-hisab-domain
   NEXA_TOKEN=nxh_...
   ```
   ঐচ্ছিক: `NEXA_ACCOUNT=Cash` (কোন account-এ খরচ যাবে), `DATA_DIR=/data` (volume থাকলে queue সেখানে থাকে)।
3. Bot redeploy করুন। চালু হওয়ার সাথে সাথে Sheet-এর **পুরনো সব খরচ** site-এ চলে যাবে।

## কীভাবে কাজ করে
- খরচ যোগ বা delete করলে পুরো Sheet-এর snapshot পাঠানো হয় (background-এ, reply দেরি হয় না)।
- Sheet থেকে delete করা খরচ site থেকেও মুছে যায়, তাই Sheet আর site সবসময় মিলে থাকে।
- Site বন্ধ থাকলে খরচ queue-তে থাকে, ৫ মিনিট পরপর আবার পাঠায়।
- `/nexa` — এখনই sync করে আর connection status দেখায়।

## নতুন / বদলানো ফাইল
- `nexa_sync.py`, `nexa_bridge.py` — নতুন
- `bot.py` — sync hook ও `/nexa` command যোগ হয়েছে (বাকি সব আগের মতো)

NEXA_URL / NEXA_TOKEN না দিলে bot ঠিক আগের মতো চলে।
