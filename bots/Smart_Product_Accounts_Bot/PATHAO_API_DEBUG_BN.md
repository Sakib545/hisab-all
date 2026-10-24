# Pathao API Debug

Telegram bot-এর `🧪 API Debug` button অথবা `/pathao_debug` command ব্যবহার করুন।

Bot সর্বোচ্চ ৩টি consignment-এর Pathao API response সংগ্রহ করে একটি JSON file পাঠাবে। Token, password, email, phone, address, customer/recipient name ইত্যাদি field mask করা হয়।

এই JSON file developer-কে দিলে exact status/COD field mapping ঠিক করা যাবে।

Rate limit এড়াতে request-এর মাঝে configured delay ব্যবহার করা হয় এবং 429 হলে debug বন্ধ হয়ে যায়।
