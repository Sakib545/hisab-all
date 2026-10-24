import unittest
from datetime import date, datetime
from manual_entry import parse_manual, looks_manual, is_deposit_slip, slip_hints, to_transaction

T = date(2026, 10, 21)
class ManualEntryTest(unittest.TestCase):
    def test_amount_only(self):
        e = parse_manual("1000", T)
        self.assertEqual((e["amount"], e["date"], e["account"]), (1000, T, ""))
    def test_full_line_any_order(self):
        e = parse_manual("100000 0220249853811 13/10/2026 IFIC Rahim", T)
        self.assertEqual((e["amount"], e["account"], e["date"], e["bank"], e["note"]), (100000, "0220249853811", date(2026, 10, 13), "IFIC", "Rahim"))
        e = parse_manual("৳১,০০,০০০ ific 13 oct", T)
        self.assertEqual((e["amount"], e["bank"], e["date"]), (100000, "IFIC", date(2026, 10, 13)))
        e = parse_manual("5000/- 13/10/26 cash deposit", T)
        self.assertEqual((e["amount"], e["date"], e["bank"], e["note"]), (5000, date(2026, 10, 13), "CASH", "deposit"))
        e = parse_manual("2500 0220-2498-5381 2026-10-01", T)
        self.assertEqual((e["account"], e["date"]), ("022024985381", date(2026, 10, 1)))
    def test_errors(self):
        for bad in ("hello 1000", "0", "1000 30/02/2026", "1000 25/12/2026", "1000 1/10 2/10"):
            with self.assertRaises(ValueError, msg=bad):
                parse_manual(bad, T)
    def test_looks_manual(self):
        self.assertTrue(looks_manual("1000"))
        self.assertTrue(looks_manual("১০০০ ific"))
        self.assertFalse(looks_manual("📊 Dashboard"))
        self.assertFalse(looks_manual("BP-0001"))
    def test_slip_detection_from_real_ocr(self):
        ocr = "Customer COPY\nDeposit Branch : ... Cash Denominations Amount\nDepositor's Name:\nTotal Amount In words"
        self.assertTrue(is_deposit_slip(ocr))
        self.assertFalse(is_deposit_slip("Pubali Bank PLC Fund Transfer(NPSB) Successful"))
        self.assertEqual(slip_hints("IFIC Bank PLC 13 OCT 2026 CASH RECEIVED")["date"], "2026-10-13")
    def test_transaction_shape(self):
        tx = to_transaction(parse_manual("100000 13/10/2026", T), slip=True, now=datetime(2026, 10, 21, 15, 0))
        self.assertEqual((tx["bank_name"], tx["account_number"], tx["transaction_time"]), ("IFIC", "CASH", "12:00:00 PM"))
        tx = to_transaction(parse_manual("1000", T), now=datetime(2026, 10, 21, 15, 4, 5))
        self.assertEqual((tx["bank_name"], tx["transaction_time"]), ("Manual", "03:04:05 PM"))

if __name__ == "__main__":
    unittest.main()
