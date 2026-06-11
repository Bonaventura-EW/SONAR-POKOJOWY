#!/usr/bin/env python3
"""
Wspólne narzędzia dla pipeline'u i generatorów.

Trzy rzeczy, które wcześniej były skopiowane w wielu plikach:
- ścieżki zakotwiczone o położenie repo (niezależne od cwd),
- strefa czasowa Europe/Warsaw,
- formatowanie dat ISO → format polski frontendu,
- atomowy zapis JSON (temp + rename) — chroni offers.json i pliki
  docs/*.json przed ucięciem przy crashu w połowie zapisu.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytz

# Ścieżki niezależne od katalogu roboczego (skrypty bywają odpalane
# i z src/, i z roota repo)
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / 'data'
DOCS_DIR = REPO_ROOT / 'docs'

OFFERS_FILE = DATA_DIR / 'offers.json'
GEOCODING_CACHE_FILE = DATA_DIR / 'geocoding_cache.json'
SCAN_HISTORY_FILE = DATA_DIR / 'scan_history.json'

TZ = pytz.timezone('Europe/Warsaw')


def format_datetime(iso_string, fmt='%d.%m.%Y %H:%M'):
    """
    ISO datetime → format polski frontendu.
    '2026-03-01T15:51:38.344630+01:00' → '01.03.2026 15:51'
    Przy błędzie parsowania zwraca wejście bez zmian.
    """
    if not iso_string:
        return ''
    try:
        dt_str = iso_string.split('+')[0].replace('Z', '')
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime(fmt)
    except (ValueError, AttributeError):
        return iso_string


def write_json_atomic(filepath, data, indent=2):
    """
    Atomowy zapis JSON: pełny zapis do pliku tymczasowego w tym samym
    katalogu, potem os.replace (atomowe na POSIX). Czytelnik nigdy nie
    zobaczy uciętego pliku.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, suffix='.json.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
