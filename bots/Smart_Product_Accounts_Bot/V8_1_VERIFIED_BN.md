# v8.1 Verified Matching

- Exact Merchant Order ID match
- Exact Consignment ID fallback
- No phone/name fuzzy matching (ভুল parcel এড়াতে)
- Unmatched delivery/return এবং Other/Insta fee আলাদা
- Zero match হলে wrong-period Deliveries CSV warning
- Fee/Payout শুধু matched row থেকে
- Settlement live join থেকে

Real CSV verification:
- deliveries_2026-07-30 + paid_invoice (1): 136 matched
- deliveries_2026-07-30 + paid_invoice (2): 0 matched (ID overlap নেই)
