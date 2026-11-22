import sys, tomllib, unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from olx_monitor.config import Market
from olx_monitor.filters import reject_reason
from olx_monitor.pricing import model_key
from olx_monitor.search import build_url, parse_card, parse_price, parse_when

NOW = datetime(2026, 11, 14, 19, 0).astimezone()


class T(unittest.TestCase):
    def test_price(self):
        self.assertEqual(parse_price("1 300 lei\nPrețul e negociabil"), (1300.0, "RON"))
        self.assertEqual(parse_price("799,99 lei"), (799.99, "RON"))
        self.assertEqual(parse_price("250 €"), (250.0, "EUR"))
        self.assertEqual(parse_price("Schimb"), (None, None))
        self.assertEqual(parse_price(""), (None, None))

    def test_when(self):
        c, t = parse_when("Bucuresti, Sectorul 5 - Azi la 18:51", NOW)
        self.assertEqual((c, t.hour, t.minute, t.day), ("Bucuresti, Sectorul 5", 18, 51, 14))
        for s in ("Arad - Reactualizat azi la 15:52", "Targu Jiu - Reactualizat la 12 noiembrie 2026", "X - 07 noiembrie 2026"):
            self.assertLess((NOW - parse_when(s, NOW)[1]).days, 8)
            self.assertGreaterEqual((NOW - parse_when(s, NOW)[1]).total_seconds(), 3 * 86400 - 1) if "Reactualizat azi" in s else None
        self.assertEqual(parse_when("Cluj - Ieri la 10:00", NOW)[1].day, 13)

    def test_card(self):
        raw = {"id": "311967043", "href": "/d/oferta/ps4-pro-IDl6YMw.html?search_reason=x",
               "title": "Playstation 4 Pro cu jocuri", "price": "1 000 lei", "locdate": "Targu Jiu - Azi la 16:02"}
        o = parse_card(raw, NOW)
        self.assertEqual((o.id, o.price, o.url), ("311967043", 1000.0, "https://www.olx.ro/d/oferta/ps4-pro-IDl6YMw.html"))
        self.assertIsNone(parse_card({**raw, "href": "https://otomoto.pl/x"}, NOW))

    def test_url(self):
        u = build_url("playstation 5", 400, 3000)
        self.assertIn("q-playstation-5", u)
        self.assertIn("from%5D=400", u.replace("%3A", ":").replace("filter_float_price:from", "from") or u)
        self.assertIn("created_at%3Adesc", u)

    def test_example_config(self):
        raw = tomllib.loads(Path(__file__).resolve().parent.parent.joinpath("config.example.toml").read_text(encoding="utf-8"))
        ms = {m["name"]: Market(**m) for m in raw["markets"]}
        con = ms["console"]
        for title in ("Consola Magica Mai Bun Ca PS5 PlayStation 4 Slim Modat", "Controller PS5 DualSense", "Joc FC27 PS5"):
            self.assertTrue(reject_reason(__import__("olx_monitor.olx", fromlist=["Offer"]).Offer(
                "1", title, "", "u", 900, "RON", None, None), con), title)
        pk = lambda m, t: model_key(t, ms[m].model_patterns, ms[m].key_features)
        self.assertEqual(pk("console", "Playstation 4 Pro 1TB impecabil"), "ps4 pro 1tb")
        self.assertEqual(pk("console", "Consola PS5 Slim digital"), "ps5 slim digital")
        self.assertEqual(pk("macbook", "MacBook Air M1 256GB"), "macbook air m1 256gb")
        self.assertEqual(pk("placi-video", "Placa video RTX 3070 Ti 8GB"), "rtx 3070 ti")
        self.assertEqual(pk("tablete", "iPad Air 5 64GB"), "ipad air 5 64gb")


if __name__ == "__main__":
    unittest.main()


class MacKeys(unittest.TestCase):
    def test_macbook_keys(self):
        raw = tomllib.loads(Path(__file__).resolve().parent.parent.joinpath("config.example.toml").read_text(encoding="utf-8"))
        m = next(Market(**x) for x in raw["markets"] if x["name"] == "macbook")
        k = lambda t: model_key(t, m.model_patterns, m.key_features)
        self.assertEqual(k("Macbook Pro 2017 Touchbar"), "macbook pro 2017")
        self.assertEqual(k('MacBook Pro 16” 2019 | Intel i7 | 16GB RAM | 512GB SSD'), "macbook pro 2019 16 512gb")
        self.assertEqual(k("Macbook Air M1 2020 256gb"), "macbook air m1 256gb")
        self.assertEqual(k("MacBook Pro M1 Touchbar 2020 13-inch 512Gb/8GB RAM"), "macbook pro m1 13 512gb")
        self.assertNotEqual(k("Macbook Pro 2017"), k("Macbook pro M2 touch bar"))


