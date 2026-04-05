"""
Nebula Enterprise - Merkezi Konfigürasyon
pydantic-settings ile .env okuma ve tip doğrulaması
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Veritabanı ────────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:password@localhost:5432/nebuladb"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    api_title: str = "Nebula Enterprise API"
    api_version: str = "1.0.0"

    # ── Scraper ───────────────────────────────────────────────────────────────
    scraper_delay_min: float = 1.5
    scraper_delay_max: float = 4.0
    scraper_retries: int = 4
    scraper_timeout: int = 20
    scraper_max_pages: int = 10

    # ── Proxy (isteğe bağlı) ──────────────────────────────────────────────────
    proxy_url: str = ""          # örn: http://user:pass@host:port
    proxy_enabled: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton ayarlar nesnesi — uygulama başına bir kez oluşturulur."""
    return Settings()
