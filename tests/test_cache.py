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


def test_expired_entries_are_deleted_from_disk(tmp_path):
    c = FetchCache(tmp_path, ttl_hours=24)
    c.put("eski", _res(), "r1")
    c.put("yeni", _res(), "r2")
    (tmp_path / "yarim.tmp").write_text("x")
    (tmp_path / "bozuk.json").write_text("{")
    old = json.loads((tmp_path / "eski.json").read_text())
    old["cached_at"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    (tmp_path / "eski.json").write_text(json.dumps(old))
    assert c.prune() == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["yeni.json"]


def test_partial_results_are_not_cached(tmp_path):
    c = FetchCache(tmp_path, ttl_hours=24)
    r = _res()
    r.error = "proje toplamı alınamadı (HTTP 503)"            # başarılı ama oranlama yapılamadı
    c.put("k", r, "r1")
    assert c.get("k") is None


def test_code_version_invalidates_keys(monkeypatch):
    import trendpipe.cache as cm
    d = date(2026, 1, 1)
    k1 = cache_key("wikimedia", {}, "q", d, d)
    monkeypatch.setattr(cm, "__version__", "9.9.9")
    assert cache_key("wikimedia", {}, "q", d, d) != k1


def test_clean_command_dry_run_then_yes(cfg, tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    for name in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (runs / name).mkdir(parents=True)
        (runs / name / "manifest.json").write_text("{}")
    cfg["cache"] = {"enabled": True, "ttl_hours": 24, "dir": str(tmp_path / "cache")}
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    FetchCache(tmp_path / "cache").put("k", _res(), "r")
    args = ["clean", "--config", str(p), "--out-dir", str(runs), "--keep", "1", "--cache"]
    assert cli.main(args) == 0 and len(list(runs.iterdir())) == 3                # önce yalnız plan
    assert cli.main(args + ["--yes"]) == 0
    assert [x.name for x in runs.iterdir()] == ["20260103-000000"]
    assert not list((tmp_path / "cache").glob("*.json"))


def test_clean_refuses_sample_dir(cfg, tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    assert cli.main(["clean", "--config", str(p), "--out-dir", str(tmp_path / "data" / "sample"), "--yes"]) == 1
