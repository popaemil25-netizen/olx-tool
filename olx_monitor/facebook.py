"""Sursa Facebook Marketplace (necesită cont logat, făcut manual de utilizator în profilul browserului).

Atenție: Meta interzice colectarea automată; folosirea poate duce la restricționarea contului.
Structura paginii se schimbă des, deci parsarea e tolerantă și se bazează doar pe linkurile /marketplace/item/.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote_plus

from .olx import Offer

BASE = "https://www.facebook.com"
CARD_SELECTOR = 'a[href*="/marketplace/item/"]'
EXTRACT_JS = """
[...document.querySelectorAll('a[href*="/marketplace/item/"]')].map(a => ({
  href: a.getAttribute('href') || '',
  text: a.innerText || ''
}))
"""
_CUR = {"ron": "RON", "lei": "RON", "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP"}
_PRICE = re.compile(r"(ron|lei|usd|eur|gbp|[$€£])\s*(\d[\d.,\s]*)|(\d[\d.,\s]*)\s*(ron|lei|usd|eur|gbp|[$€£])", re.I)
_BADGES = ("just listed", "listat acum", "recent adăugat", "recent adaugat", "sponsored", "sponsorizat")


def build_url(query: str, pmin: float | None, pmax: float | None, location: str = "", radius_km: int = 0,
              days: int = 7) -> str:
    loc = f"/{location.strip('/')}" if location else ""
    url = (f"{BASE}/marketplace{loc}/search/?query={quote_plus(query.strip())}"
           f"&sortBy=creation_time_descend&exact=false&daysSinceListed={days}")
    if radius_km:
        url += f"&radius={int(radius_km)}"
    if pmin:
        url += f"&minPrice={int(pmin)}"
    if pmax:
        url += f"&maxPrice={int(pmax)}"
    return url


def parse_price(line: str) -> tuple[float | None, str | None]:
    m = _PRICE.search(line or "")
    if not m:
        return None, None
    cur, num = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    num = re.sub(r"\s", "", num).strip(".,")
    num = re.sub(r"[.,]\d{2}$", "", num)              # zecimale (două cifre); „1.200” rămâne 1200
    digits = re.sub(r"\D", "", num)
    if not digits:
        return None, None
    return float(digits), _CUR.get(cur.lower())


def parse_card(raw: dict, now: datetime) -> Offer | None:
    m = re.search(r"/marketplace/item/(\d+)", raw.get("href") or "")
    if not m:
        return None
    lines = [l.strip() for l in (raw.get("text") or "").split("\n") if l.strip()]
    fresh = any(l.lower() in _BADGES[:3] for l in lines)
    lines = [l for l in lines if l.lower() not in _BADGES]
    pi = next((i for i, l in enumerate(lines) if _PRICE.search(l)), None)
    if pi is None or pi + 1 >= len(lines):
        return None                                   # „Gratuit”/fără preț sau card neînțeles
    price, cur = parse_price(lines[pi])
    rest = lines[pi + 1:]
    # după preț pot urma prețul vechi (tăiat) și apoi titlul; titlul = prima linie care nu e preț
    rest = [l for l in rest if not _PRICE.fullmatch(l.replace(" ", ""))] or rest
    return Offer(id="fb:" + m.group(1), title=rest[0], description="",
                 url=f"{BASE}/marketplace/item/{m.group(1)}/", price=price, currency=cur,
                 created=now if fresh else None, city=rest[1] if len(rest) > 1 else None)


def city_matches(city: str | None, allowed: list[str]) -> bool:
    """Fără listă = tot e permis. Altfel orașul din card trebuie să conțină unul din nume (fără diacritice)."""
    if not allowed:
        return True
    from .filters import _norm
    c = _norm(city or "")
    return any(_norm(a) in c for a in allowed)
