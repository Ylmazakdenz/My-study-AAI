"""Repo denetiminde (19.11.2026) bulunan sorunlar için regresyon testleri."""

from __future__ import annotations

import json
import sys
import types
from datetime import date

import pytest
import yaml
from conftest import FakeResponse, FakeSession, wiki_body

from trendpipe import cli
from trendpipe.config import ConfigError, compute_window, llm_settings
from trendpipe.models import FetchStatus
from trendpipe.storage import new_run_dir

END = date(2026, 11, 15)


def test_unexpected_adapter_error_does_not_abort_run(cfg, tmp_path, monkeypatch):
    """F1: bir adaptör beklenmeyen istisna fırlatsa da çalıştırma tamamlanır ve manifest yazılır."""
    w = compute_window(cfg, end=END)
    sess = FakeSession({"Iyi": FakeResponse(200, wiki_body(w.start, [5] * 14)),
                        "Bozuk": FakeResponse(200, "[1, 2]")})          # liste: .get() AttributeError verirdi
    cfg["window"]["yoy"] = False
    cfg["sources"] = {"wikimedia": {"enabled": True, "normalize_by_project": False}}
    cfg["terms"] = [{"id": "b", "label": "B", "queries": {"wikimedia": "Bozuk"}},
                    {"id": "i", "label": "I", "queries": {"wikimedia": "Iyi"}}]
    cfg["analysis"]["low_volume"] = {}
    import trendpipe.sources as srcmod
    orig = srcmod.build_sources

    def boom_sources(c, only=None, user_agent=""):
        srcs = orig(c, only, user_agent, sess)
        real = srcs[0].fetch

        def fetch(term_id, *a, **k):
            if term_id == "x":
                raise RuntimeError("beklenmeyen")
            return real(term_id, *a, **k)
        srcs[0].fetch = fetch
        return srcs
    monkeypatch.setattr(cli, "build_sources", boom_sources)
    cfg["terms"].insert(0, {"id": "x", "label": "X", "queries": {"wikimedia": "Iyi"}})
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    assert cli.main(["fetch", "--config", str(p), "--out-dir", str(tmp_path / "r"), "--end", END.isoformat()]) == 0
    m = json.loads(next((tmp_path / "r").iterdir()).joinpath("manifest.json").read_text(encoding="utf-8"))
    st = {f["term_id"]: f for f in m["fetches"]}
    assert st["x"]["status"] == "error" and "Beklenmeyen hata" in st["x"]["error"]
    assert st["b"]["status"] == "error" and "çözümlenemedi" in st["b"]["error"]
    assert st["i"]["status"] == "ok"


def test_two_runs_in_same_second_do_not_collide(tmp_path, monkeypatch):
    """F2: aynı saniyede iki çalıştırma çökmez, ikincisi -2 alır."""
    import trendpipe.storage as st

    class Frozen:
        @staticmethod
        def now():
            from datetime import datetime
            return datetime(2026, 11, 19, 12, 0, 0)
    monkeypatch.setattr(st, "datetime", Frozen)
    a, b = new_run_dir(tmp_path), new_run_dir(tmp_path)
    assert a.name == "20261119-120000" and b.name == "20261119-120000-2" and (b / "raw").is_dir()


def _fake_pytrends(monkeypatch, exc):
    calls = {"n": 0}

    class TrendReq:
        def __init__(self, **kw):
            pass

        def build_payload(self, *a, **k):
            pass

        def interest_over_time(self):
            calls["n"] += 1
            raise exc
    mod = types.ModuleType("pytrends.request")
    mod.TrendReq = TrendReq
    monkeypatch.setitem(sys.modules, "pytrends", types.ModuleType("pytrends"))
    monkeypatch.setitem(sys.modules, "pytrends.request", mod)
    return calls


def test_google_trends_does_not_wait_on_permanent_error(monkeypatch, cfg):
    """F3: kalıcı hatada (400) 60/120 sn beklenmez, tek deneme yapılır."""
    from trendpipe.sources.google_trends import GoogleTrendsSource
    w = compute_window(cfg, end=END)
    calls = _fake_pytrends(monkeypatch, Exception("ResponseError: The request failed: code 400"))
    res = GoogleTrendsSource({"max_retries": 2, "retry_backoff_sec": 1000}).fetch("t", "x", w.start, w.end)
    assert res.status == FetchStatus.ERROR and calls["n"] == 1 and res.http_status is None


def test_google_trends_retries_on_timeout(monkeypatch, cfg):
    from trendpipe.sources.google_trends import GoogleTrendsSource
    w = compute_window(cfg, end=END)
    calls = _fake_pytrends(monkeypatch, Exception("ReadTimeout: read timed out"))
    GoogleTrendsSource({"max_retries": 2, "retry_backoff_sec": 0}).fetch("t", "x", w.start, w.end)
    assert calls["n"] == 3


