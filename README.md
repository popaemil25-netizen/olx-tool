# OLX deal finder (căutare la cerere)

Spui „caută" → se deschide un browser real, parcurge toate piețele din `config.toml`, citește cele mai noi anunțuri,
le salvează în SQLite și îți trimite (consolă + Telegram) cele cu preț mult sub mediana modelului.

```
pip install requests playwright          # folosește Chrome/Edge deja instalat, nu descarcă Chromium
copy config.example.toml config.toml     # completează bot_token + chat_id; piețele sunt în [[markets]]
cauta.bat                                # sau: python -m olx_monitor.search
```

Surse: **OLX** rulează implicit. **Facebook Marketplace** rulează doar la cerere:
`cauta.bat --sursa facebook` (sau `cauta-facebook.bat`). La prima rulare te loghezi MANUAL în fereastra deschisă (parola nu trece prin tool);
sesiunea rămâne în `browser_profile`. Implicit caută în toată țara (`facebook_location = "brasov"` + `facebook_radius_km = 500`); poți restrânge raza sau seta `facebook_cities`.
Atenție: Meta interzice colectarea automată, contul poate fi restricționat; pauzele sunt lungi (8–15 s) și se citește anunțurile din ultimele 7 zile.
Facebook nu arată ora postării, așa că „nou” = apărut pe prima pagină și încă nevăzut de tool. `--sursa olx --sursa facebook` alege explicit sursele.

**PC-uri și laptopuri** sunt piețe „la cerere” (`on_demand = true` în config: `pc-gaming`, `pc-laptopuri`), separate de `cauta.bat`.
Rulezi `cauta-pc.bat` (adaugă `--sursa facebook` etc. dacă vrei). Cheia de comparație: placa video + procesor + RAM (+ stocare la laptopuri),
sau seria modelului la ThinkPad/Latitude/EliteBook/XPS; configurațiile fără placă video sau serie recunoscută sunt respinse.
Istoricul se umple după câteva rulări, iar alertele apar după ≥ 6 anunțuri cu aceeași configurație.

Opțiuni: `--ore 12` (nou = postat în ultimele N ore), `--noi` (listează toate anunțurile noi acceptate),
`--piata console` (doar o piață), `--profil browser_profile` (cookie-urile rămân acolo; acceptă bannerul o dată).

- **Mediana** se construiește din istoricul tău (SQLite): primele rulări doar adună date, alertele apar după ≥ `min_samples` anunțuri pe model.
- **Piețe**: cuvinte-cheie, interval de preț (devine filtru și în căutarea OLX), prag, cuvinte excluse, modele recunoscute (`model_patterns`), `use_default_exclude = false` pentru a renunța la lista implicită.
- **Filtre**: fără preț real, alta monedă decât RON, preț în afara intervalului, piese/defect/blocat/iCloud/accesorii/modat; anunțurile „Reactualizat" nu sunt considerate noi.
- **Dedup**: un anunț = cel mult o alertă.
- **Politețe**: o trecere pe pagina 1 a fiecărui cuvânt-cheie, pauze 3–6 s, fără login, fără headere false; la 403/429/captcha/banner care blochează se oprește.
- Prețurile sunt cerute, nu vândute: marja e orientativă. Verifică termenii OLX; accesul automat poate fi restricționat chiar și la cerere.

Varianta API din `main.py` (`python -m olx_monitor`) e blocată de OLX (403) și nu mai e folosită.

Teste: `python -m unittest discover -s tests`
