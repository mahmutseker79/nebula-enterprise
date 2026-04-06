"""
scraper_v4.py  –  Full-stack Akakce Scraper
============================================
Neler çekiliyor:
  1. Kategori listesi + alt kategoriler + filtreler (chip_ff)
  2. Ürün listesi (ul.pl_v9 li.w) – paralel sayfa çekimi
  3. Her ürün için detay sayfası:
       • Tam specs tablosu   → JSONB
       • Tüm CDN görselleri  → yerel indir + DB kaydı
       • Satıcı fiyatları    → ul.pp_v8 li (mağaza + fiyat)
  4. En iyi fiyat flag'i (is_best)
  5. Anti-bot:
       • Selenium stealth (undetected_chromedriver veya options ile)
       • Rastgele User-Agent + viewport + dil + platform
       • Mouse hareketi + scroll simülasyonu
       • Session havuzu: her N istek sonrası profile yenile
       • İki katmanlı gecikme: liste ve detay için ayrı
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Sabitler ────────────────────────────────────────────────────────────────

AKAKCE_BASE   = "https://www.akakce.com"
IMAGE_DIR     = Path("outputs/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# Anti-bot User-Agent havuzu (2025 Q1 tarayıcılar)
USER_AGENTS = [
    # Chrome 131-133
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    # Firefox 132-134
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
    # Edge 131
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

VIEWPORTS = [
    (1920, 1080), (1440, 900), (1366, 768),
    (1536, 864),  (1280, 720), (2560, 1440),
]

LANGUAGES = ["tr-TR,tr;q=0.9,en-US;q=0.8", "tr,en;q=0.9", "tr-TR,tr;q=0.8,en;q=0.6"]

# ─── Veri yapıları ────────────────────────────────────────────────────────────

@dataclass
class SellerInfo:
    store_id:   str   = ""
    store_name: str   = ""
    price:      float = 0.0
    url:        str   = ""
    logo_url:   str   = ""
    is_best:    bool  = False


@dataclass
class ProductDetail:
    # Liste sayfasından
    product_id:  str   = ""
    name:        str   = ""
    price:       float = 0.0
    url:         str   = ""
    main_image:  str   = ""
    brand:       str   = ""
    # Detay sayfasından
    specs:       dict[str, str]   = field(default_factory=dict)
    images:      list[str]        = field(default_factory=list)
    sellers:     list[SellerInfo] = field(default_factory=list)
    best_price:  float = 0.0
    best_store:  str   = ""


@dataclass
class FilterChip:
    label:     str = ""
    group:     str = ""    # "Dahili Hafıza", "RAM Kapasitesi" vb.
    value:     str = ""    # "256 GB", "8 GB"
    akakce_id: str = ""
    url:       str = ""


# ═══════════════════════════════════════════════════════════════
# ANTI-BOT: Selenium kurulum
# ═══════════════════════════════════════════════════════════════

def _build_driver(headless: bool = True):
    """Stealth Chrome driver oluştur."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()

    # Temel
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")

    # Anti-bot
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Rastgele UA + viewport
    ua       = random.choice(USER_AGENTS)
    vw, vh   = random.choice(VIEWPORTS)
    lang     = random.choice(LANGUAGES)

    opts.add_argument(f"user-agent={ua}")
    opts.add_argument(f"--window-size={vw},{vh}")
    opts.add_argument(f"--lang={lang.split(',')[0]}")
    opts.add_argument("--accept-lang=" + lang)

    # Platform sahteciliği
    opts.add_argument("--disable-web-security")
    opts.add_argument("--allow-running-insecure-content")

    # Bellek / hız
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-default-apps")
    opts.add_argument("--no-first-run")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-translate")

    driver = webdriver.Chrome(options=opts)

    # navigator.webdriver'ı gizle
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins',   {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['tr-TR', 'tr', 'en-US', 'en']});
        window.chrome = {runtime: {}};
    """})

    return driver, ua


def _human_scroll(driver, steps: int = 3) -> None:
    """İnsan gibi scroll simülasyonu."""
    for _ in range(steps):
        scroll_y = random.randint(200, 600)
        driver.execute_script(f"window.scrollBy(0, {scroll_y});")
        time.sleep(random.uniform(0.3, 0.8))


def _random_delay(min_s: float = 1.0, max_s: float = 2.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


# ═══════════════════════════════════════════════════════════════
# JS: Ürün listesi çek
# ═══════════════════════════════════════════════════════════════

JS_PRODUCT_LIST = """
const items = Array.from(document.querySelectorAll('ul.pl_v9 > li[data-pr]'));
return items.map(li => {
  const pt  = li.querySelector('[class^="pt_"]');
  const img = li.querySelector('img');
  const src = img?.src || img?.dataset?.src || '';
  const raw = pt ? (pt.childNodes[0]?.textContent?.trim() || '') : '';
  return {
    id:    li.dataset.pr  || '',
    brand: li.dataset.mk  || '',
    name:  li.querySelector('a.pw_v8')?.title || li.querySelector('h3')?.textContent?.trim() || '',
    price: raw,
    url:   li.querySelector('a.pw_v8')?.href || '',
    img:   src.startsWith('//') ? 'https:' + src : src
  };
});
"""

# ═══════════════════════════════════════════════════════════════
# JS: Filtreler + alt kategoriler
# ═══════════════════════════════════════════════════════════════

JS_FILTERS = """
// 1. Chip filtreleri (önerilen/aktif filtreler)
const chips = Array.from(document.querySelectorAll('li.chip_ff')).map(li => {
  const a = li.querySelector('a');
  const text = li.textContent.trim();
  // "Dahili Hafıza 256 GB" → group="Dahili Hafıza", value="256 GB"
  const match = text.match(/^(.+?)\\s+(\\S+(?:\\s+\\S+)?)$/);
  return {
    label:     text,
    group:     match ? match[1] : text,
    value:     match ? match[2] : '',
    akakce_id: li.dataset.id || '',
    url:       a ? a.href.replace('https://www.akakce.com','') : ''
  };
});

