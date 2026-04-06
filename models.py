"""
models.py  v3.0  –  Full Enterprise ORM
========================================
Tablolar:
  categories        – hiyerarşik (parent_id)
  brands            – marka
  products          – ürün (NUMERIC fiyat, JSONB specs, FTS vector)
  product_images    – ürün görsel galerisi
  price_history     – partition'lı fiyat geçmişi
  seller_prices     – satıcı bazlı anlık fiyat
  stores            – mağaza kaydı
  category_filters  – filtre grupları (RAM, Renk, Yıl vb.)
  filter_values     – filtre değerleri
  scrape_jobs       – iş kuyruğu
  scraper_sessions  – fingerprint / session havuzu
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime,
    ForeignKey, Index, Integer, Numeric, SmallInteger,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════
# CATEGORY
# ═══════════════════════════════════════════════════════════════

class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("slug",  name="uq_categories_slug"),
        Index("ix_cat_name",      "name"),
        Index("ix_cat_parent_id", "parent_id"),
        Index("ix_cat_active",    "is_active"),
        {"schema": "nebula"},
    )

    id          = Column(Integer,      primary_key=True)
    name        = Column(String(255),  nullable=False)
    slug        = Column(String(255),  nullable=False)
    url         = Column(String(1024))
    description = Column(Text)
    icon_url    = Column(String(1024))
    parent_id   = Column(Integer, ForeignKey("nebula.categories.id", ondelete="SET NULL"))
    sort_order  = Column(SmallInteger,             default=0)
    is_active   = Column(Boolean, nullable=False,  default=True)
    created_at  = Column(DateTime(timezone=True),  nullable=False, default=_utcnow)
    updated_at  = Column(DateTime(timezone=True),  nullable=False, default=_utcnow, onupdate=_utcnow)

    products    = relationship("Product", back_populates="category", lazy="select")
    children    = relationship("Category", lazy="select",
                               primaryjoin="Category.id == foreign(Category.parent_id)")
    filters     = relationship("CategoryFilter", back_populates="category", lazy="select",
                               cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"


# ═══════════════════════════════════════════════════════════════
# BRAND
# ═══════════════════════════════════════════════════════════════

class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("slug",  name="uq_brands_slug"),
        Index("ix_brands_name",   "name"),
        {"schema": "nebula"},
    )

    id           = Column(Integer,     primary_key=True)
    name         = Column(String(255), nullable=False)
    slug         = Column(String(255), nullable=False)
    logo_url     = Column(String(1024))
    website_url  = Column(String(1024))
    country_code = Column(String(2))
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    products     = relationship("Product", back_populates="brand", lazy="select")

    def __repr__(self) -> str:
        return f"<Brand id={self.id} name={self.name!r}>"


# ═══════════════════════════════════════════════════════════════
# STORE  (Mağaza kaydı)
# ═══════════════════════════════════════════════════════════════

class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        UniqueConstraint("akakce_id", name="uq_stores_akakce_id"),
        Index("ix_stores_name",       "name"),
        {"schema": "nebula"},
    )

    id          = Column(Integer,     primary_key=True)
    akakce_id   = Column(String(20))         # cdn.akakce.com/im/m6/{akakce_id}.svg
    name        = Column(String(255), nullable=False)
    slug        = Column(String(255))
    logo_url    = Column(String(1024))
    website_url = Column(String(1024))
    is_active   = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at  = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    seller_prices = relationship("SellerPrice", back_populates="store", lazy="select")

    def __repr__(self) -> str:
        return f"<Store id={self.id} name={self.name!r}>"


# ═══════════════════════════════════════════════════════════════
# PRODUCT
# ═══════════════════════════════════════════════════════════════

class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("url",              name="uq_products_url"),
        Index("ix_prod_category_id",         "category_id"),
        Index("ix_prod_brand_id",            "brand_id"),
        Index("ix_prod_price",               "price"),
        Index("ix_prod_external_id",         "external_id"),
        Index("ix_prod_source",              "source"),
        Index("ix_prod_last_scraped",        "last_scraped_at"),
        Index("ix_prod_active_price_cat",    "category_id", "price"),
        {"schema": "nebula"},
    )

    id              = Column(BigInteger,    primary_key=True)
    external_id     = Column(String(64))             # akakce data-pr
    url             = Column(String(2048),  nullable=False)
    source          = Column(String(50),    nullable=False, default="akakce")

    name            = Column(String(512),   nullable=False)
    image_url       = Column(String(2048))           # ana görsel
    description     = Column(Text)
    specs           = Column(JSONB)                  # {"RAM":"8 GB","Ekran":"6.7 inç",...}

    # Fiyat (NUMERIC = kesin para, float değil)
    price           = Column(Numeric(12, 2))
    old_price       = Column(Numeric(12, 2))

    # FTS (server-generated → sadece okunur)
    search_vector   = Column(TSVECTOR)

    in_stock        = Column(Boolean, nullable=False, default=True)
    is_active       = Column(Boolean, nullable=False, default=True)
    scrape_count    = Column(Integer, nullable=False, default=1)

    category_id     = Column(Integer,    ForeignKey("nebula.categories.id", ondelete="SET NULL"))
    brand_id        = Column(Integer,    ForeignKey("nebula.brands.id",     ondelete="SET NULL"))

    first_seen_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_scraped_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at      = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    category      = relationship("Category",      back_populates="products")
    brand         = relationship("Brand",         back_populates="products")
    images        = relationship("ProductImage",  back_populates="product",
                                 cascade="all, delete-orphan", lazy="select",
                                 order_by="ProductImage.sort_order")
    price_history = relationship("PriceHistory",  back_populates="product",
                                 cascade="all, delete-orphan", lazy="select")
    seller_prices = relationship("SellerPrice",   back_populates="product",
                                 cascade="all, delete-orphan", lazy="select")

    @hybrid_property
    def price_drop_pct(self) -> float | None:
        if self.old_price and self.old_price > 0 and self.price and self.price < self.old_price:
            return round((float(self.old_price) - float(self.price)) / float(self.old_price) * 100, 2)
        return None

    @hybrid_property
    def best_seller_price(self) -> float | None:
        if self.seller_prices:
            prices = [float(sp.price) for sp in self.seller_prices if sp.price]
            return min(prices) if prices else None
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":           self.id,
            "external_id":  self.external_id,
            "name":         self.name,
            "price":        float(self.price)     if self.price     else None,
            "old_price":    float(self.old_price) if self.old_price else None,
            "drop_pct":     self.price_drop_pct,
            "url":          self.url,
            "image_url":    self.image_url,
            "brand_id":     self.brand_id,
            "category_id":  self.category_id,
            "in_stock":     self.in_stock,
            "specs":        self.specs,
            "images":       [i.url for i in self.images] if self.images else [],
            "scraped_at":   self.last_scraped_at.isoformat() if self.last_scraped_at else None,
        }

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name[:40]!r} price={self.price}>"


# ═══════════════════════════════════════════════════════════════
# PRODUCT IMAGE  (görsel galerisi)
# ═══════════════════════════════════════════════════════════════

class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        UniqueConstraint("product_id", "url", name="uq_product_image"),
        Index("ix_pimg_product_id",    "product_id"),
        {"schema": "nebula"},
    )

    id          = Column(Integer,    primary_key=True)
    product_id  = Column(BigInteger, ForeignKey("nebula.products.id", ondelete="CASCADE"), nullable=False)
    url         = Column(String(2048), nullable=False)   # orijinal akakce CDN URL
    local_path  = Column(String(1024))                   # indirildikten sonra yerel yol
    width       = Column(SmallInteger)
    height      = Column(SmallInteger)
    sort_order  = Column(SmallInteger, default=0)        # 0 = ana görsel
    is_main     = Column(Boolean, nullable=False, default=False)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    product     = relationship("Product", back_populates="images")

    def __repr__(self) -> str:
        return f"<ProductImage id={self.id} product_id={self.product_id} order={self.sort_order}>"


# ═══════════════════════════════════════════════════════════════
# PRICE HISTORY  (partition'lı)
# ═══════════════════════════════════════════════════════════════

class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_ph_product_time", "product_id", "recorded_at"),
        {"schema": "nebula"},
    )

    id          = Column(BigInteger,     primary_key=True)
    product_id  = Column(BigInteger,     ForeignKey("nebula.products.id", ondelete="CASCADE"), nullable=False)
    price       = Column(Numeric(12, 2), nullable=False)
    source      = Column(String(50),     nullable=False, default="akakce")
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    product     = relationship("Product", back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory pid={self.product_id} price={self.price}>"


# ═══════════════════════════════════════════════════════════════
# SELLER PRICE  (anlık satıcı fiyatları)
# ═══════════════════════════════════════════════════════════════

class SellerPrice(Base):
    __tablename__ = "seller_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "store_id", name="uq_seller_price"),
        Index("ix_sp_product_id",       "product_id"),
        Index("ix_sp_store_id",         "store_id"),
        Index("ix_sp_price",            "price"),
        Index("ix_sp_scraped_at",       "scraped_at"),
        {"schema": "nebula"},
    )

    id          = Column(Integer,     primary_key=True)
    product_id  = Column(BigInteger,  ForeignKey("nebula.products.id",  ondelete="CASCADE"), nullable=False)
    store_id    = Column(Integer,     ForeignKey("nebula.stores.id",    ondelete="SET NULL"))
    price       = Column(Numeric(12, 2), nullable=False)
    url         = Column(String(2048))          # satıcıya yönlendiren link
    is_best     = Column(Boolean, nullable=False, default=False)  # en ucuz flag
    in_stock    = Column(Boolean, nullable=False, default=True)
    scraped_at  = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    product     = relationship("Product", back_populates="seller_prices")
    store       = relationship("Store",   back_populates="seller_prices")

    def __repr__(self) -> str:
        return f"<SellerPrice pid={self.product_id} store_id={self.store_id} price={self.price}>"


# ═══════════════════════════════════════════════════════════════
# CATEGORY FILTER  (filtre grubu: "RAM", "Renk", "Yıl"...)
# ═══════════════════════════════════════════════════════════════

class CategoryFilter(Base):
    __tablename__ = "category_filters"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_cat_filter"),
        Index("ix_cf_category_id",      "category_id"),
        {"schema": "nebula"},
    )

    id           = Column(Integer,    primary_key=True)
    category_id  = Column(Integer,    ForeignKey("nebula.categories.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String(255), nullable=False)   # "RAM Kapasitesi", "Dahili Hafıza"
    slug         = Column(String(255))
    sort_order   = Column(SmallInteger, default=0)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    category     = relationship("Category", back_populates="filters")
    values       = relationship("FilterValue", back_populates="filter",
                                cascade="all, delete-orphan", lazy="select")

    def __repr__(self) -> str:
        return f"<CategoryFilter id={self.id} name={self.name!r}>"


# ═══════════════════════════════════════════════════════════════
# FILTER VALUE  (filtre değeri: "8 GB", "256 GB", "2025"...)
# ═══════════════════════════════════════════════════════════════

class FilterValue(Base):
    __tablename__ = "filter_values"
    __table_args__ = (
        UniqueConstraint("filter_id", "value", name="uq_filter_value"),
        Index("ix_fv_filter_id",       "filter_id"),
        Index("ix_fv_akakce_id",       "akakce_id"),
        {"schema": "nebula"},
    )

    id          = Column(Integer,     primary_key=True)
    filter_id   = Column(Integer,     ForeignKey("nebula.category_filters.id", ondelete="CASCADE"), nullable=False)
    value       = Column(String(255), nullable=False)     # "8 GB"
    label       = Column(String(255))                     # "Ram Kapasitesi 8 GB"
    akakce_id   = Column(String(20))                      # data-id="86802"
    url         = Column(String(2048))                    # /cep-telefonu/8-gb-ram-telefon.html
    product_count = Column(Integer, default=0)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    filter      = relationship("CategoryFilter", back_populates="values")

    def __repr__(self) -> str:
        return f"<FilterValue id={self.id} value={self.value!r}>"


# ═══════════════════════════════════════════════════════════════
# SCRAPE JOB
# ═══════════════════════════════════════════════════════════════

class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','done','failed','cancelled')",
                        name="chk_job_status"),
        Index("ix_jobs_status_prio", "status", "priority"),
        Index("ix_jobs_scheduled",   "scheduled_at"),
        {"schema": "nebula"},
    )

    id             = Column(BigInteger,   primary_key=True)
    url            = Column(String(2048), nullable=False)
    category_id    = Column(Integer,      ForeignKey("nebula.categories.id"))
    status         = Column(String(20),   nullable=False, default="pending")
    priority       = Column(SmallInteger, nullable=False, default=5)
    max_pages      = Column(SmallInteger, nullable=False, default=5)
    pages_scraped  = Column(SmallInteger, default=0)
    products_found = Column(Integer,      default=0)
    error_msg      = Column(Text)
    worker_id      = Column(String(64))
    scheduled_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    started_at     = Column(DateTime(timezone=True))
    finished_at    = Column(DateTime(timezone=True))
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<ScrapeJob id={self.id} status={self.status!r}>"


# ═══════════════════════════════════════════════════════════════
# SCRAPER SESSION  (fingerprint havuzu)
# ═══════════════════════════════════════════════════════════════

class ScraperSession(Base):
    __tablename__ = "scraper_sessions"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_id"),
        Index("ix_sessions_active", "is_active", "last_used_at"),
        {"schema": "nebula"},
    )

    id            = Column(Integer,  primary_key=True)
    session_id    = Column(UUID(as_uuid=True), nullable=False,
                           server_default=func.gen_random_uuid())
    user_agent    = Column(Text,     nullable=False)
    accept_lang   = Column(String(100), default="tr-TR,tr;q=0.9")
    cookies       = Column(JSONB)
    headers       = Column(JSONB)
    proxy_host    = Column(String(255))
    proxy_port    = Column(Integer)
    is_active     = Column(Boolean,  nullable=False, default=True)
    ban_count     = Column(SmallInteger, nullable=False, default=0)
    success_count = Column(Integer,  nullable=False, default=0)
    last_used_at  = Column(DateTime(timezone=True), default=_utcnow)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<ScraperSession id={self.id} bans={self.ban_count} ok={self.success_count}>"
