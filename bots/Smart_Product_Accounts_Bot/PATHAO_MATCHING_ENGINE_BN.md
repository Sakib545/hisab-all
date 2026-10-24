# Pathao Merchant Order ID Matching Engine

এই version Pathao status response-কে imported Excel/CSV order-এর সঙ্গে তিন ধাপে match করে:

1. `merchant_order_id` → database-এর `merchant_id`
2. Pathao response-এর `consignment_id`
3. API request-এ ব্যবহৃত imported consignment ID

Pathao status endpoint COD না দিলে imported order-এর COD ব্যবহার হয়। Returned status প্রথমবার এলে ওই order-এর COD Return COD হিসেবে ধরা হয় এবং Net COD থেকে বাদ যায়। একই order পুনরায় Returned থাকলে double-minus হয় না।

Sync result-এ এখন দেখা যায়:
- Matched by Order ID
- Matched by Consignment
- Unmatched

## Railway Variables
আগের variables অপরিবর্তিত রাখুন:

PATHAO_AUTO_SYNC=false
PATHAO_SYNC_LIMIT=20
PATHAO_REQUEST_DELAY_SECONDS=2.5
PATHAO_RATE_LIMIT_COOLDOWN_SECONDS=300

প্রথমে manual `/pathao_sync` দিয়ে পরীক্ষা করুন। কয়েকবার সফল হওয়ার পর `PATHAO_AUTO_SYNC=true` করা যাবে।
