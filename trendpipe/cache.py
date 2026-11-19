"""İstek önbelleği: aynı veriyi kısa süre içinde kaynaktan tekrar çekmemek için.

Neden: 19.11.2026'da geliştirme sırasında birkaç saat içinde art arda yapılan çalıştırmalar Google Trends'in hız
sınırına (429) takıldı. Veri günlük olduğu ve dönem bitiş tarihi bugünden 2 gün önce olduğu için, aynı gün içinde
aynı dönem için kaynaktan gelecek veri değişmez.

Kurallar:
- Anahtar: kaynak tipi + veriyi etkileyen ayarlar (proje, bölge, dil, örnek sayısı...) + sorgu + başlangıç/bitiş
  tarihi. Ertesi gün dönem kaydığı için anahtar kendiliğinden değişir; ayar değişirse eski kayıt kullanılmaz.
- Yalnızca BAŞARILI yanıtlar saklanır; hata, 429, boş yanıt saklanmaz (sonraki çalıştırma yeniden dener).
- Kısmen bozuk başarılı yanıtlar da saklanmaz (ör. Vikipedi proje toplamı alınamadı, Google örneklerinden bazıları
  gelmedi): 24 saat boyunca eksik veriyle çalışılmasın.
- Anahtara kod sürümü de girer: veri işleme değiştiğinde (sürüm artınca) eski kayıtlar kullanılmaz.
- Süre (ttl_hours, varsayılan 24) dolan kayıt kullanılmaz ve her çalıştırmanın başında diskten silinir; önbellek
  birikmez. `--refresh` önbelleği yok sayar; `trendpipe clean --cache` tamamen temizler.
- Önbellekten gelen sonuç kayıtta işaretlenir (ilk çekilme zamanı ve çalıştırma kimliğiyle) ve ham yanıt yeni
  çalıştırmanın klasörüne de yazılır; her çalıştırma klasörü kendi başına eksiksizdir.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__
from .logs import get_logger
from .models import FetchResult, FetchStatus, Point

log = get_logger("cache")

CACHE_FORMAT = 1
# Kaynak tipine göre veriyi etkileyen ayarlar (istek aralığı, tekrar sayısı gibi ayarlar veriyi değiştirmez)
DATA_KEYS = {
    "wikimedia": ("project", "access", "agent", "normalize_by_project"),
    "google_trends": ("geo", "hl", "samples"),
    "gdelt": ("source_country", "source_lang", "mode"),
}


def cache_key(source_type: str, settings: dict, query: str, start: date, end: date) -> str:
    relevant = {k: settings.get(k) for k in DATA_KEYS.get(source_type, ())}
    blob = json.dumps({"v": CACHE_FORMAT, "code": __version__, "type": source_type, "settings": relevant,
                       "query": query, "start": start.isoformat(), "end": end.isoformat()},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class FetchCache:
    def __init__(self, directory: str | Path, ttl_hours: float = 24, enabled: bool = True):
        self.dir = Path(directory)
        self.ttl_hours = float(ttl_hours)
        self.enabled = enabled and self.ttl_hours > 0

    def prune(self, now: datetime | None = None) -> int:
        """Süresi dolmuş, bozuk ya da yarım kalmış kayıtları siler. Silinen dosya sayısını döndürür."""
        if not self.dir.exists():
            return 0
        now = now or datetime.now(timezone.utc)
        removed = 0
        for p in self.dir.iterdir():
            if p.suffix == ".tmp":
                expired = True
            elif p.suffix == ".json":
                try:
                    cached_at = datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["cached_at"])
                    expired = (now - cached_at).total_seconds() / 3600 > self.ttl_hours
                except (ValueError, KeyError, OSError):
                    expired = True
            else:
                continue
            if expired:
                p.unlink(missing_ok=True)
                removed += 1
        if removed:
            log.info("önbellek: süresi dolmuş/bozuk %d kayıt silindi", removed)
        return removed

    def clear(self) -> int:
        n = 0
        if self.dir.exists():
            for p in self.dir.glob("*.json"):
                p.unlink(missing_ok=True)
                n += 1
        return n

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str, now: datetime | None = None) -> FetchResult | None:
        if not self.enabled:
            return None
        p = self._path(key)
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(d["cached_at"])
        except (ValueError, KeyError, OSError) as exc:
            log.warning("önbellek kaydı okunamadı, yok sayılıyor: %s (%s)", p.name, exc)
            return None
        age_h = ((now or datetime.now(timezone.utc)) - cached_at).total_seconds() / 3600
        if age_h > self.ttl_hours or age_h < 0:
            return None
        r = d["result"]
        res = FetchResult(
            source=r["source"], term_id=r["term_id"], query=r["query"], start=date.fromisoformat(r["start"]),
            end=date.fromisoformat(r["end"]), status=r["status"], metric=r["metric"], series=r.get("series", "main"),
            points=[Point(date.fromisoformat(p["day"]), p["value"], p.get("extra")) for p in r["points"]],
            raw_body=r.get("raw_body"), raw_ext=r.get("raw_ext", "json"), request_url=r.get("request_url"),
            http_status=r.get("http_status"), error=r.get("error"), fetched_at=r.get("fetched_at"), attempts=0)
        res.from_cache = True
        res.cache_origin_run = d.get("run_id")
        log.info("önbellekten: %s/%s %s→%s (%.1f saat önce, çalıştırma %s)", r["source"], r["query"], r["start"],
                 r["end"], age_h, d.get("run_id"))
        return res

    def put(self, key: str, res: FetchResult, run_id: str) -> None:
        if not self.enabled or res.status != FetchStatus.OK or res.from_cache:
            return
        if res.error:  # başarılı ama kısmen bozuk (not içeriyor): saklanmaz, sonraki çalıştırma yeniden dener
            log.info("önbelleğe alınmadı (kısmi sonuç): %s/%s — %s", res.source, res.query, res.error)
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        d = {"cached_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "run_id": run_id,
             "result": {**res.meta(), "points": [{"day": p.day.isoformat(), "value": p.value, "extra": p.extra}
                                                 for p in res.points], "raw_body": res.raw_body}}
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path(key))   # yarım yazılmış kayıt kalmasın
