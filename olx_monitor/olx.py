"""Client pentru endpoint-ul public /api/v1/offers/ (fără autentificare)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)


class Blocked(Exception):
    """403/401 — nu insistăm și nu ocolim; oprim monitorizarea."""


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"429, retry după {retry_after}s")
        self.retry_after = retry_after


@dataclass
class Offer:
    id: str
    title: str
    description: str
    url: str
    price: float | None      # None = fără preț real (negociabil/schimb/gratuit/lipsă)
    currency: str | None
    created: datetime | None
    city: str | None


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def parse_offer(d: dict) -> Offer:
    price = currency = None
    for p in d.get("params") or []:
        if p.get("key") == "price":
            v = p.get("value") or {}
            # „arranged”/„exchange”/„free” = fără preț real
            if v.get("type", "price") == "price" and v.get("value") is not None:
                price = float(v["value"])
                currency = v.get("currency")
            break
    loc = d.get("location") or {}
    return Offer(
        id=str(d["id"]),
        title=(d.get("title") or "").strip(),
        description=(d.get("description") or "").strip(),
        url=d.get("url") or "",
        price=price,
        currency=currency,
        created=_parse_time(d.get("created_time") or d.get("last_refresh_time")),
        city=(loc.get("city") or {}).get("name"),
    )


class OlxClient:
    def __init__(self, base_url: str, user_agent: str):
        self.base_url = base_url
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def fetch(self, query: str, category_id=None, city_id=None, limit=40, offset=0) -> list[Offer]:
        params = {"offset": offset, "limit": limit, "sort_by": "created_at:desc"}
        if query:
            params["query"] = query
        if category_id:
            params["category_id"] = category_id
        if city_id:
            params["city_id"] = city_id
        r = self.s.get(self.base_url, params=params, timeout=20)
        if r.status_code in (401, 403):
            raise Blocked(f"HTTP {r.status_code} de la OLX")
        if r.status_code == 429:
            raise RateLimited(int(r.headers.get("Retry-After", 300)))
        r.raise_for_status()
        out = []
        for d in r.json().get("data", []):
            try:
                out.append(parse_offer(d))
            except (KeyError, ValueError, TypeError):
                log.warning("anunț nerecunoscut, sărit: %s", str(d)[:120])
        return out
