import sys, time, unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from olx_monitor.config import Market
from olx_monitor.db import DB
from olx_monitor.filters import looks_converted, reject_reason
from olx_monitor.main import process
from olx_monitor.olx import Offer, parse_offer
from olx_monitor.pricing import evaluate, is_shop_title, model_key, percentile


def offer(i, title, price, desc="", age_s=60):
    return Offer(str(i), title, desc, f"https://olx.ro/d/{i}", price, "RON",
                 datetime.fromtimestamp(time.time() - age_s, timezone.utc), "București")


class FakeTG:
    def __init__(self): self.sent = []
    def send(self, t): self.sent.append(t); return True


M = Market(name="tel", queries=["iphone"], min_samples=5, threshold_pct=25)


class T(unittest.TestCase):
    def test_parse(self):
        o = parse_offer({"id": 1, "title": "iPhone 13", "url": "u", "created_time": "2026-11-14T10:00:00+02:00",
                         "params": [{"key": "price", "value": {"value": 1500, "currency": "RON", "type": "price"}}],
                         "location": {"city": {"name": "Cluj"}}})
        self.assertEqual((o.price, o.city), (1500.0, "Cluj"))
        o = parse_offer({"id": 2, "title": "x", "params": [{"key": "price", "value": {"type": "arranged"}}]})
        self.assertIsNone(o.price)

    def test_filters(self):
        self.assertIn("preț", reject_reason(offer(1, "iPhone 13", None), M) or "preț")
        self.assertTrue(reject_reason(offer(1, "iPhone 13 blocat iCloud", 900), M))
        self.assertTrue(reject_reason(offer(1, "Husa iPhone 13", 200), M))
        self.assertTrue(reject_reason(offer(1, "iPhone 13", 900, "pentru piese"), M))
        self.assertIsNone(reject_reason(offer(1, "iPhone 13 128GB", 900, "nu este blocat, fara defecte"), M))
        self.assertTrue(reject_reason(offer(1, "iPhone 13", 50), M))

    def test_model_key(self):
        self.assertEqual(model_key("iPhone 13 Pro Max 256 GB impecabil"), "iphone 13 pro max 256gb")
        self.assertEqual(model_key("Samsung Galaxy S23 Ultra 8GB RAM 256GB"), "galaxy s23 ultra 256gb")
        self.assertIsNone(model_key("telefon vechi"))

    def test_flow_and_dedup(self):
        db, tg = DB(":memory:"), FakeTG()
        for i in range(6):  # istoric: ~2000 RON
            self.assertEqual(process(offer(i, "iPhone 13 128GB", 2000 + i * 10, age_s=99999), M, db, tg), "stored")
        self.assertEqual(process(offer(100, "iPhone 13 128GB", 1900), M, db, tg), "stored")  # doar 5% sub
        self.assertEqual(process(offer(101, "iPhone 13 128GB", 1200), M, db, tg), "alerted")
        self.assertEqual(process(offer(101, "iPhone 13 128GB", 1200), M, db, tg), "known")
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("sub prețul realist", tg.sent[0])
        self.assertIn("Profit orientativ", tg.sent[0])
        # vechi: nu alertează
        self.assertEqual(process(offer(102, "iPhone 13 128GB", 1000, age_s=7200), M, db, tg), "stored")
        # alt model fără istoric: nu alertează
        self.assertEqual(process(offer(103, "iPhone 15 Pro 256GB", 1500), M, db, tg), "stored")
        self.assertEqual(len(tg.sent), 1)

    def test_shop_detection(self):
        for t in ["Magazin Apple | iPhone 15 | Foarte Bun | Black | 128GB | 87% | Garantie | smilemobile.ro",
                  "Iphone 15 / Yellow/Pink / 128 GB / DeluxGSM", "Iphone 13 / 128GB / 79% BAT / #64218",
                  "iPhone 14 128GB RED – Baterie 85% – Garanție 24 Luni", "Telefon Apple Iphone 13 Zeus Amanet Rahova 36888"]:
            self.assertTrue(is_shop_title(t), t)
        for t in ["iPhone 15 128gb Negru", "Iphone 15 pink 128 gb", "iPhone 13 Midnight 128GB baterie 90%"]:
            self.assertFalse(is_shop_title(t), t)

    def test_converted_euro_prices(self):
        for p in (1871.89, 2043.03, 2674.26, 3476.36):
            self.assertTrue(looks_converted(p), p)
        for p in (1500.0, 949.99, 1449.99, 3099.99, 870.5):
            self.assertFalse(looks_converted(p), p)
        self.assertIn("EUR", reject_reason(offer(1, "PS5 Slim 1TB", 1871.89), M))
        m2 = Market(name="x", queries=["a"], reject_converted_prices=False)
        self.assertIsNone(reject_reason(offer(1, "PS5 Slim 1TB", 1871.89), m2))

    def test_percentile_and_profit(self):
        self.assertEqual(percentile([1000, 2000, 3000], 50), 2000)
        self.assertEqual(percentile([1000, 2000, 3000, 4000], 0), 1000)
        v = evaluate(1000, [1000, 1500, 2000, 2500, 3000], 3, 25)
        self.assertEqual(v.reference, 1500)
        self.assertAlmostEqual(v.profit, 500)

    def test_shops_excluded_from_history_and_min_profit(self):
        db, tg = DB(":memory:"), FakeTG()
        m = Market(name="tel", queries=["x"], min_samples=5, threshold_pct=25, min_profit=150, ref_percentile=50)
        for i in range(6):   # magazine scumpe: nu trebuie să conteze
            process(offer(i, f"iPhone 13 128GB | Garantie 24 luni | Magazin #{i}000", 2400 + i, age_s=99999), m, db, tg)
        for i in range(10, 16):   # privați ~1200
            process(offer(i, "iPhone 13 128GB", 1200 + i, age_s=99999), m, db, tg)
        # 1000 e doar ~17% sub referința privată (~1212): fără alertă; cu istoric amestecat ar fi părut 55% sub
        self.assertEqual(process(offer(200, "iPhone 13 128GB", 1000), m, db, tg), "stored")
        self.assertEqual(process(offer(201, "iPhone 13 128GB", 800), m, db, tg), "alerted")
        # profit sub minim: 25% sub 500 = 375 dar profit 125 < 150
        m2 = Market(name="mic", queries=["x"], min_samples=5, threshold_pct=25, min_profit=150, ref_percentile=50, min_price=50)
        for i in range(6):
            process(offer(300 + i, "iPhone 13 128GB", 500, age_s=99999), m2, db, tg)
        self.assertEqual(process(offer(310, "iPhone 13 128GB", 370), m2, db, tg), "stored")


if __name__ == "__main__":
    unittest.main()
