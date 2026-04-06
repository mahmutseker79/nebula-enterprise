"""
database.py  v2.0  –  Enterprise Pool + PgBouncer-ready
========================================================
Yenilikler:
  • pool_recycle=1800, pool_timeout=30, pool_pre_ping=True
  • PgBouncer transaction-mode uyumlu (server_side_cursors=False)
  • Async engine (asyncpg) + Sync engine (psycopg2) yan yana
  • bulk_upsert_products() → INSERT ON CONFLICT DO UPDATE
  • bulk_insert_price_history() → tek sorguda yüzlerce fiyat kaydı
  • get_or_create_brand() / get_or_create_category() → cache ile
  • check_db_health() → pool stats + sunucu bilgisi
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from config import get_settings
from models import Base, Brand, Category, PriceHistory, Product

logger   = logging.getLogger(__name__)
settings = get_settings()

# ─── Sync Engine ─────────────────────────────────────────────────────────────

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,          # 30 dk: DB bağlantı timeout'unun altında tut
    pool_timeout=30,            # bağlantı beklerken max 30 sn
    pool_reset_on_return="rollback",
    # PgBouncer transaction mode uyumu
    connect_args={
        "options":             "-c search_path=nebula,public",
        "application_name":    "nebula_enterprise",
        "connect_timeout":     10,
        "keepalives":          1,
        "keepalives_idle":     30,
        "keepalives_interval": 10,
        "keepalives_count":    5,
    },
    echo=False,
    future=True,
)

@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn: Any, _: Any) -> None:
    """Her yeni bağlantıda search_path'i ayarla."""
    with dbapi_conn.cursor() as cur:
        cur.execute("SET search_path TO nebula, public")
    logger.debug("DB bağlantısı kuruldu")


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# ─── Async Engine ─────────────────────────────────────────────────────────────

_async_url = (
    settings.database_url
    .replace("postgresql://",         "postgresql+asyncpg://")
    .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
)

async_engine = create_async_engine(
    _async_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
    pool_timeout=30,
    connect_args={
        "server_settings": {
            "search_path":    "nebula,public",
            "application_name": "nebula_enterprise_async",
        },
        "command_timeout": 30,
    },
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# ─── Dependency Injection ────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """FastAPI sync endpoint DI."""
    db = SessionLocal()
    try:
        yield db
    except OperationalError as exc:
        db.rollback()
        logger.error("DB OperationalError: %s", exc)
        raise
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async endpoint DI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Script / test context manager."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


@asynccontextmanager
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async script / test context manager."""
    async with AsyncSessionLocal() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


# ─── Tablo oluşturma ─────────────────────────────────────────────────────────

def create_tables() -> None:
    """Base tabloları oluştur (migration yoksa)."""
    Base.metadata.create_all(bind=engine)
    logger.info("DB tabloları kontrol edildi/oluşturuldu")


# ─── Bulk Upsert: Products ────────────────────────────────────────────────────

def bulk_upsert_products(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    index_elements: list[str] | None = None,
    commit: bool = True,
) -> int:
    """
    INSERT … ON CONFLICT (url) DO UPDATE  →  tek sorguda yüzlerce ürün.

    Returns: etkilenen satır sayısı
    """
    if not rows:
        return 0

    idx_cols = index_elements or ["url"]
    update_cols = {
        c.name: pg_insert(Product).excluded[c.name]
        for c in Product.__table__.columns
        if c.name not in ("id", *idx_cols, "created_at", "first_seen_at")
    }
    # scrape_count artır
    update_cols["scrape_count"] = Product.__table__.c.scrape_count + 1

    stmt = (
        pg_insert(Product)
        .values(rows)
        .on_conflict_do_update(index_elements=idx_cols, set_=update_cols)
    )
    result = db.execute(stmt)
    if commit:
        db.commit()
    return result.rowcount


# ─── Bulk Insert: PriceHistory ────────────────────────────────────────────────

def bulk_insert_price_history(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    commit: bool = True,
) -> int:
    """
    Toplu fiyat geçmişi kayıt.
    rows: [{"product_id": 1, "price": 1299.99, "source": "akakce", ...}, ...]
    """
    if not rows:
        return 0
    result = db.execute(pg_insert(PriceHistory).values(rows))
    if commit:
        db.commit()
    return result.rowcount


# ─── get_or_create helpers ────────────────────────────────────────────────────

_brand_cache:    dict[str, int] = {}
_category_cache: dict[str, int] = {}


def get_or_create_brand(db: Session, name: str, slug: str | None = None) -> int:
    """Marka ID'sini döndürür, yoksa oluşturur. In-process cache kullanır."""
    key = name.lower()
    if key in _brand_cache:
        return _brand_cache[key]

    brand = db.query(Brand).filter(Brand.name == name).first()
    if not brand:
        import re
        slug = slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        brand = Brand(name=name, slug=slug)
        db.add(brand)
        db.flush()

    _brand_cache[key] = brand.id
    return brand.id


def get_or_create_category(db: Session, name: str, slug: str | None = None,
                            url: str | None = None) -> int:
    """Kategori ID'sini döndürür, yoksa oluşturur."""
    key = name.lower()
    if key in _category_cache:
        return _category_cache[key]

    cat = db.query(Category).filter(Category.name == name).first()
    if not cat:
        import re
        slug = slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        cat = Category(name=name, slug=slug, url=url)
        db.add(cat)
        db.flush()

    _category_cache[key] = cat.id
    return cat.id


def invalidate_caches() -> None:
    """Marka/kategori cache'ini temizle (test veya uzun-running işlem sonrası)."""
    _brand_cache.clear()
    _category_cache.clear()


# ─── Sağlık Kontrolü ─────────────────────────────────────────────────────────

def check_db_health() -> dict[str, Any]:
    """DB + pool durumu hakkında tam rapor."""
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT version(), "
                "pg_database_size(current_database()) AS db_size_bytes, "
                "NOW() AS server_time"
            )).fetchone()
        pool = engine.pool
        return {
            "status":           "healthy",
            "pg_version":       (row[0] if row else ""),
            "db_size_mb":       round((row[1] or 0) / 1024 / 1024, 1) if row else 0,
            "server_time":      str(row[2]) if row else "",
            "pool_size":        pool.size(),
            "pool_checked_out": pool.checkedout(),
            "pool_overflow":    pool.overflow(),
            "pool_checked_in":  pool.checkedin(),
        }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


# ─── Materialized View Yenile ─────────────────────────────────────────────────

def refresh_materialized_views(db: Session | None = None) -> None:
    """Dashboard view'larını yenile (CONCURRENTLY → kilit yok)."""
    views = [
        "nebula.mv_category_stats",
        "nebula.mv_price_trend",
        "nebula.mv_top_deals",
    ]
    close_after = db is None
    if db is None:
        db = SessionLocal()
    try:
        for v in views:
            db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {v}"))
        db.commit()
        logger.info("Materialized view'lar yenilendi")
    except Exception as exc:
        db.rollback()
        logger.warning("View yenileme başarısız: %s", exc)
    finally:
        if close_after:
            db.close()
