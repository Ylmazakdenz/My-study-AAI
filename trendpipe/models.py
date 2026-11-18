"""Kaynaklar arasında ortak veri yapıları."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date


class FetchStatus:
    """Bir çekme işleminin sonucu. 'ok' dışındaki her durum açıkça raporlanır; eksik veri 0 sayılmaz."""

    OK = "ok"                  # veri geldi
    EMPTY = "empty"            # istek başarılı ama kaynak hiç veri döndürmedi
    NOT_FOUND = "not_found"    # terim / makale kaynakta bulunamadı
    ERROR = "error"            # bağlantı, zaman aşımı, kota, beklenmeyen yanıt vb.
    SKIPPED = "skipped"        # bu kaynak için sorgu tanımlı değil ya da kaynak kapalı


@dataclass
class Term:
    id: str
    label: str
    category: str = ""
    queries: dict[str, str] = field(default_factory=dict)


@dataclass
class Point:
    day: date
    value: float
    # Kaynağa özgü ek alan (ör. GDELT 'norm' = o gün izlenen toplam haber).
    extra: dict | None = None


@dataclass
class FetchResult:
    source: str
    term_id: str
    query: str
    start: date
    end: date
    status: str
    metric: str                       # değerin anlamı (ör. "pageviews", "article_count")
    points: list[Point] = field(default_factory=list)
    raw_body: str | None = None       # kaynağın ham yanıtı (olduğu gibi kaydedilir)
    raw_ext: str = "json"
    request_url: str | None = None
    http_status: int | None = None
    error: str | None = None
    fetched_at: str | None = None     # ISO-8601 UTC
    attempts: int = 0                 # kaç kez denendi (tekrar denemeler dahil)

    def meta(self) -> dict:
        d = asdict(self)
        d.pop("points")
        d.pop("raw_body")
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        d["n_points"] = len(self.points)
        return d
