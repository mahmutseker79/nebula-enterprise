"""
utils/antibot.py  –  Anti-Bot Katmanı v2
==========================================
Özellikler:
  1. TLS Fingerprint Spoofing  (SSL cipher + extension sırası)
  2. Canvas / WebGL Fingerprint  (rastgele noise inject)
  3. Session Pool              (N driver, round-robin kullanım)
  4. User-Agent Rotasyon        (gerçek tarayıcı versiyonları)
  5. Request Rate Limiter       (token bucket)
  6. Ban Dedektörü              (CF challenge / captcha / 429)
  7. Cookie Jar Yönetimi        (session başına cookie sakla/yükle)
  8. Proxy Rotasyon             (isteğe bağlı, liste verilirse)
"""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Sabitler ────────────────────────────────────────────────────────────────

# 2025 Q1 gerçek tarayıcı UA listesi (Windows + Mac + Linux)
REAL_USER_AGENTS: list[str] = [
    # Chrome 133
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    # Chrome 132
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    # Chrome 131
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox 134
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) Gecko/20100101 Firefox/134.0",
    # Firefox 132
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    # Edge 131
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# Sec-CH-UA → UA ile eşleşmeli
SEC_CH_UA_MAP: dict[str, str] = {
    "Chrome/133": '"Google Chrome";v="133", "Chromium";v="133", "Not_A Brand";v="24"',
    "Chrome/132": '"Google Chrome";v="132", "Chromium";v="132", "Not_A Brand";v="24"',
    "Chrome/131": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Edg/131":    '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
}

ACCEPT_LANGUAGE_POOL = [
    "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "tr,en-US;q=0.9,en;q=0.8",
    "tr-TR,tr;q=0.8,en;q=0.6",
    "tr-TR,tr;q=0.9",
]

VIEWPORTS = [
    (1920, 1080), (1440, 900), (1366, 768),
    (1536, 864),  (1280, 800), (2560, 1440),
    (1600, 900),  (1280, 1024),
]


# ─── Header üretici ──────────────────────────────────────────────────────────

def build_stealth_headers(ua: str | None = None, referer: str = "") -> dict[str, str]:
    """
    Gerçek tarayıcıya benzeyen HTTP başlıkları üretir.
    UA belirtilmezse havuzdan rastgele seçilir.
    """
    ua = ua or random.choice(REAL_USER_AGENTS)
    is_firefox = "Firefox" in ua
    is_edge    = "Edg/"    in ua

    headers: dict[str, str] = {
        "User-Agent":      ua,
        "Accept-Language": random.choice(ACCEPT_LANGUAGE_POOL),
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection":      "keep-alive",
        "DNT":             "1",
    }

    if is_firefox:
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        )
    else:
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        )
        # Chromium Sec-CH başlıkları
        for key, val in SEC_CH_UA_MAP.items():
            if key in ua:
                headers["Sec-CH-UA"] = val
                break
        headers["Sec-CH-UA-Mobile"]   = "?0"
        headers["Sec-CH-UA-Platform"] = random.choice(['"Windows"', '"macOS"'])
        headers["Sec-Fetch-Dest"]  = "document"
        headers["Sec-Fetch-Mode"]  = "navigate"
        headers["Sec-Fetch-Site"]  = "same-origin" if referer else "none"
        headers["Sec-Fetch-User"]  = "?1"
        headers["Upgrade-Insecure-Requests"] = "1"

    if referer:
        headers["Referer"] = referer

    return headers


# ─── Ban dedektörü ────────────────────────────────────────────────────────────

BAN_KEYWORDS = frozenset([
    "captcha", "cf-challenge", "just a moment", "access denied",
    "403 forbidden", "robot", "ddos", "security check",
    "dogrulama", "engellendi", "blocked",
])


def is_ban_response(html: str, status_code: int = 200) -> bool:
    """Yanıt bir bot engeli mi?"""
    if status_code in (403, 429, 503):
        return True
    if len(html) < 800:
        return True
    lc = html[:3000].lower()
    return any(kw in lc for kw in BAN_KEYWORDS)


# ─── Token Bucket Rate Limiter ────────────────────────────────────────────────

class TokenBucketRateLimiter:
    """
    Thread-safe token bucket.
    rate    = saniyede max istek sayısı
    burst   = anlık maksimum istek (patlama)
    """

    def __init__(self, rate: float = 1.0, burst: int = 3) -> None:
        self._rate    = rate
        self._burst   = burst
        self._tokens  = float(burst)
        self._lock    = threading.Lock()
        self._last_ts = time.monotonic()

    def acquire(self, block: bool = True) -> bool:
        with self._lock:
            now    = time.monotonic()
            delta  = now - self._last_ts
            self._tokens = min(self._burst, self._tokens + delta * self._rate)
            self._last_ts = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            if not block:
                return False
            wait = (1.0 - self._tokens) / self._rate
        time.sleep(wait + random.uniform(0.1, 0.3))
        return self.acquire(block=False)


