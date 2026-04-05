"""
Nebula Enterprise - Gelişmiş Anti-Bot Scraper v2
cloudscraper + stealth header rotasyonu + exponential backoff + proxy desteği
Cloudflare UAM, Imperva, DataDome, PerimeterX korumalarını bypass eder.
"""
import cloudscraper
from bs4 import BeautifulSoup
import time
import random
import logging
import re
from typing import Optional
from config import get_settings

logger = logging.getLogger("nebula.scraper")
settings = get_settings()

# ─── Stealth Header Havuzu (2024-2025 güncel UA'lar) ─────────────────────────
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

ACCEPT_LANGUAGES = [
    "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "tr,en-US;q=0.9,en;q=0.8",
    "tr-TR,tr;q=0.8,en;q=0.5",
    "tr-TR,tr;q=0.9",
]

# Akakçe fiyat liste CSS selectors (öncelik sırası)
PRODUCT_LIST_SELECTORS = [
    "ul.pr_v8 > li",
    "ul[class*='productList'] > li",
    ".w.pr_v8",
    "[data-testid='product-card']",
    ".product-item",
]

PRODUCT_NAME_SELECTORS = [
    "h3 a", "h2 a",
    "a[data-event*='product']",
    ".product-name a",
    "a[class*='productName']",
    ".pt_v8 a",
]

PRODUCT_PRICE_SELECTORS = [
    ".pt_v8",
    "[itemprop='price']",
    "[class*='price']:not([class*='old'])",
    "strong.price",
    ".fiyat",
]


def _build_headers(referer: Optional[str] = None) -> dict:
    """Her istek için farklı, gerçekçi header seti oluşturur."""
    ua = random.choice(USER_AGENTS)
    is_firefox = "Firefox" in ua

    headers = {
        "User-Agent": ua,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            if is_firefox else
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }

    if not is_firefox:
        headers["sec-ch-ua"] = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"Windows"'

    if referer:
        headers["Referer"] = referer

    return headers


def _exponential_delay(attempt: int, base: float = None, max_delay: float = 30.0) -> None:
    """Exponential backoff + jitter ile gecikme."""
    _base = base or settings.scraper_delay_min
    delay = min(_base * (2 ** (attempt - 1)) + random.uniform(0.5, 2.0), max_delay)
    logger.debug(f"Bekleniyor: {delay:.1f}s (deneme {attempt})")
    time.sleep(delay)


