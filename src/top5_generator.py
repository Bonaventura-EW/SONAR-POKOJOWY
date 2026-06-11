"""
Top5 Generator — wyciąga ogłoszenia ze zmianami cen do strony top5.html.

Generuje docs/top5_data.json w formacie zgodnym z SONAR-MIESZKANIOWY/top5.

Format wyjściowy:
{
    "generated_at": "ISO",
    "total_offers": int,                  # wszystkie oferty w bazie
    "offers_with_change": int,            # tylko te ze zmianą ceny (entries)
    "date_range": {"min": "ISO", "max": "ISO"},
    "entries": [
        {
            "id", "url", "address",
            "first_price", "current_price",
            "total_diff_pln", "total_diff_pct",
            "trend": "down" | "up",
            "first_seen", "last_seen", "active",
            "num_changes", "has_coords",
            "timeline": [{"date": "ISO", "price": int, "approximated": bool}, ...]
        }
    ]
}
"""

import json
from pathlib import Path
from datetime import datetime
import pytz

from shared_utils import write_json_atomic


class Top5Generator:
    def __init__(
        self,
        offers_file: str = "../data/offers.json",
        map_data_file: str = "../docs/data.json",
        output_file: str = "../docs/top5_data.json"
    ):
        self.offers_file = Path(offers_file)
        self.map_data_file = Path(map_data_file)
        self.output_file = Path(output_file)
        self.tz = pytz.timezone('Europe/Warsaw')
    
    def _load_ids_on_map(self) -> set:
        if not self.map_data_file.exists():
            print(f"⚠️  Brak pliku mapy: {self.map_data_file} — has_coords ustawione na False dla wszystkich")
            return set()
        with open(self.map_data_file, encoding='utf-8') as f:
            mapdata = json.load(f)
        ids = set()
        for marker in mapdata.get('markers', []):
            for offer in marker.get('offers', []):
                ids.add(offer['id'])
        return ids
    
    def generate(self):
        print("🔄 Generowanie danych dla strony top5...")
        
        with open(self.offers_file, encoding='utf-8') as f:
            data = json.load(f)
        
        offers = data.get('offers', [])
        total_offers = len(offers)
        ids_on_map = self._load_ids_on_map()
        
        entries = []
        
        for offer in offers:
            price_obj = offer.get('price', {})
            history_full = price_obj.get('history_full', [])
            
            if not isinstance(history_full, list) or len(history_full) < 2:
                continue
            
            first_price = history_full[0].get('price')
            current_price = price_obj.get('current')
            
            if not isinstance(first_price, (int, float)) or not isinstance(current_price, (int, float)):
                continue
            if first_price <= 0 or first_price == current_price:
                continue
            
            diff_pln = current_price - first_price
            diff_pct = round((diff_pln / first_price) * 100, 2)
            trend = 'down' if diff_pln < 0 else 'up'
            
            address = offer.get('address', {}).get('full', 'Adres nieznany')
            
            timeline = [
                {
                    'date': h.get('date', ''),
                    'price': int(h.get('price', 0)),
                    'approximated': bool(h.get('approximated', False))
                }
                for h in history_full
                if h.get('date')
            ]
            
            entries.append({
                'id': offer['id'],
                'url': offer.get('url', ''),
                'address': address,
                'first_price': int(first_price),
                'current_price': int(current_price),
                'total_diff_pln': int(diff_pln),
                'total_diff_pct': diff_pct,
                'trend': trend,
                'first_seen': offer.get('first_seen', ''),
                'last_seen': offer.get('last_seen', ''),
                'active': offer.get('active', False),
                'num_changes': len(timeline),
                'has_coords': offer['id'] in ids_on_map,
                'timeline': timeline
            })
        
        entries.sort(key=lambda x: x['total_diff_pln'])
        
        date_min = None
        date_max = None
        for e in entries:
            for key in ('first_seen', 'last_seen'):
                v = e.get(key)
                if not v:
                    continue
                if date_min is None or v < date_min:
                    date_min = v
                if date_max is None or v > date_max:
                    date_max = v
        
        result = {
            'generated_at': datetime.now(self.tz).isoformat(),
            'total_offers': total_offers,
            'offers_with_change': len(entries),
            'date_range': {'min': date_min or '', 'max': date_max or ''},
            'entries': entries
        }
        
        write_json_atomic(self.output_file, result)
        
        drops = [e for e in entries if e['trend'] == 'down']
        rises = [e for e in entries if e['trend'] == 'up']
        without_coords = [e for e in entries if not e['has_coords']]
        
        print(f"✅ Top5 data wygenerowane: {self.output_file}")
        print(f"   Wszystkich ofert w bazie: {total_offers}")
        print(f"   Ofert ze zmianami cen (entries): {len(entries)}")
        print(f"   Spadki: {len(drops)}, wzrosty: {len(rises)}")
        print(f"   Bez współrzędnych (pinezka wyłączona): {len(without_coords)}")
        
        if drops:
            print(f"   Największa obniżka: {drops[0]['total_diff_pct']:.1f}% ({drops[0]['total_diff_pln']} zł)")
        if rises:
            biggest_rise = max(rises, key=lambda x: x['total_diff_pln'])
            print(f"   Największa podwyżka: +{biggest_rise['total_diff_pct']:.1f}% (+{biggest_rise['total_diff_pln']} zł)")


if __name__ == '__main__':
    Top5Generator().generate()
