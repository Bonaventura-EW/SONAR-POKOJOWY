/**
 * firmy_badge.js — znacznik "nowe oferty" na przycisku 🏢 Firmy w belce nawigacji.
 *
 * Wariant 8: licznik nowych ofert w czerwonym kółku + pulsujący pierścień.
 *
 * Logika (jak powiadomienie):
 *  - "nowa oferta firmowa" = offer.is_new || offer.recent_change (to samo pole co
 *    badge "NOWE" w karcie na profile_tracker.html).
 *  - badge pokazuje liczbę nowych ofert, których użytkownik jeszcze NIE widział
 *    (śledzone po id w localStorage).
 *  - po wejściu na zakładkę Firmy (profile_tracker.html) wszystkie bieżące nowe id
 *    są oznaczane jako "zobaczone" → badge gaśnie na pozostałych stronach.
 *
 * Dołączany na każdej stronie z belką: <script src="firmy_badge.js" defer></script>
 * Samowystarczalny — sam wstrzykuje CSS i znajduje link Firmy.
 */
(function () {
  'use strict';

  var SEEN_KEY = 'firmy_seen_new_ids';
  var DATA_URL = 'profile_data.json';

  function readSeen() {
    try {
      var raw = localStorage.getItem(SEEN_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
  }
  function writeSeen(ids) {
    try { localStorage.setItem(SEEN_KEY, JSON.stringify(ids)); } catch (e) {}
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

  function collectNewIds(data) {
    var ids = [];
    var profiles = (data && data.profiles) || {};
    Object.keys(profiles).forEach(function (k) {
      var offers = (profiles[k] && profiles[k].offers) || [];
      offers.forEach(function (o) {
        if (o && (o.is_new || o.recent_change) && o.id) ids.push(String(o.id));
      });
    });
    return ids;
  }

  function onProfileTrackerPage() {
    return /profile_tracker\.html$/.test(location.pathname)
        || /profile_tracker\.html/.test(location.href.split('?')[0].split('#')[0]);
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

  function init() {
    var link = findFirmyLink();
    if (!link) return;

    fetch(DATA_URL, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var newIds = collectNewIds(data);
        var newSet = {};
        newIds.forEach(function (id) { newSet[id] = true; });

        // Jesteśmy NA zakładce Firmy → oznacz wszystkie bieżące nowe jako zobaczone.
        if (onProfileTrackerPage()) {
          writeSeen(newIds);
          render(0, link);
          return;
        }

        // Przytnij "seen" do tych, które nadal są nowe (żeby nie rosło w nieskończoność).
        var seen = readSeen().filter(function (id) { return newSet[id]; });
        writeSeen(seen);
        var seenSet = {};
        seen.forEach(function (id) { seenSet[id] = true; });

        var unseen = newIds.filter(function (id) { return !seenSet[id]; }).length;
        render(unseen, link);
      })
      .catch(function () { /* brak danych / offline — nie pokazuj badge */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
