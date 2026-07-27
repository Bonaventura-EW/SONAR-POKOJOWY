/**
 * firmy_badge.js — znacznik "nowe oferty" na przycisku 🏢 Firmy w belce nawigacji.
 *
 * Wariant 8: licznik nowych ofert w czerwonym kółku + pulsujący pierścień.
 *
 * Logika (spójna z sygnałami +N w zakładkach na profile_tracker.html):
 *  - "nowa oferta firmowa" = first_seen późniejszy niż Twoja ostatnia wizyta
 *    w TYM profilu (znacznik `firmy_last_visit` zapisuje profile_tracker.html).
 *  - sufit 7 dni — po tygodniu nieobecności badge nie pokazuje miesięcznej zaległości.
 *  - badge gaśnie profil po profilu: obejrzenie zakładki Poqui zdejmuje z licznika
 *    tylko nowe oferty Poqui, reszta dalej się liczy.
 *
 * Dołączany na każdej stronie z belką: <script src="firmy_badge.js" defer></script>
 * Samowystarczalny — sam wstrzykuje CSS i znajduje link Firmy.
 */
(function () {
  'use strict';

  var VISIT_KEY    = 'firmy_last_visit';   // { profileKey: epoch_ms } — pisze profile_tracker.html
  var OLD_SEEN_KEY = 'firmy_seen_new_ids'; // poprzedni mechanizm (po id) — już nieużywany
  var VISIT_CAP_MS = 7 * 24 * 60 * 60 * 1000;
  var DATA_URL = 'profile_data.json';

  function readVisits() {
    try { return JSON.parse(localStorage.getItem(VISIT_KEY)) || {}; } catch (e) { return {}; }
  }

  // PL "DD.MM.YYYY HH:MM" / "DD.MM.YYYY" oraz ISO "YYYY-MM-DD" — new Date() nie
  // sparsuje pierwszego formatu, więc parsujemy sami.
  function parseAnyDate(s) {
    if (!s) return null;
    var m = String(s).match(/^(\d{2})\.(\d{2})\.(\d{4})(?:[ T](\d{2}):(\d{2}))?/);
    if (m) return new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0)).getTime();
    m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)).getTime();
    return null;
  }

  function injectCSS() {
    if (document.getElementById('firmy-badge-css')) return;
    var css = ''
      + '.firmy-has-badge{position:relative;}'
      + '.firmy-badge{position:absolute;top:-9px;right:-9px;min-width:18px;height:18px;'
      + 'padding:0 4px;background:#dc2626;color:#fff;font-size:11px;font-weight:800;'
      + 'border-radius:999px;display:flex;align-items:center;justify-content:center;'
      + 'border:2px solid #fff;line-height:1;z-index:5;box-sizing:border-box;}'
      + '.firmy-badge::before{content:"";position:absolute;inset:-3px;border-radius:999px;'
      + 'border:2px solid #dc2626;opacity:.6;animation:firmyPing 1.5s ease-out infinite;}'
      + '@keyframes firmyPing{0%{transform:scale(1);opacity:.6}80%,100%{transform:scale(1.8);opacity:0}}'
      + '@media (prefers-reduced-motion: reduce){.firmy-badge::before{animation:none;opacity:0;}}';
    var s = document.createElement('style');
    s.id = 'firmy-badge-css';
    s.textContent = css;
    document.head.appendChild(s);
  }

  function findFirmyLink() {
    return document.querySelector('nav a[href$="profile_tracker.html"]')
        || document.querySelector('a[href$="profile_tracker.html"]');
  }

  // Nowe oferty = pojawiły się po ostatniej wizycie w danym profilu (sufit 7 dni).
  function countNewSinceVisit(data) {
    var profiles = (data && data.profiles) || {};
    var visits = readVisits();
    var capTs = Date.now() - VISIT_CAP_MS;
    var n = 0;
    Object.keys(profiles).forEach(function (k) {
      var since = Math.max(capTs, visits[k] || 0);
      var offers = (profiles[k] && profiles[k].offers) || [];
      offers.forEach(function (o) {
        var first = o && parseAnyDate(o.first_seen);
        if (first && first > since) n++;
      });
    });
    return n;
  }

  function render(count, link) {
    var old = link.querySelector('.firmy-badge');
    if (old) old.remove();
    if (count <= 0) { link.classList.remove('firmy-has-badge'); return; }
    injectCSS();
    link.classList.add('firmy-has-badge');
    var b = document.createElement('span');
    b.className = 'firmy-badge';
    b.textContent = count > 9 ? '9+' : String(count);
    b.setAttribute('aria-label', count + ' nowych ofert firmowych');
    b.title = count + ' nowych ofert firmowych';
    link.appendChild(b);
  }

  function onProfileTrackerPage() {
    return /profile_tracker\.html/.test(location.href.split('?')[0].split('#')[0]);
  }

  function init() {
    var link = findFirmyLink();
    if (!link) return;

    // Sprzątanie po poprzednim mechanizmie (lista id) — znaczniki wizyt go zastąpiły.
    try { localStorage.removeItem(OLD_SEEN_KEY); } catch (e) {}

    // Na samej zakładce Firmy licznik w belce jest zbędny — sygnały +N / ✳ / −N
    // przy zakładkach profili mówią to samo, tylko dokładniej.
    if (onProfileTrackerPage()) { render(0, link); return; }

    fetch(DATA_URL, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        render(countNewSinceVisit(data), link);
      })
      .catch(function () { /* brak danych / offline — nie pokazuj badge */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
