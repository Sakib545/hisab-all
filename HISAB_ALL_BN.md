# hisab-all

BURAQ-এর সব হিসাব এক repo-তে।

| Folder | কী | কোথায় চলে |
|---|---|---|
| `/` (root) | **Nexa Hisab** web app — BURAQ Central, Courier & COD, Dollar payments, খরচের খাতা, Telegram bots hub, ledger | Cloudflare Workers + D1 |
| `bots/BankTrackerBot` | Dollar payment receipt bot (OCR, payment cycle, হাতে লেখা slip ও manual entry) | Railway / Render |
| `bots/Smart_Product_Accounts_Bot` | Courier / COD / Paid Invoice settlement bot | Railway |
| `bots/BusinessExpenseBot` | দৈনিক খরচের bot (Google Sheet) | Railway / Render |

## চালু করার ক্রম
1. **App:** root-এর `README.md` অনুযায়ী build ও deploy; database migration `drizzle/0000` থেকে `0003` পর্যন্ত।
   Internet-এ দেওয়ার আগে পুরো app Cloudflare Access দিয়ে ঢাকুন, শুধু `/api/bot/*` খোলা রাখুন।
2. **Bot connect:** app → Telegram bots → Connect a bot → প্রতিটা bot-এর `NEXA_URL` ও `NEXA_TOKEN`।
3. **Bots:** প্রতিটা bot-এর folder-এর `NEXA_SETUP_BN.md` দেখুন। Railway-তে deploy করার সময়
   Root Directory হিসেবে `bots/<bot-নাম>` দিন (অথবা bot-এর নিজের repo-তে এই folder-এর ফাইলগুলো রাখুন)।

## কখনো commit করবেন না
`.env`, bot token, Google service-account JSON, `data/`, `receipts/`, `*.db` — `.gitignore`-এ বাদ দেওয়া আছে।
সব secret শুধু Railway / Cloudflare variable-এ রাখুন।
