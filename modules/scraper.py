"""
Nebula - Akakçe Scraper Modülü
Temel ürün ve fiyat çekme işlemleri
"""
import requests
from bs4 import BeautifulSoup
import logging
import re
import time
import random

logger = logging.getLogger("nebula.modules.scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class AkakceScraper:
    """Hafif, requests tabanlı Akakçe scraper."""

    BASE_URL = "https://www.akakce.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_prices(self, url: str) -> list[dict]:
        """Verilen URL'deki ürünlerin fiyatlarını döndürür."""
        logger.info(f"Taranan URL: {url}")
        try:
            time.sleep(random.uniform(1, 3))
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            products = []
            for item in soup.select("ul.pr_v8 > li, .w.pr_v8"):
                name_el = item.select_one("h3 a, a[data-event]")
                price_el = item.select_one(".pt_v8, [itemprop='price']")
                if name_el and price_el:
                    price_text = re.sub(r"[^\d,]", "", price_el.get_text(strip=True))
                    price = float(price_text.replace(",", ".")) if price_text else 0
                    products.append({
                        "item": name_el.get_text(strip=True),
                        "price": price,
                    })

            return products

        except requests.RequestException as exc:
            logger.error(f"İstek hatası: {exc}")
            return []
