"""
Skrypt naprawczy: Czyści błędne wpisy w historii cen
Usuwa wpisy które są o >30% niższe niż poprzednia cena (prawdopodobnie błędy parsera)
"""

import json
import sys
from datetime import datetime
import pytz

def clean_price_history(db_path='data/offers.json'):
    """
    Czyści błędne wpisy w historii cen.
    
    Zasady:
    1. Jeśli w historii jest wpis o >50% niższy niż poprzedni - usuń go
    2. Przywróć poprzednią prawidłową cenę jako current
    3. Usuń pole 'source' jeśli nie ma wartości
    """
    print("🔧 Ładowanie bazy danych...")
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    print(f"📊 Znaleziono {len(db['offers'])} ofert\n")
    
    fixed_count = 0
    total_removed = 0
    
    for offer in db['offers']:
        offer_id = offer['id']
        price_data = offer['price']
        history = price_data.get('history', [])
        
        if len(history) < 2:
            continue  # Brak historii do naprawy
        
        # Znajdź błędne wpisy
        cleaned_history = [history[0]]  # Zawsze zachowaj pierwszy wpis
        removed_prices = []
        
        for i in range(1, len(history)):
            prev_price = cleaned_history[-1]
            curr_price = history[i]
            
            # Sprawdź czy spadek jest podejrzany (>50% lub <200 zł dla pokoju)
            if curr_price < 200 or curr_price < prev_price * 0.5:
                removed_prices.append(curr_price)
                total_removed += 1
                print(f"⚠️ Usuwam błędny wpis: {offer_id[:40]}...")
                print(f"   {prev_price} zł → {curr_price} zł (spadek {(1 - curr_price/prev_price)*100:.0f}%)")
            else:
                cleaned_history.append(curr_price)
        
        # Jeśli coś usunęliśmy - aktualizuj
        if removed_prices:
            price_data['history'] = cleaned_history
            price_data['current'] = cleaned_history[-1]
            
            # Usuń nieprawidłowe pole source jeśli jest puste
            if 'source' in price_data and not price_data['source']:
                del price_data['source']
            
            fixed_count += 1
            print(f"   ✅ Przywrócono cenę: {price_data['current']} zł\n")
    
    # Backup starej bazy
    tz = pytz.timezone('Europe/Warsaw')
    timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
    backup_path = f'{db_path}.backup_{timestamp}'
    
    print(f"💾 Tworzę backup: {backup_path}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    
    # Zapisz naprawioną bazę
    print(f"💾 Zapisuję naprawioną bazę...")
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*60)
    print("📊 PODSUMOWANIE NAPRAWY")
    print("="*60)
    print(f"✅ Naprawione oferty: {fixed_count}")
    print(f"🗑️ Usunięte błędne wpisy: {total_removed}")
    print(f"💾 Backup: {backup_path}")
    print("="*60 + "\n")

if __name__ == "__main__":
    clean_price_history()