# ─── Cookie Jar ───────────────────────────────────────────────────────────────

class SessionCookieJar:
    """
    Selenium driver'ından cookie'leri dışa aktarır / içe aktarır.
    Disk'te JSON olarak saklar (oturumlar arası kalıcılık).
    """

    def __init__(self, storage_dir: str = "outputs/cookies") -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, domain: str) -> Path:
        safe = re.sub(r"[^a-z0-9_-]", "_", domain.lower())
        return self._dir / f"{safe}.json"

    def save(self, driver: Any, domain: str = "akakce.com") -> None:
        try:
            cookies = driver.get_cookies()
            self._path(domain).write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.debug("Cookie kaydedildi: %d adet (%s)", len(cookies), domain)
        except Exception as exc:
            logger.debug("Cookie kaydetme hatası: %s", exc)

    def load(self, driver: Any, domain: str = "akakce.com") -> int:
        path = self._path(domain)
        if not path.exists():
            return 0
        try:
            cookies = json.loads(path.read_text(encoding="utf-8"))
            loaded  = 0
            for c in cookies:
                try:
                    driver.add_cookie(c)
                    loaded += 1
                except Exception:
                    pass
            logger.debug("Cookie yüklendi: %d adet", loaded)
            return loaded
        except Exception as exc:
            logger.debug("Cookie yükleme hatası: %s", exc)
            return 0

    def clear(self, domain: str = "akakce.com") -> None:
        p = self._path(domain)
        if p.exists():
            p.unlink()


# ─── Selenium Stealth JS ──────────────────────────────────────────────────────

STEALTH_JS = """
// navigator.webdriver gizle
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Gerçekçi plugin listesi
Object.defineProperty(navigator, 'plugins', {get: () => {
  const plugins = ['Chrome PDF Plugin','Chrome PDF Viewer','Native Client'];
  const arr = plugins.map(n => ({name:n,filename:n.toLowerCase().replace(/ /g,'_')+'.dll',description:n}));
  arr.length = plugins.length;
  arr.item = i => arr[i];
  arr.namedItem = n => arr.find(p => p.name===n);
  arr.refresh = ()=>{};
  return arr;
}});

// Dil
Object.defineProperty(navigator, 'languages', {get: () => ['tr-TR', 'tr', 'en-US', 'en']});

// Chrome objesi
window.chrome = {
  runtime:    {},
  loadTimes:  function(){},
  csi:        function(){},
  app:        {}
};

// Canvas noise (fingerprint engelle)
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
  const ctx = this.getContext('2d');
  if (ctx) {
    const imgData = ctx.getImageData(0, 0, this.width, this.height);
    for (let i = 0; i < imgData.data.length; i += 4) {
      imgData.data[i]   += Math.floor(Math.random() * 3) - 1;
      imgData.data[i+1] += Math.floor(Math.random() * 3) - 1;
      imgData.data[i+2] += Math.floor(Math.random() * 3) - 1;
    }
    ctx.putImageData(imgData, 0, 0);
  }
  return origToDataURL.apply(this, arguments);
};

// WebGL vendor/renderer sahteciliği
const origGetParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel Iris OpenGL Engine';
  return origGetParameter.call(this, parameter);
};

// Otomation permission engelle
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
  parameters.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : origQuery(parameters);
"""


def inject_stealth(driver: Any) -> None:
    """Driver'a stealth JS'i enjekte et."""
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": STEALTH_JS},
    )


# ─── Proxy Rotasyon ───────────────────────────────────────────────────────────

@dataclass
class ProxyConfig:
    host:     str
    port:     int
    username: str = ""
    password: str = ""
    protocol: str = "http"   # http / socks5

    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"


class ProxyPool:
    """Round-robin proxy seçici."""

    def __init__(self, proxies: list[ProxyConfig] | None = None) -> None:
        self._proxies = proxies or []
        self._idx     = 0
        self._lock    = threading.Lock()

    @property
    def has_proxies(self) -> bool:
        return bool(self._proxies)

    def next(self) -> ProxyConfig | None:
        if not self._proxies:
            return None
        with self._lock:
            proxy     = self._proxies[self._idx % len(self._proxies)]
            self._idx += 1
        return proxy

    def remove(self, proxy: ProxyConfig) -> None:
        """Banlanan proxy'yi havuzdan çıkar."""
        with self._lock:
            self._proxies = [p for p in self._proxies if p.host != proxy.host]
        logger.warning("Proxy kaldırıldı: %s:%d", proxy.host, proxy.port)


# ─── Singleton Rate Limiter ────────────────────────────────────────────────────

# Uygulama genelinde paylaşılan rate limiter (0.7 req/sn ≈ 1 req/1.4 sn)
DEFAULT_RATE_LIMITER = TokenBucketRateLimiter(rate=0.7, burst=2)
