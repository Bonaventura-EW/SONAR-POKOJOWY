#!/usr/bin/env python3
"""
Dzienny rozkład cen aktywnych ofert — źródło karty „💰 Rozkład cen" na Indeksie.

Dlaczego osobny magazyn
-----------------------
`offers.json` zna tylko BIEŻĄCĄ cenę i flagę `active` każdej oferty, więc
odpowiedź na pytanie „jakie ceny miał rynek 12.08" trzeba by rekonstruować
z `first_seen`/`last_seen` — a ta rekonstrukcja zawyża przeszłość (oferty
z przerwą w życiu sprzed 03.09.2026 liczą się jako żywe przez całą przerwę,
patrz `index_history`). Zamiast zgadywać, każdy skan zapisuje tu, ile
aktywnych ofert miało jaką cenę.

Format dnia
-----------
`days[YYYY-MM-DD] = {active, prices: {"800": 54, ...}, ts}` — DOKŁADNE ceny
z licznością, bez kubełkowania i bez progu 1500 zł. Szerokość słupka i próg
to decyzja prezentacji (trend_generator), więc magazyn nie musi się zmieniać,
gdy zmieni się wykres.

Konwencja dnia: ta sama co w `index_history` — dzień opisuje skan z NAJWIĘKSZĄ
liczbą aktywnych ofert (skan częściowy nie podmieni pełniejszego obrazu dnia).
Dzięki temu `active` tutaj i w `index_history` to ten sam odczyt.

Historia sprzed wdrożenia (od 16.05.2026) jest odtworzona z rewizji
`data/offers.json` w historii gita — patrz `scripts/backfill_price_history.py`.
Te wpisy mają `backfilled: true`.
"""

import json
from datetime import date, datetime
from pathlib import Path

from shared_utils import DATA_DIR, write_json_atomic

PRICE_HISTORY_FILE = DATA_DIR / 'price_history.json'

NOTE = ("Dzienny rozklad cen aktywnych ofert: {cena: liczba ofert} ze skanu z najwieksza "
        "liczba aktywnych ofert danego dnia (ta sama konwencja co index_history). "
        "Zrodlo karty 'Rozklad cen' na trend.html. Nie edytowac recznie.")


class PriceHistoryError(RuntimeError):
    """Plik istnieje, ale nie da się go odczytać (ucięty zapis, konflikt gita)."""


def _path(base_dir=None) -> Path:
    return PRICE_HISTORY_FILE if base_dir is None else Path(base_dir) / 'data' / 'price_history.json'


def _price_key(price) -> str:
    """Klucz JSON-a dla ceny: 800 → "800", 849.5 → "849.5"."""
    return str(int(price)) if float(price).is_integer() else str(price)


def snapshot(offers) -> dict:
    """Stan rynku w chwili skanu: liczba aktywnych ofert i rozkład ich cen.

    Oferta bez sensownej ceny liczy się do `active`, ale nie do `prices`.
    """
    active = 0
    prices = {}
    for o in offers:
        if not o.get('active'):
            continue
        active += 1
        price = o.get('price')
        if isinstance(price, dict):
            price = price.get('current')
        if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0:
            key = _price_key(price)
            prices[key] = prices.get(key, 0) + 1
    return {'active': active, 'prices': dict(sorted(prices.items(), key=lambda kv: float(kv[0])))}


def load(base_dir=None, strict: bool = False) -> dict:
    """Cała zawartość pliku. Brak pliku = pusty szkielet; plik nieczytelny przy
    `strict=True` = PriceHistoryError (inaczej `record()` zapisałby na nim sam
    dzisiejszy dzień i skasował historię — ta sama pułapka co w index_history)."""
    path = _path(base_dir)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {'note': NOTE, 'days': {}}
    except (OSError, json.JSONDecodeError) as exc:
        if strict:
            raise PriceHistoryError(f"{path}: {exc}") from exc
        return {'note': NOTE, 'days': {}}
    if not isinstance(data, dict) or not isinstance(data.get('days'), dict):
        if strict:
            raise PriceHistoryError(f"{path}: brak slownika 'days'")
        return {'note': NOTE, 'days': {}}
    return data


def save(data: dict, base_dir=None) -> None:
    """Zapis atomowy. Odmawia zastąpienia niepustej (albo nieczytelnej) historii pustką."""
    days = data.get('days') or {}
    if not days:
        try:
            existing = load(base_dir, strict=True).get('days') or {}
        except PriceHistoryError as exc:
            raise PriceHistoryError(
                f"odmowa zapisu pustki: nie da sie odczytac istniejacej historii ({exc})") from exc
        if existing:
            raise PriceHistoryError(f"odmowa zapisu: {len(existing)} dni historii mialoby zniknac")
    data['note'] = NOTE
    data['generated_at'] = datetime.now().astimezone().isoformat()
    data['days'] = {d: days[d] for d in sorted(days)}
    write_json_atomic(_path(base_dir), data)


def merge_snapshot(days: dict, day: str, snap: dict, ts: str, backfilled: bool = False) -> bool:
    """Wpisuje `snap` jako stan dnia, jeśli ma WIĘCEJ aktywnych ofert niż zapisany.

    Przy remisie zostaje wcześniejszy odczyt (jak `index_history.record`, który
    trzyma `ts` pierwszego maksimum). Zwraca True, gdy dzień się zmienił.
    """
    entry = days.get(day)
    if entry and snap['active'] <= (entry.get('active') or 0):
        return False
    new = {'active': snap['active'], 'prices': snap['prices'], 'ts': ts}
    if backfilled:
        new['backfilled'] = True
    days[day] = new
    return True


def record(offers, timestamp: str = None, base_dir=None) -> dict:
    """Dopisuje rozkład cen ze skanu do dnia wynikającego z `timestamp`."""
    ts = timestamp or datetime.now().astimezone().isoformat()
    try:
        day = datetime.fromisoformat(ts).date().isoformat()
    except (ValueError, TypeError):
        day = date.today().isoformat()

    try:
        data = load(base_dir, strict=True)
    except PriceHistoryError as exc:
        # Lepiej zgubić jeden odczyt niż nadpisać historię pustką.
        print(f"   ⚠️  price_history.json nieczytelny — NIE zapisuję dnia ({exc})")
        return {}
    snap = snapshot(offers)
    if not snap['active']:
        return {}
    if merge_snapshot(data['days'], day, snap, ts):
        save(data, base_dir)
    return data['days'].get(day, {})


def daily(base_dir=None) -> dict:
    """{date: {active, prices: {float: count}}} — wpisy czytelne, ceny jako liczby."""
    out = {}
    for key, entry in load(base_dir)['days'].items():
        try:
            day = date.fromisoformat(key)
        except (ValueError, TypeError):
            continue
        prices = {}
        for p, c in (entry.get('prices') or {}).items():
            try:
                prices[float(p)] = int(c)
            except (ValueError, TypeError):
                continue
        out[day] = {'active': entry.get('active'), 'prices': prices}
    return out
