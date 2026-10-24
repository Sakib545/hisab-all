# মাসভিত্তিক হিসাব

1. আগের format-এর Deliveries CSV upload করুন।
2. Bot CSV-এর Order Date থেকে মাস নিজে শনাক্ত করবে।
3. Paid Invoice CSV upload করলে Merchant Order ID/Consignment ID দিয়ে delivery ও return update হবে।
4. `📊 Settlement` চাপলে July 2026, August 2026 ইত্যাদি available মাসের button দেখাবে।
5. প্রতিটি মাসের Total Parcel, COD, Delivered, Returned, Pending, Charge, Payout ও Remaining আলাদা থাকবে।

একটি CSV-তে একাধিক মাসের order থাকলেও bot order date অনুযায়ী মাস আলাদা করে হিসাব করবে।
