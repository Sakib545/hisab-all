# BURAQ Smart Product Accounts Bot v7.1

## পুরোনো data নিরাপদ রাখা
- প্রথম startup-এ SQLite database-এর verified backup তৈরি হবে।
- Backup path: DATA_DIR/backups/
- পুরোনো Deliveries, duplicate history, import history এবং Paid Invoice ledger রাখা হবে।
- v6/v7 legacy invoice rows নতুন manageable import history-তে link হবে।
- Railway volume/database delete করার প্রয়োজন নেই।

## Paid Invoice Delete
- Menu: 🗑 Paid Invoice Delete
- সর্বশেষ Paid Invoice import history দেখা যাবে।
- Confirm ছাড়া delete হবে না।
- Delete করলে শুধু নির্বাচিত invoice-এর ledger rows বাদ যাবে।
- Deliveries CSV এবং product export data অক্ষত থাকবে।
- Delete শেষে Delivered/Returned/Pending, fee, payout এবং settlement live rebuild হবে।
