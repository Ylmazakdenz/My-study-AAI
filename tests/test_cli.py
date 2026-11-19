"""Komut satırı uçtan uca (model hariç): terim seçimi, çekme+analiz, devre kesici, örnek veriyle çevrimdışı tekrar."""

from __future__ import annotations

import yaml
from conftest import END, FakeResponse, FakeSession, gdelt_body, wiki_body, window

from trendpipe import cli
from trendpipe.analysis import Result
from trendpipe.config import parse_terms


def test_terms_filter_and_extra(cfg):
    ts = parse_terms(cfg, only_ids=["a"], extra=["Deri Ceket"])
    assert [t.id for t in ts] == ["a", "deri_ceket"]
    assert ts[1].queries["gdelt"] == "Deri Ceket"



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



def test_offline_reanalysis_of_sample_matches_committed(tmp_path):
    """README'deki 'bağlantı olmadan tekrar' komutu, repodaki örnek analizle aynı sonucu vermeli."""
    import json
    import shutil
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "data/sample", tmp_path / "sample")

    def load(p):
        return {(r["source"], r["term_id"]): (r["result"], r.get("pct_change"))
                for r in json.loads(p.read_text(encoding="utf-8"))["rows"]}
    runs = sorted(p.parent.name for p in (root / "data/sample").glob("*/manifest.json"))
    assert len(runs) >= 2
    for run in runs:
        assert cli.main(["analyze", "--config", str(root / "config/config.yaml"),
                         "--run", str(tmp_path / "sample" / run)]) == 0
        rel = f"{run}/analysis.json"
        assert load(tmp_path / "sample" / rel) == load(root / "data/sample" / rel), run



def test_stops_after_consecutive_429(cfg, tmp_path, monkeypatch):
    import json
    cfg["sources"] = {"gdelt": {"enabled": True, "request_interval_sec": 0, "stop_after_consecutive_429": 2}}
    cfg["analysis"]["low_volume"] = {}
    cfg["terms"] = [{"id": f"t{i}", "label": f"T{i}", "queries": {"gdelt": f"q{i}"}} for i in range(4)]
    sess = FakeSession({}, default=FakeResponse(429, "Please limit requests"))
    import trendpipe.sources as srcmod
    orig = srcmod.build_sources
    monkeypatch.setattr(cli, "build_sources", lambda c, only=None, user_agent="": orig(c, only, user_agent, sess))
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    assert cli.main(["fetch", "--config", str(p), "--out-dir", str(tmp_path / "r"), "--end", END.isoformat()]) == 0
    m = json.loads(next((tmp_path / "r").iterdir()).joinpath("manifest.json").read_text(encoding="utf-8"))
    assert len(sess.calls) == 2                                   # 3. ve 4. terim denenmedi
    assert all(f["status"] == "error" for f in m["fetches"])
    assert "Denenmedi" in m["fetches"][2]["error"] and m["fetches"][2]["attempts"] == 0