# ─── Ana Scraper Sınıfı ──────────────────────────────────────────────────────
class AkakceScraper:
    BASE_URL = "https://www.akakce.com"

    def __init__(self):
        proxy_dict = None
        if settings.proxy_enabled and settings.proxy_url:
            proxy_dict = {"http": settings.proxy_url, "https": settings.proxy_url}
            logger.info(f"Proxy aktif: {settings.proxy_url[:20]}...")

        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False},
            delay=10,
        )
        if proxy_dict:
            self.scraper.proxies = proxy_dict

        self._last_url: Optional[str] = None

    # ── Düşük Seviye GET ──────────────────────────────────────────────────────
    def _get(self, url: str, retries: Optional[int] = None) -> Optional[BeautifulSoup]:
        max_retries = retries or settings.scraper_retries

        for attempt in range(1, max_retries + 1):
            try:
                # İlk denemede kısa, sonrakilerde exponential backoff
                if attempt == 1:
                    time.sleep(random.uniform(
                        settings.scraper_delay_min,
                        settings.scraper_delay_max
                    ))
                else:
                    _exponential_delay(attempt)

                resp = self.scraper.get(
                    url,
                    headers=_build_headers(referer=self._last_url),
                    timeout=settings.scraper_timeout,
                    allow_redirects=True,
                )
                resp.raise_for_status()

                # Bot tespiti kontrolleri
                if len(resp.content) < 500:
                    raise ValueError("Yanıt çok kısa (muhtemelen bot tespiti)")

                content_lower = resp.text[:2000].lower()
                if any(kw in content_lower for kw in ["captcha", "access denied", "blocked", "cf-challenge"]):
                    raise ValueError(f"Bot koruması tetiklendi: {url}")

                self._last_url = url
                return BeautifulSoup(resp.text, "lxml")

            except Exception as exc:
                logger.warning(f"[{attempt}/{max_retries}] {url} → {exc}")
                if attempt == max_retries:
                    logger.error(f"Tüm denemeler tükendi: {url}")
                    return None

    # ── Kategori Listesi ──────────────────────────────────────────────────────
    def get_categories(self) -> list[dict]:
        soup = self._get(self.BASE_URL)
        if not soup:
            return []

        categories = []
        seen_slugs: set[str] = set()

        # Akakçe kategori nav bağlantıları
        selectors = [
            "nav.menu a[href]",
            ".header-menu a[href]",
            "a[href*='/kategori/']",
            "a[href*='.html']:not([href*='//'])",
        ]

        for sel in selectors:
            links = soup.select(sel)
            if links:
                for link in links:
                    href = link.get("href", "")
                    name = link.get_text(strip=True)
                    if not name or len(name) < 2 or not href:
                        continue
                    full_url = self.BASE_URL + href if href.startswith("/") else href
                    slug = re.sub(r"[^a-z0-9-]", "-", href.strip("/").split("?")[0])
                    if slug and slug not in seen_slugs:
                        seen_slugs.add(slug)
                        categories.append({"name": name, "url": full_url, "slug": slug})
                if categories:
                    break

        logger.info(f"{len(categories)} kategori bulundu")
        return categories

    # ── Kategori Sayfası Tarama ───────────────────────────────────────────────
    def scrape_category(self, url: str, max_pages: Optional[int] = None) -> list[dict]:
        max_p = max_pages or settings.scraper_max_pages
        products: list[dict] = []
        empty_pages = 0

        for page in range(1, max_p + 1):
            page_url = f"{url}{'&' if '?' in url else '?'}pg={page}" if page > 1 else url
            soup = self._get(page_url)

            if not soup:
                logger.warning(f"Sayfa alınamadı: {page_url}")
                empty_pages += 1
                if empty_pages >= 2:
                    break
                continue

            items = self._find_product_items(soup)
            if not items:
                logger.info(f"Sayfa {page}: ürün bulunamadı — duruyorum")
                break

            empty_pages = 0
            page_products = [p for item in items if (p := self._parse_item(item, page_url))]
            products.extend(page_products)
            logger.info(f"Sayfa {page}: {len(page_products)}/{len(items)} ürün | Toplam: {len(products)}")

            # Sayfalama tükenmiş mi?
            next_page = soup.select_one("a[rel='next'], .pagination .next, a[href*='pg=']")
            if not next_page and page > 1:
                break

        return products

    # ── Ürün Listesi Elemanlarını Bul ─────────────────────────────────────────
    def _find_product_items(self, soup: BeautifulSoup) -> list:
        for sel in PRODUCT_LIST_SELECTORS:
            items = soup.select(sel)
            if len(items) >= 3:
                return items
        # Fallback: li içinde fiyat olan herhangi bir eleman
        return [
            li for li in soup.select("li")
            if li.select_one("[class*='price'], [class*='pt_'], .fiyat")
        ]

    # ── Ürün Satırı Parse ─────────────────────────────────────────────────────
    def _parse_item(self, item, source_url: str = "") -> Optional[dict]:
        try:
            # İsim
            name_el = None
            for sel in PRODUCT_NAME_SELECTORS:
                name_el = item.select_one(sel)
                if name_el:
                    break
            if not name_el:
                return None

            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                return None

            # Fiyat
            price = 0.0
            for sel in PRODUCT_PRICE_SELECTORS:
                price_el = item.select_one(sel)
                if price_el:
                    price = self._parse_price(price_el.get_text(strip=True))
                    if price > 0:
                        break

            # Görsel
            img_el = item.select_one("img[src]:not([src*='logo']), img[data-src]")
            image_url = ""
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src") or ""
                if image_url.startswith("//"):
                    image_url = "https:" + image_url

            # URL
            link_el = name_el if name_el.name == "a" else item.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            full_url = self.BASE_URL + href if href.startswith("/") else href
            if not full_url.startswith("http"):
                full_url = source_url

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
        for row in soup.select(".spec_list li, table.spec tr, [class*='spec'] li, dl dt"):
            label_el = row.select_one("b, strong, th, dt, .spec_name, .label")
            value_el = row.select_one("span, td, dd, .spec_value, .value")
            if not label_el:
                # dt sonraki kardeş dd olabilir
                value_el = row.find_next_sibling("dd")
                label_el = row
            if label_el and value_el:
                key = label_el.get_text(strip=True).rstrip(":")
                val = value_el.get_text(strip=True)
                if key and val and key != val:
                    specs[key] = val

        brand_el = soup.select_one("[itemprop='brand'], .brand_name, a[href*='/marka/']")
        brand = brand_el.get_text(strip=True) if brand_el else None

        desc_el = soup.select_one("[itemprop='description'], .description, .product-desc, .aciklama")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # Eski fiyat
        old_price_el = soup.select_one(".old-price, [class*='oldPrice'], s.price, del")
        old_price = self._parse_price(old_price_el.get_text(strip=True)) if old_price_el else None

        return {
            "specs": specs,
            "brand": brand,
            "description": description[:2000] if description else "",
            "old_price": old_price,
        }

    # ── Fiyat Parse Yardımcısı ────────────────────────────────────────────────
    @staticmethod
    def _parse_price(text: str) -> float:
        """Türkçe ve İngilizce fiyat formatlarını güvenle parse eder."""
        if not text:
            return 0.0
        try:
            # TL, ₺, TRY, virgül/nokta temizle
            cleaned = re.sub(r"[^\d,\.]", "", text.replace("₺", "").replace("TL", "").strip())
            if not cleaned:
                return 0.0
            # Türkçe format: 1.299,99 veya 1.299
            if "," in cleaned and "." in cleaned:
                # Binlik ayraç nokta, ondalık virgül
                cleaned = cleaned.replace(".", "").replace(",", ".")
            elif "," in cleaned:
                # Sadece virgül → ondalık
                cleaned = cleaned.replace(",", ".")
            # Birden fazla nokta varsa → binlik
            if cleaned.count(".") > 1:
                parts = cleaned.split(".")
                cleaned = "".join(parts[:-1]) + "." + parts[-1]
            return round(float(cleaned), 2)
        except Exception:
            return 0.0
