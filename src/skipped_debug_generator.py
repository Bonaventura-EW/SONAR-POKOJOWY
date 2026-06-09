"""
Skipped Debug Generator - generuje statyczną stronę docs/skipped_debug.html
z listą ofert pominiętych w ostatnim skanie (no_address / no_coords / duplicate / no_price).

Strona TYMCZASOWA - do diagnostyki błędów parsera/geokodera.
Po naprawie głównych problemów można ją usunąć.

Źródło danych: data/skipped_offers_sample.json (zapisywany przez main.py podczas skanu).
"""

import json
import html
from pathlib import Path
from datetime import datetime


# Mapowanie kategorii → metadane wyświetlania
CATEGORY_LABELS = {
    'no_address': {
        'label': 'Brak adresu',
        'short': 'brak adresu',
        'color': '#ef4444',
        'sub': 'parser nie znalazł żadnej ulicy w opisie',
    },
    'no_coords': {
        'label': 'Brak współrzędnych',
        'short': 'brak współrzędnych',
        'color': '#8b5cf6',
        'sub': 'parser znalazł adres, geokoder nie',
    },
    'duplicate': {
        'label': 'Duplikaty',
        'short': 'duplikat',
        'color': '#06b6d4',
        'sub': 'ten sam pokój 2× w wynikach',
    },
    'no_price': {
        'label': 'Brak ceny',
        'short': 'brak ceny',
        'color': '#f59e0b',
        'sub': 'parser nie wyciągnął ceny',
    },
    'excluded': {
        'label': 'Wykluczone (filtr)',
        'short': 'wykluczone',
        'color': '#64748b',
        'sub': 'odrzucone przez filtr fraz (np. domek/willa)',
    },
}


def _esc(text) -> str:
    """HTML-escape z fallbackiem na pusty string dla None/non-str."""
    if text is None:
        return ''
    return html.escape(str(text), quote=True)


def _format_url_display(url: str) -> str:
    """Skróć URL do wyświetlenia (bez schemy)."""
    if not url:
        return '(brak URL)'
    return url.replace('https://', '').replace('http://', '')


