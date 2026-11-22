import unittest
from datetime import datetime

from olx_monitor import publi24 as p

NOW = datetime(2026, 11, 16, 12, 0).astimezone()


class Publi24Tests(unittest.TestCase):
    def test_price(self):
        self.assertEqual(p.parse_price("1,799 RON"), (1799.0, "RON"))
        self.assertEqual(p.parse_price("2 900 RON"), (2900.0, "RON"))
        self.assertEqual(p.parse_price("300 EUR"), (300.0, "EUR"))
        self.assertEqual(p.parse_price(""), (None, None))
        self.assertEqual(p.parse_price("Negociabil"), (None, None))

    def test_when(self):
        self.assertEqual(p.parse_when("azi 10:30", NOW).hour, 10)
        self.assertEqual(p.parse_when("ieri 22:45", NOW).day, 15)
        self.assertEqual(p.parse_when("9 noiembrie", NOW).month, 11)
        self.assertEqual(p.parse_when("28 decembrie", NOW).year, 2025)
        self.assertLess(p.parse_when("???", NOW), NOW.replace(day=10))

    def test_card(self):
        raw = dict(id="abc", href="https://www.publi24.ro/x.html?y=1", title="iPhone 13 128GB\n",
                   price="1,300 RON", city="Iasi, Iasi", date="azi 09:00")
        o = p.parse_card(raw, NOW)
        self.assertEqual((o.id, o.price, o.url, o.city), ("p24:abc", 1300.0, "https://www.publi24.ro/x.html", "Iasi, Iasi"))
        self.assertIsNone(p.parse_card(dict(raw, id=""), NOW))

    def test_url(self):
        self.assertEqual(p.build_url("iphone 13", 500, 2000),
                         "https://www.publi24.ro/anunturi/?q=iphone+13&orderby=date&minprice=500&maxprice=2000")


if __name__ == "__main__":
    unittest.main()
