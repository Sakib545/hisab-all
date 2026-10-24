# BURAQ Smart Product Accounts Bot v8.0 — Live Join Settlement

আগের Deliveries CSV, product detection, Pain/Hair/Unknown Excel এবং duplicate system একই আছে।

Settlement এখন cached status, migration rebuild বা sync ব্যবহার করে না। প্রতিবার orders ও v8 invoice ledger live join করে হিসাব করে। পুরোনো buggy invoice ledger auto-migrate করা হয় না; Deliveries data অক্ষত থাকে। প্রয়োজনীয় Paid Invoice CSV একবার নতুন করে upload করুন।
