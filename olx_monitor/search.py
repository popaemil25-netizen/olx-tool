"""Căutare la cerere: deschide un browser REAL (vizibil), parcurge piețele din config,
citește prima pagină (cele mai noi) pentru fiecare cuvânt-cheie și raportează ce e nou și sub mediană.

Reguli: o singură trecere, pauze între pagini, fără autentificare, fără headere false;
la orice semn de blocare (403/429/captcha) se oprește imediat.
"""
from __future__ import annotations

import argparse
import dataclasses
import random
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote

from . import config as cfgmod
from . import facebook
from .db import DB
from .main import process
from .olx import Offer
from .telegram import Telegram

BASE = "https://www.olx.ro"
STALE = timedelta(days=7)
MONTHS = {m: i for i, m in enumerate(
    ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
     "septembrie", "octombrie", "noiembrie", "decembrie"], 1)}

EXTRACT_JS = """
[...document.querySelectorAll('[data-cy="l-card"]')].map(c => ({
  id: c.id,
  href: c.querySelector('a')?.getAttribute('href') || '',
  title: c.querySelector('[data-testid="ad-card-title"]')?.innerText || '',
  price: c.querySelector('[data-testid="ad-price"]')?.innerText || '',
  locdate: c.querySelector('[data-testid="location-date"]')?.innerText || ''
}))
"""


def build_url(query: str, pmin: float | None, pmax: float | None) -> str:
    slug = re.sub(r"\s+", "-", query.strip())
    url = f"{BASE}/oferte/q-{quote(slug)}/?search%5Border%5D=created_at%3Adesc"
    if pmin:
        url += f"&search%5Bfilter_float_price%3Afrom%5D={int(pmin)}"
    if pmax:
        url += f"&search%5Bfilter_float_price%3Ato%5D={int(pmax)}"
    return url


def parse_price(text: str) -> tuple[float | None, str | None]:
    first = (text or "").strip().split("\n")[0]
    m = re.search(r"([\d][\d\s.]*(?:,\d+)?)\s*(lei|ron|€|eur)", first, re.I)
    if not m:
        return None, None            # „Schimb”, „Gratuit”, lipsă
    num = re.sub(r"[\s.]", "", m.group(1)).replace(",", ".")
    cur = "RON" if m.group(2).lower() in ("lei", "ron") else "EUR"
    return float(num), cur


def parse_when(locdate: str, now: datetime) -> tuple[str | None, datetime]:
    """'Sector 5 - Azi la 18:51' -> (oraș, moment). Reactualizat/dată veche => considerat vechi."""
    text = re.sub(r"\s+", " ", locdate or "").strip()
    city, _, when = text.rpartition(" - ")
    city = city or None
    low = when.lower()
    stale = now - STALE
    if "reactualizat" in low:
        return city, stale
    m = re.search(r"(azi|ieri) la (\d{1,2}):(\d{2})", low)
    if m:
        day = now if m.group(1) == "azi" else now - timedelta(days=1)
        return city, day.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0)
    m = re.search(r"(\d{1,2}) ([a-z]+) (\d{4})", low)
    if m and m.group(2) in MONTHS:
        return city, now.replace(year=int(m.group(3)), month=MONTHS[m.group(2)], day=int(m.group(1)),
                                 hour=12, minute=0, second=0, microsecond=0)
    return city, stale


def parse_card(raw: dict, now: datetime) -> Offer | None:
    href = raw.get("href") or ""
    if not raw.get("id") or "/d/oferta/" not in href or not raw.get("title"):
        return None                  # carduri din alte site-uri/reclame
    url = (href if href.startswith("http") else BASE + href).split("?")[0]
    price, cur = parse_price(raw.get("price", ""))
    city, created = parse_when(raw.get("locdate", ""), now)
    return Offer(id=raw["id"], title=raw["title"].strip().split("\n")[0].strip(), description="", url=url,
                 price=price, currency=cur, created=created, city=city)


