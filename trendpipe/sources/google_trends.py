"""Google Trends — ana kaynak (resmi olmayan pytrends kütüphanesi üzerinden).

Durum (kontrol: 19.11.2026):
- Resmi Google Trends API 24.07.2025'te kapalı alfa olarak duyuruldu; erişim başvuru ile veriliyor.
- pytrends resmi değildir (arşivlendiği bildiriliyor). 19.11.2026'da ev internetinden 6/6 terim başarılı.
  Google sık istekte 429 döndürebilir (özellikle bulut / Colab IP'leri); bu durumda hata açıkça kaydedilir
  ve hat Vikipedi verisiyle devam eder.
Değerler her istekte 0-100 arasına ölçeklenir (her terim kendi dönemindeki zirvesine göre, göreli ilgi);
mutlak arama sayısı DEĞİLDİR. Bu yüzden yalnızca aynı terimin iki dönemi karşılaştırılır.
"""

from __future__ import annotations

import json
from datetime import date

from ..models import FetchStatus, Point
from .base import Source, log


class GoogleTrendsSource(Source):
    type_name = "google_trends"
    metric = "relative_interest_0_100"

    @property
    def description(self) -> str:
        geo = self.settings.get("geo", "TR")
        return (f"Google aramalarında terime duyulan göreli ilgi ({geo}; 0-100, her terim kendi dönemindeki "
                "zirvesine göre ölçeklenir). Arama ilgisini gösterir; arama sayısı veya satış değildir.")

    def fetch(self, term_id, query, start, end):
        """Göreli ilgi serisini çeker.

        Dönem ~9 aydan kısaysa Google günlük, uzunsa haftalık değer döndürür (yıllık karşılaştırma serisi haftalıktır).
        `samples` > 1 ise aynı istek tekrarlanıp ortalama alınır (Google aramaların örneklemini kullandığı için
        tekrarlanan isteklerde değerler biraz değişebilir); her örnek ham kayıtta ayrı tutulur.
        """
        try:
            from pytrends.request import TrendReq  # type: ignore
        except ImportError:
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR,
                                error="pytrends kurulu değil: pip install -r requirements.txt")
        timeframe = f"{start:%Y-%m-%d} {end:%Y-%m-%d}"
        geo = self.settings.get("geo", "TR")
        url = f"https://trends.google.com/trends/explore?q={query}&geo={geo}&date={timeframe.replace(' ', '%20')}"
        n_samples = max(1, int(self.settings.get("samples", 1)))
        samples: list[list[dict]] = []
        self._attempts = 0
        last_error: tuple[str, int | None] | None = None
        for _ in range(n_samples):
            self._throttle()
            self._attempts += 1
            try:
                client = TrendReq(hl=self.settings.get("hl", "tr-TR"), tz=-180, timeout=(10, 30))
                client.build_payload([query], timeframe=timeframe, geo=geo)
                df = client.interest_over_time()
            except Exception as exc:  # pytrends farklı istisna türleri fırlatabiliyor (429 dahil)
                msg = f"{type(exc).__name__}: {exc}"
                last_error = (msg, 429 if "429" in msg or "TooManyRequests" in msg else None)
                log.info("google_trends %s: %s", query, msg)
                continue
            if df is None or df.empty or query not in df.columns:
                samples.append([])
                continue
            samples.append([{"date": idx.date().isoformat(), "value": int(row[query]),
                             "isPartial": bool(row.get("isPartial", False))} for idx, row in df.iterrows()])

        if not samples:
            msg, code = last_error or ("bilinmeyen hata", None)
            return self._result(term_id, query, start, end, status=FetchStatus.ERROR, request_url=url,
                                error=msg, http_status=code)
        good = [s for s in samples if s]
        if not good:
            return self._result(term_id, query, start, end, status=FetchStatus.EMPTY, request_url=url,
                                error="Google Trends bu terim için veri döndürmedi (çok düşük hacim olabilir)",
                                raw_body="{}")
        by_day: dict[str, list[int]] = {}
        partial: set[str] = set()
        for rows in good:
            for r in rows:
                by_day.setdefault(r["date"], []).append(r["value"])
                if r["isPartial"]:
                    partial.add(r["date"])
        points = []
        for d in sorted(by_day):
            if d in partial:  # tamamlanmamış dönem analize girmez (ham kayıtta durur)
                continue
            vals = by_day[d]
            # 0 = "yeterli veri yok"; ortalamaya katılmaz, tüm örneklerde 0 ise 0 kalır (analizde eksik sayılır)
            nz = [v for v in vals if v != 0]
            value = sum(nz) / len(nz) if nz else 0.0
            extra = {"samples": vals} if len(vals) > 1 else None
            points.append(Point(date.fromisoformat(d), float(value), extra))
        raw_obj = {"query": query, "geo": geo, "timeframe": timeframe, "rows": good[0]}
        if len(good) > 1:
            raw_obj["samples"] = good
        note = None if len(good) == n_samples else f"{n_samples} örnekten {len(good)} tanesi alınabildi"
        return self._result(term_id, query, start, end, status=FetchStatus.OK, points=points, request_url=url,
                            http_status=200, raw_body=json.dumps(raw_obj, ensure_ascii=False), error=note)
