"""Değişim hesabı.

İki karşılaştırma yapılır:
1. Dönemsel: yakın dönem (son 28 gün) ortalaması ↔ hemen önceki 28 gün (ana seri, günlük).
2. Yıllık: yakın dönem ↔ geçen yılın aynı dönemi (52 hafta önce; uzun seri). Giyimde ilgi mevsimle değişir
   (palto her Kasım artar); yıllık karşılaştırma mevsimsel artışı gerçek değişimden ayırır.
İkisi birleştirilerek `trend_label` üretilir (ör. sezon üstü artış / mevsimsel artış).

Kurallar:
- Hesapları Python yapar; model yalnızca bu sonuçları yorumlar.
- Eksik gün sıfır sayılmaz. Bir pencerede kapsama oranı min_coverage'ın altındaysa değişim hesaplanmaz.
- Farklı kaynakların değerleri birbirine eklenmez/karşılaştırılmaz (birimleri ve anlamları farklı).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean, median, stdev

from .config import Window
from .models import FetchStatus, Point

ANALYSIS_FIELDS = [
    "source", "metric", "term_id", "label", "category", "query", "fetch_status", "result",
    "baseline_start", "baseline_end", "recent_start", "recent_end",
    "baseline_days_present", "recent_days_present", "source_gap_days", "baseline_coverage", "recent_coverage",
    "baseline_mean", "recent_mean", "baseline_raw_mean", "recent_raw_mean", "abs_change", "pct_change",
    "recent_slope_per_day",
    "direction", "pop_t_stat", "low_volume", "signal",
    "ly_start", "ly_end", "yoy_result", "yoy_granularity", "yoy_ly_points", "yoy_recent_points",
    "yoy_ly_mean", "yoy_recent_mean", "yoy_pct_change", "yoy_direction", "yoy_t_stat", "yoy_low_volume",
    "yoy_signal",
    "trend_label", "rank_in_source", "notes",
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


class Trend:
    """Dönemsel + yıllık karşılaştırmanın birleşimi (yorum etiketi)."""

    ABOVE_SEASON_UP = "sezon_ustu_artis"          # yakın dönemde arttı VE geçen yılın aynı döneminden yüksek
    SEASONAL_UP = "mevsimsel_artis"               # arttı ama geçen yılla benzer düzeyde -> mevsimin olağan artışı
    SEASONAL_UP_WEAKER = "mevsimsel_artis_gecen_yildan_zayif"
    UP_YOY_UNKNOWN = "artis_yillik_bilinmiyor"
    ABOVE_SEASON_DOWN = "sezon_alti_dusus"        # düştü VE geçen yılın aynı döneminden düşük
    SEASONAL_DOWN = "mevsimsel_dusus"
    SEASONAL_DOWN_STRONGER = "mevsimsel_dusus_gecen_yildan_guclu"
    DOWN_YOY_UNKNOWN = "dusus_yillik_bilinmiyor"
    YEARLY_UP = "yillik_artis"                    # son dönemde sabit ama geçen yıldan yüksek
    YEARLY_DOWN = "yillik_dusus"
    NO_CHANGE = "degisim_yok"
    WEAK = "dusuk_hacim"
    INSUFFICIENT = "hesaplanamadi"
    NO_DATA = "veri_yok"


def trend_label(pop: str, yoy: str | None) -> str:
    if pop == Signal.WEAK:
        return Trend.WEAK
    if pop == Signal.INSUFFICIENT:
        return Trend.INSUFFICIENT
    if pop == Signal.NO_DATA:
        return Trend.NO_DATA
    if pop == Signal.STRONG_UP:
        return {Signal.STRONG_UP: Trend.ABOVE_SEASON_UP, Signal.FLAT: Trend.SEASONAL_UP,
                Signal.STRONG_DOWN: Trend.SEASONAL_UP_WEAKER}.get(yoy, Trend.UP_YOY_UNKNOWN)
    if pop == Signal.STRONG_DOWN:
        return {Signal.STRONG_DOWN: Trend.ABOVE_SEASON_DOWN, Signal.FLAT: Trend.SEASONAL_DOWN,
                Signal.STRONG_UP: Trend.SEASONAL_DOWN_STRONGER}.get(yoy, Trend.DOWN_YOY_UNKNOWN)
    return {Signal.STRONG_UP: Trend.YEARLY_UP, Signal.STRONG_DOWN: Trend.YEARLY_DOWN}.get(yoy, Trend.NO_CHANGE)


class Result:
    COMPUTED = "computed"
    INSUFFICIENT = "insufficient_data"
    BASELINE_ZERO = "baseline_zero"
    NO_DATA = "no_data"
    NOT_FETCHED = "not_fetched"


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


def welch_t(before: list[float], after: list[float]) -> float | None:
    """İki dönemin ortalama farkının, günlük dalgalanmaya göre büyüklüğü (Welch t istatistiği).

    |t| küçükse fark, günden güne olağan dalgalanma içindedir. Ardışık günler birbirine bağımlı olduğu için
    (otokorelasyon) bu test iyimserdir; bu yüzden tek başına değil, yüzde eşiğiyle BİRLİKTE kullanılır.
    """
    if len(before) < 3 or len(after) < 3:
        return None
    se = math.sqrt(stdev(before) ** 2 / len(before) + stdev(after) ** 2 / len(after))
    diff = mean(after) - mean(before)
    if se == 0:
        return 0.0 if diff == 0 else math.copysign(99.0, diff)
    return round(diff / se, 2)


def _direction(pct: float, t: float | None, thr: float, min_t: float) -> tuple[str, str | None]:
    """Yön ve (varsa) açıklama notu. Belirgin sayılmak için hem yüzde eşiği hem gürültü testi geçilmeli."""
    if abs(pct) < thr:
        return "flat", None
    if min_t > 0 and t is not None and abs(t) < min_t:
        return "flat", (f"%{pct:+.1f} değişim eşiği aştı ama günlük dalgalanma içinde (t={t:.2f} < {min_t:g}); "
                        "belirgin sayılmadı.")
    return ("up" if pct > 0 else "down"), None


def source_gap_days(series_list: list[list[Point]], window: Window, min_series: int = 3) -> set[date]:
    """Bir kaynağın TÜM terimlerinde aynı anda eksik olan günler = kaynağın kendi kesintisi.

    Terime özgü bir boşluk değil, kaynağın o gün veri üretmemesidir (ör. GDELT'te o gün 'norm' da yoktur).
    Bu çıkarım için en az `min_series` başarılı seri gerekir.
    """
    if len(series_list) < min_series:
        return set()
    present = {p.day for pts in series_list for p in pts}
    return {d for d in _days(window.start, window.end) if d not in present}


def normalize_by_norm(series_list: list[list[Point]], min_norm_ratio: float = 0.2, per: float = 10_000
                      ) -> tuple[list[list[Point]], int]:
    """GDELT: eşleşen haber sayısını o gün izlenen toplam habere ('norm') oranlar (10.000 haberde kaç tane).

    Ham sayı, GDELT'in o gün kaç haber izlediğine bağlıdır; izleme hacmi düşünce sayı da düşer (gerçek bir ilgi
    değişimi olmadan). İlk gerçek çalıştırmada (18.11.2026) yakın dönemde 'norm' ortalaması önceki dönemin
    yarısının altına indi. Ayrıca izleme hacmi medyanın `min_norm_ratio` katından düşük olan günler bozuk
    sayılır ve çıkarılır (sıfır sayılmaz, eksik sayılır). Döndürür: (yeni seriler, çıkarılan gün sayısı).
    """
    norms = [p.extra["norm"] for pts in series_list for p in pts if p.extra and p.extra.get("norm")]
    if not norms:
        return series_list, 0
    cutoff = min_norm_ratio * median(norms)
    dropped: set[date] = set()
    out = []
    for pts in series_list:
        new = []
        for p in pts:
            n = (p.extra or {}).get("norm")
            if not n or n < cutoff:
                dropped.add(p.day)
                continue
            new.append(Point(p.day, p.value / n * per, {**(p.extra or {}), "raw": p.value}))
        out.append(new)
    return out, len(dropped)


def analyze_series(points: list[Point], window: Window, *, min_coverage: float = 0.8,
                   flat_threshold_pct: float = 15.0, low_volume: float | None = None,
                   gap_days: set[date] | None = None, min_window_days_ratio: float = 0.5,
                   min_t_stat: float = 0.0) -> dict:
    """gap_days: kaynağın kesinti günleri; kapsama hesabının paydasından çıkarılır (sıfır sayılmaz, yok sayılır)."""
    gap_days = gap_days or set()
    by_day = {p.day: p.value for p in points}
    raw_by_day = {p.day: (p.extra or {}).get("raw", p.value) for p in points}
    all_base = _days(window.baseline_start, window.baseline_end)
    all_rec = _days(window.recent_start, window.recent_end)
    base_days = [d for d in all_base if d not in gap_days]
    rec_days = [d for d in all_rec if d not in gap_days]
    base_vals = [by_day[d] for d in base_days if d in by_day]
    rec_vals = [by_day[d] for d in rec_days if d in by_day]
    out = {
        **window.as_dict(),
        "baseline_days_present": len(base_vals), "recent_days_present": len(rec_vals),
        "source_gap_days": len(gap_days),
        "baseline_coverage": round(len(base_vals) / len(base_days), 3) if base_days else 0.0,
        "recent_coverage": round(len(rec_vals) / len(rec_days), 3) if rec_days else 0.0,
        "baseline_mean": None, "recent_mean": None, "baseline_raw_mean": None, "recent_raw_mean": None,
        "abs_change": None, "pct_change": None,
        "recent_slope_per_day": None, "direction": None, "pop_t_stat": None, "low_volume": None, "notes": [],
    }
    if gap_days:
        out["notes"].append(f"Kaynak kesintisi: {len(gap_days)} gün tüm terimlerde eksik; bu günler sıfır sayılmadı, "
                            "hesaba katılmadı.")
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
    if len(base_vals) < min_window_days_ratio * len(all_base) or len(rec_vals) < min_window_days_ratio * len(all_rec):
        out["result"] = Result.INSUFFICIENT
        out["notes"].append(f"Kaynak kesintisinden sonra pencerelerde çok az gün kaldı (önceki {len(base_vals)}/"
                            f"{len(all_base)}, yakın {len(rec_vals)}/{len(all_rec)}); değişim hesaplanmadı.")
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
        out["pop_t_stat"] = welch_t(base_vals, rec_vals)
        out["direction"], note = _direction(round(pct, 1), out["pop_t_stat"], flat_threshold_pct, min_t_stat)
        if note:
            out["notes"].append(note)
    # Düşük hacim, normalize edilmişse ham sayılar üzerinden değerlendirilir.
    rbm = mean(raw_by_day[d] for d in base_days if d in by_day)
    rrm = mean(raw_by_day[d] for d in rec_days if d in by_day)
    # Ham ortalamalar (normalize edilmemiş birimde) düşük hacim açıklamasında kullanılır.
    out["baseline_raw_mean"], out["recent_raw_mean"] = round(rbm, 3), round(rrm, 3)
    out["low_volume"] = bool(low_volume is not None and rbm < low_volume and rrm < low_volume)
    if out["low_volume"]:
        out["notes"].append(f"Düşük hacim (ortalamalar < {low_volume}); küçük sayılardaki değişim gürültü olabilir.")
    return out


def granularity(points: list[Point]) -> int:
    """Serinin adımı (gün): 1 = günlük, 7 = haftalık (Google Trends uzun dönemde haftalık döndürür)."""
    days = sorted(p.day for p in points)
    if len(days) < 2:
        return 1
    gaps = sorted((b - a).days for a, b in zip(days, days[1:], strict=False))
    return 7 if gaps[len(gaps) // 2] >= 6 else 1


def _expected_points(start: date, end: date, step: int, anchor: date) -> list[date]:
    """Pencereye TAMAMEN düşen beklenen nokta tarihleri (haftalıkta: haftanın 7 günü de pencere içinde)."""
    if step == 1:
        return _days(start, end)
    first = anchor + timedelta(days=((start - anchor).days + step - 1) // step * step)
    out, d = [], first
    while d + timedelta(days=step - 1) <= end:
        out.append(d)
        d += timedelta(days=step)
    return out


def analyze_yoy(points: list[Point], window: Window, *, min_coverage: float = 0.8,
                flat_threshold_pct: float = 15.0, low_volume: float | None = None, min_t_stat: float = 0.0) -> dict:
    """Yakın dönem ↔ geçen yılın aynı dönemi. İki dönem de AYNI seriden (aynı istekten) alınır; Google Trends'te
    ölçekleme istek başına yapıldığı için bu şarttır."""
    out = {"yoy_result": None, "yoy_granularity": None, "yoy_ly_points": 0, "yoy_recent_points": 0,
           "yoy_ly_mean": None, "yoy_recent_mean": None, "yoy_pct_change": None, "yoy_direction": None,
           "yoy_t_stat": None, "yoy_low_volume": None, "yoy_notes": []}
    if not window.has_yoy or not points:
        out["yoy_result"] = Result.NO_DATA
        return out
    step = granularity(points)
    out["yoy_granularity"] = "haftalık" if step == 7 else "günlük"
    by_day = {p.day: p.value for p in points}
    raw = {p.day: (p.extra or {}).get("raw", p.value) for p in points}
    anchor = min(by_day)
    exp_ly = _expected_points(window.ly_start, window.ly_end, step, anchor)
    exp_rec = _expected_points(window.recent_start, window.recent_end, step, anchor)
    ly = [d for d in exp_ly if d in by_day]
    rec = [d for d in exp_rec if d in by_day]
    out["yoy_ly_points"], out["yoy_recent_points"] = len(ly), len(rec)
    if not exp_ly or not exp_rec or len(ly) < max(1, min_coverage * len(exp_ly)) or \
            len(rec) < max(1, min_coverage * len(exp_rec)):
        out["yoy_result"] = Result.INSUFFICIENT
        out["yoy_notes"].append(f"Yıllık karşılaştırma için yeterli nokta yok (geçen yıl {len(ly)}/{len(exp_ly)}, "
                                f"bu yıl {len(rec)}/{len(exp_rec)}).")
        return out
    lm, rm = mean(by_day[d] for d in ly), mean(by_day[d] for d in rec)
    out["yoy_ly_mean"], out["yoy_recent_mean"] = round(lm, 3), round(rm, 3)
    out["yoy_low_volume"] = bool(low_volume is not None and mean(raw[d] for d in ly) < low_volume
                                 and mean(raw[d] for d in rec) < low_volume)
    if lm == 0:
        out["yoy_result"] = Result.BASELINE_ZERO
        return out
    pct = (rm - lm) / lm * 100
    out["yoy_pct_change"] = round(pct, 1)
    if step == 1:
        out["yoy_t_stat"] = welch_t([by_day[d] for d in ly], [by_day[d] for d in rec])
        out["yoy_direction"], note = _direction(round(pct, 1), out["yoy_t_stat"], flat_threshold_pct, min_t_stat)
        if note:
            out["yoy_notes"].append("Yıllık: " + note)
    else:  # haftalık seride 3-4 nokta var; gürültü testi güvenilir olmaz, yalnız yüzde eşiği uygulanır
        out["yoy_direction"], _ = _direction(round(pct, 1), None, flat_threshold_pct, 0)
    out["yoy_result"] = Result.COMPUTED
    return out


def classify_yoy(y: dict) -> str:
    return classify({"result": y["yoy_result"], "low_volume": y.get("yoy_low_volume"),
                     "direction": y.get("yoy_direction")})


def _prepare_series(manifest: dict, series: dict, a: dict, kind: str, window: Window
                    ) -> tuple[dict, dict, dict, dict]:
    """Seri ön işleme (kaynak bazında): Google 0 → eksik, GDELT oranlama, kaynak kesinti günleri."""
    nb = a.get("normalize_by_norm") or {}
    norm_sources = {k: 10_000 for k in nb} if isinstance(nb, list) else dict(nb)
    zero_missing = set(a.get("zero_is_missing") or [])
    out = dict(series)
    gaps: dict[str, set[date]] = {}
    normalized: dict[str, int] = {}
    zeros: dict[tuple[str, str], int] = {}
    recs = [r for r in manifest["fetches"] if r.get("series", "main") == kind]
    for src in {r["source"] for r in recs}:
        ok_ids = [r["term_id"] for r in recs if r["source"] == src and r["status"] == FetchStatus.OK]
        if src in zero_missing:
            for t in ok_ids:
                pts = out.get((src, t, kind), [])
                kept = [p for p in pts if p.value != 0]
                zeros[(src, t)] = len(pts) - len(kept)
                out[(src, t, kind)] = kept
        if src in norm_sources and ok_ids:
            series_list = [out.get((src, t, kind), []) for t in ok_ids]
            if any(p.extra and p.extra.get("norm") for pts in series_list for p in pts):
                new, dropped = normalize_by_norm(series_list, float(a.get("min_norm_ratio", 0.2)),
                                                 per=float(norm_sources[src]))
                out.update({(src, t, kind): pts for t, pts in zip(ok_ids, new, strict=True)})
                normalized[src] = (dropped, float(norm_sources[src]))
        if kind == "main":
            gaps[src] = source_gap_days([out.get((src, t, kind), []) for t in ok_ids], window)
    return out, gaps, normalized, zeros


def analyze_run(manifest: dict, series: dict, cfg: dict, window: Window) -> list[dict]:
    a = cfg.get("analysis") or {}
    low = a.get("low_volume") or {}
    min_cov = float(a.get("min_coverage", 0.8))
    thr = float(a.get("flat_threshold_pct", 15))
    min_t = float(a.get("min_t_stat", 0))
    series, gaps, normalized, zeros = _prepare_series(manifest, series, a, "main", window)
    series, _, yoy_normalized, yoy_zeros = _prepare_series(manifest, series, a, "yoy", window)
    yoy_recs = {(r["source"], r["term_id"]): r for r in manifest["fetches"] if r.get("series") == "yoy"}

    rows = []
    for rec in manifest["fetches"]:
        if rec.get("series", "main") != "main":
            continue
        src, tid = rec["source"], rec["term_id"]
        base = {k: rec.get(k) for k in ("source", "metric", "term_id", "label", "category", "query")}
        base["fetch_status"] = rec["status"]
        if rec["status"] != FetchStatus.OK:
            stats = {**window.as_dict(), "result": Result.NO_DATA,
                     "notes": [f"Veri alınamadı ({rec['status']}): {rec.get('error') or '-'}"]}
        else:
            stats = analyze_series(series.get((src, tid, "main"), []), window, min_coverage=min_cov,
                                   flat_threshold_pct=thr, low_volume=low.get(src), gap_days=gaps.get(src),
                                   min_window_days_ratio=float(a.get("min_window_days_ratio", 0.5)),
                                   min_t_stat=min_t)
            if zeros.get((src, tid)):
                stats["notes"].insert(0, f"{zeros[(src, tid)]} gün 0 değeri (kaynağa göre 'yeterli veri yok') "
                                         "eksik sayıldı, sıfır olarak hesaba katılmadı.")
            if src in normalized:
                dropped, per = normalized[src]
                unit = f"{per:,.0f}".replace(",", ".")
                stats["metric"] = f"per_{int(per)}_of_source_total"
                stats["notes"].insert(0, f"Değerler kaynağın o günkü toplamına oranlandı ({unit} birimde) — kaynağın "
                                         "genel hacmindeki değişim terim değişimi sanılmasın diye"
                                         + (f"; toplamı çok düşük {dropped} gün bozuk sayılıp çıkarıldı."
                                            if dropped else "."))

        # Yıllık karşılaştırma
        yrec = yoy_recs.get((src, tid))
        if yrec is None:
            y = {"yoy_result": Result.NOT_FETCHED, "yoy_notes": ["Yıllık seri çekilmedi (eski kayıt ya da kapalı)."]}
        elif yrec["status"] != FetchStatus.OK:
            y = {"yoy_result": Result.NO_DATA,
                 "yoy_notes": [f"Yıllık seri alınamadı ({yrec['status']}): {yrec.get('error') or '-'}"]}
        else:
            y = analyze_yoy(series.get((src, tid, "yoy"), []), window, min_coverage=min_cov,
                            flat_threshold_pct=thr, low_volume=low.get(src), min_t_stat=min_t)
            if src in yoy_normalized:
                y["yoy_notes"].insert(0, "Yıllık seri de kaynağın günlük toplamına oranlandı (kaynağın genel hacmi "
                                         "yıldan yıla değişebilir).")
            if yoy_zeros.get((src, tid)):
                y["yoy_notes"].insert(0, f"Yıllık seride {yoy_zeros[(src, tid)]} nokta 0 (yeterli veri yok), "
                                         "eksik sayıldı.")
        notes = stats.pop("notes", []) + y.pop("yoy_notes", [])
        rows.append({**base, **stats, **y, "notes": notes})

    for r in rows:
        r["signal"] = classify(r)
        r["yoy_signal"] = classify_yoy(r) if r.get("yoy_result") not in (None, Result.NOT_FETCHED) else None
        r["trend_label"] = trend_label(r["signal"], r["yoy_signal"])

    # Sıralama yalnızca aynı kaynak içinde ve hesaplanabilen yüzde değişimlere göre yapılır.
    for src in {r["source"] for r in rows}:
        ranked = sorted([r for r in rows if r["source"] == src and r.get("pct_change") is not None],
                        key=lambda r: r["pct_change"], reverse=True)
        for i, r in enumerate(ranked, 1):
            r["rank_in_source"] = i
    return rows


def flatten_for_csv(rows: list[dict]) -> list[dict]:
    return [{**r, "notes": " | ".join(r.get("notes") or [])} for r in rows]
