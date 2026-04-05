"""
Nebula Enterprise - Retry & Circuit Breaker Yardımcıları
Async/sync uyumlu exponential backoff + jitter + circuit breaker
"""
import asyncio
import time
import logging
import functools
from typing import Callable, Optional, Type, Union

logger = logging.getLogger("nebula.retry")


# ─── Retry Decorator ─────────────────────────────────────────────────────────
def retry(
    max_attempts: int = 3,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff: float = 2.0,
    jitter: float = 0.5,
    on_retry: Optional[Callable] = None,
):
    """
    Async + sync fonksiyonlar için exponential backoff retry decorator.

    Args:
        max_attempts: Maksimum deneme sayısı
        exceptions: Yakalanacak hata tipleri
        base_delay: İlk bekleme süresi (saniye)
        max_delay: Maksimum bekleme süresi (saniye)
        backoff: Her denemede gecikmeyi çarpan katsayı
        jitter: Rasgele ek gecikme aralığı (0 = jitter yok)
        on_retry: Her retry'da çağrılacak callback(attempt, exc, delay)

    Kullanım:
        @retry(max_attempts=4, exceptions=(httpx.RequestError,), base_delay=2.0)
        async def fetch(url): ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exc: Optional[Exception] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (backoff ** (attempt - 1)), max_delay)
                    if jitter:
                        import random
                        delay += random.uniform(0, jitter)
                    logger.warning(
                        f"[{func.__name__}] deneme {attempt}/{max_attempts} başarısız: "
                        f"{exc!r} → {delay:.1f}s beklenecek"
                    )
                    if on_retry:
                        on_retry(attempt, exc, delay)
                    await asyncio.sleep(delay)
            logger.error(f"[{func.__name__}] tüm {max_attempts} deneme tükendi")
            raise last_exc

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exc: Optional[Exception] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (backoff ** (attempt - 1)), max_delay)
                    if jitter:
                        import random
                        delay += random.uniform(0, jitter)
                    logger.warning(
                        f"[{func.__name__}] deneme {attempt}/{max_attempts} başarısız: "
                        f"{exc!r} → {delay:.1f}s beklenecek"
                    )
                    if on_retry:
                        on_retry(attempt, exc, delay)
                    time.sleep(delay)
            logger.error(f"[{func.__name__}] tüm {max_attempts} deneme tükendi")
            raise last_exc

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# ─── Circuit Breaker ─────────────────────────────────────────────────────────
class CircuitBreaker:
    """
    Devre kesici pattern — art arda belirli sayıda hata olunca
    servisi geçici olarak devre dışı bırakır.

    Durumlar:
      CLOSED   → Normal çalışma
      OPEN     → Devre açık, istekler reddediliyor
      HALF_OPEN→ Tek deneme yapılır, başarılıysa CLOSED'a geçer
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exceptions: tuple[Type[Exception], ...] = (Exception,),
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.monotonic() - (self._last_failure_time or 0) >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                logger.info("Circuit Breaker: HALF_OPEN")
        return self._state

    def _on_success(self):
        self._failure_count = 0
        if self._state != self.CLOSED:
            logger.info("Circuit Breaker: CLOSED (başarı)")
        self._state = self.CLOSED

    def _on_failure(self, exc: Exception):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            if self._state != self.OPEN:
                logger.warning(
                    f"Circuit Breaker: OPEN — {self._failure_count} ardışık hata "
                    f"({exc!r}). {self.recovery_timeout}s sonra tekrar denenecek."
                )
            self._state = self.OPEN

    def __call__(self, func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if self.state == self.OPEN:
                raise RuntimeError(
                    f"Circuit Breaker AÇIK — servis geçici olarak devre dışı "
                    f"({self._failure_count} hata)"
                )
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exceptions as exc:
                self._on_failure(exc)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if self.state == self.OPEN:
                raise RuntimeError(
                    f"Circuit Breaker AÇIK — {self._failure_count} ardışık hata"
                )
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exceptions as exc:
                self._on_failure(exc)
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
