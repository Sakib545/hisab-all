# Railway-তে Nexa Hisab

এই repo-র root = Nexa Hisab app। Bot গুলো `bots/` folder-এ, প্রতিটা আলাদা Railway service।

## ১. App service
1. Railway → New → GitHub repo → `hisab-all`। **Root Directory খালি রাখুন** (repo root)।
   Build ও Start command `railway.json` থেকে নিজে নেয়:
   build `pnpm run build`, start `node scripts/railway-start.mjs`, health check `/__health`।
2. **Volume যোগ করুন** — service-এর ওপর right-click → *Attach Volume* → Mount path: `/data`।
   ⚠️ Volume না দিলে প্রতিবার deploy-এ সব হিসাব মুছে যাবে।
3. **Variables:**
   - `APP_PASSWORD` = শক্ত password (১০+ অক্ষর)। এটা না দিলে site কোনো data দেখাবে না, শুধু নির্দেশনা।
   - (ঐচ্ছিক) `BOT_SYNC_TOKEN` = ৩২+ অক্ষর — শুধু পুরনো master-key পদ্ধতির জন্য; নতুন bot-এর লাগে না।
4. Settings → Networking → **Generate Domain**। এই link-ই আপনার site (login page আসবে)।

প্রথম চালুতে database migration নিজে চলে (`/data/nexa-hisab/nexa-migrations.json`-এ লেখা থাকে),
পরের deploy-এ শুধু নতুন migration চলে।

## ২. Bot service (প্রতিটা bot-এর জন্য)
New → GitHub repo → `hisab-all` → Settings → **Root Directory** = `bots/BankTrackerBot`
(অথবা `bots/Smart_Product_Accounts_Bot`, `bots/BusinessExpenseBot`)। Variables-এ আগের মতো BOT_TOKEN ইত্যাদি, আর:
```
NEXA_URL=https://<আপনার app-এর Railway domain>
NEXA_TOKEN=nxh_...   (site → Telegram bots → Connect a bot)
```
Bot-এর data-র জন্যও Volume দিন (bot-এর নিজের README অনুযায়ী, সাধারণত `/data` আর `DATA_DIR=/data`)।

## Build ব্যর্থ হলে
- "Could not resolve './.openai/hosting.json'" — পুরনো version। এই version-এ `config/hosting.json` ব্যবহার হয়,
  GitHub website দিয়ে upload করলেও build হবে।
- GitHub website-এ এক বারে ১০০টার বেশি file দেওয়া যায় না, আর Mac লুকানো (`.` দিয়ে শুরু) file বাদ দেয় —
  git / GitHub Desktop ব্যবহার করাই ভালো।

## একটা জিনিস জেনে রাখুন
App-টা Cloudflare Workers-এর জন্য বানানো; Railway-তে এটা Cloudflare-এর নিজস্ব runtime (workerd, wrangler-এর ভেতর)
দিয়ে একটা server-এ চলে, database একটা SQLite file (Volume-এ)। এক ব্যবসার জন্য যথেষ্ট; Railway-র Volume backup
চালু রাখুন। ভবিষ্যতে চাইলে একই code সরাসরি Cloudflare-এও deploy করা যায়।
