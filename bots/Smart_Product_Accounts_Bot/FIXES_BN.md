# Bug Fix Report

এই ভার্সনে যা যা ঠিক করা হয়েছে, ফাইল ও কারণসহ।

---

## 🔴 গুরুতর

### ১. `.env` রিপো থেকে সরানো হয়েছে + `.gitignore` যোগ

**ফাইল:** `.gitignore` (নতুন), `.env.example` (নতুন), `.env` (মোছা), `railway_variables.txt`

আসল `BOT_TOKEN`, `ADMIN_IDS` আর `GOOGLE_SHEET_ID` রিপোতে কমিট করা ছিল।

> ⚠️ **এটুকু আপনাকে নিজে করতে হবে:**
> ১. BotFather → `/revoke` → নতুন token নিন, Railway-তে বসান।
> ২. Google service account key টাও নতুন করে ইস্যু করুন।
> ৩. `git rm --cached .env` এবং `git rm -r --cached __pycache__` চালান।
>
> পুরোনো token git history-তে থেকেই যাবে, তাই revoke করা ছাড়া উপায় নেই।

### ২. `update_courier_status()` — NameError

**ফাইল:** `database.py`

আগে এটি `update_courier_status_matching()` কল করত, যে ফাংশনটি কোথাও লেখা
ছিল না। কল করলেই `NameError`। এখন আসল implementation লেখা হয়েছে —
consignment বা merchant order ID মিলিয়ে status, COD, delivered/returned
timestamp update করে। ID-তে space/hyphen/underscore থাকলেও মেলে।

### ৩. তারিখ উল্টে যাওয়া

**ফাইল:** `processor.py` (`parse_date`), `settlement.py` (`_parse_datetime`)

আগে `dayfirst=False` আগে চেষ্টা করা হতো:

| ইনপুট | আগে | এখন |
|---|---|---|
| `01/08/2026` | ২০২৬-০১-০৮ ❌ | ২০২৬-০৮-০১ ✅ |
| `13/08/2026` | ২০২৬-০৮-১৩ ✅ | ২০২৬-০৮-১৩ ✅ |
| `2026-08-01` | ২০২৬-০৮-০১ ✅ | ২০২৬-০৮-০১ ✅ |

মানে একই ফাইলের ভেতরেই তারিখ ১–১২ হলে দিন-মাস উল্টে যেত, কোনো error
ছাড়াই। এখন ISO ফরম্যাট (`YYYY-...`) হলে year-first, বাকি সব ক্ষেত্রে
day-first ধরা হয়।

> ⚠️ পুরোনো ডেটাবেজে ইতিমধ্যে ভুল তারিখ বসে থাকতে পারে। দরকার হলে ওই
> ব্যাচগুলো `/imports` থেকে delete করে আবার upload করুন।

### ৪. লোকাল মেশিনে bot চালু না হওয়া

**ফাইল:** `database.py`

`DATA_DIR` ডিফল্ট `/data` ছিল আর import-এর সময়েই `mkdir` হতো, তাই
Mac/Windows-এ `PermissionError`। এখন ক্রমান্বয়ে চেষ্টা করে:
`$DATA_DIR` → `/data` → `<app>/bot_data` → temp folder — প্রথম যেটিতে
লেখা যায়।

---

## 🟠 বড়

### ৫. সব read কমান্ডে Admin চেক

**ফাইল:** `bot.py`

`/dashboard`, `/today`, `/yesterday`, `/date`, `/month`, `/monthly`,
`/summary`, `/find`, `/hair`, `/pain`, `/returns` — এগুলোতে কোনো চেক ছিল
না। যে কেউ বটের username পেলে পুরো COD হিসাব দেখত, আর `/find` দিয়ে
customer-এর ফোন নম্বরও বের করতে পারত। এখন ১১টি হ্যান্ডলারে
`require_admin` যোগ করা হয়েছে।

`ADMIN_IDS` খালি থাকলে এখনও সবাই access পায় (নইলে ভুল কনফিগে নিজেই লক
হয়ে যাবেন), কিন্তু startup-এ log-এ স্পষ্ট warning আসবে।

### ৬. Combo order ভুল product-এ জমা হওয়া

