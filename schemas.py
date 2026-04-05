"""
Nebula Enterprise - Pydantic Şemaları
Request / Response tip güvenliği ve otomatik validasyon
"""
from pydantic import BaseModel, HttpUrl, field_validator, ConfigDict
from typing import Optional, Any
from datetime import datetime


# ─── Temel Mixin ─────────────────────────────────────────────────────────────
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════════
# KATEGORİ
# ════════════════════════════════════════════════════════════════
class CategoryCreate(BaseModel):
    name: str
    slug: str
    url: Optional[str] = None
    description: Optional[str] = None

    @field_validator("slug")
    @classmethod
    def slug_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("Slug boşluk içeremez")
        return v.lower()


class CategoryOut(ORMBase):
    id: int
    name: str
    slug: str
    url: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime


# ════════════════════════════════════════════════════════════════
# MARKA
# ════════════════════════════════════════════════════════════════
class BrandCreate(BaseModel):
    name: str
    logo_url: Optional[str] = None


class BrandOut(ORMBase):
    id: int
    name: str
    logo_url: Optional[str] = None
    is_active: bool
    created_at: datetime


# ════════════════════════════════════════════════════════════════
# ÜRÜN
# ════════════════════════════════════════════════════════════════
class ProductOut(ORMBase):
    id: int
    name: str
    url: str
    price: Optional[float] = None
    old_price: Optional[float] = None
    image_url: Optional[str] = None
    specs: Optional[dict[str, Any]] = None
    in_stock: bool
    created_at: datetime
    updated_at: datetime
    category_id: Optional[int] = None
    brand_id: Optional[int] = None


class ProductListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[ProductOut]


# ════════════════════════════════════════════════════════════════
# FİYAT GEÇMİŞİ
# ════════════════════════════════════════════════════════════════
class PriceHistoryOut(ORMBase):
    id: int
    product_id: int
    price: float
    recorded_at: datetime
    source: str


# ════════════════════════════════════════════════════════════════
# SCRAPER
# ════════════════════════════════════════════════════════════════
class ScrapeRequest(BaseModel):
    url: str
    category_id: Optional[int] = None
    max_pages: int = 5

    @field_validator("url")
    @classmethod
    def url_must_be_akakce_or_valid(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("http"):
            raise ValueError("URL http:// veya https:// ile başlamalı")
        return v

    @field_validator("max_pages")
    @classmethod
    def max_pages_range(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("max_pages 1-50 arasında olmalı")
        return v


class ScrapeResponse(BaseModel):
    status: str
    url: str
    message: str


# ════════════════════════════════════════════════════════════════
# SİSTEM
# ════════════════════════════════════════════════════════════════
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    time: datetime
