"""
API Generator - generuje statyczne pliki JSON dla aplikacji mobilnej

Endpointy (pliki statyczne na GitHub Pages):
- /api/status.json    - aktualny status + ostatni skan
- /api/history.json   - historia ostatnich 20 skanów
- /api/health.json    - prosty health check

Architektura przygotowana na dodanie ScanMonitor w przyszłości.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from statistics import median
from typing import Dict, List, Optional
import pytz

from scan_logger import ScanLogger
from shared_utils import write_json_atomic


class APIGenerator:
    """Generator statycznych plików JSON API dla aplikacji mobilnej."""
    
    # Harmonogram skanów (CET)
    SCAN_SCHEDULE = ["09:00", "15:00", "21:00"]

    # Progi alertów o masowym odpływie ofert (patrz _build_alerts)
    MASS_DEACT_WARNING_PCT = 15.0    # % aktywnych z poprzedniego skanu
    MASS_DEACT_CRITICAL_PCT = 30.0
    MASS_DEACT_WARNING_ABS = 100     # ...albo tyle ofert naraz
    SCRAPE_DROP_WARNING_PCT = 70.0   # scrape < 70% mediany ostatnich skanów
    
    def __init__(self, output_dir: str = "../docs/api"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tz = pytz.timezone('Europe/Warsaw')
        self.logger = ScanLogger(log_file="../data/scan_history.json")
    
    def generate_all(self):
        """Generuje wszystkie pliki API."""
        print("🔄 Generowanie API dla aplikacji mobilnej...")

        # Alerty liczone raz i wstrzykiwane do wszystkich endpointów
        self.alerts = self._build_alerts()
        for alert in self.alerts:
            icon = "🔴" if alert['severity'] == 'critical' else "🟠"
            print(f"   {icon} ALERT [{alert['type']}]: {alert['message']}")

        self._generate_status()
        self._generate_history()
        self._generate_health()
        self._generate_scan_status()
        
        print(f"✅ API wygenerowane w: {self.output_dir}")

    def _build_alerts(self) -> List[Dict]:
        """
        Buduje listę alertów dla ostatniego skanu.

        Powód: 25.07.2026 jeden scan zdeaktywował 311 ofert (spadek 43%), bo OLX
        oddał pustą stronę w połowie paginacji. Scan zaraportował się jako
        `success` — nic w API nie krzyczało, że baza właśnie straciła 40% rynku.

        Typy alertów:
        - partial_scrape     — main.py zablokował dezaktywację (SCRAPE_PARTIAL/BLOCKED)
        - mass_deactivation  — nienormalnie dużo ofert wypadło w jednym skanie
        - scrape_drop        — scrape dużo mniejszy niż mediana ostatnich skanów

        Returns:
            Lista alertów (critical przed warning). Pusta gdy wszystko OK.
        """
        recent = self.logger.get_recent_scans(count=8)
        if not recent:
            return []

        last = recent[0]
        stats = last.get('stats', {})
        scan_id = last.get('timestamp', '')[:19].replace(':', '-')
        alerts = []

        # 1. Scraper padł, dezaktywacja zablokowana przez guard w main.py
        for err in last.get('errors', []):
            msg = str(err.get('message', ''))
            if msg.startswith(('SCRAPE_PARTIAL', 'SCRAPE_BLOCKED')):
                alerts.append({
                    "type": "partial_scrape",
                    "severity": "critical",
                    "scanId": scan_id,
                    "message": "Częściowy scrape OLX — dezaktywacja ofert wstrzymana. "
                               "Dane z tego skanu są niepełne.",
                    "details": {"reason": msg}
                })
                break

        # 2. Masowy odpływ ofert względem poprzedniego skanu
        prev = next((s for s in recent[1:] if s.get('status') == 'completed'), None)
        if prev and last.get('status') in ('completed', 'warning'):
            prev_active = prev.get('stats', {}).get('active', 0)
            deactivated = max(
                0,
                prev_active + stats.get('new', 0) + stats.get('reactivated', 0)
                - stats.get('active', 0)
            )
            drop_pct = round(deactivated / prev_active * 100, 1) if prev_active else 0.0

            if drop_pct >= self.MASS_DEACT_CRITICAL_PCT:
                severity = "critical"
            elif drop_pct >= self.MASS_DEACT_WARNING_PCT or deactivated >= self.MASS_DEACT_WARNING_ABS:
                severity = "warning"
            else:
                severity = None

            if severity:
                alerts.append({
                    "type": "mass_deactivation",
                    "severity": severity,
                    "scanId": scan_id,
                    "message": f"W jednym skanie wypadło {deactivated} ofert "
                               f"({drop_pct}% aktywnych). Sprawdź czy scraper nie został ucięty.",
                    "details": {
                        "deactivated": deactivated,
                        "dropPercent": drop_pct,
                        "activeBefore": prev_active,
                        "activeAfter": stats.get('active', 0),
                        "previousScanAt": prev.get('timestamp')
                    }
                })

        # 3. Scrape dużo mniejszy niż zwykle (nawet jeśli guard go przepuścił)
        healthy = [
            s['stats'].get('raw_offers', 0)
            for s in recent[1:]
            if s.get('stats', {}).get('raw_offers')
            and not any(str(e.get('message', '')).startswith(('SCRAPE_PARTIAL', 'SCRAPE_BLOCKED'))
                        for e in s.get('errors', []))
        ]
        raw_offers = stats.get('raw_offers', 0)
        if len(healthy) >= 3 and raw_offers:
            median_raw = int(median(healthy))
            pct_of_median = round(raw_offers / median_raw * 100, 1) if median_raw else 100.0
            if pct_of_median < self.SCRAPE_DROP_WARNING_PCT:
                alerts.append({
                    "type": "scrape_drop",
                    "severity": "warning",
                    "scanId": scan_id,
                    "message": f"Scraper pobrał {raw_offers} ofert — tylko {pct_of_median}% "
                               f"mediany ostatnich skanów ({median_raw}).",
                    "details": {
                        "rawOffers": raw_offers,
                        "medianRawOffers": median_raw,
                        "percentOfMedian": pct_of_median
                    }
                })

        alerts.sort(key=lambda a: 0 if a['severity'] == 'critical' else 1)
        return alerts

    def _generate_scan_status(self):
        """
        Generuje /api/scan_status.json

        Uproszczony endpoint dedykowany dla aplikacji Android (ScanMonitor).
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
            if status == 'warning' and errors:
                failure_reason = errors[0].get('message', 'Blokada OLX lub awaria scrapera')
            elif status not in ('completed', 'warning'):
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

        alerts = getattr(self, 'alerts', [])
        data = {
            "generatedAt": now.isoformat(),
            "lastScan": last,
            "recentScans": [_format(i) for i in range(min(3, len(recent_scans)))],
            "nextScanAt": (self._calculate_next_scan_time().isoformat()
                           if self._calculate_next_scan_time() else None),
            # Alerty dla aplikacji: `alert` = najgroźniejszy (do banera), `alerts` = wszystkie
            "alert": alerts[0] if alerts else None,
            "alerts": alerts,
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
        alerts = getattr(self, 'alerts', [])
        system_status = self._determine_system_status(last_scan, statistics)
        if alerts and system_status == "operational":
            system_status = "degraded"
        has_critical = any(a['severity'] == 'critical' for a in alerts)

        status_data = {
            "system": "sonar",
            "version": "1.0.0",
            "generatedAt": datetime.now(self.tz).isoformat(),
            
            "status": {
                "current": system_status,
                "isHealthy": system_status in ["operational", "degraded"] and not has_critical,
                "hasErrors": has_errors,
                "errorMessages": error_messages,
                "hasAlerts": bool(alerts),
                "alertLevel": ("critical" if has_critical else "warning") if alerts else "none"
            },

            # Alerty jakościowe ostatniego skanu (masowy odpływ ofert, urwany scrape)
            "alerts": alerts,
            
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
        
        alerts = getattr(self, 'alerts', [])
        has_critical = any(a['severity'] == 'critical' for a in alerts)
        if not is_fresh:
            health_status = "stale"
        elif has_critical:
            health_status = "critical"
        elif alerts:
            health_status = "warning"
        else:
            health_status = "ok"

        health_data = {
            "status": health_status,  # ok | warning | critical | stale
            "timestamp": datetime.now(self.tz).isoformat(),
            "lastScanAt": last_scan['timestamp'] if last_scan else None,
            "hoursSinceLastScan": hours_since_last_scan,
            "isFresh": is_fresh,
            "alerts": [
                {"type": a["type"], "severity": a["severity"], "message": a["message"]}
                for a in alerts
            ],
            "systems": {
                "sonar": {
                    "enabled": True,
                    "lastStatus": last_scan.get('status', 'unknown') if last_scan else 'unknown'
                },
                "scanMonitor": {
                    "enabled": False,
                    "lastStatus": None,
                    "message": "Coming soon"
                }
            }
        }
        
        self._save_json("health.json", health_data)
        print(f"   💓 health.json - {health_status} ({hours_since_last_scan}h ago)")
    
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
        
        if last_scan.get('status') == 'warning':
            return "degraded"

        if last_scan.get('status') not in ('completed', 'warning'):
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
        """Zapisuje dane JSON do pliku (atomowo)."""
        write_json_atomic(self.output_dir / filename, data)


def main():
    """Główna funkcja - generuje wszystkie pliki API."""
    generator = APIGenerator()
    generator.generate_all()


if __name__ == "__main__":
    main()
