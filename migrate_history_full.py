"""
Migracja history → history_full (timestampy zmian cen).

Strategia (Opcja A2 ustalona z użytkownikiem):
- Dla ogłoszenia z 1 wpisem history: history_full = [{price, date: first_seen, approximated: False}]
- Dla ogłoszenia z >=2 wpisami history:
  * pierwszy wpis: date = first_seen, approximated = False
  * ostatni wpis: date = price_changed_at (lub last_seen), approximated = False
  * środkowe wpisy (jeśli są): daty rozłożone równomiernie, approximated = True

Zachowuje istniejące pole 'history' bez zmian (kompatybilność wsteczna).
"""

import json
from datetime import datetime
from pathlib import Path
import shutil


def parse_iso(s: str) -> datetime:
    """Parsuje ISO 8601 string do datetime."""
    return datetime.fromisoformat(s)


def build_history_full(offer: dict) -> list:
    """Buduje history_full z dostępnych danych ogłoszenia."""
    history = offer.get('price', {}).get('history', [])
    if not isinstance(history, list) or not history:
        # Brak historii — użyj current jako jedyny wpis
        current = offer.get('price', {}).get('current')
        if current is None:
            return []
        return [{
            'price': current,
            'date': offer.get('first_seen', ''),
            'approximated': False
        }]
    
    first_seen = offer.get('first_seen', '')
    
    # Data ostatniej zmiany ceny — preferuj price_changed_at, fallback last_seen
    last_change_date = (
        offer.get('price', {}).get('price_changed_at')
        or offer.get('last_seen')
        or first_seen
    )
    
    if len(history) == 1:
        # Tylko jedna cena, nigdy się nie zmieniła
        return [{
            'price': history[0],
            'date': first_seen,
            'approximated': False
        }]
    
    # >=2 wpisy: pierwszy w first_seen, ostatni w price_changed_at
    result = []
    
    try:
        t_start = parse_iso(first_seen)
        t_end = parse_iso(last_change_date)
        if t_end <= t_start:
            # Niespójne daty — fallback: oba w first_seen
            t_end = t_start
        total_secs = (t_end - t_start).total_seconds()
    except (ValueError, TypeError):
        # Fallback: nie znamy dat, dajemy wszystko na first_seen
        return [
            {'price': p, 'date': first_seen, 'approximated': (i != 0 and i != len(history) - 1)}
            for i, p in enumerate(history)
        ]
    
    n = len(history)
    for i, price in enumerate(history):
        if i == 0:
            date_str = first_seen
            approximated = False
        elif i == n - 1:
            date_str = last_change_date
            approximated = False
        else:
            # Równomiernie rozłóż między t_start a t_end
            # i = 1, 2, ..., n-2 → ułamek i/(n-1)
            frac = i / (n - 1)
            delta_secs = total_secs * frac
            t_mid = t_start.fromtimestamp(t_start.timestamp() + delta_secs, tz=t_start.tzinfo)
            date_str = t_mid.isoformat()
            approximated = True
        
        result.append({
            'price': price,
            'date': date_str,
            'approximated': approximated
        })
    
    return result


def migrate(data_path: str = 'data/offers.json', dry_run: bool = False):
    path = Path(data_path)
    with open(path) as f:
        data = json.load(f)
    
    offers = data['offers']
    migrated = 0
    skipped = 0
    
    for offer in offers:
        price_obj = offer.get('price', {})
        if 'history_full' in price_obj:
            skipped += 1
            continue
        
        history_full = build_history_full(offer)
        if history_full:
            price_obj['history_full'] = history_full
            migrated += 1
    
    print(f"Migracja: {migrated} ofert zmigrowanych, {skipped} pominiętych (już miały history_full)")
    print(f"Razem ofert: {len(offers)}")
    
    # Statystyki: ile ma realnie >1 wpis
    with_multi = sum(1 for o in offers if len(o.get('price', {}).get('history_full', [])) > 1)
    with_approximated = sum(
        1 for o in offers 
        if any(h.get('approximated') for h in o.get('price', {}).get('history_full', []))
    )
    print(f"Z >1 wpisem ceny: {with_multi}")
    print(f"Z przybliżonymi datami środkowymi: {with_approximated}")
    
    if dry_run:
        print("\n[DRY RUN] Nie zapisuję")
        return
    
    # Backup
    backup_path = path.parent / f"{path.stem}.backup_before_history_full{path.suffix}"
    shutil.copy(path, backup_path)
    print(f"Backup: {backup_path}")
    
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Zapisano: {path}")


if __name__ == '__main__':
    import sys
    dry = '--dry-run' in sys.argv
    migrate(dry_run=dry)
