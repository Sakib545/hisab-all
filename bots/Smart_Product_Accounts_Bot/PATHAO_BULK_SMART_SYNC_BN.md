# Pathao Bulk Smart Sync

এই version-এ `Pathao Sync` একবার চাপলে একটি active queue থেকে সর্বোচ্চ
`PATHAO_BULK_MAX_ORDERS` parcel পরীক্ষা করে। Default 100।

## Railway Variables

```env
PATHAO_AUTO_SYNC=false
PATHAO_SYNC_LIMIT=20
PATHAO_BULK_MAX_ORDERS=100
PATHAO_REQUEST_DELAY_SECONDS=2.5
PATHAO_RATE_LIMIT_COOLDOWN_SECONDS=300
```

- Delivered, Returned ও Cancelled parcel terminal; পরের sync-এ আর পরীক্ষা হবে না।
- Pending/In Transit parcel queue-এর শেষে যায়, তাই অন্য parcel আটকে থাকে না।
- 429 হলে cycle বন্ধ হয়ে cooldown নেয়।
- Return COD imported Excel/CSV-এর COD থেকে নেওয়া হয়, কারণ status endpoint COD দেয় না।
- একই terminal status দ্বিতীয়বার count বা minus হয় না।
