#!/usr/bin/env python3
"""
Generator trend_data.json dla SONAR POKOJOWY

Buduje szereg czasowy liczby AKTYWNYCH ofert pokoi (pole stats.active z każdego
skanu) z data/scan_history.json → docs/trend_data.json.

To "indeks podaży" w stylu betonometr.pl: ile żywych ofert wynajmu pokoi w
Lublinie monitoruje szperacz w danym momencie. Każdy punkt = jeden skan.
"""

import json
from datetime import datetime
from pathlib import Path

from shared_utils import write_json_atomic, format_datetime

TITLE = "Lublin – pokoje: wynajem"
UNIT = "ofert"
DAY_MS = 86_400_000


def _to_ms(iso_string: str) -> int:
    """ISO z offsetem → epoch w milisekundach (instant)."""
    return int(datetime.fromisoformat(iso_string).timestamp() * 1000)


def build_series(history):
    """[(ms, active, iso), ...] posortowane rosnąco po czasie."""
    rows = []
    for scan in history:
        ts = scan.get('timestamp')
        active = (scan.get('stats') or {}).get('active')
        if not ts or active is None:
            continue
        try:
            rows.append((_to_ms(ts), int(active), ts))
        except (ValueError, TypeError):
            continue
    rows.sort(key=lambda r: r[0])
    return rows


def _value_at_or_before(series, target_ms):
    """Ostatnia wartość w serii o czasie <= target_ms (seria posortowana)."""
    best = None
    for ms, val in series:
        if ms <= target_ms:
            best = val
        else:
            break
    return best


def compute_deltas(series):
    """Zmiany 1D/1M/6M/1Y vs teraz. None gdy nie mamy tak starej historii."""
    if not series:
        return {}
    now_ms = series[-1][0]
    current = series[-1][1]
    first_ms = series[0][0]
    out = {}
    for label, days in (('1D', 1), ('1M', 30), ('6M', 182), ('1Y', 365)):
        target = now_ms - days * DAY_MS
        if target < first_ms:
            out[label] = None  # brak tak starych danych → front pokaże "—"
            continue
        past = _value_at_or_before(series, target)
        out[label] = (current - past) if past is not None else None
    return out


def generate_trend_data(base_dir: Path = None) -> bool:
    """data/scan_history.json → docs/trend_data.json."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent
    input_file = base_dir / 'data' / 'scan_history.json'
    output_file = base_dir / 'docs' / 'trend_data.json'

    print("🔄 Generowanie trend_data.json...")
    with open(input_file, 'r', encoding='utf-8') as f:
        history = json.load(f)

    rows = build_series(history)
    if not rows:
        print("⚠️  Brak danych w scan_history.json — pomijam trend_data.json")
        return False

    series = [[ms, val] for ms, val, _ in rows]
    values = [val for _, val in series]
    current = values[-1]
    mx, mn = max(values), min(values)
    # MAX: pierwsze wystąpienie, MIN: ostatnie (spójnie z mockupem)
    max_ts = next(ms for ms, val in series if val == mx)
    min_ts = next(ms for ms, val in reversed(series) if val == mn)
    last_iso = rows[-1][2]

    data = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'title': TITLE,
        'metric': 'active',
        'unit': UNIT,
        'current': current,
        'max': mx,
        'min': mn,
        'max_ts': max_ts,
        'min_ts': min_ts,
        'last_label': format_datetime(last_iso, '%d.%m.%Y, %H:%M'),
        'points': len(series),
        'deltas': compute_deltas(series),
        'series': series,
    }

    write_json_atomic(output_file, data)
    print(f"✅ trend_data.json: {len(series)} punktów, teraz={current}, "
          f"max={mx}, min={mn}")
    return True


if __name__ == '__main__':
    generate_trend_data()
