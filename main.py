"""
Nebula Enterprise - FastAPI Ana Uygulama
Kategoriler, Markalar, Ürünler ve Scraper tetikleyici endpoint'leri
"""
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

import models
import database
from database import engine, get_db
from scraper_pro import AkakceScraper

# ─── Tablo Oluşturma ─────────────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

# ─── Uygulama ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Nebula Enterprise API",
    description="Akakçe + e-ticaret fiyat takip & analiz platformu",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("nebula.api")


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════
@app.get("/api/health", tags=["System"])
def health_check():
    return {"status": "ok", "service": "Nebula Enterprise", "time": datetime.utcnow()}


# ═══════════════════════════════════════════════════════════════
# KATEGORİLER
# ═══════════════════════════════════════════════════════════════
@app.get("/api/categories", tags=["Categories"])
def list_categories(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return db.query(models.Category).filter(
        models.Category.is_active == True
    ).offset(skip).limit(limit).all()


@app.get("/api/categories/{category_id}", tags=["Categories"])
def get_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    return cat


@app.post("/api/categories", tags=["Categories"], status_code=201)
def create_category(
    name: str,
    slug: str,
    url: Optional[str] = None,
    db: Session = Depends(get_db)
):
    existing = db.query(models.Category).filter(models.Category.slug == slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu slug zaten mevcut")
    cat = models.Category(name=name, slug=slug, url=url)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


# ═══════════════════════════════════════════════════════════════
# MARKALAR
# ═══════════════════════════════════════════════════════════════
@app.get("/api/brands", tags=["Brands"])
def list_brands(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Brand).offset(skip).limit(limit).all()


@app.get("/api/brands/{brand_id}", tags=["Brands"])
def get_brand(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Marka bulunamadı")
    return brand


# ═══════════════════════════════════════════════════════════════
# ÜRÜNLER
# ═══════════════════════════════════════════════════════════════
@app.get("/api/products", tags=["Products"])
def list_products(
    category_id: Optional[int] = Query(None),
    brand_id: Optional[int] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    q = db.query(models.Product)

    if category_id:
        q = q.filter(models.Product.category_id == category_id)
    if brand_id:
        q = q.filter(models.Product.brand_id == brand_id)
    if min_price is not None:
        q = q.filter(models.Product.price >= min_price)
    if max_price is not None:
        q = q.filter(models.Product.price <= max_price)
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))

    total = q.count()
    products = q.order_by(models.Product.price.asc()).offset(skip).limit(limit).all()

    return {"total": total, "items": products, "skip": skip, "limit": limit}


@app.get("/api/products/{product_id}", tags=["Products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return p


@app.get("/api/products/{product_id}/history", tags=["Products"])
def get_price_history(product_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    history = (
        db.query(models.PriceHistory)
        .filter(models.PriceHistory.product_id == product_id)
        .order_by(models.PriceHistory.recorded_at.desc())
        .limit(100)
        .all()
    )
    return history


# ═══════════════════════════════════════════════════════════════
# SCRAPER TETİKLEYİCİ
# ═══════════════════════════════════════════════════════════════
def _scrape_and_save(url: str, category_id: Optional[int]):
    """Arka planda çalışan scraper işi."""
    db = database.SessionLocal()
    try:
        scraper = AkakceScraper()
        raw_products = scraper.scrape_category(url)

        saved = 0
        for p in raw_products:
            if not p.get("url"):
                continue

            existing = db.query(models.Product).filter(
                models.Product.url == p["url"]
            ).first()

            if existing:
                # Fiyat geçmişi kaydet
                if existing.price and existing.price != p["price"]:
                    ph = models.PriceHistory(
                        product_id=existing.id,
                        price=existing.price
                    )
                    db.add(ph)
                existing.price = p["price"]
                existing.image_url = p.get("image_url", existing.image_url)
                existing.updated_at = datetime.utcnow()
            else:
                new_p = models.Product(
                    name=p["name"],
                    url=p["url"],
                    price=p["price"],
                    image_url=p.get("image_url", ""),
                    specs=p.get("specs", {}),
                    category_id=category_id,
                )
                db.add(new_p)
                saved += 1

        db.commit()
        logger.info(f"Scrape tamamlandı: {len(raw_products)} ürün işlendi, {saved} yeni kayıt")

    except Exception as exc:
        logger.error(f"Scrape hatası: {exc}")
        db.rollback()
    finally:
        db.close()


@app.post("/api/scrape", tags=["Scraper"])
def trigger_scrape(
    url: str,
    category_id: Optional[int] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Belirtilen URL'yi arka planda tara ve veritabanına kaydet."""
    background_tasks.add_task(_scrape_and_save, url, category_id)
    return {"status": "started", "url": url, "message": "Scrape arka planda başlatıldı"}


@app.get("/api/scrape/categories", tags=["Scraper"])
def scrape_all_categories():
    """Akakçe ana sayfasından kategorileri çek (test)."""
    scraper = AkakceScraper()
    categories = scraper.get_categories()
    return {"count": len(categories), "categories": categories[:20]}
