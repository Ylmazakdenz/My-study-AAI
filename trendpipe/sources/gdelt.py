"""GDELT DOC 2.0 API — haber görünürlüğü zaman serisi.

Belge: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
Anahtar gerekmez. Çok sık istek gönderilirse düz metin hata mesajı döner; bu yüzden istekler arasında bekleriz.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

import requests

from ..models import FetchStatus, Point
from .base import Source, error_result

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltSource(Source):
    type_name = "gdelt"

    @property
    def description(self) -> str:
        return ("GDELT'in izlediği çevrim içi haberlerde terimin geçtiği haber sayısı (Türkiye kaynaklı, Türkçe "
                "haberler); analizde o gün izlenen toplam habere oranlanır (10.000 haberde). Medya/haber "
                "görünürlüğünü gösterir; tüketici talebi veya satış değildir.")

    @property
    def metric(self) -> str:  # type: ignore[override]
        return "article_count" if self.mode == "timelinevolraw" else "volume_intensity_pct"

    @property
    def mode(self) -> str:
        return str(self.settings.get("mode", "timelinevolraw")).lower()

    def build_params(self, query: str, start: date, end: date) -> dict:
        q = query
        if self.settings.get("source_country"):
            q += f" sourcecountry:{self.settings['source_country']}"
        if self.settings.get("source_lang"):
            q += f" sourcelang:{self.settings['source_lang']}"
        return {
            "query": q,
            "mode": self.mode,
            "format": "json",
            "startdatetime": f"{start:%Y%m%d}000000",
            "enddatetime": f"{end:%Y%m%d}235959",
        }

    def fetch(self, term_id, query, start, end):
        params = self.build_params(query, start, end)
        try:
            r = self._get(BASE, params)
        except requests.RequestException as exc:
            return error_result(self, term_id, query, start, end, exc, BASE)

        common = dict(request_url=r.url, http_status=r.status_code, raw_body=r.text)
        text = r.text.strip()
        if r.status_code != 200:
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR,
                                error=f"HTTP {r.status_code}: {text[:200]}", **common)
        if not text or text == "{}":
            return self._result(term_id, query, start, end, status=FetchStatus.EMPTY,
                                error="GDELT bu sorgu ve dönem için eşleşen haber döndürmedi", **common)
        try:
            payload = r.json()
        except ValueError:
            # GDELT hataları (sorgu çok kısa, hız sınırı vb.) düz metin olarak döner.
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR,
                                error=f"GDELT JSON yerine metin döndürdü: {text[:200]}", raw_ext="txt", **common)
        try:
            points = parse_timeline(payload)
        except (ValueError, KeyError, TypeError) as exc:
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR,
                                error=f"Yanıt çözümlenemedi: {exc}", **common)
        points = [p for p in points if start <= p.day <= end]
        status = FetchStatus.OK if points else FetchStatus.EMPTY
        return self._result(term_id, query, start, end, status=status, points=points, **common)


def parse_timeline(payload: dict) -> list[Point]:
    """GDELT timeline yanıtını günlük noktalara çevirir.

    Çözünürlük günden küçükse (saatlik/15 dk) değerler günlük toplanır; 'norm' (izlenen toplam haber) da toplanır.
    timelinevol (yüzde) modunda günlük ortalama alınır.
    """
    timeline = payload.get("timeline") or []
    if not timeline:
        return []
    series = timeline[0]
    is_raw = "count" in str(series.get("series", "")).lower() or any("norm" in d for d in series.get("data", []))
    sums: dict[date, float] = defaultdict(float)
    norms: dict[date, float] = defaultdict(float)
    counts: dict[date, int] = defaultdict(int)
    for d in series.get("data", []):
        day = _parse_date(d["date"])
        sums[day] += float(d["value"])
        counts[day] += 1
        if "norm" in d:
            norms[day] += float(d["norm"])
    points = []
    for day in sorted(sums):
        value = sums[day] if is_raw else sums[day] / counts[day]
        extra = {"norm": norms[day]} if day in norms else None
        points.append(Point(day, value, extra))
    return points


def _parse_date(s: str) -> date:
    # Örnek: "20251001T000000Z" ya da "20251001000000"
    digits = s.replace("T", "").replace("Z", "")
    dt = datetime.strptime(digits[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
    return dt.date()