def test_wikimedia_attempts_reflect_article_request(cfg):
    """F4: proje toplamı isteği, makale isteğinin deneme sayısını ezmez."""
    from trendpipe.sources.wikimedia import WikimediaSource
    w = compute_window(cfg, end=END)
    seq = [FakeResponse(503, "x"), FakeResponse(200, wiki_body(w.start, [5] * 14)),
           FakeResponse(200, wiki_body(w.start, [1000] * 14))]

    class S:
        def get(self, *a, **k):
            return seq.pop(0)
    res = WikimediaSource({"max_retries": 2}, session=S()).fetch("t", "X", w.start, w.end)
    assert res.status == FetchStatus.OK and res.attempts == 2 and res.points[0].extra == {"norm": 1000.0}


def test_bad_env_number_gives_clear_error(monkeypatch):
    """F9: .env'de sayı yerine metin varsa anlaşılır hata."""
    monkeypatch.setenv("OLLAMA_TEMPERATURE", "düşük")
    with pytest.raises(ConfigError, match="OLLAMA_TEMPERATURE sayı olmalı"):
        llm_settings()


def test_interpret_reanalyzes_stale_analysis(tmp_path, monkeypatch):
    """F8: interpret, eski sürümün yazdığı analysis.json yerine güncel kodla yeniden analiz eder."""
    import shutil
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    run = tmp_path / "20261119-162956"
    shutil.copytree(root / "data/sample/20261119-162956", run)
    stale = json.loads((run / "analysis.json").read_text(encoding="utf-8"))
    for r in stale["rows"]:
        r.pop("trend_label", None)                                       # eski sürüm: etiket yok
    (run / "analysis.json").write_text(json.dumps(stale), encoding="utf-8")
    reply = {"ozet": "x", "one_cikanlar": [], "urun_katkisi": [], "soyleyemediklerimiz": []}

    class Client:
        def __init__(self, host=None, timeout=None):
            pass

        def chat(self, model, messages, options=None, format=None):
            return {"message": {"content": json.dumps(reply)}}
    mod = types.ModuleType("ollama")
    mod.Client = Client
    monkeypatch.setitem(sys.modules, "ollama", mod)
    assert cli.main(["interpret", "--config", str(root / "config/config.yaml"), "--run", str(run)]) == 0
    fresh = json.loads((run / "analysis.json").read_text(encoding="utf-8"))
    assert all("trend_label" in r for r in fresh["rows"])


def test_manifest_records_environment_and_market_timezone(cfg, tmp_path, monkeypatch):
    """P3/P4: manifest ortam bilgisini (sürüm, Python, paketler, git) yazar; 'bugün' pazar saat dilimine göredir."""
    from datetime import datetime, timezone

    from trendpipe import config as cfgmod
    from trendpipe.provenance import run_environment
    env = run_environment()
    assert env["python"] and env["trendpipe"] and "pytrends" in env["packages"]
    # 23:30 UTC = İstanbul'da ertesi gün 02:30 → pazar günü İstanbul'a göre hesaplanır
    fixed = datetime(2026, 11, 19, 23, 30, tzinfo=timezone.utc)

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    import datetime as dtmod
    monkeypatch.setattr(dtmod, "datetime", FakeDT)
    assert cfgmod.market_today("Europe/Istanbul") == date(2026, 11, 20)
    assert cfgmod.market_today("UTC") == date(2026, 11, 19)
    assert cfgmod.utc_offset_minutes("Europe/Istanbul") == 180


def test_unknown_timezone_rejected(tmp_path):
    from pathlib import Path

    from trendpipe.config import load_config
    root = Path(__file__).resolve().parents[1]
    c = yaml.safe_load((root / "config/config.yaml").read_text(encoding="utf-8"))
    c["window"]["timezone"] = "Europe/Istambul"
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError, match="bilinmeyen saat dilimi"):
        load_config(p)


def test_doctor_reports_missing_model(monkeypatch, tmp_path, capsys):
    """P5: doctor, Ollama'da model yoksa hata verir ve nasıl indirileceğini söyler."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]

    class Client:
        def __init__(self, host=None, timeout=None):
            pass

        def list(self):
            return {"models": [{"model": "llama3.2:latest"}]}
    mod = types.ModuleType("ollama")
    mod.Client = Client
    monkeypatch.setitem(sys.modules, "ollama", mod)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["doctor", "--config", str(root / "config/config.yaml"), "--out-dir", str(tmp_path / "runs")])
    out = capsys.readouterr().out
    assert rc == 1 and "ollama pull llama3.1:8b" in out and "ayar dosyası" in out and ".env" in out


def test_doctor_ok_without_llm(tmp_path, capsys, monkeypatch):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["doctor", "--config", str(root / "config/config.yaml"), "--out-dir", str(tmp_path / "r"),
                   "--no-llm"])
    out = capsys.readouterr().out
    assert "paket pytrends" in out and "ayar dosyası" in out and "Ollama" not in out
    assert rc in (0, 1)
