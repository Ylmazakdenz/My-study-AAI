"""Testler ağa çıkmaz. Kaynakların yanıt BİÇİMİNİ taklit eden sahte oturum kullanılır.
Buradaki sayılar gerçek veri değildir; gerçek örnek veri data/sample/ altındadır."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeResponse:
    def __init__(self, status_code=200, body="", url="https://example.test"):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.url = url

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """url içinde geçen anahtar kelimeye göre yanıt döndürür."""

    def __init__(self, routes: dict, default=None):
        self.routes = routes
        self.default = default or FakeResponse(404, {"detail": "not found"})
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params, headers))
        key = url + " " + json.dumps(params or {}, ensure_ascii=False)
        for needle, resp in self.routes.items():
            if needle in key:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return self.default


def wiki_body(start: date, values: list[int | None]) -> dict:
    items = []
    for i, v in enumerate(values):
        if v is None:  # Wikimedia görüntüleme olmayan günü hiç döndürmez
            continue
        d = start + timedelta(days=i)
        items.append({"project": "tr.wikipedia", "article": "X", "granularity": "daily",
                      "timestamp": d.strftime("%Y%m%d") + "00", "access": "all-access",
                      "agent": "user", "views": v})
    return {"items": items}


def gdelt_body(start: date, values: list[int]) -> dict:
    data = [{"date": (start + timedelta(days=i)).strftime("%Y%m%dT000000Z"), "value": v, "norm": 1000}
            for i, v in enumerate(values)]
    return {"query_details": {"title": "x"}, "timeline": [{"series": "Article Count", "data": data}]}


@pytest.fixture
def cfg():
    return {
        "brand": {"name": "Test", "market": "TR", "season": "KŞ"},
        "cache": {"enabled": False},          # testler birbirinin verisini okumasın
        "window": {"recent_days": 7, "baseline_days": 7, "end_offset_days": 2},
        "analysis": {"min_coverage": 0.8, "flat_threshold_pct": 15, "low_volume": {"wikimedia": 5, "gdelt": 1}},
        "sources": {"wikimedia": {"enabled": True, "project": "tr.wikipedia"},
                    "gdelt": {"enabled": True, "source_country": "turkey", "source_lang": "turkish",
                              "request_interval_sec": 0}},
        "terms": [
            {"id": "a", "label": "Yükselen", "queries": {"wikimedia": "Yukselen", "gdelt": "rising"}},
            {"id": "b", "label": "Eksik", "queries": {"wikimedia": "Eksik"}},
            {"id": "c", "label": "Yok", "queries": {"wikimedia": "Yok_Makale", "gdelt": "nothing"}},
        ],
    }
