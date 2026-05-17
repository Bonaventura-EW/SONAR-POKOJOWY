"""
Top5 Generator — wyciąga ogłoszenia ze zmianami cen do strony top5.html.

Generuje docs/top5_data.json zawierający WSZYSTKIE ogłoszenia z >1 wpisem
w history_full (filtrowanie zakresu dat odbywa się w frontendzie).

Format wyjściowy:
{
    "generated_at": "ISO",
    "total_with_price_changes": int,
    "offers": [
        {
            "id": str,
            "url": str,
            "address": str,
            "first_price": int,           # history_full[0].price
            "current_price": int,         # price.current
            "change_pln": int,            # current - first (ujemne = obniżka)
            "change_percent": float,      # ((current - first) / first) * 100
            "first_seen": "ISO",
            "last_seen": "ISO",
            "active": bool,
            "history_full": [             # pełna historia z timestampami
                {"price": int, "date": "ISO", "approximated": bool},
                ...
            ]
        },
        ...
    ]
}
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import pytz


class Top5Generator:
    def __init__(
        self,
        offers_file: str = "../data/offers.json",
        output_file: str = "../docs/top5_data.json"
    ):
        self.offers_file = Path(offers_file)
        self.output_file = Path(output_file)
        self.tz = pytz.timezone('Europe/Warsaw')
    
    def generate(self):
        """Generuje plik top5_data.json."""
        print("🔄 Generowanie danych dla strony top5...")
        
        with open(self.offers_file, encoding='utf-8') as f:
            data = json.load(f)
        
        offers = data.get('offers', [])
        eligible = []
        
        for offer in offers:
            price_obj = offer.get('price', {})
            history_full = price_obj.get('history_full', [])
            
            # Musi mieć >= 2 wpisy historii (czyli realna zmiana ceny)
            if not isinstance(history_full, list) or len(history_full) < 2:
                continue
            
            first_price = history_full[0].get('price')
            current_price = price_obj.get('current')
            
            if not isinstance(first_price, (int, float)) or not isinstance(current_price, (int, float)):
                continue
            if first_price <= 0:
                continue
            if first_price == current_price:
                # Brak realnej zmiany (np. cena wróciła do startowej) — pomijamy
                continue
            
            change_pln = current_price - first_price
            change_percent = (change_pln / first_price) * 100
            
            address = offer.get('address', {}).get('full', 'Adres nieznany')
            
            eligible.append({
                'id': offer['id'],
                'url': offer.get('url', ''),
                'address': address,
                'first_price': int(first_price),
                'current_price': int(current_price),
                'change_pln': int(change_pln),
                'change_percent': round(change_percent, 2),
                'first_seen': offer.get('first_seen', ''),
                'last_seen': offer.get('last_seen', ''),
                'active': offer.get('active', False),
                'history_full': history_full
            })
        
        # Sortowanie: pierwsze największe obniżki (najbardziej ujemne change_percent)
        eligible.sort(key=lambda x: x['change_percent'])
        
        result = {
            'generated_at': datetime.now(self.tz).isoformat(),
            'total_with_price_changes': len(eligible),
            'offers': eligible
        }
        
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Statystyki
        drops = [o for o in eligible if o['change_percent'] < 0]
        rises = [o for o in eligible if o['change_percent'] > 0]
        
        print(f"✅ Top5 data wygenerowane: {self.output_file}")
        print(f"   Ogłoszeń ze zmianami cen: {len(eligible)}")
        print(f"   Obniżki: {len(drops)}, podwyżki: {len(rises)}")
        
        if drops:
            biggest_drop = drops[0]
            print(f"   Największa obniżka: {biggest_drop['change_percent']:.1f}% ({biggest_drop['change_pln']} zł)")
        if rises:
            biggest_rise = rises[-1]
            print(f"   Największa podwyżka: +{biggest_rise['change_percent']:.1f}% (+{biggest_rise['change_pln']} zł)")


if __name__ == '__main__':
    generator = Top5Generator()
    generator.generate()
