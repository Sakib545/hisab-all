# BURAQ Smart Product Accounts Bot v7.0

## অপরিবর্তিত
- Deliveries CSV product detection
- Pain Oil, Hair Oil, Hair Oil 100ml/200ml, Unknown Excel export
- Duplicate protection ও আগের reports

## নতুন Settlement Engine
- নতুন immutable Paid Invoice ledger
- Merchant Order ID ও Consignment ID শক্তিশালী normalization
- পুরোনো v6 invoice rows automatic migration
- delivery = DELIVERED
- return = RETURNED (return priority)
- unmatched সম্পূর্ণ ignored
- Settlement প্রতিবার live database থেকে হিসাব করে
- একই invoice পুনরায় upload করলে duplicate count হয় না

## Deployment
পুরোনো persistent database delete করবেন না। v7 নিজে migration করবে।
