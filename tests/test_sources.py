"""Kaynak adaptörleri (ağ yok; sahte oturum / sahte pytrends): ayrıştırma, hata durumları, tekrar deneme."""

from __future__ import annotations

from datetime import date

from conftest import FakeResponse, FakeSession, gdelt_body, wiki_body, window

from trendpipe.models import FetchStatus
from trendpipe.sources.gdelt import GdeltSource, parse_timeline
from trendpipe.sources.wikimedia import WikimediaSource


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



class _SeqSession:
    def __init__(self, seq):
        self.seq = list(seq)
        self.calls = 0

    def get(self, *a, **k):
        self.calls += 1
        item = self.seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item



def test_gdelt_retries_on_timeout_and_429(cfg):
    import requests
    w = window(cfg)
    sess = _SeqSession([requests.ReadTimeout("yavaş"), FakeResponse(429, "Please limit requests"),
                        FakeResponse(200, gdelt_body(w.start, [1] * 14))])
    src = GdeltSource({"max_retries": 3, "retry_backoff_sec": 0}, session=sess)
    res = src.fetch("t", "coat", w.start, w.end)
    assert res.status == FetchStatus.OK and res.attempts == 3 and sess.calls == 3



def test_gdelt_gives_up_after_retries(cfg):
    w = window(cfg)
    sess = _SeqSession([FakeResponse(429, "Please limit requests")] * 3)
    res = GdeltSource({"max_retries": 2, "retry_backoff_sec": 0}, session=sess).fetch("t", "coat", w.start, w.end)
    assert res.status == FetchStatus.ERROR and "429" in res.error and res.attempts == 3



def test_two_wikimedia_instances():
    from trendpipe.sources import build_sources
    cfg2 = {"sources": {"wikimedia": {"type": "wikimedia", "enabled": True, "project": "tr.wikipedia"},
                        "wikimedia_en": {"type": "wikimedia", "enabled": True, "project": "en.wikipedia"},
                        "gdelt": {"enabled": False}}}
    srcs = build_sources(cfg2)
    assert [s.name for s in srcs] == ["wikimedia", "wikimedia_en"]
    assert "/en.wikipedia/" in srcs[1].build_url("Trench coat", date(2026, 1, 1), date(2026, 1, 2))
    assert "İngilizce" in srcs[1].description



def _fake_pytrends(monkeypatch, df=None, exc=None):
    import sys
    import types
    mod = types.ModuleType("pytrends.request")

    class TrendReq:
        def __init__(self, **kw):
            pass

        def build_payload(self, kw, timeframe, geo):
            self.kw = kw

        def interest_over_time(self):
            if exc:
                raise exc
            return df
    mod.TrendReq = TrendReq
    monkeypatch.setitem(sys.modules, "pytrends", types.ModuleType("pytrends"))
    monkeypatch.setitem(sys.modules, "pytrends.request", mod)



def test_google_trends_parses_and_drops_partial(monkeypatch, cfg):
    import pandas as pd

    from trendpipe.sources.google_trends import GoogleTrendsSource
    w = window(cfg)
    idx = pd.date_range(w.start, w.end, freq="D")
    df = pd.DataFrame({"hırka": range(len(idx)), "isPartial": [False] * (len(idx) - 1) + [True]}, index=idx)
    _fake_pytrends(monkeypatch, df=df)
    res = GoogleTrendsSource({"geo": "TR"}).fetch("h", "hırka", w.start, w.end)
    assert res.status == FetchStatus.OK
    assert len(res.points) == len(idx) - 1          # tamamlanmamış son gün analize girmez
    assert '"isPartial": true' in res.raw_body       # ama ham kayıtta durur



def test_google_trends_429_triggers_breaker_code(monkeypatch, cfg):
    from trendpipe.sources.google_trends import GoogleTrendsSource
    w = window(cfg)
    _fake_pytrends(monkeypatch, exc=Exception("The request failed: Google returned a response with code 429"))
    res = GoogleTrendsSource({}).fetch("h", "hırka", w.start, w.end)
    assert res.status == FetchStatus.ERROR and res.http_status == 429



def test_default_config_sources():
    from pathlib import Path

    from trendpipe.config import load_config
    from trendpipe.sources import build_sources
    cfg2 = load_config(Path(__file__).resolve().parents[1] / "config/config.yaml")
    assert [s.name for s in build_sources(cfg2)] == ["google_trends", "wikimedia", "wikimedia_en"]



def test_google_trends_retries_after_429(monkeypatch, cfg):
    import sys
    import types

    import pandas as pd

    from trendpipe.sources.google_trends import GoogleTrendsSource
    w = window(cfg)
    idx = pd.date_range(w.start, w.end, freq="D")
    calls = {"n": 0}

    class TrendReq:
        def __init__(self, **kw):
            pass

        def build_payload(self, kw, timeframe, geo):
            pass

        def interest_over_time(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("TooManyRequestsError: Google returned a response with code 429")
            return pd.DataFrame({"x": [50] * len(idx), "isPartial": [False] * len(idx)}, index=idx)
    mod = types.ModuleType("pytrends.request")
    mod.TrendReq = TrendReq
    monkeypatch.setitem(sys.modules, "pytrends", types.ModuleType("pytrends"))
    monkeypatch.setitem(sys.modules, "pytrends.request", mod)
    res = GoogleTrendsSource({"max_retries": 2, "retry_backoff_sec": 0}).fetch("t", "x", w.start, w.end)
    assert res.status == FetchStatus.OK and res.attempts == 2 and res.http_status == 200

