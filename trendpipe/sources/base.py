"""Tüm veri kaynaklarının ortak arayüzü.

Her kaynak `fetch(term_id, query, start, end)` ile bir FetchResult döndürür ve ASLA istisna fırlatmaz:
hatalar FetchResult.status / error alanlarında raporlanır. Bu sayede bir kaynağın düşmesi diğerlerini
durdurmaz ve ileride aynı fonksiyon bir MCP aracı olarak dışarı açılabilir.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone

import requests

from ..models import FetchResult, FetchStatus


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Source(ABC):
    name: str = "base"
    metric: str = ""
    description: str = ""       # verinin anlamı (LLM'e ve README'ye gider)

    def __init__(self, settings: dict, session: requests.Session | None = None,
                 user_agent: str = "SENG360-trendpipe/0.1", timeout: float = 30.0):
        self.settings = settings or {}
        self.session = session or requests.Session()
        self.user_agent = user_agent
        self.timeout = timeout
        self._last_request = 0.0

    @abstractmethod
    def fetch(self, term_id: str, query: str, start: date, end: date) -> FetchResult:
        ...

    # --- yardımcılar ---
    def _result(self, term_id: str, query: str, start: date, end: date, **kw) -> FetchResult:
        kw.setdefault("fetched_at", utc_now_iso())
        return FetchResult(source=self.name, term_id=term_id, query=query, start=start, end=end,
                           metric=self.metric, **kw)

    def _throttle(self) -> None:
        interval = float(self.settings.get("request_interval_sec", 0) or 0)
        wait = self._last_request + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        self._throttle()
        return self.session.get(url, params=params, timeout=self.timeout,
                                headers={"User-Agent": self.user_agent, "Accept": "application/json"})


def error_result(src: Source, term_id: str, query: str, start: date, end: date,
                 exc: Exception, url: str | None = None) -> FetchResult:
    return src._result(term_id, query, start, end, status=FetchStatus.ERROR,
                       error=f"{type(exc).__name__}: {exc}", request_url=url)
