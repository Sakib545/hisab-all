BankTrackerBot v7.0.4 — Smart Restore Patch

Replace only:
1) bot.py
2) disaster_recovery.py

Do not replace/delete:
- .env
- data/
- receipts/
- exports/
- transactions.db
- doctor.py
- maintenance.py

New features:
- Backup ZIP upload করলে current এবং backup transaction/payment count compare
- পুরোনো বা ছোট backup হলে warning
- risky restore-এর জন্য দ্বিতীয় confirmation
- manifest, checksum, ZIP path এবং SQLite integrity verification
- restore-এর আগে automatic safety backup
- restore শেষে transaction count ও database integrity verification
- একই second-এ backup filename collision fix
- SQLite WAL/SHM replay protection during restore

Test:
1) Deploy
2) /fullbackup
3) একটি test receipt add করুন
4) আগের backup ZIP upload করুন
5) কম transaction warning আসবে
6) Review & Restore > Restore Anyway
7) Restore complete message-এ verified transaction count দেখাবে

Commit:
git add bot.py disaster_recovery.py
git commit -m "feat: add v7.0.4 smart restore"
git push origin main