def _build_offer_card(category: str, sample: dict) -> str:
    """Buduje HTML jednej karty oferty."""
    cat_meta = CATEGORY_LABELS.get(category, CATEGORY_LABELS['no_address'])
    badge_class = category
    title = _esc(sample.get('title', '(brak tytułu)'))
    url = sample.get('url', '')
    url_esc = _esc(url)
    desc = _esc(sample.get('description_preview', ''))

    # Metadane różne per kategoria
    meta_items = []
    note = sample.get('note', '')
    parsed_addr = sample.get('address_parsed', '')

    if parsed_addr:
        meta_items.append(
            f'<span class="parsed-addr">parsed: "{_esc(parsed_addr)}"</span>'
        )
    excluded_phrase = sample.get('excluded_phrase', '')
    if excluded_phrase:
        meta_items.append(
            f'<span class="note">⚠️ fraza: "{_esc(excluded_phrase)}"</span>'
        )
    if note:
        meta_items.append(f'<span class="note">⚠️ {_esc(note)}</span>')

    meta_html = ''
    if meta_items:
        meta_html = f'<div class="offer-meta">{"".join(meta_items)}</div>'

    # Sekcja porównania duplikatów (tylko gdy category == duplicate i mamy duplicate_of)
    compare_html = ''
    if category == 'duplicate' and sample.get('duplicate_of'):
        dup_of = sample['duplicate_of']
        similarity = sample.get('similarity')
        sim_label = f'{similarity * 100:.1f}% podobne' if isinstance(similarity, (int, float)) else 'podobne'
        orig_url = dup_of.get('url', '')
        orig_url_esc = _esc(orig_url)
        orig_id_esc = _esc(dup_of.get('id', '(brak ID)'))
        orig_addr_esc = _esc(dup_of.get('address', '(brak adresu)'))
        orig_price = dup_of.get('price')
        orig_price_str = f'{orig_price} zł' if orig_price is not None else 'brak'
        this_price = (sample.get('price') if sample.get('price') is not None else None)
        this_price_str = f'{this_price} zł' if this_price is not None else 'brak'
        this_addr_esc = _esc(sample.get('address_parsed', '(brak)'))

        # Link "Odrzucone" - URL z sample
        this_url_display = _format_url_display(url)
        orig_url_display = _format_url_display(orig_url)

        compare_html = f'''
        <div class="duplicate-compare">
          <div class="duplicate-compare-title">
            🔗 Porównaj oferty
            <span class="similarity-pill">{_esc(sim_label)}</span>
          </div>
          <div class="duplicate-compare-grid">
            <div class="duplicate-side this">
              <div class="role-label">⚠️ Odrzucone (duplikat)</div>
              <strong>{title}</strong>
              <a href="{url_esc}" target="_blank" rel="noopener" class="url">{_esc(this_url_display)} ↗</a>
              <div class="meta">parsed: {this_addr_esc} · cena: {_esc(this_price_str)}</div>
            </div>
            <div class="duplicate-arrow">≈</div>
            <div class="duplicate-side original">
              <div class="role-label">✅ Pozostawione na mapie</div>
              <strong>ID: {orig_id_esc}</strong>
              <a href="{orig_url_esc}" target="_blank" rel="noopener" class="url">{_esc(orig_url_display)} ↗</a>
              <div class="meta">adres: {orig_addr_esc} · cena: {_esc(orig_price_str)}</div>
            </div>
          </div>
        </div>
        '''

    # Dla nie-duplikatów - prosty link "→ OLX"
    olx_link_html = ''
    if category != 'duplicate' and url:
        olx_link_html = f'<a href="{url_esc}" target="_blank" rel="noopener" class="offer-link">→ OLX</a>'

    desc_html = ''
    if desc:
        desc_html = f'<div class="offer-desc" onclick="this.classList.toggle(\'expanded\')">{desc}</div>'

    return f'''
    <div class="offer" data-category="{category}" data-search="{_esc((title + ' ' + desc).lower())}">
      <div class="offer-header">
        <span class="badge {badge_class}">{_esc(cat_meta['short'])}</span>
        <div class="offer-title">{title}</div>
        {olx_link_html}
      </div>
      {desc_html}
      {meta_html}
      {compare_html}
    </div>
    '''


