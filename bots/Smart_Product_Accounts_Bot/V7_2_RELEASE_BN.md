# BURAQ Smart Product Accounts Bot v7.2

এই release-এ Paid Invoice system clean ledger architecture-এ স্থিতিশীল করা হয়েছে।

## মূল পরিবর্তন
- প্রতিটি Paid Invoice-এর আলাদা Invoice ID: `INV-000001`
- Current file summary এবং monthly cumulative Settlement আলাদা
- একই file আবার upload করলে duplicate row যোগ হয় না
- Merchant Order ID ও Consignment ID normalize করে match
- Return সবসময় Delivery-এর উপর priority পায়
- Unmatched ও Other/Insta Fee row settlement-এ ধরা হয় না
- প্রতিটি invoice-এর matched fee/payout আলাদাভাবে সংরক্ষণ
- Invoice History menu
- নির্দিষ্ট invoice delete করলে শুধু তার effect rollback
- Delete-এর পর status ও Settlement live rebuild
- পুরোনো database-এর verified automatic backup
- পুরোনো Paid Invoice ledger migration

## পুরোনো সুবিধা অপরিবর্তিত
- Deliveries CSV product detection
- Pain Oil / Hair Oil / Hair Oil 100ml / Hair Oil 200ml / Unknown Excel output
- Duplicate protection
- Quantity, Status এবং COD mismatch reports
- Google Sheets integration

## Automated test cases
- New invoice import
- Same invoice duplicate import
- Multiple invoices
- Delivery পরে Return
- Unmatched row ignore
- Other/Insta Fee ignore
- Merchant ID `1003.0` normalization
- Invoice delete এবং Settlement rollback
- Old database migration ও backup
