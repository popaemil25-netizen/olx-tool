from __future__ import annotations

import argparse
import logging
import random
import re
import time
from datetime import datetime, timezone

from . import config as cfgmod
from .db import DB
from .filters import reject_reason
from .olx import Blocked, OlxClient, RateLimited
from .pricing import evaluate, model_key
from .telegram import Telegram, format_alert

log = logging.getLogger("olx_monitor")


def process(o, market, db: DB, tg: Telegram, alert: bool = True, now: float | None = None) -> str:
    """Procesează un anunț nou. Întoarce: 'known'|'rejected'|'stored'|'alerted'."""
    now = now or time.time()
    if db.is_known(o.id):
        return "known"
    reason = reject_reason(o, market)
    key = model_key(o.title, market.model_patterns, market.key_features, market.use_storage)
    if reason is None and key is None:
        reason = "model nerecunoscut"
    if reason is None and market.require_storage and not re.search(r"\d(gb|tb)$", key):
        reason = "stocare necunoscută"
    if reason:
        db.insert_offer(o, market.name, key, "rejected", reason, now)
        return "rejected"

    # mediana se calculează din istoric, fără anunțul curent
    hist = db.history_prices(market.name, key, market.history_days, o.id, now, market.exclude_shops)
    db.insert_offer(o, market.name, key, "ok", None, now)
    if not alert:
        return "stored"
    fresh = o.created is None or (now - o.created.timestamp()) <= market.max_age_minutes * 60
    v = evaluate(o.price, hist, market.min_samples, market.ref_percentile)
    if (fresh and v and v.pct_below >= market.threshold_pct and v.profit >= market.min_profit
            and not db.already_alerted(o.id)):
        if tg.send(format_alert(o, market.name, key, v, market.threshold_pct)):
            db.record_alert(o.id, o.price, v.reference, v.pct_below)
            return "alerted"
    return "stored"


def run_market(client: OlxClient, market, db, tg, cfg, alert=True, pages=None) -> dict:
    stats = {"known": 0, "rejected": 0, "stored": 0, "alerted": 0}
    for q in market.queries:
        for page in range(pages or cfg.max_pages):
            offers = client.fetch(q, market.category_id, market.city_id,
                                  cfg.page_size, page * cfg.page_size)
            if not offers:
                break
            # procesăm de la cele mai vechi la cele mai noi: istoricul crește în ordine
            page_known = 0
            for o in reversed(offers):
                r = process(o, market, db, tg, alert)
                stats[r] += 1
                page_known += r == "known"
            if page_known == len(offers):   # pagină deja văzută complet -> stop
                break
            time.sleep(random.uniform(1.5, 3.5))
        time.sleep(random.uniform(1.5, 3.5))
    return stats


def main():
    ap = argparse.ArgumentParser(description="Monitor OLX — anunțuri sub mediană")
    ap.add_argument("-c", "--config", default="config.toml")
    ap.add_argument("--bootstrap", type=int, metavar="PAGINI",
                    help="doar umple istoricul (fără alerte), N pagini/cuvânt-cheie, apoi iese")
    ap.add_argument("--once", action="store_true", help="un singur ciclu")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    cfg = cfgmod.load(a.config)
    db = DB(cfg.db_path)
    tg = Telegram(cfg.bot_token, cfg.chat_id)
    client = OlxClient(cfg.base_url, cfg.user_agent)

    backoff = 0
    while True:
        try:
            for m in cfg.markets:
                st = run_market(client, m, db, tg, cfg,
                                alert=not a.bootstrap, pages=a.bootstrap)
                log.info("[%s] %s", m.name, st)
            backoff = 0
        except Blocked as e:
            log.error("%s — opresc. Nu ocolesc protecțiile; verifică termenii OLX.", e)
            return 2
        except RateLimited as e:
            backoff = max(e.retry_after, 300)
            log.warning("%s — pauză %ss", e, backoff)
        except Exception as e:  # rețea / JSON
            backoff = min(max(backoff * 2, 120), 1800)
            log.warning("eroare %s — pauză %ss", type(e).__name__, backoff)
        if a.once or a.bootstrap:
            return 0
        time.sleep(backoff or cfg.interval_seconds + random.uniform(0, cfg.jitter_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
