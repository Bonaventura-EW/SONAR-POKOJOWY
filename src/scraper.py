"""
OLX Scraper - pobiera wszystkie oferty pokoi w Lublinie
Obsługuje paginację (wszystkie strony), opóźnienia anti-block
"""

import requests
from bs4 import BeautifulSoup
import time
import random
from typing import List, Dict, Optional
from urllib.parse import urljoin

class OLXScraper:
    BASE_URL = "https://www.olx.pl/nieruchomosci/stancje-pokoje/lublin/"
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    def __init__(self, delay_range: tuple = (2, 4)):
        """
        Args:
            delay_range: Zakres opóźnień między requestami (min, max) w sekundach
        """
        self.delay_min, self.delay_max = delay_range
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    def _random_delay(self):
        """Losowe opóźnienie między requestami."""
        delay = random.uniform(self.delay_min, self.delay_max)
        time.sleep(delay)
    
    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        Pobiera stronę i zwraca BeautifulSoup object.
        """
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'lxml')
        except requests.RequestException as e:
            print(f"❌ Błąd pobierania {url}: {e}")
            return None
    
    def _extract_offers_from_page(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Wyciąga wszystkie oferty z pojedynczej strony.
        
        Returns:
            Lista Dict z kluczami: url, title, description_snippet, price_raw
        """
        offers = []
        
        # OLX używa różnych struktur HTML, szukamy głównych kontenerów
        # Wariant 1: div[data-cy="l-card"]
        listings = soup.find_all('div', {'data-cy': 'l-card'})
        
        if not listings:
            # Wariant 2: div zawierający link do ogłoszenia
            listings = soup.find_all('div', class_=lambda x: x and 'css-' in x and 'offer' in str(x).lower())
        
        for listing in listings:
            try:
                # URL ogłoszenia
                link_tag = listing.find('a', href=True)
                if not link_tag:
                    continue
                
                url = link_tag['href']
                if not url.startswith('http'):
                    url = urljoin(self.BASE_URL, url)
                
                # Pomijamy promowane/wyróżnione (czasem duplikaty)
                if '/d/oferta/' not in url:
                    continue
                
                # Tytuł
                title_tag = listing.find('h6') or listing.find('h4') or listing.find('strong')
                title = title_tag.get_text(strip=True) if title_tag else ""
                
                # Cena (raw text, będzie parsowana później)
                price_tag = listing.find('p', {'data-testid': 'ad-price'})
                if not price_tag:
                    price_tag = listing.find('p', class_=lambda x: x and 'price' in str(x).lower())
                
                price_raw = price_tag.get_text(strip=True) if price_tag else ""
                
                # Snippet opisu (jeśli dostępny na liście)
                desc_tag = listing.find('p', class_=lambda x: x and 'description' in str(x).lower())
                description_snippet = desc_tag.get_text(strip=True) if desc_tag else ""
                
                offers.append({
                    'url': url,
                    'title': title,
                    'description_snippet': description_snippet,
                    'price_raw': price_raw
                })
                
            except Exception as e:
                print(f"⚠️ Błąd parsowania ogłoszenia: {e}")
                continue
        
        return offers
    
    def _get_next_page_url(self, soup: BeautifulSoup, current_page: int) -> Optional[str]:
        """
        Znajduje URL następnej strony.
        
        Returns:
            URL następnej strony lub None jeśli to ostatnia
        """
        # Szukamy linku "następna" lub page=X
        next_link = soup.find('a', {'data-testid': 'pagination-forward'})
        
        if next_link and next_link.get('href'):
            return urljoin(self.BASE_URL, next_link['href'])
        
        # Alternatywnie: próbujemy page=X+1
        next_page_num = current_page + 1
        test_url = f"{self.BASE_URL}?page={next_page_num}"
        
        # Sprawdzamy czy następna strona istnieje (nie róbmy requesta, tylko sprawdźmy czy jest link)
        pagination = soup.find('ul', {'data-testid': 'pagination-list'})
        if pagination:
            page_links = pagination.find_all('a')
            for link in page_links:
                if f"page={next_page_num}" in link.get('href', ''):
                    return urljoin(self.BASE_URL, link['href'])
        
        return None
    
    def scrape_all_pages(self, max_pages: int = 20) -> List[Dict]:
        """
        Scrapuje wszystkie strony z ofertami (z limitem max_pages).
        
        Args:
            max_pages: Maksymalna liczba stron do przejrzenia (zabezpieczenie)
            
        Returns:
            Lista wszystkich ofert ze wszystkich stron
        """
        all_offers = []
        current_url = self.BASE_URL
        page_num = 1
        
        print(f"🔍 Rozpoczynam scraping OLX Lublin - Pokoje...")
        
        while current_url and page_num <= max_pages:
            print(f"📄 Strona {page_num}: {current_url}")
            
            soup = self._fetch_page(current_url)
            if not soup:
                print(f"⚠️ Nie udało się pobrać strony {page_num}")
                break
            
            # Wyciągamy oferty z tej strony
            offers = self._extract_offers_from_page(soup)
            print(f"   Znaleziono {len(offers)} ofert")
            
            if not offers:
                print("   ⚠️ Brak ofert na stronie - koniec paginacji")
                break
            
            # Pobierz pełny opis TYLKO jeśli w snippet nie ma numeru
            for i, offer in enumerate(offers, 1):
                snippet = offer['title'] + ' ' + offer.get('description_snippet', '')
                
                # Sprawdź czy snippet zawiera jakikolwiek numer (potencjalny adres)
                if not re.search(r'\d+', snippet):
                    print(f"   [{i}/{len(offers)}] Brak numeru w snippet, pobieram pełny opis...")
                    details = self.fetch_offer_details(offer['url'])
                    if details:
                        offer['description'] = details['description']
                        self._random_delay()
                else:
                    # Użyj snippet jako opisu
                    offer['description'] = snippet
            
            all_offers.extend(offers)
            
            # Sprawdzamy czy jest następna strona
            next_url = self._get_next_page_url(soup, page_num)
            
            if not next_url:
                print(f"✅ Osiągnięto ostatnią stronę")
                break
            
            current_url = next_url
            page_num += 1
            
            # Opóźnienie przed następną stroną
            if page_num <= max_pages:
                self._random_delay()
        
        print(f"\n✅ Scraping zakończony: {len(all_offers)} ofert z {page_num} stron")
        return all_offers
    
    def fetch_offer_details(self, url: str) -> Optional[Dict]:
        """
        Pobiera pełne szczegóły ogłoszenia (pełny opis).
        
        Args:
            url: URL ogłoszenia
            
        Returns:
            Dict z pełnym opisem i innymi danymi
        """
        soup = self._fetch_page(url)
        if not soup:
            return None
        
        try:
            # Pełny opis
            desc_div = soup.find('div', {'data-cy': 'ad_description'})
            if not desc_div:
                desc_div = soup.find('div', class_=lambda x: x and 'description' in str(x).lower())
            
            description = desc_div.get_text(strip=True) if desc_div else ""
            
            return {
                'description': description
            }
            
        except Exception as e:
            print(f"⚠️ Błąd parsowania szczegółów ogłoszenia {url}: {e}")
            return None


# Testy jednostkowe
if __name__ == "__main__":
    scraper = OLXScraper(delay_range=(1, 2))  # Krótsze opóźnienia dla testów
    
    print("🧪 Test scrapera - pierwsze 2 strony:\n")
    offers = scraper.scrape_all_pages(max_pages=2)
    
    print(f"\n📊 Podsumowanie:")
    print(f"   Łącznie ofert: {len(offers)}")
    
    if offers:
        print(f"\n📝 Przykładowa oferta:")
        sample = offers[0]
        print(f"   Tytuł: {sample['title'][:60]}...")
        print(f"   URL: {sample['url']}")
        print(f"   Cena: {sample['price_raw']}")
