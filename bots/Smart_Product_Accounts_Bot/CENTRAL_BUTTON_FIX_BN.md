# Central Button Fix

সমস্যা: Reply keyboard-এ Central Export ও Central Sync ছিল, কিন্তু text handler এবং filter list-এ ছিল না। তাই Telegram update `not handled` দেখাচ্ছিল।

সমাধান:
- `📦 Central Export` → `central_export_cmd`
- `🔄 Central Sync` → `central_sync_cmd`
- দুইটি text menu filter-এ register করা হয়েছে
- `/central_export` ও `/central_sync` command আগের মতো থাকবে
