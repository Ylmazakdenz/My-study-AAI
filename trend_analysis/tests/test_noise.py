"""Gürültü testi: yüzde eşiğini aşan ama günlük dalgalanma içinde kalan değişim 'belirgin' sayılmamalı."""

from __future__ import annotations

from datetime import date, timedelta

from trendpipe.analysis import analyze_series, analyze_yoy, welch_t
from trendpipe.config import compute_window
from trendpipe.models import Point

END = date(2026, 11, 15)


def _w():
    return compute_window({"window": {"recent_days": 14, "baseline_days": 14}}, end=END)


def _pts(start, values):
    return [Point(start + timedelta(days=i), v) for i, v in enumerate(values)]


def test_welch_t_basic():
    assert welch_t([10, 10, 10], [10, 10, 10]) == 0.0
    assert welch_t([10, 11, 9, 10], [20, 21, 19, 20]) > 10
    assert welch_t([1, 2], [3, 4, 5]) is None                    # en az 3 nokta


def test_noisy_change_is_not_strong():
    w = _w()
    noisy_before = [5, 40, 8, 35, 6, 42, 9, 38, 7, 41, 6, 37, 8, 40]   # ort ~23, çok dalgalı
    noisy_after = [x * 1.2 for x in noisy_before]                      # +%20 ama dalgalanma içinde
    r = analyze_series(_pts(w.start, noisy_before + noisy_after), w, min_t_stat=2.0)
    assert r["pct_change"] == 20.0 and abs(r["pop_t_stat"]) < 2
    assert r["direction"] == "flat" and any("günlük dalgalanma içinde" in n for n in r["notes"])


def test_clear_change_is_strong():
    w = _w()
    before = [100 + (i % 3) for i in range(14)]
    after = [130 + (i % 3) for i in range(14)]
    r = analyze_series(_pts(w.start, before + after), w, min_t_stat=2.0)
    assert r["direction"] == "up" and r["pop_t_stat"] > 2 and not r["notes"]


def test_noise_check_can_be_disabled():
    w = _w()
    noisy_before = [5, 40, 8, 35, 6, 42, 9, 38, 7, 41, 6, 37, 8, 40]
    r = analyze_series(_pts(w.start, noisy_before + [x * 1.2 for x in noisy_before]), w, min_t_stat=0)
    assert r["direction"] == "up"


def test_weekly_yoy_uses_threshold_only():
    """Haftalık yıllık seride 3-4 nokta olduğu için t testi uygulanmaz (yanlışlıkla 'belirsiz' denmesin)."""
    w = compute_window({"window": {"recent_days": 28, "baseline_days": 28, "end_offset_days": 0}},
                       end=date(2026, 11, 17))
    sunday = w.ly_start - timedelta(days=(w.ly_start.weekday() + 1) % 7)
    pts, d, i = [], sunday, 0
    while d <= w.recent_end:
        pts.append(Point(d, (40 if d < w.recent_start - timedelta(days=200) else 60) + (i % 2) * 15))
        d += timedelta(days=7)
        i += 1
    y = analyze_yoy(pts, w, min_t_stat=2.0)
    assert y["yoy_granularity"] == "haftalık" and y["yoy_t_stat"] is None and y["yoy_direction"] == "up"