class _Out:
    """Afișează în consolă și trimite pe Telegram (dacă e configurat)."""
    def __init__(self, tg: Telegram):
        self.tg = tg

    def send(self, text: str) -> bool:
        print("\n" + re.sub(r"</?[a-z]+>", "", text) + "\n")
        return self.tg.send(text) if self.tg.enabled else True


def _open_context(p, profile: str):
    last = None
    for channel in ("chrome", "msedge", None):       # browserul instalat; Chromium doar ca rezervă
        try:
            kw = {"channel": channel} if channel else {}
            return p.chromium.launch_persistent_context(profile, headless=False, **kw)
        except Exception as e:                       # noqa: BLE001
            last = e
    raise SystemExit(f"Nu pot porni un browser: {last}\nRulează: python -m playwright install chromium")


SOURCES = {
    "olx": dict(label="OLX", build_url=build_url, selector='[data-cy="l-card"]', js=EXTRACT_JS, parse=parse_card,
                empty_selector=None),
    "facebook": dict(label="Facebook", build_url=None, selector=facebook.CARD_SELECTOR, js=facebook.EXTRACT_JS,
                     parse=facebook.parse_card, empty_selector=None, soft=True, pause=(8, 15)),
}
DEFAULT_SOURCES = ("olx",)          # Facebook doar la cerere: --sursa facebook


def ensure_facebook_login(ctx, page) -> bool:
    """Deschide Facebook și așteaptă (max 5 min) să te loghezi MANUAL; nu atingem parola."""
    def logged():
        return any(c["name"] == "c_user" for c in ctx.cookies("https://www.facebook.com"))
    if logged():
        return True
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    print("\nFacebook: nu ești logat. Loghează-te în fereastra deschisă (o singură dată; rămâi logat în profil). "
          "Aștept până la 5 minute...")
    for _ in range(100):
        if logged():
            time.sleep(3)
            return True
        time.sleep(3)
    print("Facebook: nu m-am logat la timp, sar peste sursa Facebook.")
    return False


