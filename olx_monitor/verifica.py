"""Verificare manuală: dai titlul și prețul unui anunț găsit oriunde (Okazii, Facebook, Publi24...),
iar tool-ul îl compară cu mediana din istoricul tău. Nu accesează niciun site.

  python -m olx_monitor.verifica "MacBook Air M1 256GB" 1500
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from . import config as cfgmod
from .db import DB
from .filters import reject_reason
from .olx import Offer
from .pricing import evaluate, model_key


def main():
    import sys
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Compară un anunț (titlu + preț) cu istoricul")
    ap.add_argument("titlu")
    ap.add_argument("pret", type=float, help="preț în RON")
    ap.add_argument("-c", "--config", default="config.toml")
    ap.add_argument("--marja", type=float, default=None, help="marja dorită sub mediană, în %% (implicit: pragul pieței)")
    a = ap.parse_args()

    cfg = cfgmod.load(a.config)
    db = DB(cfg.db_path)
    o = Offer("manual", a.titlu, "", "", a.pret, "RON", datetime.now(timezone.utc), None)

    for m in cfg.markets:
        key = model_key(a.titlu, m.model_patterns, m.key_features, m.use_storage)
        if not key:
            continue
        print(f"Piață: {m.name}   Model: {key}")
        why = reject_reason(o, m)
        if why:
            print(f"⚠ Anunțul ar fi respins de filtre: {why}")
        allp = db.history_prices(m.name, key, m.history_days, "manual")
        hist = db.history_prices(m.name, key, m.history_days, "manual", exclude_shops=m.exclude_shops)
        if not hist:
            hist = allp
        v = evaluate(a.pret, hist, 1, m.ref_percentile)
        if not v:
            print("Nu am istoric pentru acest model. Rulează „cauta” de câteva ori ca să se umple.")
            return 0
        thr = a.marja if a.marja is not None else m.threshold_pct
        sign = "sub" if v.pct_below >= 0 else "PESTE"
        print(f"Preț cerut:  {a.pret:,.0f} lei".replace(",", " "))
        print(f"Mediană:     {v.median:,.0f} lei  ({v.samples} anunțuri, {min(hist):,.0f}–{max(hist):,.0f})".replace(",", " "))
        print(f"Preț realist (percentila {m.ref_percentile:.0f}; fără magazine): {v.reference:,.0f} lei".replace(",", " "))
        print(f"Diferență:   {abs(v.pct_below):.0f}% {sign} prețul realist  (profit orientativ ~{v.profit:,.0f} lei)".replace(",", " "))
        print(f"Preț țintă pentru {thr:.0f}% sub prețul realist: {v.reference * (1 - thr / 100):,.0f} lei".replace(",", " "))
        if v.samples < m.min_samples:
            print(f"⚠ Doar {v.samples} anunțuri în istoric (minim recomandat {m.min_samples}): mediana e nesigură.")
        elif v.pct_below >= thr and v.profit >= m.min_profit:
            print("✔ Trece de prag.")
        elif v.pct_below >= thr:
            print(f"✘ Procentul trece, dar profitul (~{v.profit:,.0f} lei) e sub minimul de {m.min_profit:,.0f} lei.".replace(",", " "))
        else:
            print("✘ Nu trece de prag.")
        print("Prețuri cerute, nu vândute: marja e orientativă.")
        return 0
    print("Nu recunosc modelul din titlu. Adaugă un model_patterns pentru el în config.toml.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
