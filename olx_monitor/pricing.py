"""Identificare model + mediană + evaluare „sub piață”."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .filters import _norm

# Fiecare pattern trebuie să aibă un grup de captură = numele modelului.
DEFAULT_PATTERNS = [
    r"(iphone\s?se(?:\s?20(?:16|20|22))?)",                        # SE: generațiile diferă mult ca preț
    r"(iphone\s?(?:x[rs]?|1[0-9]|[5-9])(?:e\b)?(?:\s?(?:pro\s?max|pro|plus|max|mini|air))?)",
    r"(galaxy\s?(?:s|a|m|z\s?(?:flip|fold))\s?\d{1,2}(?:\s?(?:ultra|plus|fe|\+))?)",
    r"((?:redmi|poco)\s?(?:note\s?)?[a-z]?\d{1,2}[a-z]?(?:\s?pro)?)",
    r"(pixel\s?\d{1,2}(?:\s?(?:pro|a|xl))?)",
]
_STORAGE = re.compile(r"\b(\d{1,4})\s?(gb|tb)\b")


def _norm_feature(v: str) -> str:
    """„ryzen5 5600”/„i5-12400f”/„32 gb” -> formă unică, ca istoricul să nu se spargă în chei diferite."""
    v = re.sub(r"(\d)\s+(gb|tb)\b", r"\1\2", v)
    v = re.sub(r"\bryzen\s?(\d)\s?", r"ryzen \1 ", v)
    v = re.sub(r"\b(i[3579])[\s-]?(\d)", r"\1 \2", v)
    return re.sub(r"\s+", " ", v).strip()


def model_key(title: str, extra_patterns: list[str] | None = None,
              features: list[list[str]] | None = None, use_storage: bool = True) -> str | None:
    """features: listă de grupuri de regex-uri; din fiecare grup se ia primul care se potrivește
    (primul grup de captură) și se adaugă la cheie. Ex. [[chip, an], [mărime]] => „macbook pro m1 13”."""
    t = re.sub(r"play\s?station\s?", "ps", _norm(title))   # „playstation 5” == „ps5”
    for pat in (extra_patterns or []) + DEFAULT_PATTERNS:
        prefix = ""
        if " :: " in pat:                       # „prefix :: regex” = pune un prefix fix în cheie
            prefix, pat = pat.split(" :: ", 1)
        m = re.search(pat, t)
        if m:
            model = re.sub(r"\s+", " ", prefix + " " + " ".join(g for g in m.groups() if g)).strip()   # toate grupurile = numele modelului
            model = re.sub(r"^(iphone|galaxy|pixel)(\d)", r"\1 \2", model)
            for group in features or []:
                for fpat in group:
                    fm = re.search(fpat, t)
                    if fm:
                        model += " " + _norm_feature(fm.group(1))
                        break
            # stocarea: o valoare plauzibilă (>=32 GB sau TB); RAM-ul mic e ignorat
            storage = ""
            for n, unit in (_STORAGE.findall(t) if use_storage else []):
                gb = int(n) * (1024 if unit == "tb" else 1)
                if gb >= 32:
                    storage = f" {n}{unit}"
                    break
            return model + storage
    return None


# Semne că anunțul e de la magazin/amanet/service (prețuri mari, cu garanție) => nu intră în istoricul de referință
_SHOP = [
    re.compile(r"\b(amanet\w*|magazin\w*|service|srl|second\s?hand|secondhand|rate|in rate|credit)\b"),
    re.compile(r"\bgarantie\s+\d+\s*(luni|ani|zile)\b|\b\d+\s*(luni|ani)\s+garantie\b|\bgarantie\b.*\b\d+\s*(luni|ani)\b"),
    re.compile(r"#\s?\d{3,6}\b|\(ag\.?\s?\d+|\bcod\s*(produs)?\s*[:\-]?\s*\w*\d{3,}"),
    re.compile(r"\.(ro|com)\b"),
]


def is_shop_title(title: str) -> bool:
    t = _norm(title or "")
    if t.count(" | ") >= 2 or t.count(" / ") >= 2:       # „iPhone 13 | 128 GB | 100% baterie | ...”
        return True
    return any(p.search(t) for p in _SHOP)


OUTLIER_LOW = 0.5   # valorile sub 50% din mediană nu intră în prețul de referință


def percentile(values: list[float], p: float) -> float:
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


@dataclass
class Verdict:
    median: float          # mediana istoricului (doar informativ)
    samples: int
    pct_below: float       # față de prețul de referință (percentila aleasă, implicit 35)
    reference: float = 0.0     # „preț realist de revânzare”
    profit: float = 0.0        # referință − preț cerut, în RON


def evaluate(price: float, history: list[float], min_samples: int, ref_percentile: float = 50.0) -> Verdict | None:
    if len(history) < min_samples:
        return None
    med0 = statistics.median(history)
    history = [x for x in history if x >= OUTLIER_LOW * med0]   # accesorii/jocuri/clone/anunțuri greșite trag referința în jos
    if len(history) < min_samples:
        return None
    med = statistics.median(history)
    ref = percentile(history, ref_percentile)
    if med <= 0 or ref <= 0:
        return None
    return Verdict(median=med, samples=len(history), pct_below=(ref - price) / ref * 100,
                   reference=ref, profit=ref - price)