def run(cfg, ore: float, show_new: bool, only: str | None, profile: str, sources=DEFAULT_SOURCES) -> int:
    try:
        from playwright.sync_api import Error as PWError, sync_playwright
    except ImportError:
        raise SystemExit("Lipsește playwright. Rulează: pip install playwright")

    db, out = DB(cfg.db_path), _Out(Telegram(cfg.bot_token, cfg.chat_id))
    summary, new_ok = [], []
    fails = restarts = 0
    with sync_playwright() as p:
        ctx = _open_context(p, profile)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if "facebook" in sources and not ensure_facebook_login(ctx, page):
            sources = tuple(x for x in sources if x != "facebook")
        for m0 in cfg.markets:
            if only and only.lower() not in m0.name.lower():
                continue
            if m0.on_demand and not only:
                continue                         # piețe la cerere (ex. pc-gaming): doar cu --piata
            m = dataclasses.replace(m0, max_age_minutes=int(ore * 60))
            stats = {"known": 0, "rejected": 0, "stored": 0, "alerted": 0}
            for src_name in sources:
              src = SOURCES[src_name]
              if src_name == "facebook" and not m.facebook:
                  continue                           # piață scoasă din Facebook (facebook = false)
              for q in m.queries:
                url = (facebook.build_url(q, m.min_price, m.max_price, cfg.facebook_location, cfg.facebook_radius_km)
                       if src_name == "facebook" else src["build_url"](q, m.min_price, m.max_price))
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if resp and resp.status in (401, 403, 429):
                        print(f"{src['label']} a răspuns {resp.status}. Mă opresc; nu ocolesc blocarea.")
                        ctx.close()
                        return 2
                    try:
                        page.wait_for_selector(src["selector"], timeout=15000)
                    except Exception:                    # noqa: BLE001
                        body = page.inner_text("body").lower()
                        if "nu am găsit" in body or "nu am gasit" in body:
                            continue
                        if src.get("soft"):
                            if page.query_selector('input[name="email"]') or "login" in page.url:
                                print(f"[{src['label']}/{m.name}/{q}] Sesiunea nu mai e logată. Sar peste {src['label']}.")
                                sources = tuple(x for x in sources if x != src_name)
                                break
                            if page.query_selector('[role="main"], [role="navigation"]'):
                                continue                 # pagină normală, fără anunțuri pentru căutarea asta
                            print(f"[{src['label']}/{m.name}/{q}] Pagină neînțeleasă (structură schimbată?). "
                                  f"Sar peste {src['label']}.")
                            sources = tuple(x for x in sources if x != src_name)
                            break
                        print(f"[{src['label']}/{m.name}/{q}] Nu văd anunțuri (posibil banner cookie, captcha sau blocare). "
                              "Rezolvă manual în fereastră dacă e cazul și rulează din nou. Mă opresc.")
                        ctx.close()
                        return 2
                    if src["empty_selector"] and page.query_selector(src["empty_selector"]):
                        continue                         # căutare fără rezultate (restul sunt sugestii)
                    now = datetime.now().astimezone()
                    seen_ids = set()
                    for raw in reversed(page.evaluate(src["js"])):   # de la cele mai vechi la cele mai noi
                        o = src["parse"](raw, now)
                        if not o or o.id in seen_ids:
                            continue
                        if src_name == "facebook" and not facebook.city_matches(o.city, cfg.facebook_cities):
                            continue                     # în afara orașelor dorite
                        seen_ids.add(o.id)
                        was_known = db.is_known(o.id)
                        r = process(o, m, db, out)
                        stats[r] += 1
                        if not was_known and r in ("stored", "alerted") and (o.created is None or now - o.created <= timedelta(hours=ore)):
                            new_ok.append((f"{src['label']}/{m.name}", o))
                    time.sleep(random.uniform(*src.get("pause", (3, 6))))
                    fails = 0
                except PWError as ex:
                    fails += 1
                    print(f"[{src['label']}/{m.name}/{q}] {type(ex).__name__}: pagina nu a răspuns, sar peste această căutare.")
                    if fails >= 3 or "closed" in str(ex).lower() or "crash" in str(ex).lower():
                        restarts += 1
                        if restarts > 3:
                            print("Browserul se blochează repetat. Mă opresc; rulează din nou mai târziu.")
                            try:
                                ctx.close()
                            except Exception:                # noqa: BLE001
                                pass
                            return 3
                        print("Repornesc browserul.")
                        try:
                            ctx.close()
                        except Exception:                    # noqa: BLE001
                            pass
                        ctx = _open_context(p, profile)
                        page = ctx.pages[0] if ctx.pages else ctx.new_page()
                        fails = 0
            summary.append((m.name, stats))
        ctx.close()

    print("\n=== Rezumat ===")
    for name, s in summary:
        print(f"{name}: {s['alerted']} alerte, {s['stored']} acceptate, {s['rejected']} respinse, {s['known']} deja văzute")
    if show_new:
        print(f"\n=== Anunțuri noi (ultimele {ore:g} h) care trec filtrele ===")
        for name, o in new_ok:
            print(f"[{name}] {o.price:,.0f} lei  {o.title}  ({o.city})\n    {o.url}".replace(",", " "))
    return 0


def main():
    import sys
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Căutare la cerere pe OLX, pe toate piețele din config")
    ap.add_argument("-c", "--config", default="config.toml")
    ap.add_argument("--ore", type=float, default=12, help="anunțul e „nou” dacă e postat în ultimele N ore")
    ap.add_argument("--noi", action="store_true", help="listează toate anunțurile noi acceptate, nu doar alertele")
    ap.add_argument("--piata", help="rulează doar piețele al căror nume conține textul")
    ap.add_argument("--sursa", choices=list(SOURCES), action="append",
                    help="sursa (implicit: olx; facebook doar dacă o ceri); poate fi repetat")
    ap.add_argument("--profil", default="browser_profile", help="folder profil browser (cookie-urile rămân aici)")
    a = ap.parse_args()
    return run(cfgmod.load(a.config), a.ore, a.noi, a.piata, a.profil, tuple(a.sursa or DEFAULT_SOURCES))


if __name__ == "__main__":
    raise SystemExit(main())