**ফাইল:** `processor.py` (`detect_product`, `export_eligibility`)

`"Hair Oil 200ml || Pain Oil"` (COD ১৫০০) — score দিয়ে জোর করে একটি
product বেছে নেওয়া হতো, ফলে পুরো ১৫০০ টাকা Hair Oil-এর নামে জমা হতো।
এখন একাধিক product-এর keyword মিললে `Unknown Product` হয়। Excel
export-এ এগুলো আগের মতোই **Mixed Orders** ফাইলেই যাবে।

### ৭. বাংলা keyword ম্যাচিং-এ Unicode normalization

**ফাইল:** `processor.py` (`normalize_match_text`)

`products.json`-এ "ম্যাসাজ অয়েল", "হেয়ার অয়েল" ইত্যাদি দুইবার লেখা ছিল —
একটা NFC form, একটা NFD form। এখন NFKC normalize করা হয়, তাই যেকোনো
form-এ লেখা description মেলে। চাইলে `products.json` থেকে ডুপ্লিকেট
এন্ট্রিগুলো মুছে ফেলতে পারেন (রেখে দিলেও কোনো ক্ষতি নেই)।

---

## 🟡 মাঝারি

| # | কী | ফাইল |
|---|---|---|
| ৮ | অব্যবহৃত ৪টি module `legacy/` ফোল্ডারে সরানো হয়েছে; `processor_filename_updated.py`-এর `datetime` NameError ঠিক | `legacy/` |
| ৯ | Windows setup script `.env`-এ খালি token লিখত (delayed expansion বাগ); এখন `ADMIN_IDS`-ও জিজ্ঞেস করে | `setup_and_run_windows.bat`, `setup_and_run_mac.command` |
| ১০ | `saved_exports/` এখন `DATA_DIR`-এ — redeploy-এ আর মুছে যাবে না; ৩০ দিনের পুরোনো ফাইল startup-এ auto-delete (`SAVED_EXPORTS_KEEP_DAYS`) | `bot.py` |
| ১১ | SQLite connection এখন `session()` দিয়ে বন্ধ হয় (আগে leak হতো); schema DDL process-এ একবারই চলে | `database.py`, `settlement.py`, `return_reconciliation.py` |
| ১২ | Google Sheets: tab format/freeze/hide প্রতিবার না করে একবার; row delete পাশাপাশি range ধরে — API কোটা অনেক কম | `google_sheets.py` |
| ১৩ | Central sync ১২০ বার full scan না করে একবারেই সব মাসের summary বের করে (`settlement_summaries`) | `settlement.py`, `central_sync.py` |
| ১৪ | "Google Sheet-এ Sync: N" এখন আসল যোগ হওয়া row গোনে, সব row না | `google_sheets.py` |

---

## ছোটখাটো

- `central_sync.py` — `chr(64+n)` এর বদলে `get_column_letter()`; ২৬-এর বেশি কলামেও কাজ করবে।
- `bot.py` — `DefaultBotProperties(parse_mode=HTML)` সেট; exception/product text এখন `html.escape` করা।
- `bot.py` — background retry task-এর reference রাখা হয় (GC হওয়া ঠেকাতে), বন্ধ হওয়ার সময় bot session close হয়।
- `processor.py` — Status-wise Excel-এ sheet name unique করা হয়; আগে দুইটি status-এর প্রথম ৩১ অক্ষর এক হলে পুরো upload fail করত।
- `settlement.py` — invoice code delete-এর পরও unique থাকে; paid invoice import-এ প্রতি row-তে ১০ বার Series তৈরি করা বন্ধ।
- `bot.py`, `database.py` — অব্যবহৃত import সরানো। সব ফাইল এখন pyflakes-clean।

---

## টেস্ট করা হয়েছে

`process_file` → `insert_orders_with_results` → Excel export → analysis
report → `import_paid_invoice` → `settlement_summary` → `import_return_csv`
→ `delete_import` — পুরো flow চালিয়ে দেখা হয়েছে, সবগুলো ফাইলও তৈরি হয়।
`update_courier_status` এখন কাজ করে, আর `/data` না থাকলেও bot import হয়।
