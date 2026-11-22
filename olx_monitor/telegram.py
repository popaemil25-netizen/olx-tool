from __future__ import annotations

import html
import logging

import requests

log = logging.getLogger(__name__)


def format_alert(o, market_name: str, model: str, v, threshold: float) -> str:
    e = html.escape
    return (
        f"🔔 <b>{e(o.title)}</b>\n"
        f"💰 <b>{o.price:,.0f} RON</b> — cu <b>{v.pct_below:.0f}%</b> sub prețul realist "
        f"({v.reference:,.0f} RON; mediană {v.median:,.0f})\n"
        f"📈 Profit orientativ: ~<b>{v.profit:,.0f} RON</b> (înainte de costuri)\n"
        f"📊 Motiv: model <i>{e(model)}</i>, {v.samples} anunțuri comparabile (fără magazine), "
        f"prag {threshold:.0f}%\n"
        f"📍 {e(o.city or '—')} · piață: {e(market_name)}\n"
        f"🔗 {e(o.url)}\n"
        f"<i>Prețuri cerute, nu vândute — marja e orientativă.</i>"
    ).replace(",", " ")


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            print("[dry-run, Telegram neconfigurat]\n" + text + "\n")
            return True
        ok = False
        for chat in [c.strip() for c in str(self.chat_id).split(",") if c.strip()]:   # mai multe chat-uri: "id1,id2"
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                          "disable_web_page_preview": False},
                    timeout=15)
                r.raise_for_status()
                ok = True
            except requests.RequestException as ex:
                log.error("Telegram a eșuat (chat %s): %s", chat, type(ex).__name__)  # fără URL (conține tokenul)
        return ok
