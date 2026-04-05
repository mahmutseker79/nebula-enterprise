"""
Nebula Enterprise - TTL In-Memory Cache
Redis gerektirmeden sık okunan verileri önbellekler.
Thread-safe, asyncio uyumlu.
"""
import asyncio
import time
import threading
import logging
from typing import Any, Optional, Callable
from functools import wraps

logger = logging.getLogger("nebula.cache")


class TTLCache:
    """
    Thread-safe TTL (Time-To-Live) önbellek.
    Her giriş belirli bir süre sonra otomatik olarak geçersiz olur.
    """

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None
            value, expires_at = self._store[key]
            if time.monotonic() > expires_at:
                del self._store[key]
                self._misses += 1
                logger.debug(f"Cache EXPIRED: {key}")
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        _ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.monotonic() + _ttl
        with self._lock:
            self._store[key] = (value, expires_at)
        logger.debug(f"Cache SET: {key} (TTL={_ttl}s)")

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
        logger.info("Cache temizlendi")

    def invalidate_prefix(self, prefix: str) -> int:
        """Belirli bir prefix ile başlayan tüm anahtarları siler."""
        with self._lock:
            keys_to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]
        if keys_to_delete:
            logger.debug(f"Cache INVALIDATED prefix='{prefix}': {len(keys_to_delete)} girdi")
        return len(keys_to_delete)

    def evict_expired(self) -> int:
        """Süresi dolmuş tüm girişleri temizler."""
        now = time.monotonic()
        with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]
        return len(expired)

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        with self._lock:
            size = len(self._store)
        return {
            "size": size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
        }

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# ─── Uygulama Genelinde Önbellekler ──────────────────────────────────────────
category_cache = TTLCache(default_ttl=600)    # 10 dakika
brand_cache = TTLCache(default_ttl=600)        # 10 dakika
product_cache = TTLCache(default_ttl=120)      # 2 dakika
stats_cache = TTLCache(default_ttl=60)         # 1 dakika


# ─── Sync Cache Decorator ────────────────────────────────────────────────────
def cached(cache: TTLCache, key_fn: Callable, ttl: Optional[int] = None):
    """
    Fonksiyon sonucunu TTLCache'e kaydeden decorator.

    Kullanım:
        @cached(category_cache, key_fn=lambda *a, **kw: f"cats:{kw.get('skip')}:{kw.get('limit')}")
        def list_categories(skip=0, limit=100): ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = key_fn(*args, **kwargs)
            result = cache.get(key)
            if result is not None:
                logger.debug(f"Cache HIT: {key}")
                return result
            result = func(*args, **kwargs)
            cache.set(key, result, ttl)
            return result

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            key = key_fn(*args, **kwargs)
            result = cache.get(key)
            if result is not None:
                logger.debug(f"Cache HIT: {key}")
                return result
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl)
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
    return decorator
