"""Filtre: întoarce motivul respingerii sau None dacă anunțul e acceptat."""
from __future__ import annotations

import re

from .config import Market
from .olx import Offer

DEFAULT_EXCLUDE = [
    "piese", "pentru piese", "defect", "defecta", "blocat", "icloud", "contract",
    "display spart", "ecran spart", "placa de baza", "dezmembrez", "schimb",
    "husa", "huse", "folie", "geam", "incarcator", "cablu", "carcasa", "suport",
    "casti", "airpods", "adaptor", "baterie", "capac", "cutie goala", "replica",
    "copie", "dummy", "topcase", "model de expozitie", "atrapa", "cumpar", "caut", "vandut", "vandută", "rezervat",
]
# „nu este defect”, „fără icloud” etc. nu trebuie să respingă anunțul
_NEGATION = re.compile(r"(fara|fără|nu e|nu este|nu are|not|no)\s+(\w+\s+){0,2}$")


_NORMAL_CENTS = {0.0, 0.5, 0.9, 0.95, 0.99}


def looks_converted(price: float) -> bool:
    """OLX arată anunțurile în EUR convertite în lei (382 € -> 1871.89). Prețurile „normale” au .00/.50/.90/.99."""
    return round(price % 1, 2) not in _NORMAL_CENTS


def _norm(s: str) -> str:
    s = s.lower()
    for a, b in (("ă", "a"), ("â", "a"), ("î", "i"), ("ș", "s"), ("ş", "s"), ("ț", "t"), ("ţ", "t")):
        s = s.replace(a, b)
    return s


def _hit(text: str, words: list[str], check_negation: bool) -> str | None:
    for w in words:
        for m in re.finditer(r"\b" + re.escape(_norm(w)) + r"\b", text):
            if check_negation and _NEGATION.search(text[max(0, m.start() - 20):m.start()]):
                continue
            return w
    return None


def reject_reason(o: Offer, m: Market) -> str | None:
    if o.price is None:
        return "fără preț real"
    if o.currency and o.currency.upper() != "RON":
        return f"monedă {o.currency}"
    if m.reject_converted_prices and looks_converted(o.price):
        return f"preț convertit din EUR ({o.price:.2f})"
    if o.price < m.min_price:
        return f"preț sub minim ({o.price:.0f})"
    if o.price > m.max_price:
        return f"preț peste maxim ({o.price:.0f})"
    words = (DEFAULT_EXCLUDE if m.use_default_exclude else []) + m.exclude_words
    title = _norm(o.title)
    w = _hit(title, words, check_negation=False)
    if w:
        return f"titlu conține „{w}”"
    w = _hit(_norm(o.description), words, check_negation=True)
    if w:
        return f"descriere conține „{w}”"
    return None
