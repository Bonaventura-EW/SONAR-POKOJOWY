"""
API Generator - generuje statyczne pliki JSON dla aplikacji mobilnej

Endpointy (pliki statyczne na GitHub Pages):
- /api/status.json    - aktualny status + ostatni skan
- /api/history.json   - historia ostatnich 20 skanów
- /api/health.json    - prosty health check

Architektura przygotowana na dodanie SZPERACZ w przyszłości.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz

from scan_logger import ScanLogger


class APIGenerator:
    """Generator statycznych plików JSON API dla aplikacji mobilnej."""
    
    # Harmonogram skanów (CET)
    SCAN_SCHEDULE = ["09:00", "15:00", "21:00"]
    
    def __init__(self, output_dir: str = "../docs/api"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tz = pytz.timezone('Europe/Warsaw')
        self.logger = ScanLogger(log_file="../data/scan_history.json")
    
    def generate_all(self):
        """Generuje wszystkie pliki API."""
        print("🔄 Generowanie API dla aplikacji mobilnej...")
        
        self._generate_status()
        self._generate_history()
        self._generate_health()
        self._generate_scan_status()
        
        print(f"✅ API wygenerowane w: {self.output_dir}")

    def _generate_scan_status(self):
        """
        Generuje /api/scan_status.json

        Uproszczony endpoint dedykowany dla aplikacji Android (SZPERACZ).
        Zawiera:
        - Wynik ostatniego skanu (success/failed) z powodem niepowodzenia
        - Liczba nowych i usuniętych ofert z ostatniego skanu
        - Historia 3 ostatnich skanów
        """
        # Pobieramy 4 skany żeby mieć prev dla najstarszego z 3
        recent_scans = self.logger.get_recent_scans(count=4)
        now = datetime.now(self.tz)

        def _format(idx: int) -> Dict:
            scan = recent_scans[idx] if idx < len(recent_scans) else None
            if not scan:
                return None
            prev = recent_scans[idx + 1] if idx + 1 < len(recent_scans) else None
            stats = scan.get('stats', {})
            errors = scan.get('errors', [])
            status = scan.get('status', 'unknown')

            success = status == 'completed' and not errors
            failure_reason = None
            if status != 'completed':
                failure_reason = f"Skan zakończył się statusem: {status}"
            elif errors:
                failure_reason = errors[0].get('message', 'Nieznany błąd')

            deactivated = None
            if prev:
                prev_stats = prev.get('stats', {})
                deactivated = max(
                    0,
                    prev_stats.get('active', 0)
                    + stats.get('new', 0)
                    + stats.get('reactivated', 0)
                    - stats.get('active', 0)
                )

            return {
                "id": scan.get('timestamp', '')[:19].replace(':', '-'),
                "timestamp": scan.get('timestamp'),
                "durationFormatted": self._format_duration(scan.get('total_duration')),
                "success": success,
                "failureReason": failure_reason,
                "newOffers": stats.get('new', 0),
                "deactivatedOffers": deactivated,  # null jeśli brak poprzedniego skanu w historii
                "activeOffers": stats.get('active', 0),
                "foundOffers": stats.get('raw_offers', 0),
            }

        last = _format(0)

        data = {
            "generatedAt": now.isoformat(),
            "lastScan": last,
            "recentScans": [_format(i) for i in range(min(3, len(recent_scans)))],
            "nextScanAt": (self._calculate_next_scan_time().isoformat()
                           if self._calculate_next_scan_time() else None),
        }

        self._save_json("scan_status.json", data)
        status_label = "✅ success" if (last and last["success"]) else "❌ failed"
        print(f"   📱 scan_status.json - ostatni skan: {status_label}")
    
    def _generate_status(self):
        """
        Generuje /api/status.json
        
        Zawiera:
        - Aktualny status systemu
        - Szczegóły ostatniego skanu
        - Przewidywany czas następnego skanu
        - Flagi dla powiadomień (hasErrors, isHealthy)
        """
        recent_scans = self.logger.get_recent_scans(count=5)
        statistics = self.logger.get_statistics()
        
        last_scan = recent_scans[0] if recent_scans else None
        
        # Oblicz następny zaplanowany skan
        next_scan_time = self._calculate_next_scan_time()
        
        # Sprawdź czy ostatni skan miał błędy
        has_errors = False
        error_messages = []
        if last_scan:
            errors = last_scan.get('errors', [])
            if errors:
                has_errors = True
                error_messages = [e.get('message', 'Unknown error') for e in errors]
        
        # Określ status systemu
        system_status = self._determine_system_status(last_scan, statistics)
        
        status_data = {
            "system": "sonar",
            "version": "1.0.0",
            "generatedAt": datetime.now(self.tz).isoformat(),
            
            "status": {
                "current": system_status,
                "isHealthy": system_status in ["operational", "degraded"],
                "hasErrors": has_errors,
                "errorMessages": error_messages
            },
            
            "lastScan": self._format_scan_for_api(last_scan) if last_scan else None,
            
            "schedule": {
                "times": self.SCAN_SCHEDULE,
                "timezone": "Europe/Warsaw",
                "nextScanAt": next_scan_time.isoformat() if next_scan_time else None
            },
            
            "statistics": {
                "totalScans": statistics.get('total_scans', 0),
                "successRate": round(statistics.get('success_rate', 0), 1),
                "avgDurationSeconds": statistics.get('avg_duration', 0),
                "avgOffersFound": statistics.get('avg_offers_found', 0)
            }
        }
        
        self._save_json("status.json", status_data)
        print(f"   📊 status.json - status: {system_status}")
    
    def _generate_history(self):
        """
        Generuje /api/history.json
        
        Zawiera ostatnie 20 skanów z pełnymi szczegółami.
        Używane do wyświetlania historii w aplikacji.
        """
        recent_scans = self.logger.get_recent_scans(count=20)
        
        history_data = {
            "system": "sonar",
            "generatedAt": datetime.now(self.tz).isoformat(),
            "count": len(recent_scans),
            "scans": [
                self._format_scan_for_api(recent_scans[i], recent_scans[i + 1] if i + 1 < len(recent_scans) else None)
                for i in range(len(recent_scans))
            ]
        }
        
        self._save_json("history.json", history_data)
        print(f"   📜 history.json - {len(recent_scans)} skanów")
    
    def _generate_health(self):
        """
        Generuje /api/health.json
        
        Prosty health check - aplikacja może odpytywać ten endpoint
        żeby sprawdzić czy API jest dostępne i aktualne.
        """
        recent_scans = self.logger.get_recent_scans(count=1)
        last_scan = recent_scans[0] if recent_scans else None
        
        # Sprawdź czy ostatni skan był w ciągu ostatnich 12h
        is_fresh = False
        hours_since_last_scan = None
        
        if last_scan:
            try:
                last_scan_time = datetime.fromisoformat(last_scan['timestamp'])
                now = datetime.now(self.tz)
                delta = now - last_scan_time
                hours_since_last_scan = round(delta.total_seconds() / 3600, 1)
                is_fresh = hours_since_last_scan < 12
            except (KeyError, ValueError):
                pass
        
        health_data = {
            "status": "ok" if is_fresh else "stale",
            "timestamp": datetime.now(self.tz).isoformat(),
            "lastScanAt": last_scan['timestamp'] if last_scan else None,
            "hoursSinceLastScan": hours_since_last_scan,
            "isFresh": is_fresh,
            "systems": {
                "sonar": {
                    "enabled": True,
                    "lastStatus": last_scan.get('status', 'unknown') if last_scan else 'unknown'
                },
                "szperacz": {
                    "enabled": False,
                    "lastStatus": None,
                    "message": "Coming soon"
                }
            }
        }
        
        self._save_json("health.json", health_data)
        print(f"   💓 health.json - {'fresh' if is_fresh else 'stale'} ({hours_since_last_scan}h ago)")
    
    def _format_scan_for_api(self, scan: Dict, prev_scan: Optional[Dict] = None) -> Dict:
        """
        Formatuje pojedynczy skan do formatu API.
        Upraszcza strukturę i dodaje pola przydatne dla aplikacji mobilnej.

        prev_scan: poprzedni skan (starszy) używany do obliczenia deactivated.
        """
        if not scan:
            return None
        
        stats = scan.get('stats', {})
        errors = scan.get('errors', [])
        
        # Określ status dla UI
        ui_status = "success"
        if scan.get('status') != 'completed':
            ui_status = "failed"
        elif errors:
            ui_status = "warning"

        # Oblicz ile ogłoszeń zniknęło w tym skanie
        # Formuła: prev_active + new + reactivated - curr_active
        # FIX 2026-05-23: pomijamy scany failed - ich active=0 daje absurdalne wyniki.
        deactivated = None
        if prev_scan and scan.get('status') == 'completed' and prev_scan.get('status') == 'completed':
            prev_stats = prev_scan.get('stats', {})
            prev_active = prev_stats.get('active', 0)
            new = stats.get('new', 0)
            reactivated = stats.get('reactivated', 0)
            curr_active = stats.get('active', 0)
            deactivated = max(0, prev_active + new + reactivated - curr_active)
        
        return {
            "id": scan.get('timestamp', '')[:19].replace(':', '-'),  # Unikalne ID
            "timestamp": scan.get('timestamp'),
            "endTimestamp": scan.get('end_timestamp'),
            "durationSeconds": scan.get('total_duration'),
            "durationFormatted": self._format_duration(scan.get('total_duration')),
            
            "uiStatus": ui_status,  # success | warning | failed
            "rawStatus": scan.get('status'),
            
            "offers": {
                "found": stats.get('raw_offers', 0),
                "processed": stats.get('processed', 0),
                "new": stats.get('new', 0),
                "deactivated": deactivated,  # ile ogłoszeń znikło (null jeśli brak poprzedniego skanu)
                "updated": stats.get('updated', 0),
                "active": stats.get('active', 0),
                "inactive": stats.get('inactive', 0)
            },
            
            "skipped": {
                "noAddress": stats.get('skipped_no_address', 0),
                "noPrice": stats.get('skipped_no_price', 0),
                "noCoords": stats.get('skipped_no_coords', 0),
                "duplicates": stats.get('skipped_duplicate', 0)
            },
            
            "errors": [
                {
                    "message": e.get('message', 'Unknown error'),
                    "timestamp": e.get('timestamp')
                }
                for e in errors
            ],
            "hasErrors": len(errors) > 0
        }
    
    def _calculate_next_scan_time(self) -> Optional[datetime]:
        """
        Oblicza przewidywany czas następnego skanu
        na podstawie harmonogramu (09:00, 15:00, 21:00 CET).
        """
        now = datetime.now(self.tz)
        today = now.date()
        
        for time_str in self.SCAN_SCHEDULE:
            hour, minute = map(int, time_str.split(':'))
            scan_time = self.tz.localize(
                datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
            )
            if scan_time > now:
                return scan_time
        
        # Jeśli wszystkie dzisiejsze skany minęły, zwróć pierwszy jutrzejszy
        tomorrow = today + timedelta(days=1)
        hour, minute = map(int, self.SCAN_SCHEDULE[0].split(':'))
        return self.tz.localize(
            datetime.combine(tomorrow, datetime.min.time().replace(hour=hour, minute=minute))
        )
    
    def _determine_system_status(self, last_scan: Optional[Dict], statistics: Dict) -> str:
        """
        Określa ogólny status systemu.
        
        Returns:
            operational - wszystko działa
            degraded - działa z błędami
            down - ostatni skan się nie powiódł
            unknown - brak danych
        """
        if not last_scan:
            return "unknown"
        
        if last_scan.get('status') != 'completed':
            return "down"
        
        if last_scan.get('errors'):
            return "degraded"
        
        # Sprawdź success rate z ostatnich skanów
        if statistics.get('success_rate', 100) < 80:
            return "degraded"
        
        return "operational"
    
    def _format_duration(self, seconds: Optional[float]) -> str:
        """Formatuje czas trwania do czytelnej postaci."""
        if seconds is None:
            return "N/A"
        
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        
        if minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"
    
    def _save_json(self, filename: str, data: Dict):
        """Zapisuje dane JSON do pliku."""
        filepath = self.output_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    """Główna funkcja - generuje wszystkie pliki API."""
    generator = APIGenerator()
    generator.generate_all()


if __name__ == "__main__":
    main()