// 2. Tüm iç linkler (sub-kategori + filtreler)
const internalLinks = Array.from(document.querySelectorAll('a[href*=".html"]'))
  .map(a => ({text: a.textContent.trim(), href: a.href}))
  .filter(l => l.text && l.href.includes('akakce.com') && !l.href.includes('fiyati,'));
const uniqueLinks = [...new Map(internalLinks.map(l => [l.href, l])).values()];

// 3. Sayfalama bilgisi
const pager = document.querySelector('.pager_v8');
const totalPages = pager ? (pager.textContent.match(/\\/ (\\d+)/)?.[1] || '1') : '1';

return {chips, links: uniqueLinks.slice(0,80), totalPages: parseInt(totalPages)};
"""

# ═══════════════════════════════════════════════════════════════
# JS: Ürün detay sayfası
# ═══════════════════════════════════════════════════════════════

JS_PRODUCT_DETAIL = """
// SPECS — tüm tablo satırları
const specs = {};
document.querySelectorAll('table tr').forEach(tr => {
  const cells = Array.from(tr.querySelectorAll('td,th'));
  if (cells.length >= 2) {
    const k = cells[0].textContent.trim().replace(/:\\s*/,'');
    const v = cells[1].textContent.trim().replace(/^:\\s*/,'');
    if (k && v && k !== 'Özellik' && k.length < 100) specs[k] = v;
  }
});

// GÖRSELLER — CDN görsel listesi
const imgs = Array.from(new Set(
  Array.from(document.querySelectorAll('img[src*="cdn.akakce"]'))
    .map(i => i.src)
    .filter(Boolean)
));

// SATICILAR — pp_v8 listesi
const sellers = Array.from(document.querySelectorAll('ul.pp_v8 li')).map(li => {
  const pt   = li.querySelector('span.pt_v8');
  const priceText = pt ? pt.childNodes[0]?.textContent?.trim() : '';
  const imgEl = li.querySelector('img');
  const imgSrc = imgEl?.src || '';
  // Mağaza ID: cdn.akakce.com/im/m6/{id}.svg
  const storeId = imgSrc.match(/\\/m6\\/(\\d+)/)?.[1] || '';
  const storeName = li.querySelector('[class*="st_"]')?.textContent?.trim() || '';
  return {storeId, storeName, price: priceText, logoUrl: imgSrc};
}).filter(s => s.price && parseFloat(s.price.replace(/[^\\d.]/,'')) > 0);

// EN UCUZ
let bestPrice = Infinity, bestStore = '';
sellers.forEach(s => {
  const p = parseFloat(s.price.replace(/[^\\d.,]/g,'').replace(',','.'));
  if (!isNaN(p) && p < bestPrice) { bestPrice = p; bestStore = s.storeId; }
});
sellers.forEach(s => {
  const p = parseFloat(s.price.replace(/[^\\d.,]/g,'').replace(',','.'));
  s.isBest = (!isNaN(p) && p === bestPrice);
});

