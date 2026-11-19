"""Tüm veri kaynaklarının ortak arayüzü.

Her kaynak `fetch(term_id, query, start, end)` ile bir FetchResult döndürür ve ASLA istisna fırlatmaz:
hatalar FetchResult.status / error alanlarında raporlanır. Bu sayede bir kaynağın düşmesi diğerlerini
durdurmaz ve ileride aynı fonksiyon bir MCP aracı olarak dışarı açılabilir.

Aynı tipten birden fazla kaynak kullanılabilir (ör. Türkçe ve İngilizce Vikipedi). Kaynağın adı config'teki
anahtardır; tipi `type:` alanıyla verilir.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone

import requests

from ..logs import get_logger
from ..models import FetchResult, FetchStatus

log = get_logger("sources")

# Geçici olabilecek durumlar: tekrar denemeye değer.
RETRY_HTTP = {429, 500, 502, 503, 504}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Source(ABC):
    type_name: str = "base"
    metric: str = ""

    def __init__(self, settings: dict, session: requests.Session | None = None,
                 user_agent: str = "SENG360-trendpipe/0.1", name: str | None = None):
        self.settings = settings or {}
        self.name = name or self.type_name
        self.session = session or requests.Session()
        self.user_agent = user_agent
        self.timeout = float(self.settings.get("timeout_sec", 30))
        self.max_retries = int(self.settings.get("max_retries", 0))
        self.retry_backoff = float(self.settings.get("retry_backoff_sec", 0))
        self._last_request = 0.0
        self._attempts = 0
        self.timezone = "Europe/Istanbul"  # build_sources config'teki window.timezone ile ayarlar

    @property
    def description(self) -> str:
        """Verinin anlamı (LLM'e ve README'ye gider)."""
        return ""

    @abstractmethod
    def fetch(self, term_id: str, query: str, start: date, end: date) -> FetchResult:
        ...

    # --- yardımcılar ---
    def _result(self, term_id: str, query: str, start: date, end: date, **kw) -> FetchResult:
        kw.setdefault("fetched_at", utc_now_iso())
        kw.setdefault("attempts", self._attempts)
        return FetchResult(source=self.name, term_id=term_id, query=query, start=start, end=end,
                           metric=self.metric, **kw)

    def _throttle(self) -> None:
        interval = float(self.settings.get("request_interval_sec", 0) or 0)
        wait = self._last_request + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        """Hız sınırına uyarak GET; zaman aşımı, bağlantı hatası ve 429/5xx'te artan beklemeyle tekrar dener.

        Son denemede de başarısız olursa son yanıtı döndürür ya da son istisnayı fırlatır.
        """
        self._attempts = 0
        for attempt in range(self.max_retries + 1):
            r = None
            self._throttle()
            self._attempts = attempt + 1
            last = attempt == self.max_retries
            try:
                r = self.session.get(url, params=params, timeout=self.timeout,
                                     headers={"User-Agent": self.user_agent, "Accept": "application/json"})
            except (requests.Timeout, requests.ConnectionError) as exc:
                log.info("%s deneme %d/%d: %s", self.name, attempt + 1, self.max_retries + 1, type(exc).__name__)
                if last:
                    raise
            else:
                log.info("%s deneme %d/%d: HTTP %s %s", self.name, attempt + 1, self.max_retries + 1,
                         r.status_code, getattr(r, "url", url))
                if r.status_code not in RETRY_HTTP or last:
                    return r
            wait = max(self.retry_backoff * (attempt + 1), _retry_after(r))
            log.info("%s: %.0f sn beklenip tekrar denenecek", self.name, wait)
            time.sleep(wait)
        raise RuntimeError("ulaşılamaz")  # pragma: no cover


def _retry_after(resp) -> float:
    """Sunucu 'Retry-After' başlığıyla ne kadar beklememizi söylediyse onu kullan (en fazla 120 sn)."""
    headers = getattr(resp, "headers", None) or {}
    try:
        return min(float(headers.get("Retry-After", 0)), 120.0)
    except (TypeError, ValueError):
        return 0.0


def error_result(src: Source, term_id: str, query: str, start: date, end: date,
                 exc: Exception, url: str | None = None) -> FetchResult:
    return src._result(term_id, query, start, end, status=FetchStatus.ERROR,
                       error=f"{type(exc).__name__}: {exc}", request_url=url)
