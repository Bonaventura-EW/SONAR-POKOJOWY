---
id: 2026-09-08-event-timestamp-granularity
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-08
category: bugfix
what: Sygnał „co się zmieniło od Twojej ostatniej wizyty" przestał gubić zdarzenia z dnia wizyty — porównanie ze znacznikiem wizyty dostaje dokładną godzinę zamiast północy.
why: Lista zdarzeń była trzymana w rozdzielczości DNI, a znacznik wizyty w milisekundach. Zdarzenie z dnia D parsowało się na D 00:00, więc wypadało PRZED każdą wizytą tego samego dnia i plakietka nigdy się nie zapalała — także przy każdym kolejnym wejściu, bo data w liście nie dostanie godziny wstecz. Kto wchodzi codziennie, nie widział sygnału ani razu. Ten sam ekran pokazywał obok „zdarzenie było", bo tamten element czytał pole z pełnym znacznikiem.
how: (1) Nie podnosimy rozdzielczości całej historii — wystarczy ostatni wpis, bo tylko on może kolidować z dniem wizyty (starsze wpisy to całe dni wcześniej, godzina niczego nie zmienia). Pod ostatni dzień listy podstawiamy dokładny znacznik z pola, które i tak już go niosło, dopasowując po dniu. (2) Znacznik nie może być doklejany jako osobne zdarzenie: bywa wypełniony przy PUSTEJ liście dni (data z pierwszego widzenia rekordu, sprzed uruchomienia śledzenia), więc mapujemy po liście zdarzeń, nie sklejamy zbiorów. (3) Drugie źródło tej samej klasy błędu było w generatorze: pełne ISO z bazy było ścinane do „DD.MM.YYYY" przy eksporcie na front. Dołożone równoległe pole z surowym ISO — wyświetlanie bierze skrócone, porównania biorą surowe; brak nowego pola ma fallback na stare zachowanie.
surface: docs/profile_tracker.html, src/profile_generator.py, test_refresh_signals.py
generality: universal
propagate: yes
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

**Przenośna jest reguła, nie kod.** W jednym zdaniu: *jeśli porównujesz zdarzenie
zapisane z dokładnością do DNIA ze znacznikiem zapisanym co do MILISEKUNDY, to
zdarzenia z dnia granicznego znikają systematycznie — i to w jedną stronę.* Data bez
godziny parsuje się na północ, więc zawsze przegrywa z każdym „od kiedy" z tego
samego dnia. Nie objawia się jako błąd: nic nie wybucha, licznik po prostu pokazuje
zero i wygląda, jakby faktycznie nic się nie wydarzyło.

Gdzie tego szukać u siebie — wszędzie, gdzie stoi obok siebie „lista dni" i „znacznik
ostatniej wizyty / ostatniego sprawdzenia": badge „nowe od ostatniego wejścia", diff
„co się zmieniło od…", filtry „od daty". Sygnałem alarmowym jest sytuacja, w której
**ten sam ekran** pokazuje zdarzenie w jednym miejscu, a w drugim go nie liczy — u nas
lista ofert miała plakietkę „odświeżona" (czytała pełne ISO), a zakładka nad nią nie
miała ikony (czytała dni). To nie dwie różne prawdy, tylko dwie różne rozdzielczości
tej samej daty.

**Odrzucona alternatywa: traktować dzień jako 23:59 zamiast 00:00.** Kusi, bo to
jednolinijkowa zmiana bez dokładania pól. Ale zamienia ciche gubienie na ciche
zmyślanie: zdarzenie z rana, obejrzane po południu, przy następnym wejściu znów
liczyłoby się jako nowe. Lepiej użyć dokładnego znacznika tam, gdzie realnie go masz,
a resztę zostawić na północy.

**Sprawdź, czy Twój odpowiednik `last_*` faktycznie jest spójny z ostatnim wpisem
listy** — cały fix na tym stoi. U nas oba pola aktualizuje jedna funkcja, więc
niezmiennik trzyma się na całej bazie (452 rekordy, 0 rozjazdów); mamy go zamkniętego
w teście, żeby nikt go po cichu nie rozspoił. Jeśli u Ciebie te pola są pisane
niezależnie, dokładna godzina może trafić w zły dzień — wtedy najpierw niezmiennik,
potem fix.

**O teście**: uruchamia PRAWDZIWE funkcje wycięte z pliku frontu w node zamiast ich
imitacji po stronie testów — inaczej pilnowałby własnej kopii logiki, nie tej, która
trafia do przeglądarki. Wycinanie po nazwie funkcji działa, gdy funkcje najwyższego
poziomu są niewcięte (domknięcie = `}` w kolumnie 0); przy innym stylu formatowania
trzeba innego cięcia. Warto też zrobić weryfikację odwrotną: cofnąć fix i sprawdzić,
że test świeci czerwono — inaczej nie wiesz, czy przechodzi z właściwego powodu.
