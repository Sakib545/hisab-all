# BURAQ Smart Product Accounts Bot v6.0

এই release-এ আগের Deliveries CSV workflow অপরিবর্তিত রাখা হয়েছে।

## আগের সুবিধা একই আছে
- Product detection
- Pain Oil, Hair Oil, Hair Oil 100ml/200ml এবং Unknown আলাদা Excel
- Duplicate protection
- Quantity/size report
- Status-wise export
- COD mismatch report
- Google Sheets sync

## নতুন settlement সুবিধা
- Paid Invoice auto-detect
- delivery হলে DELIVERED
- return হলে RETURNED
- Invoice-এ না পাওয়া parcel PENDING
- Unmatched invoice row সম্পূর্ণ ignored
- Month-wise settlement
- Courier charge, payout ও remaining
- Product report

## ব্যবহার
1. Deliveries CSV upload করুন। আগের মতো product Excel পাবেন।
2. Paid Invoice CSV upload করুন।
3. Settlement থেকে মাস নির্বাচন করুন।
