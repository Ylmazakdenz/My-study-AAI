"""Değişim hesabı: yakın dönem ortalaması ile hemen önceki dönem ortalamasının karşılaştırılması.

Kurallar:
- Hesapları Python yapar; model yalnızca bu sonuçları yorumlar.
- Eksik gün sıfır sayılmaz. Bir pencerede kapsama oranı min_coverage'ın altındaysa değişim hesaplanmaz.
- Farklı kaynakların değerleri birbirine eklenmez/karşılaştırılmaz (birimleri ve anlamları farklı).
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from .config import Window
from .models import FetchStatus, Point

ANALYSIS_FIELDS = [
    "source", "metric", "term_id", "label", "category", "query", "fetch_status", "result",
    "baseline_start", "baseline_end", "recent_start", "recent_end",
    "baseline_days_present", "recent_days_present", "baseline_coverage", "recent_coverage",
    "baseline_mean", "recent_mean", "abs_change", "pct_change", "recent_slope_per_day",
    "direction", "low_volume", "signal", "rank_in_source", "notes",
]


class Signal:
    """Yorum için sınıflandırma (Python yapar, model değil)."""

    STRONG_UP = "strong_up"          # yeterli hacim + eşik üstü artış
    STRONG_DOWN = "strong_down"      # yeterli hacim + eşik üstü düşüş
    FLAT = "flat"                    # yeterli hacim, anlamlı değişim yok
    WEAK = "weak"                    # hesaplandı ama düşük hacim / önceki dönem 0 -> güvenilmez
    INSUFFICIENT = "insufficient"    # kapsama yetersiz, hesaplanmadı
    NO_DATA = "no_data"              # veri alınamadı


def classify(row: dict) -> str:
    res = row.get("result")
    if res == Result.NO_DATA:
        return Signal.NO_DATA
    if res == Result.INSUFFICIENT:
        return Signal.INSUFFICIENT
    if res == Result.BASELINE_ZERO or row.get("low_volume"):
        return Signal.WEAK
    return {"up": Signal.STRONG_UP, "down": Signal.STRONG_DOWN}.get(row.get("direction"), Signal.FLAT)


class Result:
    COMPUTED = "computed"
    INSUFFICIENT = "insufficient_data"
    BASELINE_ZERO = "baseline_zero"
    NO_DATA = "no_data"


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _slope(values: list[tuple[int, float]]) -> float | None:
    """Basit doğrusal regresyon eğimi (birim/gün)."""
    if len(values) < 3:
        return None
    xs = [x for x, _ in values]
    ys = [y for _, y in values]
    mx, my = mean(xs), mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in values) / den


def analyze_series(points: list[Point], window: Window, *, min_coverage: float = 0.8,
                   flat_threshold_pct: float = 15.0, low_volume: float | None = None) -> dict:
    by_day = {p.day: p.value for p in points}
    base_days = _days(window.baseline_start, window.baseline_end)
    rec_days = _days(window.recent_start, window.recent_end)
    base_vals = [by_day[d] for d in base_days if d in by_day]
    rec_vals = [by_day[d] for d in rec_days if d in by_day]
    out = {
        **window.as_dict(),
        "baseline_days_present": len(base_vals), "recent_days_present": len(rec_vals),
        "baseline_coverage": round(len(base_vals) / len(base_days), 3),
        "recent_coverage": round(len(rec_vals) / len(rec_days), 3),
        "baseline_mean": None, "recent_mean": None, "abs_change": None, "pct_change": None,
        "recent_slope_per_day": None, "direction": None, "low_volume": None, "notes": [],
    }
    if not base_vals and not rec_vals:
        out["result"] = Result.NO_DATA
        out["notes"].append("Pencere içinde hiç veri yok.")
        return out
    if out["baseline_coverage"] < min_coverage or out["recent_coverage"] < min_coverage:
        out["result"] = Result.INSUFFICIENT
        out["notes"].append(
            f"Kapsama yetersiz (önceki {out['baseline_coverage']:.0%}, yakın {out['recent_coverage']:.0%}; "
            f"gereken ≥{min_coverage:.0%}). Eksik günler sıfır sayılmadı, değişim hesaplanmadı.")
        return out

    bm, rm = mean(base_vals), mean(rec_vals)
    out["baseline_mean"] = round(bm, 3)
    out["recent_mean"] = round(rm, 3)
    out["abs_change"] = round(rm - bm, 3)
    slope = _slope([((d - window.recent_start).days, by_day[d]) for d in rec_days if d in by_day])
    out["recent_slope_per_day"] = round(slope, 4) if slope is not None else None

    if bm == 0:
        out["result"] = Result.BASELINE_ZERO
        out["notes"].append("Önceki dönem ortalaması 0; yüzde değişim tanımsız.")
        out["direction"] = "up" if rm > 0 else "flat"
    else:
        pct = (rm - bm) / bm * 100
        out["pct_change"] = round(pct, 1)
        out["result"] = Result.COMPUTED
        out["direction"] = "up" if pct >= flat_threshold_pct else "down" if pct <= -flat_threshold_pct else "flat"
    out["low_volume"] = bool(low_volume is not None and bm < low_volume and rm < low_volume)
    if out["low_volume"]:
        out["notes"].append(f"Düşük hacim (ortalamalar < {low_volume}); küçük sayılardaki değişim gürültü olabilir.")
    return out


def analyze_run(manifest: dict, series: dict, cfg: dict, window: Window) -> list[dict]:
    a = cfg.get("analysis") or {}
    low = a.get("low_volume") or {}
    rows = []
    for rec in manifest["fetches"]:
        base = {k: rec.get(k) for k in ("source", "metric", "term_id", "label", "category", "query")}
        base["fetch_status"] = rec["status"]
        if rec["status"] != FetchStatus.OK:
            rows.append({**base, **window.as_dict(), "result": Result.NO_DATA,
                         "notes": [f"Veri alınamadı ({rec['status']}): {rec.get('error') or '-'}"]})
            continue
        stats = analyze_series(series.get((rec["source"], rec["term_id"]), []), window,
                               min_coverage=float(a.get("min_coverage", 0.8)),
                               flat_threshold_pct=float(a.get("flat_threshold_pct", 15)),
                               low_volume=low.get(rec["source"]))
        rows.append({**base, **stats})
    for r in rows:
        r["signal"] = classify(r)

    # Sıralama yalnızca aynı kaynak içinde ve hesaplanabilen yüzde değişimlere göre yapılır.
    for src in {r["source"] for r in rows}:
        ranked = sorted([r for r in rows if r["source"] == src and r.get("pct_change") is not None],
                        key=lambda r: r["pct_change"], reverse=True)
        for i, r in enumerate(ranked, 1):
            r["rank_in_source"] = i
    return rows


def flatten_for_csv(rows: list[dict]) -> list[dict]:
    return [{**r, "notes": " | ".join(r.get("notes") or [])} for r in rows]
