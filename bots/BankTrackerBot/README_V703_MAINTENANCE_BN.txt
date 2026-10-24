BankTrackerBot v7.0.3 Auto Maintenance Patch
=============================================

Replace/add only:
- bot.py
- maintenance.py (new)

Commands:
- /maintenance
- Menu: 🛠 Maintenance

Automatic schedule:
- Default: প্রতি রবিবার রাত ৪:০০ (TIMEZONE অনুযায়ী)
- সফল হলে নীরবে কাজ করবে। কোনো task fail করলে Admin-কে report পাঠাবে।

Optional environment variables:
AUTO_MAINTENANCE_ENABLED=true
AUTO_MAINTENANCE_DAY=6
AUTO_MAINTENANCE_HOUR=4
AUTO_MAINTENANCE_MINUTE=0
LOG_RETENTION_DAYS=30
TEMP_RETENTION_HOURS=24
EXPORT_RETENTION_DAYS=0

Day numbers: Monday=0 ... Sunday=6
EXPORT_RETENTION_DAYS=0 হলে কোনো export delete হবে না।
Receipt images এবং transaction records কখনো maintenance দ্বারা delete হয় না।
