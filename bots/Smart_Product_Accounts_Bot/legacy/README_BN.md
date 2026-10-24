# legacy/ — বর্তমানে ব্যবহার হচ্ছে না

এই ফাইলগুলো `bot.py` বা অন্য কোনো module থেকে import হয় না। রেফারেন্সের
জন্য রাখা হলো, কিন্তু এগুলো চালু কোডের অংশ নয়।

- `processor_filename_updated.py` — `processor.py`-এর পুরোনো fork।
  লাইন ৪৮৯-এ `datetime` import ছাড়াই ব্যবহার করা হয়েছে (NameError)।
  এর একমাত্র দরকারি অংশ — combo order-কে `Unknown Product` করা — এখন
  মূল `processor.py`-এ যোগ করা হয়েছে।
- `central_export.py` — Excel styling helper, কেউ import করে না।
  Central Export আসলে `central_sync.export_central_xlsx()` ব্যবহার করে।
- `central_push.py` — Central API upload, কেউ import করে না।
- `pathao_client.py` — Pathao API client, কেউ import করে না।
  এটি চালাতে হলে `requirements.txt`-এ `aiohttp` যোগ করতে হবে।

আবার ব্যবহার শুরু করতে চাইলে আগে বাগগুলো ঠিক করে নিন।