return {specs, imgs, sellers, bestStore};
"""


# ═══════════════════════════════════════════════════════════════
# Yardımcı: fiyat parse
# ═══════════════════════════════════════════════════════════════

def _parse_price(raw: str) -> float:
    """'32.299,00 TL' → 32299.0"""
    cleaned = re.sub(r"[^\d,.]", "", (raw or "").strip())
    parts = cleaned.split(",")
    if len(parts) == 2:
        return float(parts[0].replace(".", "") + "." + parts[1][:2])
    else:
        return float(cleaned.replace(".", "") or 0)


# ═══════════════════════════════════════════════════════════════
# Görsel indirme
# ═══════════════════════════════════════════════════════════════

def _download_image(url: str, product_id: str) -> str | None:
    """Görseli indir, yerel yolu döndür."""
    if not url or not url.startswith("http"):
        return None
    try:
        import urllib.request
        ext      = Path(url.split("?")[0]).suffix or ".jpg"
        fname    = hashlib.md5(url.encode()).hexdigest() + ext
        local_p  = IMAGE_DIR / fname
        if local_p.exists():
            return str(local_p)
        headers  = {"User-Agent": random.choice(USER_AGENTS), "Referer": AKAKCE_BASE}
        req      = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            local_p.write_bytes(resp.read())
        return str(local_p)
    except Exception as exc:
        logger.debug("Görsel indirilemedi [%s]: %s", url, exc)
        return None


# ═══════════════════════════════════════════════════════════════
# ANA SCRAPER SINIFI
# ═══════════════════════════════════════════════════════════════

class AkakceScraperV4:
    """
    Kullanım:
        scraper = AkakceScraperV4(headless=True, download_images=True)
        result  = scraper.scrape_category(
            category_url="https://www.akakce.com/cep-telefonu.html",
            max_products=100,
            detail=True,        # ürün detay sayfasına git
        )
    """

    def __init__(
        self,
        headless:         bool  = True,
        download_images:  bool  = True,
        detail_workers:   int   = 3,       # eş zamanlı detay thread sayısı
        list_delay:       tuple = (1.0, 2.0),
        detail_delay:     tuple = (1.5, 3.0),
        session_refresh:  int   = 30,      # her N sayfa sonrası driver yenile
    ) -> None:
        self.headless        = headless
        self.download_images = download_images
        self.detail_workers  = detail_workers
        self.list_delay      = list_delay
        self.detail_delay    = detail_delay
        self.session_refresh = session_refresh
        self._driver         = None
        self._ua             = ""
        self._request_count  = 0

    # ── Driver yönetimi ──────────────────────────────────────────────────────

    def _init_driver(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
        self._driver, self._ua = _build_driver(self.headless)
        self._request_count    = 0
        logger.info("Driver başlatıldı: %s…", self._ua[:50])

    def _maybe_refresh_driver(self) -> None:
        """Session sınırına ulaşıldıysa driver'ı yenile."""
        self._request_count += 1
        if self._request_count >= self.session_refresh:
            logger.info("Session yenileniyor (%d istek yapıldı)", self._request_count)
            self._init_driver()

    def _get(self, url: str, wait_sel: str | None = None, delay: tuple = (1.0, 2.0)) -> bool:
        """URL'ye git, opsiyonel element bekle."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        self._maybe_refresh_driver()
        try:
            self._driver.get(url)
            if wait_sel:
                WebDriverWait(self._driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_sel))
                )
            _human_scroll(self._driver, steps=random.randint(1, 3))
            _random_delay(*delay)
            return True
        except Exception as exc:
            logger.warning("GET başarısız [%s]: %s", url, exc)
            return False

    def close(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    # ── Context manager ──────────────────────────────────────────────────────

    def __enter__(self) -> "AkakceScraperV4":
        self._init_driver()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── Filtreler ────────────────────────────────────────────────────────────

    def scrape_filters(self, category_url: str) -> tuple[list[FilterChip], int]:
        """
        Kategori sayfasından filtre chip'leri + toplam sayfa sayısı döndürür.
        Returns: (filters_list, total_pages)
        """
        ok = self._get(category_url, "ul.pl_v9", self.list_delay)
        if not ok:
            return [], 1

        data   = self._driver.execute_script(JS_FILTERS) or {}
        chips  = data.get("chips", [])
        pages  = data.get("totalPages", 1)

        filters = []
        for c in chips:
            filters.append(FilterChip(
                label=c.get("label",""),
                group=c.get("group",""),
                value=c.get("value",""),
                akakce_id=c.get("akakce_id",""),
                url=c.get("url",""),
            ))

        logger.info("Filtreler: %d chip | Toplam sayfa: %d", len(filters), pages)
        return filters, pages

    # ── Ürün Listesi ─────────────────────────────────────────────────────────

    def scrape_product_list(
        self,
        category_url: str,
        max_products:  int = 100,
    ) -> list[ProductDetail]:
        """
        Kategori listesinden ürünleri çeker.
        URL formatı: cep-telefonu.html → cep-telefonu,2.html → ...
        """
        # Temel URL + sayfa URL kalıbı
        base_html = category_url  # .html ile bitiyor
        base_part = re.sub(r"\.html$", "", base_html)  # uzantısız

        all_products: list[ProductDetail] = []
        seen_ids: set[str] = set()
        page = 1

        while len(all_products) < max_products:
            page_url = base_html if page == 1 else f"{base_part},{page}.html"
            ok = self._get(page_url, "ul.pl_v9", self.list_delay)
            if not ok:
                break

            rows = self._driver.execute_script(JS_PRODUCT_LIST) or []
            if not rows:
                logger.info("Sayfa %d boş, dur.", page)
                break

            new_count = 0
            for r in rows:
                pid = r.get("id", "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                all_products.append(ProductDetail(
                    product_id=pid,
                    name=r.get("name", ""),
                    price=_parse_price(r.get("price", "")),
                    url=r.get("url", ""),
                    main_image=r.get("img", ""),
                    brand=r.get("brand", ""),
                ))
                new_count += 1
                if len(all_products) >= max_products:
                    break

            logger.info("Sayfa %d: %d yeni | Toplam: %d", page, new_count, len(all_products))
            if new_count == 0:
                break
            page += 1

        return all_products[:max_products]

    # ── Ürün Detayı ──────────────────────────────────────────────────────────

    def scrape_product_detail(self, product: ProductDetail) -> ProductDetail:
        """
        Tek ürün detay sayfasını scrape et:
          specs, images, sellers
        """
        if not product.url:
            return product

        ok = self._get(product.url, "table", self.detail_delay)
        if not ok:
            return product

        data = self._driver.execute_script(JS_PRODUCT_DETAIL) or {}

        # Specs
        raw_specs = data.get("specs", {})
        product.specs = {
            k: re.sub(r"\s+", " ", v).strip()
            for k, v in raw_specs.items()
            if k and v
        }

        # Görseller
        imgs = data.get("imgs", [])
        product.images = list(dict.fromkeys(imgs))  # dedup sıra koruyarak

        # Satıcılar
        sellers: list[SellerInfo] = []
        for s in (data.get("sellers") or []):
            raw_p = s.get("price", "")
            price = _parse_price(raw_p)
            if price > 0:
                sellers.append(SellerInfo(
                    store_id=s.get("storeId", ""),
                    store_name=s.get("storeName", ""),
                    price=price,
                    logo_url=s.get("logoUrl", ""),
                    is_best=bool(s.get("isBest", False)),
                ))
        sellers.sort(key=lambda x: x.price)
        product.sellers = sellers

        if sellers:
            product.best_price = sellers[0].price
            product.best_store = sellers[0].store_id

        # Görselleri indir
        if self.download_images and product.images:
            local_paths = []
            for img_url in product.images[:8]:  # max 8 görsel/ürün
                lp = _download_image(img_url, product.product_id)
                if lp:
                    local_paths.append(lp)
            logger.debug("Ürün %s: %d görsel indirildi", product.product_id, len(local_paths))

        logger.debug(
            "Detay [%s]: %d spec | %d img | %d satıcı | en iyi %.2f",
            product.product_id, len(product.specs),
            len(product.images), len(product.sellers),
            product.best_price,
        )
        return product

    # ── Ana Pipeline ─────────────────────────────────────────────────────────

    def scrape_category(
        self,
        category_url:  str,
        max_products:  int  = 100,
        detail:        bool = True,
        max_pages:     int  = 10,
    ) -> dict[str, Any]:
        """
        Tam pipeline:
          1. Filtreler
          2. Ürün listesi
          3. (opsiyonel) Her ürün için detay sayfası

        Returns:
            {
              "products": [ProductDetail, ...],
              "filters":  [FilterChip,  ...],
              "total_pages": int,
              "scraped_at": str,
            }
        """
        t0 = time.monotonic()
        logger.info("Pipeline başlıyor: %s (max %d)", category_url, max_products)

        # 1. Filtreler
        filters, total_pages = self.scrape_filters(category_url)

        # 2. Ürün listesi
        products = self.scrape_product_list(category_url, max_products)
        logger.info("Liste tamamlandı: %d ürün", len(products))

        # 3. Detay (her ürün)
        if detail and products:
            logger.info("Detay scrape başlıyor (%d ürün)…", len(products))
            for i, p in enumerate(products, 1):
                products[i - 1] = self.scrape_product_detail(p)
                if i % 10 == 0:
                    logger.info("Detay: %d/%d tamamlandı", i, len(products))

        elapsed = time.monotonic() - t0
        logger.info(
            "Pipeline bitti: %d ürün | %d filtre | %.1f sn",
            len(products), len(filters), elapsed,
        )
        return {
            "products":     products,
            "filters":      filters,
            "total_pages":  total_pages,
            "category_url": category_url,
            "scraped_at":   datetime.now(timezone.utc).isoformat(),
            "elapsed_sec":  round(elapsed, 1),
        }

    # ── Sonuçları JSON / Excel olarak kaydet ─────────────────────────────────

    @staticmethod
    def save_to_json(result: dict[str, Any], path: str) -> None:
        def _serial(obj: Any) -> Any:
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _serial(getattr(obj, k)) for k in obj.__dataclass_fields__}
            if isinstance(obj, list):
                return [_serial(i) for i in obj]
            return obj

        with open(path, "w", encoding="utf-8") as f:
            json.dump(_serial(result), f, ensure_ascii=False, indent=2)
        logger.info("JSON kaydedildi: %s", path)

    @staticmethod
    def save_to_excel(result: dict[str, Any], path: str) -> None:
        import pandas as pd

        products = result.get("products", [])
        if not products:
            return

        rows = []
        for i, p in enumerate(products, 1):
            best = p.sellers[0] if p.sellers else None
            rows.append({
                "No":             i,
                "Urun Adi":       p.name,
                "Marka":          p.brand,
                "Fiyat (TL)":     p.price,
                "En Iyi Fiyat":   p.best_price or p.price,
                "En Iyi Magaza":  p.best_store,
                "Satici Sayisi":  len(p.sellers),
                "Spec Sayisi":    len(p.specs),
                "Gorsel Sayisi":  len(p.images),
                "URL":            p.url,
                "Ana Gorsel":     p.main_image,
                # En popüler specs
                "RAM":            p.specs.get("RAM", ""),
                "Dahili Hafiza":  p.specs.get("Dahili Hafıza", ""),
                "Ekran":          p.specs.get("Ekran Boyutu", ""),
                "Batarya":        p.specs.get("Batarya Kapasitesi", ""),
                "Cikis Yili":     p.specs.get("Çıkış Yılı", ""),
                "Islemci":        p.specs.get("Chipset", p.specs.get("İşlemci", "")),
                "Renk":           p.specs.get("Renk Seçenekleri", ""),
            })

        df = pd.DataFrame(rows)

        # Satıcı fiyatları — ayrı sheet
        seller_rows = []
        for p in products:
            for s in p.sellers:
                seller_rows.append({
                    "Urun Adi":  p.name,
                    "Urun ID":   p.product_id,
                    "Magaza ID": s.store_id,
                    "Fiyat":     s.price,
                    "En Ucuz":   "EVET" if s.is_best else "",
                    "Logo":      s.logo_url,
                })
        df_sellers = pd.DataFrame(seller_rows)

        # Filtreler — ayrı sheet
        filters = result.get("filters", [])
        df_filters = pd.DataFrame([{
            "Grup":      f.group,
            "Deger":     f.value,
            "Etiket":    f.label,
            "ID":        f.akakce_id,
            "URL":       f.url,
        } for f in filters])

        with pd.ExcelWriter(path, engine="openpyxl") as wr:
            df.to_excel(wr,         index=False, sheet_name="Urunler")
            df_sellers.to_excel(wr, index=False, sheet_name="Satici_Fiyatlari")
            df_filters.to_excel(wr, index=False, sheet_name="Filtreler")

            for sheet_name in wr.sheets:
                ws = wr.sheets[sheet_name]
                for col in ws.columns:
                    ml = max((len(str(c.value or "")) for c in col), default=10)
                    ws.column_dimensions[col[0].column_letter].width = min(ml + 2, 60)

        logger.info("Excel kaydedildi: %s  (3 sheet)", path)
