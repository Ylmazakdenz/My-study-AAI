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
AGG = "https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate"


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

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._totals: dict[tuple[date, date], dict[date, float] | str] = {}

    def project_totals(self, start: date, end: date) -> dict[date, float] | str:
        """Projenin (ör. en.wikipedia) günlük TOPLAM insan görüntülemesi; makale değerleri buna oranlanır.

        Neden: Vikipedi'nin genel trafiği yıldan yıla değişiyor (Wikimedia 2025'te bot tespitini güncelledi ve
        insan görüntülemelerinde ~%8 düşüş bildirdi). 19.11.2026 çalıştırmasında İngilizce Vikipedi'de 6 terimin
        hepsi geçen yıla göre %27-62 düşük çıktı: bu, terimlere değil kaynağın kendisine ait bir değişim.
        Hata durumunda hata metni döner (makale verisi yine kullanılır, oranlama yapılmaz).
        """
        key = (start, end)
        if key not in self._totals:
            s = self.settings
            url = (f"{AGG}/{self.project}/{s.get('access', 'all-access')}/{s.get('agent', 'user')}/daily/"
                   f"{start:%Y%m%d}/{end:%Y%m%d}")
            try:
                r = self._get(url)
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                self._totals[key] = {datetime.strptime(i["timestamp"][:8], "%Y%m%d").date(): float(i["views"])
                                     for i in r.json().get("items", [])}
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                self._totals[key] = f"proje toplamı alınamadı ({type(exc).__name__}: {exc})"
        return self._totals[key]

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
        note = None
        if points and self.settings.get("normalize_by_project", True):
            totals = self.project_totals(start, end)
            if isinstance(totals, str):
                note = totals
            else:
                points = [Point(p.day, p.value, {"norm": totals[p.day]} if p.day in totals else None)
                          for p in points]
        status = FetchStatus.OK if points else FetchStatus.EMPTY
        return self._result(term_id, query, start, end, status=status, points=points, error=note, **common)


def _detail(r: requests.Response) -> str:
    try:
        j = r.json()
        return str(j.get("detail") or j.get("title") or "")
    except ValueError:
        return ""
