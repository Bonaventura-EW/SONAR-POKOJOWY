---
id: 2026-10-26-outflow-without-blinks
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-10-26
category: bugfix
what: Odpływ ofert (wykres i suwak "Zniknięcia" na mapie) nie liczy mignięć, czyli deaktywacji, po której oferta wróciła w ciągu 24 h.
why: Rozbiór jednego dnia oferta po ofercie pokazał, że 12 z 32 "zniknięć" już wróciło, w tym 10 przy następnym skanie tego samego dnia. Od wdrożenia deactivation_dates mignięcia stanowiły prawie co czwarte zdarzenie odpływu (465 z 1983) i zawyżały rekordy (72 → 46 dla jednego dnia).
how: Jedna funkcja `trend_generator.exit_days(offer)` zbiera znaczniki `deactivation_dates` i `reactivation_dates` (także z `versions[]`) i pomija deaktywację, po której najbliższa reaktywacja przyszła w ciągu `BLINK_MAX_HOURS = 24`. Fallback na `last_seen` dla ofert bez dat deaktywacji bez zmian. Używa jej zarówno `build_outflow`, jak i `map_generator._gone_days`, więc mapa i wykres nie mogą się rozjechać.
surface: src/trend_generator.py, src/map_generator.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

Dotyczy każdego brata, który zapisuje daty deaktywacji i reaktywacji ofert ze
skanów listingu: oferta potrafi wypaść z jednego skanu i wrócić w następnym.

Pułapki:
- Zniknięcie z ostatnich skanów liczy się, dopóki oferta nie wróci, więc wartość
  ostatniej doby może spaść przy następnej generacji.
- Powroty mignięć nadal są w szeregach reaktywacji i napływu całkowitego — u nas
  zostawione jako osobna decyzja.
- Jeśli dzień zniknięcia liczysz w dwóch miejscach (wykres, mapa), wydziel jedną
  funkcję; dwie kopie konwencji już raz się u nas rozjechały.
