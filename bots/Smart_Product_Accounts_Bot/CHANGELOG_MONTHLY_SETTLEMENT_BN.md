# Monthly Settlement Update

- Deliveries CSV থেকে Total fee / Courier Charge save হয়।
- Paid Invoice CSV column দেখে automatic শনাক্ত হয়।
- `delivery` row matched হলে DELIVERED।
- `return` row matched হলে RETURNED; Return status Delivery-এর ওপর priority পায়।
- Return consignment আলাদা RB... হলেও Merchant Order ID দিয়ে match হয়।
- Merchant Order ID না মিললে Consignment ID fallback।
- Paid Invoice-এ না পাওয়া order Pending থাকে।
- একই invoice file আবার upload করলে duplicate import হয় না।
- `📊 Settlement` report: Total COD, Delivered, Returned, Pending, Total Charge, Expected Settlement, Payout, Remaining।