def generate_skipped_debug_page(
    sample_path: str = "../data/skipped_offers_sample.json",
    output_path: str = "../docs/skipped_debug.html"
) -> bool:
    """
    Generuje docs/skipped_debug.html z aktualnymi próbkami pominiętych ofert.

    Returns:
        True jeśli wygenerowano stronę, False jeśli sample_path nie istnieje.
    """
    sample_file = Path(sample_path)
    if not sample_file.exists():
        print(f"⚠️  skipped_debug_generator: brak {sample_path}, pomijam generację.")
        return False

    with open(sample_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    counts = data.get('counts', {})
    samples = data.get('samples', {})
    scan_ts_raw = data.get('scan_timestamp', '')

    # Sformatuj timestamp do czytelnej postaci
    scan_ts_display = scan_ts_raw
    try:
        dt = datetime.fromisoformat(scan_ts_raw)
        scan_ts_display = dt.strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        pass

    # Liczniki dla kart
    total_samples = sum(len(s) for s in samples.values())

    # Renderuj karty
    cards_html_parts = []
    for cat_key in ('no_address', 'no_coords', 'excluded', 'duplicate', 'no_price'):
        meta = CATEGORY_LABELS[cat_key]
        count = counts.get(cat_key, 0)
        sub = meta['sub']
        cards_html_parts.append(f'''
        <div class="stat-card {cat_key}">
          <div class="label">{_esc(meta['label'])}</div>
          <div class="value">{count}</div>
          <div class="sub">{_esc(sub)}</div>
        </div>
        ''')
    cards_html = ''.join(cards_html_parts)

    # Renderuj listy ofert (per kategoria - duplikaty pierwsze bo najbardziej diagnostyczne)
    offers_html_parts = []
    for cat_key in ('duplicate', 'no_address', 'no_coords', 'excluded', 'no_price'):
        cat_samples = samples.get(cat_key, [])
        for s in cat_samples:
            offers_html_parts.append(_build_offer_card(cat_key, s))
    offers_html = ''.join(offers_html_parts)

    if not offers_html:
        offers_html = '<div class="empty">Brak danych — uruchom skan żeby wygenerować próbki.</div>'

    # Opcje filtra
    filter_options = []
    filter_options.append(f'<option value="all">Wszystkie ({total_samples} próbek)</option>')
    for cat_key in ('no_address', 'no_coords', 'excluded', 'duplicate', 'no_price'):
        meta = CATEGORY_LABELS[cat_key]
        cnt = len(samples.get(cat_key, []))
        filter_options.append(
            f'<option value="{cat_key}">{_esc(meta["label"])} ({cnt})</option>'
        )
    filter_options_html = ''.join(filter_options)

    # Pełen HTML
    html_doc = f'''<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SONAR POKOJOWY - Pominięte oferty (debug)</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fa; color: #2d3748; line-height: 1.5; }}
header {{ background: linear-gradient(120deg, #fb923c 0%, #ef4444 50%, #ec4899 100%); color: white; padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap; box-shadow: 0 2px 12px rgba(239,68,68,0.25); }}
header .sp-brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
header .sp-brand-svg {{ width: 32px; height: 32px; flex-shrink: 0; }}
header h1 {{ margin: 0; font-size: 18px; font-weight: 700; color: white; display: inline-flex; align-items: baseline; gap: 0; white-space: nowrap; }}
header h1 .sp-b {{ font-weight: 800; letter-spacing: 0.5px; }}
header h1 .sp-s {{ opacity: 0.5; margin: 0 8px; font-weight: 300; }}
header h1 .sp-p {{ font-weight: 500; opacity: 0.95; }}
header nav {{ display: flex; gap: 4px; flex-wrap: wrap; }}
header nav a {{ color: #be123c; text-decoration: none; padding: 7px 13px; border-radius: 10px; font-size: 13px; font-weight: 600; background: rgba(255,255,255,0.88); border: 1px solid rgba(255,255,255,0.4); transition: background 0.15s, box-shadow 0.15s; }}
header nav a:hover {{ background: white; }}
header nav a.active {{ background: white; color: #9f1239; border-color: #ef4444; box-shadow: 0 2px 6px rgba(190,18,60,0.25); }}
@media (max-width: 768px) {{ header {{ padding: 12px 16px; }} header h1 {{ font-size: 16px; }} header nav a {{ padding: 6px 10px; font-size: 12px; }} }}
.banner {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 24px; color: #78350f; font-size: 14px; }}
.container {{ max-width: 1400px; margin: 24px auto; padding: 0 24px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); border-left: 4px solid; }}
.stat-card.no_address {{ border-color: #ef4444; }}
.stat-card.no_price {{ border-color: #f59e0b; }}
.stat-card.no_coords {{ border-color: #8b5cf6; }}
.stat-card.duplicate {{ border-color: #06b6d4; }}
.stat-card.excluded {{ border-color: #64748b; }}
.stat-card .label {{ font-size: 12px; color: #718096; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
.stat-card .value {{ font-size: 28px; font-weight: 700; color: #2d3748; }}
.stat-card .sub {{ font-size: 12px; color: #a0aec0; margin-top: 4px; }}
.filter-bar {{ background: white; padding: 16px 24px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
.filter-bar label {{ font-weight: 600; font-size: 14px; color: #4a5568; }}
.filter-bar select, .filter-bar input {{ padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 14px; font-family: inherit; }}
.filter-bar input {{ flex: 1; min-width: 200px; }}
.timestamp {{ color: #718096; font-size: 12px; margin-left: auto; }}
.offer-list {{ background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); overflow: hidden; }}
.offer {{ padding: 16px 20px; border-bottom: 1px solid #edf2f7; }}
.offer:last-child {{ border-bottom: none; }}
.offer.hidden {{ display: none; }}
.offer-header {{ display: flex; gap: 12px; align-items: flex-start; margin-bottom: 8px; flex-wrap: wrap; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; }}
.badge.no_address {{ background: #fee2e2; color: #991b1b; }}
.badge.no_price {{ background: #fef3c7; color: #92400e; }}
.badge.no_coords {{ background: #ede9fe; color: #5b21b6; }}
.badge.duplicate {{ background: #cffafe; color: #155e75; }}
.badge.excluded {{ background: #e2e8f0; color: #334155; }}
.offer-title {{ font-weight: 600; color: #2d3748; font-size: 15px; flex: 1; min-width: 0; }}
.offer-link {{ color: #667eea; text-decoration: none; font-size: 13px; white-space: nowrap; }}
.offer-link:hover {{ text-decoration: underline; }}
.offer-desc {{ color: #4a5568; font-size: 13px; line-height: 1.6; margin-top: 4px; max-height: 60px; overflow: hidden; transition: max-height 0.3s; cursor: pointer; position: relative; }}
.offer-desc.expanded {{ max-height: 1000px; }}
.offer-meta {{ display: flex; gap: 16px; font-size: 12px; color: #718096; margin-top: 8px; flex-wrap: wrap; }}
.offer-meta .note {{ color: #d97706; font-weight: 600; }}
.offer-meta .parsed-addr {{ color: #5b21b6; font-family: monospace; }}

/* === Sekcja porównania duplikatów === */
.duplicate-compare {{
    margin-top: 12px;
    background: #f0fdfa;
    border: 1px solid #99f6e4;
    border-radius: 6px;
    padding: 12px 14px;
}}
.duplicate-compare-title {{
    font-size: 12px;
    font-weight: 700;
    color: #0f766e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}}
.duplicate-compare-grid {{
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 12px;
    align-items: center;
}}
@media (max-width: 700px) {{
    .duplicate-compare-grid {{ grid-template-columns: 1fr; }}
    .duplicate-arrow {{ transform: rotate(90deg); }}
}}
.duplicate-side {{
    background: white;
    padding: 10px 12px;
    border-radius: 4px;
    font-size: 13px;
    min-width: 0;
}}
.duplicate-side .role-label {{
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}}
.duplicate-side.this {{ border-left: 3px solid #f59e0b; }}
.duplicate-side.this .role-label {{ color: #d97706; }}
.duplicate-side.original {{ border-left: 3px solid #10b981; }}
.duplicate-side.original .role-label {{ color: #047857; }}
.duplicate-side .url {{ color: #667eea; text-decoration: none; word-break: break-all; display: block; margin-top: 4px; font-size: 12px; }}
.duplicate-side .url:hover {{ text-decoration: underline; }}
.duplicate-side .meta {{ color: #718096; font-size: 11px; margin-top: 4px; }}
.duplicate-arrow {{ font-size: 20px; color: #0d9488; font-weight: bold; text-align: center; }}
.similarity-pill {{
    display: inline-block;
    background: #0d9488;
    color: white;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}}

.empty {{ text-align: center; padding: 60px 20px; color: #a0aec0; }}
.no-results {{ text-align: center; padding: 40px 20px; color: #a0aec0; display: none; }}
.no-results.visible {{ display: block; }}
</style>
</head>
<body>

<header>
  <div class="sp-brand">
    <svg class="sp-brand-svg" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="spRb-skip" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#1a3a1a"/>
          <stop offset="100%" stop-color="#0a1a0a"/>
        </radialGradient>
        <linearGradient id="spRs-skip" x1="50%" y1="50%" x2="100%" y2="50%">
          <stop offset="0%" stop-color="#00ff00" stop-opacity="0.8"/>
          <stop offset="100%" stop-color="#00ff00" stop-opacity="0"/>
        </linearGradient>
        <mask id="spRm-skip"><circle cx="32" cy="32" r="28" fill="white"/></mask>
      </defs>
      <circle cx="32" cy="32" r="32" fill="url(#spRb-skip)"/>
      <circle cx="32" cy="32" r="30" fill="none" stroke="#00ff00" stroke-width="0.5" opacity="0.6"/>
      <circle cx="32" cy="32" r="22" fill="none" stroke="#00ff00" stroke-width="0.3" opacity="0.3"/>
      <circle cx="32" cy="32" r="14" fill="none" stroke="#00ff00" stroke-width="0.3" opacity="0.3"/>
      <line x1="32" y1="4" x2="32" y2="60" stroke="#00ff00" stroke-width="0.3" opacity="0.3"/>
      <line x1="4" y1="32" x2="60" y2="32" stroke="#00ff00" stroke-width="0.3" opacity="0.3"/>
      <g mask="url(#spRm-skip)">
        <path d="M32,32 L32,4 A28,28 0 0,1 60,32 Z" fill="url(#spRs-skip)" opacity="0.6">
          <animateTransform attributeName="transform" type="rotate" from="0 32 32" to="360 32 32" dur="3s" repeatCount="indefinite"/>
        </path>
      </g>
      <circle cx="22" cy="18" r="1.5" fill="#00ff00">
        <animate attributeName="opacity" values="0.8;0.3;0.8" dur="1.5s" repeatCount="indefinite"/>
      </circle>
    </svg>
    <h1>
      <span class="sp-b">SONAR POKOJOWY</span>
      <span class="sp-s">·</span>
      <span class="sp-p">🐛 Pominięte</span>
    </h1>
  </div>
  <nav>
    <a href="index.html">🗺️ Mapa</a>
    <a href="analytics.html">📈 Analityka</a>
    <a href="monitoring.html">📊 Monitoring</a>
    <a href="market_analysis.html">🔍 Analiza Rynku</a>
    <a href="top5.html">🏆 Top 5</a>
    <a href="ostatnie.html">🆕 Ostatnie</a>
    <a href="profile_tracker.html">🏢 Firmy</a>
    <a href="skipped_debug.html" class="active">🐛 Pominięte</a>
  </nav>
</header>

<div class="banner">
  ⚠️ <strong>Strona tymczasowa</strong> do analizy błędów parsera. Pokazuje oferty które scraper pobrał ale nie trafiły na mapę.
  Zostanie usunięta po naprawie głównych problemów.
</div>

<div class="container">
  <div class="stats-grid">
    {cards_html}
  </div>

  <div class="filter-bar">
    <label for="category-filter">Kategoria:</label>
    <select id="category-filter">
      {filter_options_html}
    </select>
    <label for="search-input">Szukaj:</label>
    <input type="text" id="search-input" placeholder="filtruj po tytule/opisie/URL...">
    <span class="timestamp">Aktualizacja: {_esc(scan_ts_display)}</span>
  </div>

  <div class="offer-list" id="offer-list">
    {offers_html}
  </div>
  <div class="no-results" id="no-results">Brak wyników dla wybranych filtrów.</div>
</div>

<script>
(function() {{
    const categoryFilter = document.getElementById('category-filter');
    const searchInput = document.getElementById('search-input');
    const offers = document.querySelectorAll('#offer-list .offer');
    const noResults = document.getElementById('no-results');
    const offerList = document.getElementById('offer-list');

    function applyFilters() {{
        const selectedCategory = categoryFilter.value;
        const searchTerm = searchInput.value.toLowerCase().trim();
        let visibleCount = 0;

        offers.forEach(offer => {{
            const offerCategory = offer.getAttribute('data-category');
            const offerSearch = offer.getAttribute('data-search') || '';

            const categoryMatch = selectedCategory === 'all' || offerCategory === selectedCategory;
            const searchMatch = !searchTerm || offerSearch.indexOf(searchTerm) !== -1;

            if (categoryMatch && searchMatch) {{
                offer.classList.remove('hidden');
                visibleCount++;
            }} else {{
                offer.classList.add('hidden');
            }}
        }});

        if (visibleCount === 0) {{
            noResults.classList.add('visible');
            offerList.style.display = 'none';
        }} else {{
            noResults.classList.remove('visible');
            offerList.style.display = '';
        }}
    }}

    categoryFilter.addEventListener('change', applyFilters);
    searchInput.addEventListener('input', applyFilters);
}})();
</script>

</body>
</html>'''

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html_doc)

    print(f"✅ skipped_debug.html wygenerowany: {out}")
    print(f"   Próbek: no_address={len(samples.get('no_address', []))}, "
          f"no_coords={len(samples.get('no_coords', []))}, "
          f"duplicate={len(samples.get('duplicate', []))}, "
          f"no_price={len(samples.get('no_price', []))}")
    return True


if __name__ == "__main__":
    generate_skipped_debug_page()
