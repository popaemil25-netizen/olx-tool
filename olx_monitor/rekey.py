"""Recalculează model_key pentru anunțurile deja salvate (după ce schimbi model_patterns/key_features).
Rulează: python -m olx_monitor.rekey"""
from __future__ import annotations

import argparse
import sqlite3

from . import config as cfgmod
from .pricing import model_key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.toml")
    a = ap.parse_args()
    cfg = cfgmod.load(a.config)
    db = sqlite3.connect(cfg.db_path)
    changed = 0
    for m in cfg.markets:
        rows = db.execute("SELECT id, title, model_key FROM offers WHERE market=? AND status='ok'", (m.name,)).fetchall()
        for oid, title, old in rows:
            new = model_key(title or "", m.model_patterns, m.key_features, m.use_storage)
            if new and new != old:
                db.execute("UPDATE offers SET model_key=? WHERE id=?", (new, oid))
                changed += 1
    db.commit()
    print(f"chei model actualizate: {changed}")


if __name__ == "__main__":
    main()
