# v6.1 Settlement Reconciliation Fix

- Duplicate Paid Invoice নতুন করে count হয় না।
- আগে invoice এবং পরে সঠিক Deliveries CSV দিলে stored invoice rows পুনরায় match হয়।
- Settlement খোলার আগে delivery/return status database থেকে rebuild হয়।
- Return status delivery-এর উপর অগ্রাধিকার পায়।
- Unmatched row fee, payout বা settlement-এ ধরা হয় না।
