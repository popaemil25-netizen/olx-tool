"""Sursa Publi24.ro: URL de căutare, extragere din pagină și parsare carduri."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from .olx import Offer

BASE = "https://www.publi24.ro"
STALE = timedelta(days=7)
MONTHS = {m: i for i, m in enumerate(
    ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
     "septembrie", "octombrie", "noiembrie", "decembrie"], 1)}

CARD_SELECTOR = ".article-item"
NO_RESULTS_SELECTOR = ".noresults-message"
EXTRACT_JS = """
[...document.querySelectorAll('.article-item')].map(c => ({
  id: c.getAttribute('location') || '',
  href: c.querySelector('.article-title a')?.href || '',
  title: c.querySelector('.article-title')?.innerText || '',
  price: c.querySelector('.new-price')?.innerText || c.querySelector('.article-price')?.innerText || '',
  city: c.querySelector('.article-location')?.innerText || '',
  date: c.querySelector('.article-date')?.innerText || ''
}))
"""


def build_url(query: str, pmin: float | None, pmax: float | None) -> str:
    url = f"{BASE}/anunturi/?q={quote_plus(query.strip())}&orderby=date"
    if pmin:
        url += f"&minprice={int(pmin)}"
    if pmax:
        url += f"&maxprice={int(pmax)}"
    return url


def parse_price(text: str) -> tuple[float | None, str | None]:
    """„1,799 RON” / „2 900 RON” / „1 300 EUR” -> (preț, monedă); lipsă/negociabil -> (None, None)."""
    m = re.search(r"(\d[\d\s.,]*)\s*(ron|lei|eur|€)", (text or "").strip().split("\n")[0], re.I)
    if not m:
        return None, None
    digits = re.sub(r"\D", "", m.group(1))
    if not digits:
        return None, None
    cur = "RON" if m.group(2).lower() in ("ron", "lei") else "EUR"
    return float(digits), cur


def parse_when(text: str, now: datetime) -> datetime:
    """„azi 10:30”, „ieri 22:45”, „9 noiembrie”. Necunoscut => considerat vechi."""
    low = re.sub(r"\s+", " ", (text or "").lower()).strip()
    m = re.search(r"(azi|ieri) (\d{1,2}):(\d{2})", low)
    if m:
        day = now if m.group(1) == "azi" else now - timedelta(days=1)
        return day.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0)
    m = re.search(r"(\d{1,2}) ([a-z]+)(?: (\d{4}))?", low)
    if m and m.group(2) in MONTHS:
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            d = now.replace(year=year, month=MONTHS[m.group(2)], day=int(m.group(1)),
                            hour=12, minute=0, second=0, microsecond=0)
        except ValueError:
            return now - STALE
        if d > now and not m.group(3):               # „28 decembrie” văzut în ianuarie
            d = d.replace(year=d.year - 1)
        return d
    return now - STALE


def parse_card(raw: dict, now: datetime) -> Offer | None:
    if not raw.get("id") or not raw.get("href") or not raw.get("title"):
        return None
    price, cur = parse_price(raw.get("price", ""))
    city = re.sub(r"\s+", " ", raw.get("city", "")).strip() or None
    return Offer(id="p24:" + raw["id"], title=raw["title"].strip().split("\n")[0].strip(), description="",
                 url=raw["href"].split("?")[0], price=price, currency=cur,
                 created=parse_when(raw.get("date", ""), now), city=city)
