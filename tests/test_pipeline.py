from __future__ import annotations

from datetime import date

import yaml

from conftest import FakeResponse, FakeSession, gdelt_body, wiki_body
from trendpipe import cli
from trendpipe.analysis import Result, analyze_series
from trendpipe.config import compute_window, parse_terms
from trendpipe.llm import check_numbers
from trendpipe.models import FetchStatus, Point
from trendpipe.sources.gdelt import GdeltSource, parse_timeline
from trendpipe.sources.wikimedia import WikimediaSource

END = date(2026, 11, 15)


def window(cfg):
    return compute_window(cfg, end=END)


# ---------- pencere ----------

def test_window_is_contiguous(cfg):
    w = window(cfg)
    assert w.recent_end == END
    assert (w.recent_end - w.recent_start).days == 6
    assert (w.recent_start - w.baseline_end).days == 1
    assert (w.baseline_end - w.baseline_start).days == 6


# ---------- analiz ----------

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


# ---------- kaynak ayrıştırma ----------

def test_wikimedia_404_is_not_found(cfg):
    w = window(cfg)
    src = WikimediaSource(cfg["sources"]["wikimedia"], session=FakeSession({}))
    res = src.fetch("c", "Yok_Makale", w.start, w.end)
    assert res.status == FetchStatus.NOT_FOUND
    assert res.points == []


def test_wikimedia_connection_error(cfg):
    import requests
    w = window(cfg)
    src = WikimediaSource(cfg["sources"]["wikimedia"],
                          session=FakeSession({"Yukselen": requests.ConnectionError("ağ yok")}))
    res = src.fetch("a", "Yukselen", w.start, w.end)
    assert res.status == FetchStatus.ERROR and "ağ yok" in res.error


def test_wikimedia_url_and_user_agent(cfg):
    w = window(cfg)
    sess = FakeSession({"Kot_pantolon": FakeResponse(200, wiki_body(w.start, [5] * 14))})
    src = WikimediaSource(cfg["sources"]["wikimedia"], session=sess, user_agent="UA/1")
    res = src.fetch("k", "Kot pantolon", w.start, w.end)
    assert res.status == FetchStatus.OK and len(res.points) == 14
    url, _, headers = sess.calls[0]
    assert "/tr.wikipedia/all-access/user/Kot_pantolon/daily/" in url
    assert headers["User-Agent"] == "UA/1"


def test_gdelt_text_error_and_empty(cfg):
    w = window(cfg)
    src = GdeltSource(cfg["sources"]["gdelt"], session=FakeSession({
        "short": FakeResponse(200, "Your search contained a keyword that was too short."),
        "nothing": FakeResponse(200, "{}"),
    }))
    assert src.fetch("x", "short", w.start, w.end).status == FetchStatus.ERROR
    assert src.fetch("y", "nothing", w.start, w.end).status == FetchStatus.EMPTY


def test_gdelt_query_filters(cfg):
    p = GdeltSource(cfg["sources"]["gdelt"]).build_params('"trench coat"', date(2026, 1, 1), date(2026, 1, 31))
    assert p["query"] == '"trench coat" sourcecountry:turkey sourcelang:turkish'
    assert p["startdatetime"] == "20260101000000" and p["enddatetime"] == "20260131235959"


def test_gdelt_hourly_aggregated_to_daily():
    payload = {"timeline": [{"series": "Article Count", "data": [
        {"date": "20261101T000000Z", "value": 2, "norm": 10},
        {"date": "20261101T120000Z", "value": 3, "norm": 15},
        {"date": "20261102T000000Z", "value": 1, "norm": 9}]}]}
    pts = parse_timeline(payload)
    assert [(p.day.day, p.value, p.extra["norm"]) for p in pts] == [(1, 5.0, 25.0), (2, 1.0, 9.0)]


# ---------- terimler ----------

def test_terms_filter_and_extra(cfg):
    ts = parse_terms(cfg, only_ids=["a"], extra=["Deri Ceket"])
    assert [t.id for t in ts] == ["a", "deri_ceket"]
    assert ts[1].queries["gdelt"] == "Deri Ceket"


# ---------- sayı kontrolü ----------

def test_check_numbers():
    rows = [{"pct_change": 42.3, "baseline_coverage": 1.0, "recent_coverage": 1.0}]
    assert check_numbers("Trençkot %42,3 arttı.", rows)["ok"]
    bad = check_numbers("Satışlar %80 artacak.", rows)
    assert not bad["ok"] and bad["unmatched_percentages"] == [80.0]


# ---------- uçtan uca (model hariç) ----------

def test_end_to_end_fetch_and_analyze(cfg, tmp_path, monkeypatch, capsys):
    w = window(cfg)
    sess = FakeSession({
        "Yukselen": FakeResponse(200, wiki_body(w.start, [100] * 7 + [150] * 7)),
        "Eksik": FakeResponse(200, wiki_body(w.start, [50] * 7 + [None] * 5 + [60, 60])),
        "rising": FakeResponse(200, gdelt_body(w.start, [2] * 7 + [4] * 7)),
        "nothing": FakeResponse(200, "{}"),
    })
    import trendpipe.sources as srcmod
    orig = srcmod.build_sources
    monkeypatch.setattr(cli, "build_sources", lambda c, only=None, user_agent="": orig(c, only, user_agent, sess))
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    rc = cli.main(["all", "--config", str(cfg_path), "--out-dir", str(tmp_path / "runs"),
                   "--end", END.isoformat(), "--skip-llm"])
    assert rc == 0
    run = next((tmp_path / "runs").iterdir())
    import json
    m = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    st = {(f["source"], f["term_id"]): f["status"] for f in m["fetches"]}
    assert st[("wikimedia", "a")] == "ok"
    assert st[("wikimedia", "c")] == "not_found"
    assert st[("gdelt", "b")] == "skipped"
    assert st[("gdelt", "c")] == "empty"
    assert all("fetched_at" in f and f["start"] and f["end"] for f in m["fetches"])
    assert (run / "raw" / "wikimedia__a.json").exists()

    rows = {(r["source"], r["term_id"]): r for r in
            json.loads((run / "analysis.json").read_text(encoding="utf-8"))["rows"]}
    assert rows[("wikimedia", "a")]["pct_change"] == 50.0
    assert rows[("gdelt", "a")]["pct_change"] == 100.0
    assert rows[("wikimedia", "b")]["result"] == Result.INSUFFICIENT
    assert rows[("wikimedia", "c")]["result"] == Result.NO_DATA

    # kayıtlı veriden bağlantısız tekrar analiz
    assert cli.main(["analyze", "--run", str(run)]) == 0
