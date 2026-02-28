"""
Monitoring Data Generator - przygotowuje dane dla dashboardu monitoringu
"""

import json
from pathlib import Path
from scan_logger import ScanLogger


def generate_monitoring_data():
    """
    Generuje plik monitoring_data.json z pełnymi statystykami dla dashboardu.
    """
    logger = ScanLogger(log_file="../data/scan_history.json")
    
    # Pobierz ostatnie 50 skanów i statystyki
    recent_scans = logger.get_recent_scans(count=50)
    statistics = logger.get_statistics()
    
    # Przygotuj dane dla wykresów
    chart_data = {
        'duration_over_time': [],
        'offers_over_time': [],
        'success_rate': []
    }
    
    for scan in reversed(recent_scans):  # Odwróć na chronologiczną kolejność
        timestamp = scan.get('timestamp', '')
        
        # Wykres czasu wykonania
        if 'total_duration' in scan:
            chart_data['duration_over_time'].append({
                'timestamp': timestamp,
                'duration': scan['total_duration']
            })
        
        # Wykres liczby ofert
        if 'stats' in scan:
            chart_data['offers_over_time'].append({
                'timestamp': timestamp,
                'raw_offers': scan['stats'].get('raw_offers', 0),
                'processed': scan['stats'].get('processed', 0),
                'new': scan['stats'].get('new', 0)
            })
    
    # Zbierz dane dla podstrony
    monitoring_data = {
        'generated_at': recent_scans[0]['timestamp'] if recent_scans else None,
        'statistics': statistics,
        'recent_scans': recent_scans[:20],  # Ostatnie 20 dla tabeli
        'charts': chart_data
    }
    
    # Zapisz do docs/
    output_file = Path("../docs/monitoring_data.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(monitoring_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Dane monitoringu wygenerowane: {output_file}")
    print(f"   Statystyki: {statistics}")
    print(f"   Ostatnich skanów: {len(recent_scans)}")


if __name__ == "__main__":
    generate_monitoring_data()
