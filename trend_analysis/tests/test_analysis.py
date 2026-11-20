"""Analiz: pencereler, dönemsel değişim, eksik veri kuralları, kaynak kesintisi, oranlama."""

from __future__ import annotations

from datetime import date

from conftest import END, window

from trendpipe.analysis import Result, analyze_series
from trendpipe.models import Point


def test_window_is_contiguous(cfg):
    w = window(cfg)
    assert w.recent_end == END
    assert (w.recent_end - w.recent_start).days == 6
    assert (w.recent_start - w.baseline_end).days == 1
    assert (w.baseline_end - w.baseline_start).days == 6



def _pts(start, values):
    from datetime import timedelta
    return [Point(start + timedelta(days=i), v) for i, v in enumerate(values) if v is not None]



def test_pct_change_up(cfg):
    w = window(cfg)
    r = analyze_series(_pts(w.start, [10] * 7 + [20] * 7), w)
    assert r["result"] == Result.COMPUTED
    assert r["pct_change"] == 100.0
    assert r["direction"] == "up"



def test_missing_days_not_treated_as_zero(cfg):
    w = window(cfg)
    # yakın dönemde 7 günün 3'ü eksik -> kapsama %57 < %80 -> hesaplanmaz
    r = analyze_series(_pts(w.start, [10] * 7 + [20, None, None, None, 20, 20, 20]), w, min_coverage=0.8)
    assert r["result"] == Result.INSUFFICIENT
    assert r["pct_change"] is None



def test_baseline_zero(cfg):
    w = window(cfg)
    r = analyze_series(_pts(w.start, [0] * 7 + [3] * 7), w)
    assert r["result"] == Result.BASELINE_ZERO
    assert r["pct_change"] is None



def test_low_volume_note(cfg):
    w = window(cfg)
    r = analyze_series(_pts(w.start, [1] * 7 + [2] * 7), w, low_volume=5)
    assert any("Düşük hacim" in n for n in r["notes"])



def test_source_wide_gap_excluded(cfg):
    from datetime import timedelta

    from trendpipe.analysis import analyze_series, source_gap_days
    w = window(cfg)
    missing = {w.start + timedelta(days=i) for i in (1, 2, 9)}            # tüm terimlerde aynı günler eksik
    series = [[Point(w.start + timedelta(days=i), v) for i in range(14)
               if w.start + timedelta(days=i) not in missing] for v in (1, 2, 3)]
    gaps = source_gap_days(series, w)
    assert gaps == missing
    r = analyze_series(series[0], w, gap_days=gaps)
    assert r["result"] == Result.COMPUTED and r["baseline_coverage"] == 1.0 and r["source_gap_days"] == 3
    assert analyze_series(series[0], w)["result"] == Result.INSUFFICIENT   # kesinti bilinmezse hesaplanmaz



def test_gdelt_normalized_by_monitored_volume():
    from trendpipe.analysis import normalize_by_norm
    d = date(2026, 1, 1)
    from datetime import timedelta
    pts = [Point(d + timedelta(days=i), 10, {"norm": 100_000}) for i in range(5)] + \
          [Point(d + timedelta(days=5), 5, {"norm": 50_000}), Point(d + timedelta(days=6), 1, {"norm": 100})]
    (out,), dropped = normalize_by_norm([pts], min_norm_ratio=0.2)
    assert dropped == 1                                   # izleme hacmi çok düşük gün çıkarıldı
    assert [round(p.value, 3) for p in out] == [1.0] * 6  # ham sayı yarıya inse de oran aynı
    assert out[-1].extra["raw"] == 5



def test_google_trends_zero_is_missing(cfg):
    """Google Trends'te 0 = yeterli veri yok -> eksik gün (19.11.2026 'kaşe kaban' örneği: 2 gün 0)."""
    from datetime import timedelta

    from trendpipe.analysis import analyze_run
    w = window(cfg)
    vals = [0, 30, 0, 30, 30, 30, 30] + [60] * 7                         # pencereler 7+7 gün
    pts = [Point(w.start + timedelta(days=i), v) for i, v in enumerate(vals)]
    manifest = {"fetches": [{"source": "google_trends", "term_id": "p", "label": "Palto", "status": "ok"}]}
    a = {"analysis": {"min_coverage": 0.7, "zero_is_missing": ["google_trends"]}}
    r = analyze_run(manifest, {("google_trends", "p", "main"): pts}, a, w)[0]
    assert r["baseline_mean"] == 30.0 and r["pct_change"] == 100.0       # sıfırlar ortalamayı düşürmedi
    assert any("eksik sayıldı" in n for n in r["notes"])
    r0 = analyze_run(manifest, {("google_trends", "p", "main"): pts}, {"analysis": {"min_coverage": 0.7}}, w)[0]
    assert r0["pct_change"] > 100                                         # kural kapalıyken yapay yüksek

