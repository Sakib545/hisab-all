# Pathao Rate-Limit Safe Polling

এই version webhook ছাড়াই Pathao status sync করে।

Railway Variables:

```env
PATHAO_AUTO_SYNC=false
PATHAO_SYNC_MINUTES=60
PATHAO_SYNC_LIMIT=20
PATHAO_REQUEST_DELAY_SECONDS=2.5
PATHAO_RATE_LIMIT_COOLDOWN_SECONDS=300
```

প্রথমে manual `/pathao_sync` দিয়ে test করুন। 429 না এলে পরে `PATHAO_AUTO_SYNC=true` করতে পারবেন।

কাজের নিয়ম:
- শুধু non-terminal parcel queue থেকে check হয়।
- Delivered, Returned, Cancelled parcel আর check হয় না।
- প্রতি cycle-এ সর্বোচ্চ 20 parcel check হয়।
- প্রতিটি API request-এর মাঝে 2.5 seconds delay থাকে।
- 429 এলে cycle সঙ্গে সঙ্গে বন্ধ হয় এবং অন্তত 5 minutes cooldown নেয়।
- একটি parcel error দিলে সেটি queue-এর শেষে যায়; অন্য parcel block করে না।
