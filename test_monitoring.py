#!/usr/bin/env python3
"""
Test diagnostyczny dla monitoring.html - sprawdza JavaScript errors
"""

import json
import os

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

def check_monitoring_issues():
    """Sprawdza potencjalne problemy w monitoring.html"""
    
    print("🔍 DIAGNOSTYKA MONITORING.HTML\n")
    print("=" * 70)
    
    issues = []
    warnings = []
    
    # 1. Sprawdź czy pliki istnieją
    print("\n📁 SPRAWDZANIE PLIKÓW:")
    files_to_check = [
        'docs/monitoring.html',
        'docs/monitoring_data.json'
    ]
    
    for file in files_to_check:
        if os.path.exists(file):
            print(f"   ✅ {file} - istnieje")
        else:
            issues.append(f"Brak pliku: {file}")
            print(f"   ❌ {file} - BRAK")
    
    # 2. Sprawdź strukturę monitoring_data.json
    print("\n📊 SPRAWDZANIE DANYCH MONITORINGU:")
    try:
        with open('docs/monitoring_data.json', 'r') as f:
            data = json.load(f)
        
        # Sprawdź wymagane klucze
        required_keys = ['generated_at', 'statistics', 'recent_scans', 'charts']
        for key in required_keys:
            if key in data:
                print(f"   ✅ Klucz '{key}' - obecny")
            else:
                issues.append(f"Brak wymaganego klucza: {key}")
                print(f"   ❌ Klucz '{key}' - BRAK")
        
        # Sprawdź statystyki
        if 'statistics' in data:
            stats = data['statistics']
            stats_keys = ['total_scans', 'successful', 'failed', 'success_rate', 'avg_duration', 'avg_offers_found']
            missing_stats = [k for k in stats_keys if k not in stats]
            if missing_stats:
                warnings.append(f"Brakujące statystyki: {missing_stats}")
        
        # Sprawdź recent_scans
        if 'recent_scans' in data:
            scans = data['recent_scans']
            print(f"   ✅ Liczba skanów: {len(scans)}")
            
            if scans:
                scan = scans[0]
                required_scan_keys = ['timestamp', 'status', 'stats', 'total_duration']
                missing_keys = [k for k in required_scan_keys if k not in scan]
                if missing_keys:
                    warnings.append(f"Pierwszy skan - brakujące klucze: {missing_keys}")
        
        # Sprawdź charts
        if 'charts' in data:
            charts = data['charts']
            chart_types = ['duration_over_time', 'offers_over_time', 'success_rate']
            
            for chart in chart_types:
                if chart in charts:
                    count = len(charts[chart])
                    print(f"   ✅ Wykres '{chart}': {count} punktów")
                    
                    if count == 0:
                        warnings.append(f"Wykres '{chart}' jest pusty")
                else:
                    issues.append(f"Brak wykresu: {chart}")
                    print(f"   ❌ Wykres '{chart}' - BRAK")
        
    except json.JSONDecodeError as e:
        issues.append(f"Błąd parsowania JSON: {e}")
    except FileNotFoundError:
        issues.append("Plik monitoring_data.json nie istnieje")
    
    # 3. Sprawdź monitoring.html
    print("\n🌐 SPRAWDZANIE HTML:")
    try:
        with open('docs/monitoring.html', 'r') as f:
            html_content = f.read()
        
        # Sprawdź czy są wymagane elementy
        required_elements = [
            'id="loading"',
            'id="content"',
            'id="error"',
            'id="total-scans"',
            'id="durationChart"',
            'id="offersChart"',
            'Chart.js',
            'loadMonitoringData',
            'renderCharts'
        ]
        
        for element in required_elements:
            if element in html_content:
                print(f"   ✅ Element '{element}' - obecny")
            else:
                issues.append(f"HTML - brak elementu: {element}")
                print(f"   ❌ Element '{element}' - BRAK")
        
        # Sprawdź czy Chart.js jest z CDN
        if 'cdn.jsdelivr.net/npm/chart.js' in html_content:
            print(f"   ✅ Chart.js CDN - poprawny")
        else:
            warnings.append("Chart.js może nie być załadowany z CDN")
    
    except FileNotFoundError:
        issues.append("Plik monitoring.html nie istnieje")
    
    # 4. Podsumowanie
    print("\n" + "=" * 70)
    print(f"\n📊 PODSUMOWANIE:")
    
    if not issues and not warnings:
        print("\n✅ Wszystko wygląda dobrze! Nie znaleziono problemów.")
        return 0
    
    if warnings:
        print(f"\n⚠️  OSTRZEŻENIA ({len(warnings)}):")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")
    
    if issues:
        print(f"\n❌ BŁĘDY ({len(issues)}):")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        return 1
    
    return 0

if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    exit(check_monitoring_issues())
