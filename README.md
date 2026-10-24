# Nexa Hisab v2 — Business Manager

Includes: income/expense ledger, product costs and inventory, parcel dispatch/delivery/returns, COD collection, combined cost and estimated profit reports, Bengali/English browser OCR, CSV export and print/PDF.

## Run locally (Mac / Windows / Linux)
Requires Node.js 22.13+ (Node 24 recommended), npm and internet for installing dependencies. OCR models and runtime assets are included.

1. Extract this ZIP and open Terminal in the Nexa-Hisab-v2 folder.
2. Run `npm install`.
3. Run `npm run build`.
4. Initialize the local database, once on a new installation:

```sh
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_daffy_exodus.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0001_chemical_proteus.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0002_bot_hub.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0003_bot_commands.sql
```

5. Run `npm start`. Open the localhost URL printed in Terminal.

The local database lives in `.wrangler/state`; keep it when updating the app. Do not replay the migration commands on an already initialized database. Local records are separate from the hosted app.

## Usage
Products & stock → Add product → New parcel. Stock received is cumulative: add new units to the previous total when restocking. Sent/delivered reserve stock; returned parcels release it. Product unit costs are saved per parcel. Delivered parcels recognize sales and product cost. Courier/packaging costs start at Sent. Set COD collected after receiving payment.

All costs combines parcel costs with general expenses. Do not enter parcel costs a second time as ledger expenses. Reports are operational estimates grouped by order creation date; stock purchases entered again as expenses can double count product cost.

Scan receipts → choose image → Read image → verify amount/date/reference → Review as expense → Save transaction. OCR images stay in the browser; only reviewed text/transaction fields are saved. PDF pages require screenshots. OCR accuracy depends on image quality.

## Current boundaries
Courier statuses are manual; no live courier API or hosted database backup is included. One product/SKU per parcel record. Existing source tests are included in tests/.

## BURAQ bots: Central, Courier & COD, Dollar payments
- **BURAQ Central** — the bots' Central Export "Combined Summary", live: expected courier settlement, courier payout, dollar payment, business expense, balance, per month; CSV / PDF.
- **Courier & COD** (Smart Product Accounts Bot) — dashboard and reports (today / yesterday / month / any date / any month / product), monthly settlement identical to the bot's `settlement.py` (tested against real bot output), orders with search, imports, Paid Invoices, duplicates, returns; upload Deliveries / Paid Invoice / Return CSV, delete import or invoice, clear duplicates, Central Export.
- **Dollar payments** (BankTrackerBot) — running payment, cycles (complete / reopen / set month), receipts with search, analytics, activity log, tools (doctor, maintenance, backup); upload receipt photos which the bot reads with its own OCR.

Data is mirrored by each bot every ~20 s; actions from the site are queued and run by the bot with its own code (`/api/bots/commands`). Run migration `drizzle/0003_bot_commands.sql` once (after 0002). Bot patches and setup: each bot's `NEXA_SETUP_BN.md`.

## খরচের খাতা (Expense book)
Same rules as BusinessExpenseBot: type `500 খাবার` or several at once (`500 খরচ 300 নাস্তা`), Bangla digits work, an amount alone asks for the category. Seven bot categories plus custom ones; Today / This week / This month / any of the last 12 months / All; category totals; delete with confirm; weekly or monthly export as Excel (CSV) or PDF. Expenses synced from the bot show a bot badge.

## Telegram bots (Bot hub)
The **Telegram bots** page collects data from all your bots in one place: per-bot keys, live status, 14-day activity, a searchable record list, CSV/JSON import and a 3-step connect wizard. Payment records can also be added to Transactions; the same record is never saved twice.

**Existing installations:** run the new migration once, after building:

```sh
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0002_bot_hub.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0003_bot_commands.sql
```

New installations run it as the third migration in step 4. For the hosted Cloudflare D1 database use `--remote` instead of `--local --persist-to …`.

Bot setup, the Python client (`integrations/telegram/nexa_sync.py`), SQLite import and the HTTP API: see `integrations/telegram/README.md`. An optional shared master key can be set with `npm start -- --var BOT_SYNC_TOKEN:<32+ chars>` (or `wrangler secret put BOT_SYNC_TOKEN`); per-bot keys from the app don't need it.

## Hosting
This export removes the original Site identity. Its database binding is DB. The hosted version uses private platform access; the standalone app has no separate login system. Keep localhost private; add authentication before exposing it to the internet. If bots on Railway/Render must reach the app, put the whole app behind Cloudflare Access (or another login) and bypass only `/api/bot/*`, which is protected by bot keys. For other hosting, configure Cloudflare Workers/D1 or adapt the database/server runtime; this is not a plain static HTML site.

No API keys, credentials, node_modules, generated build, or business database are included.
