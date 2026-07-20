"""
Konfiguracja śledzonych profili OLX - agencji/właścicieli w Lublinie
Każdy profil ma unikalny klucz, wyświetlaną nazwę i URL strony użytkownika.
"""

TRACKED_PROFILES = {
    'villahome': {
        'name': 'VillaHome',
        'url': 'https://www.olx.pl/oferty/uzytkownik/1n7fOJ/',
        'user_id': 1257717661,
    },
    'mzuri': {
        'name': 'Mzuri',
        'url': 'https://www.olx.pl/oferty/uzytkownik/4avCO/',
        'user_id': 61614038,
    },
    'pokojewlublinie': {
        'name': 'PokojewLublinie',
        'url': 'https://www.olx.pl/oferty/uzytkownik/3cxbz/',
        'user_id': 47316513,
    },
    'poqui': {
        'name': 'Poqui',
        'url': 'https://www.olx.pl/oferty/uzytkownik/p8eWV/',
        'user_id': 371372432,
    },
    'artymiuk': {
        'name': 'Artymiuk',
        'url': 'https://www.olx.pl/oferty/uzytkownik/BAm3j/',
        'user_id': 555389013,
    },
    'dawny_patron': {
        'name': 'Dawny Patron',
        'url': 'https://www.olx.pl/oferty/uzytkownik/uD2d4/',
        'user_id': 452593370,
    },
    'stylowe_pokoje_ania': {
        'name': 'stylowe pokoje-ania',
        'url': 'https://www.olx.pl/oferty/uzytkownik/1WLoW/',
        'user_id': 28543245,
    },
    'mat': {
        'name': 'MAT',
        'url': 'https://www.olx.pl/oferty/uzytkownik/4B6oQ/',
        'user_id': 67948084,
    },
    'myrent': {
        'name': 'MyRent',
        'url': 'https://www.olx.pl/oferty/uzytkownik/56DT9/',
        'user_id': 75464983,
    },
}

# Kolor obwódki pinezek na mapie (jednolity dla wszystkich profili firmowych)
FIRM_BORDER_COLOR = '#FFD700'  # Złoty
FIRM_BORDER_WIDTH = '4'        # Grubsza niż standardowa (2px)
