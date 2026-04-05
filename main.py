"""
Nebula Enterprise - FastAPI Ana Uygulama
Kategoriler, Markalar, Ürünler, Fiyat Geçmişi ve Scraper endpoint'leri
"""
import logging
import logging.config
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
from config import get_settings
from database import engine, get_db, SessionLocal
from scraper_pro import AkakceScraper

# ─── Logging Yapılandırması ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nebula.api")
settings = get_settings()


# ─── Uygulama Yaşam Döngüsü ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Başlangıçta tabloları oluştur, kapanışta temizle."""
    logger.info("Nebula Enterprise başlatılıyor...")
    models.Base.metadata.create_all(bind=engine)
    logger.info("Veritabanı tabloları hazır")
    yield
    logger.info("Nebula Enterprise kapatılıyor.")


# ─── FastAPI Uygulaması ───────────────────────────────────────────────────────
app = FastAPI(
    title=settings.api_title,
    description="Akakçe + Türk e-ticaret fiyat takip & analiz platformu",
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# SİSTEM
# ═══════════════════════════════════════════════════════════════
@app.get("/api/health", response_model=schemas.HealthResponse, tags=["System"])
def health_check():
    return schemas.HealthResponse(
        status="ok",
        service="Nebula Enterprise",
        version=settings.api_version,
        time=datetime.utcnow(),
    )


# ═══════════════════════════════════════════════════════════════
# KATEGORİLER
# ═══════════════════════════════════════════════════════════════
@app.get("/api/categories", response_model=list[schemas.CategoryOut], tags=["Categories"])
def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Category)
        .filter(models.Category.is_active == True)
        .offset(skip)
        .limit(limit)
        .all()
    )


@app.get("/api/categories/{category_id}", response_model=schemas.CategoryOut, tags=["Categories"])
def get_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    return cat


@app.post("/api/categories", response_model=schemas.CategoryOut, status_code=201, tags=["Categories"])
def create_category(payload: schemas.CategoryCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Category).filter(models.Category.slug == payload.slug).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"'{payload.slug}' slug'ı zaten mevcut")
    cat = models.Category(**payload.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    logger.info(f"Yeni kategori oluşturuldu: {cat.name} (id={cat.id})")
    return cat


@app.delete("/api/categories/{category_id}", status_code=204, tags=["Categories"])
def delete_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    cat.is_active = False
    db.commit()


# ═══════════════════════════════════════════════════════════════
# MARKALAR
# ═══════════════════════════════════════════════════════════════
@app.get("/api/brands", response_model=list[schemas.BrandOut], tags=["Brands"])
def list_brands(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(models.Brand).offset(skip).limit(limit).all()


@app.get("/api/brands/{brand_id}", response_model=schemas.BrandOut, tags=["Brands"])
def get_brand(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Marka bulunamadı")
    return brand


@app.post("/api/brands", response_model=schemas.BrandOut, status_code=201, tags=["Brands"])
def create_brand(payload: schemas.BrandCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Brand).filter(models.Brand.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"'{payload.name}' markası zaten mevcut")
    brand = models.Brand(**payload.model_dump())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


# ═══════════════════════════════════════════════════════════════
# ÜRÜNLER
# ═══════════════════════════════════════════════════════════════
@app.get("/api/products", response_model=schemas.ProductListResponse, tags=["Products"])
def list_products(
    category_id: Optional[int] = Query(None),
    brand_id: Optional[int] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    search: Optional[str] = Query(None, max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(models.Product)

    if category_id is not None:
        q = q.filter(models.Product.category_id == category_id)
    if brand_id is not None:
        q = q.filter(models.Product.brand_id == brand_id)
    if min_price is not None:
        q = q.filter(models.Product.price >= min_price)
    if max_price is not None:
        q = q.filter(models.Product.price <= max_price)
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))

    total = q.count()
    items = q.order_by(models.Product.price.asc()).offset(skip).limit(limit).all()

    return schemas.ProductListResponse(total=total, skip=skip, limit=limit, items=items)


@app.get("/api/products/{product_id}", response_model=schemas.ProductOut, tags=["Products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return p


@app.get(
    "/api/products/{product_id}/history",
    response_model=list[schemas.PriceHistoryOut],
    tags=["Products"],
)
def get_price_history(
    product_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return (
        db.query(models.PriceHistory)
        .filter(models.PriceHistory.product_id == product_id)
        .order_by(models.PriceHistory.recorded_at.desc())
        .limit(limit)
        .all()
    )


# ═══════════════════════════════════════════════════════════════
# SCRAPER
# ═══════════════════════════════════════════════════════════════
def _scrape_and_save(url: str, category_id: Optional[int], max_pages: int) -> None:
    """Arka plan görev — URL'yi scrape edip veritabanına kaydeder."""
    db = SessionLocal()
    try:
        scraper = AkakceScraper()
        raw_products = scraper.scrape_category(url, max_pages=max_pages)

        new_count = updated_count = 0

        for p in raw_products:
            if not p.get("url"):
                continue

            existing = (
                db.query(models.Product)
                .filter(models.Product.url == p["url"])
                .first()
            )

            if existing:
                if existing.price is not None and existing.price != p.get("price"):
                    db.add(models.PriceHistory(product_id=existing.id, price=existing.price))
                existing.price = p.get("price")
                existing.image_url = p.get("image_url") or existing.image_url
                existing.updated_at = datetime.utcnow()
                updated_count += 1
            else:
                db.add(models.Product(
                    name=p["name"],
                    url=p["url"],
                    price=p.get("price"),
                    image_url=p.get("image_url", ""),
                    specs=p.get("specs", {}),
                    category_id=category_id,
                ))
                new_count += 1

        db.commit()
        logger.info(
            f"Scrape tamamlandı: {len(raw_products)} ürün | "
            f"{new_count} yeni | {updated_count} güncellendi"
        )
    except Exception as exc:
        logger.exception(f"Scrape arka plan hatası: {exc}")
        db.rollback()
    finally:
        db.close()


@app.post("/api/scrape", response_model=schemas.ScrapeResponse, tags=["Scraper"])
def trigger_scrape(payload: schemas.ScrapeRequest, background_tasks: BackgroundTasks):
    """Verilen URL'yi arka planda tara ve veritabanına kaydet."""
    background_tasks.add_task(
        _scrape_and_save, payload.url, payload.category_id, payload.max_pages
    )
    return schemas.ScrapeResponse(
        status="started",
        url=payload.url,
        message=f"Scrape başlatıldı (max {payload.max_pages} sayfa)",
    )


@app.get("/api/scrape/preview", tags=["Scraper"])
def scrape_preview(url: str = Query(..., description="Taranacak URL")):
    """URL'den ilk sayfayı canlı çekip önizleme döndür (test için)."""
    scraper = AkakceScraper()
    products = scraper.scrape_category(url, max_pages=1)
    return {
        "url": url,
        "count": len(products),
        "sample": products[:5],
    }


@app.get("/api/scrape/akakce-categories", tags=["Scraper"])
def get_akakce_categories():
    """Akakçe ana sayfasından kategorileri canlı çek."""
    scraper = AkakceScraper()
    categories = scraper.get_categories()
    return {"count": len(categories), "categories": categories}
