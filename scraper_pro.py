"""
Nebula Enterprise - Gelişmiş Anti-Bot Scraper
cloudscraper + BeautifulSoup + stealth header rotasyonu
Cloudflare, Imperva, DataDome korumalarını bypass eder.
"""
import cloudscraper
from bs4 import BeautifulSoup
import time
import random
import logging
import re
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("nebula.scraper")

# ─── Stealth Header Havuzu ───────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

ACCEPT_LANGUAGES = [
    "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "tr,en-US;q=0.9,en;q=0.8",
    "tr-TR,tr;q=0.8,en;q=0.6",
]


def _build_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


# ─── Ana Scraper Sınıfı ──────────────────────────────────────────────────────
class AkakceScraper:
    BASE_URL = "https://www.akakce.com"

    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False},
            delay=10
        )

    # ── Düşük Seviye GET ──────────────────────────────────────────────────────
    def _get(self, url: str, retries: int = 4) -> Optional[BeautifulSoup]:
        for attempt in range(1, retries + 1):
            try:
                delay = random.uniform(1.5, 4.0) + (attempt - 1) * 2
                time.sleep(delay)

                resp = self.scraper.get(
                    url,
                    headers=_build_headers(),
                    timeout=20,
                    allow_redirects=True
                )
                resp.raise_for_status()

                if len(resp.content) < 500:
                    raise ValueError("Yanıt çok kısa — muhtemelen bot tespiti")

                return BeautifulSoup(resp.text, "lxml")

            except Exception as exc:
                logger.warning(f"[{attempt}/{retries}] GET başarısız → {url} | {exc}")
                if attempt == retries:
                    logger.error(f"Tüm denemeler tükendi: {url}")
                    return None

    # ── Kategori Listesi ──────────────────────────────────────────────────────
    def get_categories(self) -> list[dict]:
        soup = self._get(self.BASE_URL)
        if not soup:
            return []

        categories = []
        for link in soup.select("nav a[href]"):
            href = link.get("href", "")
            name = link.get_text(strip=True)
            if not name or len(name) < 2:
                continue
            full_url = self.BASE_URL + href if href.startswith("/") else href
            slug = href.strip("/").replace("/", "-")
            categories.append({"name": name, "url": full_url, "slug": slug})

        logger.info(f"{len(categories)} kategori bulundu")
        return categories

    # ── Kategori Tarama ───────────────────────────────────────────────────────
    def scrape_category(self, url: str, max_pages: int = 5) -> list[dict]:
        products = []

        for page in range(1, max_pages + 1):
            page_url = f"{url}?pg={page}" if page > 1 else url
            soup = self._get(page_url)
            if not soup:
                logger.warning(f"Sayfa alınamadı: {page_url}")
                break

            items = (
                soup.select("ul.pr_v8 > li")
                or soup.select(".w.pr_v8")
                or soup.select("[class*='productList'] li")
            )

            if not items:
                logger.info(f"Sayfa {page}: ürün yok — duruluyor")
                break

            for item in items:
                product = self._parse_item(item)
                if product:
                    products.append(product)

            logger.info(f"Sayfa {page}: {len(items)} ürün | Toplam: {len(products)}")

        return products

    # ── Ürün Satırı Parse ─────────────────────────────────────────────────────
    def _parse_item(self, item) -> Optional[dict]:
        try:
            name_el = item.select_one("h3 a, h2 a, .pt_v8 a, a[data-event]")
            price_el = item.select_one(".pt_v8, [class*='price'], [itemprop='price']")
            img_el = item.select_one("img[src], img[data-src]")
            link_el = item.select_one("a[href]")

            if not name_el:
                return None

            name = name_el.get_text(strip=True)
            price_text = price_el.get_text(strip=True) if price_el else "0"
            price = self._parse_price(price_text)
            image_url = (
                img_el.get("src") or img_el.get("data-src") or ""
            ) if img_el else ""
            href = link_el.get("href", "") if link_el else ""
            full_url = self.BASE_URL + href if href.startswith("/") else href

            return {
                "name": name,
                "price": price,
                "image_url": image_url,
                "url": full_url,
                "specs": {},
            }
        except Exception as exc:
            logger.debug(f"Item parse hatası: {exc}")
            return None

    # ── Ürün Detay Sayfası ────────────────────────────────────────────────────
    def scrape_product_detail(self, url: str) -> dict:
        soup = self._get(url)
        if not soup:
            return {}

        specs: dict = {}

        # Spec tablosu selectors (akakce yapısına göre)
        for row in soup.select(".spec_list li, table.spec tr, [class*='spec'] li"):
            label_el = row.select_one("b, strong, th, .spec_name")
            value_el = row.select_one("span, td, .spec_value")
            if label_el and value_el:
                key = label_el.get_text(strip=True).rstrip(":")
                val = value_el.get_text(strip=True)
                if key and val:
                    specs[key] = val

        # Marka çıkar
        brand = None
        brand_el = soup.select_one("[itemprop='brand'], .brand_name, a[href*='/marka/']")
        if brand_el:
            brand = brand_el.get_text(strip=True)

        description_el = soup.select_one("[itemprop='description'], .description, .desc")
        description = description_el.get_text(strip=True) if description_el else ""

        return {
            "specs": specs,
            "brand": brand,
            "description": description,
        }

    # ── Fiyat Parse Yardımcısı ────────────────────────────────────────────────
    @staticmethod
    def _parse_price(text: str) -> float:
        try:
            cleaned = re.sub(r"[^\d,\.]", "", text)
            # Türkçe format: 1.299,99 TL
            if "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            elif "," in cleaned:
                cleaned = cleaned.replace(",", ".")
            return round(float(cleaned), 2)
        except Exception:
            return 0.0
