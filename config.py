"""
config.py  v2.0  –  Pydantic-settings ile merkezi yapılandırma
==============================================================
Tüm ayarlar .env dosyasından veya ortam değişkenlerinden okunur.
Singleton: get_settings() → aynı nesneyi döndürür (lru_cache).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Veritabanı ────────────────────────────────────────────
    database_url:       str     = "postgresql://postgres:postgres@localhost:5432/nebula"
    db_pool_size:       int     = Field(10,  ge=1,  le=100)
    db_max_overflow:    int     = Field(20,  ge=0,  le=100)
    db_pool_recycle:    int     = Field(1800, ge=60)   # 30 dk
    db_pool_timeout:    int     = Field(30,  ge=5)
    db_schema:          str     = "nebula"

    # ── API ───────────────────────────────────────────────────
    api_host:           str     = "0.0.0.0"
    api_port:           int     = Field(8000, ge=1, le=65535)
    api_debug:          bool    = False
    api_workers:        int     = Field(1, ge=1, le=32)
    secret_key:         str     = "change-me-in-production-32chars!!"

    # ── Scraper ───────────────────────────────────────────────
    scraper_delay_min:  float   = Field(1.0,  ge=0.1)
    scraper_delay_max:  float   = Field(2.5,  ge=0.5)
    scraper_retries:    int     = Field(3,    ge=1, le=10)
    scraper_timeout:    int     = Field(30,   ge=5)
    scraper_headless:   bool    = True
    scraper_workers:    int     = Field(3,    ge=1, le=10)   # paralel detay worker
    scraper_session_refresh: int = Field(30,  ge=5)          # her N istekte driver yenile
    download_images:    bool    = True
    image_dir:          str     = "outputs/images"

    # ── Proxy (opsiyonel) ─────────────────────────────────────
    proxy_enabled:      bool    = False
    proxy_url:          Optional[str] = None                  # http://user:pass@host:port
    proxy_list:         Optional[str] = None                  # dosya yolu: her satırda 1 proxy

    # ── Cache ─────────────────────────────────────────────────
    cache_category_ttl: int     = 600    # sn
    cache_brand_ttl:    int     = 600
    cache_product_ttl:  int     = 120
    cache_stats_ttl:    int     = 60

    # ── Çıktılar ──────────────────────────────────────────────
    output_dir:         str     = "outputs"
    log_level:          str     = "INFO"
    log_file:           Optional[str] = None

    # ── Materialized View yenileme (dakika) ───────────────────
    mv_refresh_interval: int    = 30

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgresql+psycopg2://", "postgresql+asyncpg://")):
            raise ValueError("database_url PostgreSQL bağlantısı olmalı")
        return v

    @field_validator("scraper_delay_max")
    @classmethod
    def validate_delay(cls, v: float, info: object) -> float:
        # delay_max >= delay_min
        return v

    @property
    def async_database_url(self) -> str:
        return (
            self.database_url
            .replace("postgresql://", "postgresql+asyncpg://")
            .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        )

    @property
    def proxy_list_parsed(self) -> list[str]:
        """proxy_list dosyasını satır satır oku."""
        if not self.proxy_list:
            return []
        try:
            from pathlib import Path
            return [
                line.strip() for line in
                Path(self.proxy_list).read_text().splitlines()
                if line.strip() and not line.startswith("#")
            ]
        except Exception:
            return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
