"""Yıllık karşılaştırma (mevsimsellik) testleri."""

from __future__ import annotations

import json
from datetime import date, timedelta

import yaml
from conftest import FakeResponse, FakeSession, wiki_body

from trendpipe import cli
from trendpipe.analysis import Result, Signal, Trend, analyze_yoy, granularity, trend_label
from trendpipe.config import compute_window
from trendpipe.models import Point

END = date(2026, 11, 15)


def _w(cfg):
    return compute_window(cfg, end=END)


def test_window_has_last_year_aligned_by_weekday(cfg):
    w = _w(cfg)
    assert w.has_yoy
    assert (w.recent_start - w.ly_start).days == 364
    assert w.ly_start.weekday() == w.recent_start.weekday()          # 52 hafta: haftanın günü hizalı


def test_granularity_detection():
    d = date(2026, 1, 4)
    assert granularity([Point(d + timedelta(days=i), 1) for i in range(10)]) == 1
    assert granularity([Point(d + timedelta(days=7 * i), 1) for i in range(10)]) == 7


def test_yoy_daily(cfg):
    w = _w(cfg)
    pts = [Point(w.ly_start + timedelta(days=i), 100) for i in range(7)] + \
          [Point(w.recent_start + timedelta(days=i), 150) for i in range(7)]
    y = analyze_yoy(pts, w)
    assert y["yoy_result"] == Result.COMPUTED and y["yoy_pct_change"] == 50.0 and y["yoy_direction"] == "up"
    assert y["yoy_granularity"] == "günlük"


def test_yoy_weekly_counts_only_full_weeks():
    cfg = {"window": {"recent_days": 28, "baseline_days": 28, "end_offset_days": 0}}
    w = compute_window(cfg, end=date(2026, 11, 17))                   # yakın dönem 21.10–17.11 (salı–salı)
    sunday = w.ly_start - timedelta(days=(w.ly_start.weekday() + 1) % 7)   # Google haftası pazar başlar
    pts, d = [], sunday
    while d <= w.recent_end:
        pts.append(Point(d, 40 if d < w.recent_start - timedelta(days=200) else 60))
        d += timedelta(days=7)
    y = analyze_yoy(pts, w)
    assert y["yoy_granularity"] == "haftalık"
    assert y["yoy_ly_points"] == y["yoy_recent_points"] == 3          # 28 günlük pencereye 3 tam hafta sığar
    assert y["yoy_pct_change"] == 50.0


def test_yoy_insufficient_when_last_year_missing(cfg):
    w = _w(cfg)
    pts = [Point(w.recent_start + timedelta(days=i), 150) for i in range(7)]
    assert analyze_yoy(pts, w)["yoy_result"] == Result.INSUFFICIENT


def test_trend_labels():
    assert trend_label(Signal.STRONG_UP, Signal.STRONG_UP) == Trend.ABOVE_SEASON_UP
    assert trend_label(Signal.STRONG_UP, Signal.FLAT) == Trend.SEASONAL_UP
    assert trend_label(Signal.STRONG_UP, None) == Trend.UP_YOY_UNKNOWN
    assert trend_label(Signal.STRONG_DOWN, Signal.FLAT) == Trend.SEASONAL_DOWN
    assert trend_label(Signal.FLAT, Signal.STRONG_UP) == Trend.YEARLY_UP
    assert trend_label(Signal.FLAT, Signal.WEAK) == Trend.NO_CHANGE
    assert trend_label(Signal.WEAK, Signal.STRONG_UP) == Trend.WEAK


def test_end_to_end_with_yoy(cfg, tmp_path, monkeypatch):
    """Ana seri + yıllık seri ayrı isteklerle çekilir, ayrı ham dosyalara yazılır ve birlikte analiz edilir."""
    w = _w(cfg)
    ly_body = wiki_body(w.ly_start, [100] * ((w.end - w.ly_start).days + 1))
    # yıllık seri: geçen yıl 100, bu yıl yakın dönem 200 -> yıllık +%100
    for item in ly_body["items"]:
        if item["timestamp"][:8] >= w.recent_start.strftime("%Y%m%d"):
            item["views"] = 200
    sess = FakeSession({
        f"Yukselen/daily/{w.start:%Y%m%d}": FakeResponse(200, wiki_body(w.start, [100] * 7 + [200] * 7)),
        f"Yukselen/daily/{w.ly_start:%Y%m%d}": FakeResponse(200, ly_body),
    })
    cfg["sources"] = {"wikimedia": {"enabled": True, "project": "tr.wikipedia"}}
    cfg["terms"] = [{"id": "a", "label": "Yükselen", "queries": {"wikimedia": "Yukselen"}}]
    cfg["analysis"]["low_volume"] = {}
    import trendpipe.sources as srcmod
    orig = srcmod.build_sources
    monkeypatch.setattr(cli, "build_sources", lambda c, only=None, user_agent="": orig(c, only, user_agent, sess))
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    assert cli.main(["all", "--config", str(p), "--out-dir", str(tmp_path / "r"), "--end", END.isoformat(),
                     "--skip-llm"]) == 0
    run = next((tmp_path / "r").iterdir())
    assert (run / "raw" / "wikimedia__a.json").exists() and (run / "raw" / "wikimedia__a__yoy.json").exists()
    assert (run / "run.log").read_text(encoding="utf-8").count("wikimedia/a/") == 2
    row = json.loads((run / "analysis.json").read_text(encoding="utf-8"))["rows"][0]
    assert row["pct_change"] == 100.0 and row["yoy_pct_change"] == 100.0
    assert row["trend_label"] == Trend.ABOVE_SEASON_UP
