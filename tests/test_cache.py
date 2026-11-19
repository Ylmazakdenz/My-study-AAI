"""İstek önbelleği: tekrar istek yok, süre, hatalar saklanmaz, --refresh, ayar değişikliği, şeffaflık."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import yaml
from conftest import FakeResponse, FakeSession, wiki_body

from trendpipe import cli
from trendpipe.cache import FetchCache, cache_key
from trendpipe.config import compute_window
from trendpipe.models import FetchResult, FetchStatus, Point

END = date(2026, 11, 15)


def _setup(cfg, tmp_path, monkeypatch, sess, ttl=24):
    cfg["cache"] = {"enabled": True, "ttl_hours": ttl, "dir": str(tmp_path / "cache")}
    cfg["window"]["yoy"] = False
    cfg["sources"] = {"wikimedia": {"enabled": True, "project": "tr.wikipedia", "normalize_by_project": False}}
    cfg["terms"] = [{"id": "a", "label": "A", "queries": {"wikimedia": "Makale_A"}},
                    {"id": "b", "label": "B", "queries": {"wikimedia": "Makale_B"}}]
    cfg["analysis"]["low_volume"] = {}
    import trendpipe.sources as srcmod
    orig = srcmod.build_sources
    monkeypatch.setattr(cli, "build_sources", lambda c, only=None, user_agent="": orig(c, only, user_agent, sess))
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return p


def _run(p, tmp_path, *extra):
    assert cli.main(["fetch", "--config", str(p), "--out-dir", str(tmp_path / "r"), "--end", END.isoformat(),
                     *extra]) == 0
    run = sorted((tmp_path / "r").iterdir())[-1]
    return run, json.loads((run / "manifest.json").read_text(encoding="utf-8"))


def test_second_run_uses_cache_and_is_self_contained(cfg, tmp_path, monkeypatch):
    w = compute_window(cfg, end=END)
    body = FakeResponse(200, wiki_body(w.start, [10] * 14))
    sess = FakeSession({"Makale_A": body, "Makale_B": body})
    p = _setup(cfg, tmp_path, monkeypatch, sess)
    run1, m1 = _run(p, tmp_path)
    assert len(sess.calls) == 2 and not any(f["from_cache"] for f in m1["fetches"])
    import time
    time.sleep(1.1)                                                      # farklı çalıştırma klasörü adı
    run2, m2 = _run(p, tmp_path)
    assert len(sess.calls) == 2                                          # kaynağa yeni istek gitmedi
    assert all(f["from_cache"] and f["cache_origin_run"] == run1.name for f in m2["fetches"])
    assert m2["fetches"][0]["fetched_at"] == m1["fetches"][0]["fetched_at"]   # ilk çekilme zamanı korunur
    assert (run2 / "raw" / "wikimedia__a.json").exists()                 # ham yanıt yeni klasörde de var
    assert (run2 / "processed" / "timeseries.csv").read_text(encoding="utf-8").count("\n") == 29


def test_errors_are_not_cached(cfg, tmp_path, monkeypatch):
    w = compute_window(cfg, end=END)
    sess = FakeSession({"Makale_A": FakeResponse(200, wiki_body(w.start, [10] * 14)),
                        "Makale_B": FakeResponse(429, "Too many requests")})
    p = _setup(cfg, tmp_path, monkeypatch, sess)
    _run(p, tmp_path)
    import time
    time.sleep(1.1)
    _, m2 = _run(p, tmp_path)
    st = {f["term_id"]: (f["status"], f["from_cache"]) for f in m2["fetches"]}
    assert st["a"] == ("ok", True) and st["b"] == ("error", False)      # hatalı olan yeniden denendi
    assert sum("Makale_B" in c[0] for c in sess.calls) == 2


def test_refresh_bypasses_cache(cfg, tmp_path, monkeypatch):
    w = compute_window(cfg, end=END)
    body = FakeResponse(200, wiki_body(w.start, [10] * 14))
    sess = FakeSession({"Makale_A": body, "Makale_B": body})
    p = _setup(cfg, tmp_path, monkeypatch, sess)
    _run(p, tmp_path)
    import time
    time.sleep(1.1)
    _, m2 = _run(p, tmp_path, "--refresh")
    assert len(sess.calls) == 4 and not any(f["from_cache"] for f in m2["fetches"])
    assert m2["cache"]["refresh"] is True


def _res():
    d = date(2026, 1, 1)
    return FetchResult(source="s", term_id="t", query="q", start=d, end=d, status=FetchStatus.OK, metric="m",
                       points=[Point(d, 5.0, {"norm": 10})], raw_body="{}")


def test_ttl_expiry(tmp_path):
    c = FetchCache(tmp_path, ttl_hours=24)
    c.put("k", _res(), "run1")
    later = datetime.now(timezone.utc) + timedelta(hours=25)
    assert c.get("k") is not None and c.get("k", now=later) is None
    got = c.get("k")
    assert got.points[0].extra == {"norm": 10} and got.attempts == 0


def test_key_depends_on_data_settings_and_dates():
    d1, d2 = date(2026, 1, 1), date(2026, 1, 28)
    base = cache_key("google_trends", {"geo": "TR", "request_interval_sec": 10}, "kazak", d1, d2)
    assert base == cache_key("google_trends", {"geo": "TR", "request_interval_sec": 30}, "kazak", d1, d2)
    assert base != cache_key("google_trends", {"geo": "DE"}, "kazak", d1, d2)          # bölge değişti
    assert base != cache_key("google_trends", {"geo": "TR"}, "kazak", d1, d2 + timedelta(days=1))  # ertesi gün


def test_disabled_cache_never_stores(tmp_path):
    c = FetchCache(tmp_path, ttl_hours=24, enabled=False)
    c.put("k", _res(), "r")
    assert c.get("k") is None and not list(tmp_path.iterdir())
