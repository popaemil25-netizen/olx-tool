"""Încărcare configurație din TOML (Python 3.11+)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field


@dataclass
class Market:
    name: str
    queries: list[str]
    category_id: int | None = None
    city_id: int | None = None
    threshold_pct: float = 25.0          # alertă dacă prețul e cu >= x% sub mediană
    min_samples: int = 8                 # nr. minim de anunțuri în istoric pentru mediană
    history_days: int = 30
    max_age_minutes: int = 30            # alertăm doar anunțuri „proaspete”
    min_price: float = 150.0             # sub asta = preț nereal / accesoriu
    max_price: float = 20000.0
    exclude_words: list[str] = field(default_factory=list)
    ref_percentile: float = 35.0         # prețul „realist” = această percentilă din istoric (50 = mediana)
    min_profit: float = 150.0            # alertă doar dacă (preț realist − preț cerut) >= x RON
    exclude_shops: bool = True           # anunțurile de magazin/amanet/garanție nu intră în istoricul de referință
    use_storage: bool = True             # false = ignoră GB/TB din titlu (procesoare, ceasuri, aspiratoare)
    require_storage: bool = False        # true = respinge anunțurile fără GB/TB în titlu (nu pot fi comparate)
    reject_converted_prices: bool = True   # respinge prețuri cu zecimale ciudate (ex. 1871.89) = anunțuri în EUR convertite de OLX
    facebook: bool = True                # false = piața nu se caută pe Facebook (puține rezultate)
    on_demand: bool = False              # true = rulează doar când o ceri cu --piata (ex. cauta-pc.bat)
    use_default_exclude: bool = True     # false = doar exclude_words proprii (ex. ceasuri, scule)
    model_patterns: list[str] = field(default_factory=list)
    key_features: list[list[str]] = field(default_factory=list)   # vezi pricing.model_key


@dataclass
class Config:
    bot_token: str
    chat_id: str
    base_url: str
    interval_seconds: int
    jitter_seconds: int
    page_size: int
    max_pages: int
    user_agent: str
    db_path: str
    facebook_location: str
    facebook_radius_km: int
    facebook_cities: list[str]
    markets: list[Market]


def load(path: str) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    tg = raw.get("telegram", {})
    poll = raw.get("poll", {})
    markets = [Market(**m) for m in raw.get("markets", [])]
    if not markets:
        raise SystemExit("Config invalid: definește cel puțin un [[markets]].")
    return Config(
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", tg.get("bot_token", "")),
        chat_id=os.environ.get("TELEGRAM_CHAT_ID", ",".join(
            str(x) for x in (tg.get("chat_id", "") if isinstance(tg.get("chat_id", ""), list)
                             else [tg.get("chat_id", "")]))),
        base_url=raw.get("olx", {}).get("base_url", "https://www.olx.ro/api/v1/offers/"),
        interval_seconds=max(60, int(poll.get("interval_seconds", 90))),
        jitter_seconds=int(poll.get("jitter_seconds", 15)),
        page_size=min(50, int(poll.get("page_size", 40))),
        max_pages=int(poll.get("max_pages", 2)),
        user_agent=poll.get("user_agent", "olx-deal-monitor/0.1 (uz personal)"),
        db_path=raw.get("db_path", "olx.sqlite3"),
        facebook_location=raw.get("facebook_location", ""),
        facebook_radius_km=int(raw.get("facebook_radius_km", 0)),
        facebook_cities=list(raw.get("facebook_cities", [])),
        markets=markets,
    )