class IphoneKeys(unittest.TestCase):
    def test_iphone_models_are_separate(self):
        k = model_key
        self.assertEqual(k("iPhone 16e 128GB"), "iphone 16e 128gb")
        self.assertNotEqual(k("iPhone 13 128GB"), k("iPhone 14 128GB"))
        self.assertNotEqual(k("iPhone SE 2020 64GB"), k("iPhone SE 2022 64GB"))
        self.assertEqual(k("iPhone 14 Pro Max 256GB"), "iphone 14 pro max 256gb")
        self.assertEqual(k("iPhone 17 Air 256GB"), "iphone 17 air 256gb")
        self.assertEqual(k("iPhone 13 Mini 128"), "iphone 13 mini")

    def test_require_storage(self):
        import time
        from datetime import datetime, timezone
        from olx_monitor.db import DB
        from olx_monitor.main import process
        from olx_monitor.olx import Offer
        m = Market(name="t", queries=["x"], require_storage=True, min_price=100)
        o = lambda i, t: Offer(str(i), t, "", "u", 1500, "RON", datetime.now(timezone.utc), None)
        class TG:
            def send(self, t): return True
        db = DB(":memory:")
        self.assertEqual(process(o(1, "iPhone 13 Pro"), m, db, TG()), "rejected")
        self.assertEqual(process(o(2, "iPhone 13 Pro 128GB"), m, db, TG()), "stored")


class NewMarkets(unittest.TestCase):
    def setUp(self):
        raw = tomllib.loads(Path(__file__).resolve().parent.parent.joinpath("config.example.toml").read_text(encoding="utf-8"))
        self.ms = {x["name"]: Market(**x) for x in raw["markets"]}

    def k(self, market, title):
        m = self.ms[market]
        return model_key(title, m.model_patterns, m.key_features, m.use_storage)

    def test_keys(self):
        self.assertEqual(self.k("handheld-gaming", "Steam Deck OLED 512GB"), "steam deck oled 512gb")
        self.assertEqual(self.k("handheld-gaming", "ASUS ROG Ally Z1 Extreme 512GB"), "rog ally 512gb")
        self.assertEqual(self.k("vr", "Oculus Meta Quest 3 128GB"), "quest 3 128gb")
        self.assertEqual(self.k("vr", "Quest 2 256 GB"), "quest 2 256gb")
        self.assertEqual(self.k("procesoare", "Procesor AMD Ryzen 7 5800X3D"), "ryzen 7 5800x3d")
        self.assertEqual(self.k("procesoare", "Intel Core i5-12600K 32GB"), "i5 12600k")
        self.assertEqual(self.k("aspiratoare-dyson", "Aspirator Dyson V11 Absolute"), "dyson v11 absolute")
        self.assertEqual(self.k("smartwatch", "Apple Watch Series 9 45mm"), "apple watch 9 45")
        self.assertEqual(self.k("smartwatch", "Apple Watch Ultra 2 49 mm"), "apple watch ultra 2 49")
        self.assertEqual(self.k("smartwatch", "Garmin Fenix 7 Pro Solar"), "garmin fenix 7 pro solar")

    def test_filters(self):
        from olx_monitor.olx import Offer
        o = lambda t, p: Offer("1", t, "", "u", p, "RON", None, None)
        self.assertTrue(reject_reason(o("Curea Apple Watch", 300), self.ms["smartwatch"]))
        self.assertTrue(reject_reason(o("Kit Ryzen 5 5600 + placa de baza", 900), self.ms["procesoare"]))
        self.assertTrue(reject_reason(o("Controller Meta Quest 3", 600), self.ms["vr"]))
        self.assertIsNone(reject_reason(o("Dyson V10 Absolute", 900), self.ms["aspiratoare-dyson"]))


class VrFixes(NewMarkets):
    def test_oculus_alias_and_sold(self):
        from olx_monitor.olx import Offer
        self.assertEqual(self.k("vr", "Meta oculus 3s 128gb"), "quest 3s 128gb")
        self.assertEqual(self.k("vr", "Meta Quest 3 512GB"), "quest 3 512gb")
        o = Offer("1", "Meta quest 2 128gb VANDUT", "", "u", 700, "RON", None, None)
        self.assertTrue(reject_reason(o, self.ms["vr"]))
