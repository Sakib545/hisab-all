# Paid Invoice Settlement System

1. আগে Deliveries CSV upload করুন। Bot Consignment ID, Merchant Order ID, Product এবং COD save করবে।
2. পরে Paid Invoice CSV upload করুন। File আলাদা button দিয়ে নির্বাচন করতে হবে না; Bot column দেখে নিজে চিনবে।
3. Matching priority:
   - Merchant_Order_ID (Return consignment RB... আলাদা হতে পারে বলে এটি সবচেয়ে নির্ভরযোগ্য)
   - Consignment_ID fallback
4. `Invoice type = delivery` হলে order `DELIVERED` হবে।
5. `Invoice type = return` হলে order `RETURNED` হবে। একই order delivery এবং return দুটোতেই থাকলে Return final status হবে।
6. Paid Invoice-এ না পাওয়া saved order Pending থাকবে।
7. `📊 Settlement` অথবা `/settlement` থেকে Total COD, Delivered, Return, Pending, Total Fee, Payout ও Remaining দেখা যাবে।
8. একই Paid Invoice file আবার upload করলে SHA-256 file hash দিয়ে duplicate import বন্ধ থাকবে।
