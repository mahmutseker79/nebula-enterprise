# Nebula Enterprise 🛒

**Türk e-ticaret fiyat takip ve analiz platformu**

Akakçe ve diğer Türk e-ticaret sitelerinden ürün, fiyat ve özellik verisi toplayan; PostgreSQL'de saklayan ve FastAPI üzerinden sunan tam kapsamlı backend sistemi.

---

## Özellikler

- 🤖 **Anti-Bot Scraper** — cloudscraper + stealth header rotasyonu (Cloudflare bypass)
- 🗄️ **PostgreSQL + SQLAlchemy ORM** — Kategori, Marka, Ürün, Fiyat Geçmişi, Spec JSON
- ⚡ **FastAPI** — Otomatik Swagger/ReDoc dokümantasyonu, CORS, background tasks
- 📊 **Pandas Raporlama** — CSV/Excel çıktısı, fiyat istatistikleri
- 🖼️ **WebP Dönüştürücü** — Pillow ile toplu PNG/JPG → WebP
- 🔄 **Modüler Mimari** — Her modül bağımsız test edilebilir

---

## Kurulum

### 1. PostgreSQL Hazırla

PostgreSQL kuruluysa `pgAdmin` üzerinden `nebuladb` adında boş bir veritabanı oluştur.

### 2. Projeyi Başlat

```bash
# .env dosyasını düzenle
copy .env.example .env
# İçindeki DATABASE_URL'yi kendi PostgreSQL bilgilerinle güncelle

# Sunucuyu başlat (venv + pip + uvicorn otomatik)
baslat.bat
```

### 3. API'yi Test Et

Tarayıcıdan: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Proje Yapısı

```
Nebula_Enterprise/
├── main.py              # FastAPI uygulaması (endpoint'ler)
├── database.py          # PostgreSQL bağlantısı (SQLAlchemy engine)
├── models.py            # ORM modelleri: Category, Brand, Product, PriceHistory
├── scraper_pro.py       # Anti-bot gelişmiş scraper (cloudscraper)
├── modules/
│   ├── scraper.py       # Hafif requests tabanlı scraper
│   ├── analyzer.py      # Pandas analiz ve CSV raporlama
│   └── webp_converter.py# PNG/JPG → WebP dönüştürücü
├── images/              # WebP dönüşümü için kaynak resimler
├── outputs/
│   ├── reports/         # CSV raporları
│   └── webp_images/     # Dönüştürülmüş WebP'ler
├── requirements.txt
├── .env.example
├── baslat.bat           # Windows başlatıcı (tek tıkla çalıştır)
└── README.md
```

---

## API Endpoint'leri

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/health` | Sağlık kontrolü |
| GET | `/api/categories` | Tüm kategorileri listele |
| POST | `/api/categories` | Kategori ekle |
| GET | `/api/brands` | Tüm markaları listele |
| GET | `/api/products` | Ürünleri filtrele (kategori, marka, fiyat, arama) |
| GET | `/api/products/{id}` | Ürün detayı |
| GET | `/api/products/{id}/history` | Fiyat geçmişi |
| POST | `/api/scrape` | URL tara ve veritabanına kaydet (arka plan) |
| GET | `/api/scrape/categories` | Akakçe kategorilerini çek |

---

## Gereksinimler

- Python 3.10+
- PostgreSQL 14+
- Windows 10/11 (baslat.bat için)
