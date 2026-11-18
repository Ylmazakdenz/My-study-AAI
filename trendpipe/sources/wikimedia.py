"""Wikimedia Analytics API — makale bazında günlük sayfa görüntüleme.

Belge: https://doc.wikimedia.org/analytics-api/
Erişim politikası: User-Agent zorunlu, anahtar yok, istekleri sırayla gönder.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

import requests

from ..models import FetchStatus, Point
from .base import Source, error_result

BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


class WikimediaSource(Source):
    type_name = "wikimedia"
    metric = "pageviews"

    @property
    def project(self) -> str:
        return self.settings.get("project", "tr.wikipedia")

    @property
    def description(self) -> str:
        lang = {"tr": "Türkçe", "en": "İngilizce"}.get(self.project.split(".")[0], self.project)
        scope = "Türkçe okuyucular" if self.project.startswith("tr.") else "dünya geneli okuyucular"
        return (f"{lang} Vikipedi ({self.project}) makalesinin günlük görüntülenme sayısı, botlar hariç "
                f"({scope}). Bir ürün tipine duyulan bilgi merakını gösterir; satın alma niyeti veya satış değildir.")

    def build_url(self, article: str, start: date, end: date) -> str:
        s = self.settings
        title = quote(article.replace(" ", "_"), safe="")
        return (f"{BASE}/{self.project}/{s.get('access', 'all-access')}/"
                f"{s.get('agent', 'user')}/{title}/daily/{start:%Y%m%d}/{end:%Y%m%d}")

    def fetch(self, term_id, query, start, end):
        url = self.build_url(query, start, end)
        try:
            r = self._get(url)
        except requests.RequestException as exc:
            return error_result(self, term_id, query, start, end, exc, url)

        common = dict(request_url=url, http_status=r.status_code, raw_body=r.text)
        if r.status_code == 404:
            # Wikimedia makale yoksa ya da aralıkta hiç görüntüleme yoksa 404 döner.
            return self._result(term_id, query, start, end, status=FetchStatus.NOT_FOUND,
                                error=_detail(r) or "Makale bulunamadı ya da bu aralıkta veri yok", **common)
        if r.status_code != 200:
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR,
                                error=f"HTTP {r.status_code}: {_detail(r) or r.text[:200]}", **common)
        try:
            items = r.json().get("items", [])
            points = [Point(datetime.strptime(i["timestamp"][:8], "%Y%m%d").date(), float(i["views"]))
                      for i in items]
        except (ValueError, KeyError, TypeError) as exc:
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR,
                                error=f"Yanıt çözümlenemedi: {exc}", **common)
        status = FetchStatus.OK if points else FetchStatus.EMPTY
        return self._result(term_id, query, start, end, status=status, points=points, **common)


def _detail(r: requests.Response) -> str:
    try:
        j = r.json()
        return str(j.get("detail") or j.get("title") or "")
    except ValueError:
        return ""
