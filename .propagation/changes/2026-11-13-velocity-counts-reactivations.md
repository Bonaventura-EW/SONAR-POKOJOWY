---
id: 2026-11-13-velocity-counts-reactivations
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-11-13
category: bugfix
what: Wskaźnik rotacji rynku (velocity) liczy w napływie nie tylko nowe oferty, ale też reaktywacje, żeby był symetryczny z odpływem.
why: Odpływ liczył każde zniknięcie oferty, a jej powrót na rynek nie liczył się nigdzie, więc oferta, która zeszła i wróciła, zawyżała wskaźnik o jedno zdarzenie bez przeciwwagi. Na naszych danych różnica to +26% średnio (136 → 171).
how: build_velocity bierze z napływu serię „nowe + reaktywacje" zamiast samych nowych. Reaktywacje mają późniejszy początek rzetelnych danych niż nowe oferty, więc wskaźnik dziedziczy luki przed tą datą zamiast liczyć ze starej, niepełnej serii. Zniknięcie i powrót w kilka dni nadal wypadają razem (odsiew zacięć pipeline'u), więc nie dublują się po obu stronach.
surface: src/trend_generator.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

**Reguła, która się przenosi:** metryka „rotacja = zdarzenia wejścia + zdarzenia
wyjścia" musi liczyć powroty po obu stronach albo po żadnej. Liczenie zniknięć bez
powrotów zawyża rotację dokładnie o tyle, ile ofert wraca.

**Sprawdź u siebie:** czy wskaźnik bierze napływ bez reaktywacji, a odpływ ze
wszystkimi zniknięciami. Jeśli tak, ten sam skos.

**Koszt:** wskaźnik traci historię sprzed daty, od której dane o reaktywacjach są
rzetelne (u nas 07.07.2026). Alternatywa „odjąć od odpływu zniknięcia, po których
oferta wróciła" jest czystsza pojęciowo, ale przepisuje historię wstecz.
