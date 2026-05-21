"""
Konfiguracja śledzonych profili OLX - agencji/właścicieli w Lublinie
Każdy profil ma unikalny klucz, wyświetlaną nazwę i URL strony użytkownika.
"""

TRACKED_PROFILES = {
    'villahome': {
        'name': 'VillaHome',
        'url': 'https://www.olx.pl/oferty/uzytkownik/1n7fOJ/',
    },
    'mzuri': {
        'name': 'Mzuri',
        'url': 'https://www.olx.pl/oferty/uzytkownik/4avCO/',
    },
    'pokojewlublinie': {
        'name': 'PokojewLublinie',
        'url': 'https://www.olx.pl/oferty/uzytkownik/3cxbz/',
    },
    'poqui': {
        'name': 'Poqui',
        'url': 'https://www.olx.pl/oferty/uzytkownik/p8eWV/',
    },
    'artymiuk': {
        'name': 'Artymiuk',
        'url': 'https://www.olx.pl/oferty/uzytkownik/BAm3j/',
    },
    'dawny_patron': {
        'name': 'Dawny Patron',
        'url': 'https://www.olx.pl/oferty/uzytkownik/uD2d4/',
    },
}

# Kolor obwódki pinezek na mapie (jednolity dla wszystkich profili firmowych)
FIRM_BORDER_COLOR = '#FFD700'  # Złoty
FIRM_BORDER_WIDTH = '4'        # Grubsza niż standardowa (2px)
