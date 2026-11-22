"""Persistență SQLite: anunțuri, istoric prețuri, alerte trimise (dedup)."""
from __future__ import annotations

import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    title TEXT, url TEXT, city TEXT,
    price REAL, model_key TEXT,
    created_ts INTEGER, first_seen INTEGER NOT NULL,
    status TEXT NOT NULL,          -- 'ok' | 'rejected'
    reject_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_hist ON offers(market, model_key, status, first_seen);
CREATE TABLE IF NOT EXISTS alerts (
    offer_id TEXT PRIMARY KEY,
    sent_ts INTEGER NOT NULL,
    price REAL, median REAL, pct_below REAL
);
"""


class DB:
    def __init__(self, path: str):
        self.c = sqlite3.connect(path)
        self.c.executescript(SCHEMA)

    def is_known(self, offer_id: str) -> bool:
        return self.c.execute("SELECT 1 FROM offers WHERE id=?", (offer_id,)).fetchone() is not None

    def insert_offer(self, o, market: str, model_key, status: str, reason, now=None):
        self.c.execute(
            "INSERT OR IGNORE INTO offers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (o.id, market, o.title, o.url, o.city, o.price, model_key,
             int(o.created.timestamp()) if o.created else None,
             int(now or time.time()), status, reason),
        )
        self.c.commit()

    def history_prices(self, market: str, model_key: str, days: int, exclude_id: str, now=None,
                       exclude_shops: bool = False) -> list[float]:
        from .pricing import is_shop_title
        since = int(now or time.time()) - days * 86400
        rows = self.c.execute(
            "SELECT price, title FROM offers WHERE market=? AND model_key=? AND status='ok' "
            "AND first_seen>=? AND id!=?", (market, model_key, since, exclude_id)).fetchall()
        return [p for p, t in rows if not (exclude_shops and is_shop_title(t))]

    def already_alerted(self, offer_id: str) -> bool:
        return self.c.execute("SELECT 1 FROM alerts WHERE offer_id=?", (offer_id,)).fetchone() is not None

    def record_alert(self, offer_id: str, price, median, pct):
        self.c.execute("INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?)",
                       (offer_id, int(time.time()), price, median, pct))
        self.c.commit()
