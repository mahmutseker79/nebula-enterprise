"""
schemas.py  v2.0  –  Pydantic v2 API Şemaları
==============================================
Request / Response modelleri — DB modelleriyle birebir değil,
API katmanı için optimize edilmiş.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ─── Ortak ───────────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ═══════════════════════════════════════════════════════════════
# CATEGORY
# ═══════════════════════════════════════════════════════════════

class CategoryCreate(BaseModel):
    name:       str  = Field(..., min_length=1, max_length=255)
    slug:       str  = Field(..., min_length=1, max_length=255,
                             pattern=r"^[a-z0-9-]+$")
    url:        Optional[str] = None
    description: Optional[str] = None
    parent_id:  Optional[int] = None
    sort_order: int = 0


class CategoryOut(OrmBase):
    id:          int
    name:        str
    slug:        str
    url:         Optional[str]  = None
    description: Optional[str]  = None
    parent_id:   Optional[int]  = None
    sort_order:  int
    is_active:   bool
    created_at:  datetime


# ═══════════════════════════════════════════════════════════════
# BRAND
# ═══════════════════════════════════════════════════════════════

class BrandCreate(BaseModel):
    name:        str  = Field(..., min_length=1, max_length=255)
    slug:        str  = Field(..., min_length=1, max_length=255,
                              pattern=r"^[a-z0-9-]+$")
    logo_url:    Optional[str] = None
    website_url: Optional[str] = None
    country_code: Optional[str] = Field(None, max_length=2)


class BrandOut(OrmBase):
    id:          int
    name:        str
    slug:        str
    logo_url:    Optional[str]  = None
    website_url: Optional[str]  = None
    country_code: Optional[str] = None
    is_active:   bool
    created_at:  datetime


# ═══════════════════════════════════════════════════════════════
# STORE
# ═══════════════════════════════════════════════════════════════

class StoreOut(OrmBase):
    id:          int
    akakce_id:   Optional[str]  = None
    name:        str
    logo_url:    Optional[str]  = None
    website_url: Optional[str]  = None
    is_active:   bool


# ═══════════════════════════════════════════════════════════════
# PRODUCT
# ═══════════════════════════════════════════════════════════════

class ProductOut(OrmBase):
    id:             int
    external_id:    Optional[str]   = None
    name:           str
    price:          Optional[float] = None
    old_price:      Optional[float] = None
    price_drop_pct: Optional[float] = None
    url:            str
    image_url:      Optional[str]   = None
    brand_id:       Optional[int]   = None
    category_id:    Optional[int]   = None
    in_stock:       bool
    is_active:      bool
    scrape_count:   int
    specs:          Optional[dict[str, Any]] = None
    last_scraped_at: Optional[datetime]      = None
    created_at:     datetime

    @field_validator("price", "old_price", mode="before")
    @classmethod
    def decimal_to_float(cls, v: Any) -> Optional[float]:
        if isinstance(v, Decimal):
            return float(v)
        return v


class ProductDetail(OrmBase):
    """Detay endpoint'i için genişletilmiş ürün şeması."""
    id:             int
    external_id:    Optional[str]   = None
    name:           str
    price:          Optional[float] = None
    old_price:      Optional[float] = None
    price_drop_pct: Optional[float] = None
    url:            str
    image_url:      Optional[str]   = None
    description:    Optional[str]   = None
    specs:          Optional[dict[str, Any]] = None
    brand_id:       Optional[int]   = None
    category_id:    Optional[int]   = None
    in_stock:       bool
    scrape_count:   int
    last_scraped_at: Optional[datetime]      = None
    created_at:     datetime

    # İlişkili veriler
    images:       list["ProductImageOut"]  = []
    seller_prices: list["SellerPriceOut"] = []

    @field_validator("price", "old_price", mode="before")
    @classmethod
    def decimal_to_float(cls, v: Any) -> Optional[float]:
        if isinstance(v, Decimal):
            return float(v)
        return v


class ProductListResponse(BaseModel):
    items:     list[ProductOut]
    total:     int
    page:      int
    page_size: int
    pages:     int = 0

    def model_post_init(self, __context: Any) -> None:
        import math
        self.pages = math.ceil(self.total / self.page_size) if self.page_size else 0


# ═══════════════════════════════════════════════════════════════
# PRODUCT IMAGE
# ═══════════════════════════════════════════════════════════════

