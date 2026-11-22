import unittest
from datetime import datetime

from olx_monitor import facebook as f

NOW = datetime(2026, 11, 16, 12, 0).astimezone()


class FacebookTests(unittest.TestCase):
    def test_price(self):
        self.assertEqual(f.parse_price("$1,350"), (1350.0, "USD"))
        self.assertEqual(f.parse_price("RON 1,200"), (1200.0, "RON"))
        self.assertEqual(f.parse_price("1.200 lei"), (1200.0, "RON"))
        self.assertEqual(f.parse_price("1.299,50 RON"), (1299.0, "RON"))
        self.assertEqual(f.parse_price("Gratuit"), (None, None))

    def test_card(self):
        raw = dict(href="/marketplace/item/2706389639801807/?ref=search", text="Just listed\nRON 1,350\nRON 1,500\nPS5 Pro 2TB\nIasi")
        o = f.parse_card(raw, NOW)
        self.assertEqual((o.id, o.price, o.currency, o.title, o.city, o.created),
                         ("fb:2706389639801807", 1350.0, "RON", "PS5 Pro 2TB", "Iasi", NOW))
        o = f.parse_card(dict(href="/marketplace/item/1/", text="RON 450\nPS5 Slim\nCluj-Napoca"), NOW)
        self.assertIsNone(o.created)
        self.assertEqual(o.url, "https://www.facebook.com/marketplace/item/1/")
        self.assertIsNone(f.parse_card(dict(href="/marketplace/item/2/", text="Free\nPS5\nIasi"), NOW))
        self.assertIsNone(f.parse_card(dict(href="/x", text="RON 1\nA"), NOW))

    def test_url(self):
        self.assertIn("/marketplace/bucharest/search/?query=ps5", f.build_url("ps5", 400, 3000, "bucharest"))


if __name__ == "__main__":
    unittest.main()
