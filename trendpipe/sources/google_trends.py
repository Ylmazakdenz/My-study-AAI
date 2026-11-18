"""Google Trends — DENEYSEL adaptör (resmi olmayan pytrends kütüphanesi).

Durum (kontrol: 2026-11-19):
- Resmi Google Trends API 24.07.2025'te kapalı alfa olarak duyuruldu; erişim başvuru ile veriliyor.
- pytrends resmi değildir, Nisan 2025'te arşivlendi; Google sık sık 429 (çok fazla istek) döndürür,
  özellikle bulut / Colab IP'lerinden.
Bu yüzden varsayılan olarak kapalıdır. Açmak için: pip install -r requirements-optional.txt ve config'te enabled: true.
Değerler her istekte 0-100 arasına ölçeklenir (göreli ilgi); mutlak arama sayısı DEĞİLDİR.
"""

from __future__ import annotations

import json

from ..models import FetchStatus, Point
from .base import Source


class GoogleTrendsSource(Source):
    name = "google_trends"
    metric = "relative_interest_0_100"
    description = ("Google aramalarında terime duyulan göreli ilgi (0-100, her terim kendi dönemindeki zirvesine "
                   "göre ölçeklenir). Arama ilgisini gösterir; arama sayısı veya satış değildir.")

    def fetch(self, term_id, query, start, end):
        try:
            from pytrends.request import TrendReq  # type: ignore
        except ImportError:
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR,
                                error="pytrends kurulu değil: pip install -r requirements-optional.txt")
        timeframe = f"{start:%Y-%m-%d} {end:%Y-%m-%d}"
        geo = self.settings.get("geo", "TR")
        url = f"https://trends.google.com/trends/explore?q={query}&geo={geo}&date={timeframe.replace(' ', '%20')}"
        self._throttle()
        try:
            client = TrendReq(hl=self.settings.get("hl", "tr-TR"), tz=-180, timeout=(10, 30))
            client.build_payload([query], timeframe=timeframe, geo=geo)
            df = client.interest_over_time()
        except Exception as exc:  # pytrends farklı istisna türleri fırlatabiliyor (429 dahil)
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR, request_url=url,
                                error=f"{type(exc).__name__}: {exc}")
        if df is None or df.empty or query not in df.columns:
            return self._result(term_id, query, start, end, status=FetchStatus.EMPTY, request_url=url,
                                error="Google Trends bu terim için veri döndürmedi (çok düşük hacim olabilir)",
                                raw_body="{}")
        records = []
        points = []
        for idx, row in df.iterrows():
            d = idx.date()
            partial = bool(row.get("isPartial", False))
            records.append({"date": d.isoformat(), "value": int(row[query]), "isPartial": partial})
            if not partial:  # tamamlanmamış dönemi analize katma
                points.append(Point(d, float(row[query])))
        raw = json.dumps({"query": query, "geo": geo, "timeframe": timeframe, "rows": records}, ensure_ascii=False)
        status = FetchStatus.OK if points else FetchStatus.EMPTY
        return self._result(term_id, query, start, end, status=status, points=points, request_url=url,
                            http_status=200, raw_body=raw)