class ProductImageOut(OrmBase):
    id:         int
    product_id: int
    url:        str
    local_path: Optional[str]  = None
    width:      Optional[int]  = None
    height:     Optional[int]  = None
    sort_order: int
    is_main:    bool
    created_at: datetime


# ═══════════════════════════════════════════════════════════════
# PRICE HISTORY
# ═══════════════════════════════════════════════════════════════

class PriceHistoryOut(OrmBase):
    id:          int
    product_id:  int
    price:       float
    source:      str
    recorded_at: datetime

    @field_validator("price", mode="before")
    @classmethod
    def decimal_to_float(cls, v: Any) -> float:
        return float(v) if isinstance(v, Decimal) else v


# ═══════════════════════════════════════════════════════════════
# SELLER PRICE
# ═══════════════════════════════════════════════════════════════

class SellerPriceOut(OrmBase):
    id:         int
    product_id: int
    store_id:   Optional[int]   = None
    price:      float
    url:        Optional[str]   = None
    is_best:    bool
    in_stock:   bool
    scraped_at: datetime

    store: Optional[StoreOut] = None

    @field_validator("price", mode="before")
    @classmethod
    def decimal_to_float(cls, v: Any) -> float:
        return float(v) if isinstance(v, Decimal) else v


# ═══════════════════════════════════════════════════════════════
# SCRAPE
# ═══════════════════════════════════════════════════════════════

class ScrapeRequest(BaseModel):
    url:         str  = Field(..., min_length=10)
    category_id: Optional[int]  = None
    max_products: int = Field(100, ge=1, le=1000)
    detail:      bool = True      # ürün detay sayfasını da scrape et
    max_pages:   int  = Field(5,  ge=1, le=50)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL http(s):// ile başlamalı")
        return v


class ScrapeResponse(BaseModel):
    status:  str
    url:     str
    message: str
    job_id:  Optional[int] = None


# ═══════════════════════════════════════════════════════════════
# SCRAPE JOB
# ═══════════════════════════════════════════════════════════════

class ScrapeJobOut(OrmBase):
    id:             int
    url:            str
    status:         str
    priority:       int
    max_pages:      int
    pages_scraped:  Optional[int]      = None
    products_found: Optional[int]      = None
    error_msg:      Optional[str]      = None
    scheduled_at:   datetime
    started_at:     Optional[datetime] = None
    finished_at:    Optional[datetime] = None
    created_at:     datetime


# ═══════════════════════════════════════════════════════════════
# FILTER
# ═══════════════════════════════════════════════════════════════

class FilterValueOut(OrmBase):
    id:            int
    filter_id:     int
    value:         str
    label:         Optional[str] = None
    akakce_id:     Optional[str] = None
    url:           Optional[str] = None
    product_count: int


class CategoryFilterOut(OrmBase):
    id:          int
    category_id: int
    name:        str
    slug:        Optional[str] = None
    sort_order:  int
    values:      list[FilterValueOut] = []


# ═══════════════════════════════════════════════════════════════
# DASHBOARD / İSTATİSTİKLER
# ═══════════════════════════════════════════════════════════════

class CategoryStatsOut(BaseModel):
    category_id:   int
    category_name: str
    category_slug: str
    total_products: int
    in_stock_count: int
    avg_price:     Optional[float] = None
    min_price:     Optional[float] = None
    max_price:     Optional[float] = None
    median_price:  Optional[float] = None
    brand_count:   int
    last_scraped_at: Optional[datetime] = None
    refreshed_at:  Optional[datetime]   = None


class TopDealOut(BaseModel):
    id:            int
    name:          str
    image_url:     Optional[str]   = None
    url:           str
    current_price: Optional[float] = None
    price_30d_ago: Optional[float] = None
    drop_pct:      Optional[float] = None
    last_updated:  Optional[datetime] = None


class GlobalStatsOut(BaseModel):
    total_products:    int
    total_categories:  int
    total_brands:      int
    total_stores:      int
    avg_price:         Optional[float] = None
    min_price:         Optional[float] = None
    max_price:         Optional[float] = None
    total_price_records: int
    total_seller_prices: int
    total_images:      int


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status:  str        # "ok" | "degraded" | "unhealthy"
    version: str
    db:      dict[str, Any] = {}
    cache:   dict[str, Any] = {}
