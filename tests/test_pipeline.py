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


# ---------- Colab'daki ilk gerçek denemeden çıkan durumlar ----------

def _colab_rows():
    """2026-11-18 Colab çalıştırmasındaki analiz sonuçlarının özeti (wikimedia tr + gdelt hataları)."""
    def ok(label, bm, rm, pct, d):
        return {"source": "wikimedia", "label": label, "fetch_status": "ok", "result": "computed",
                "baseline_mean": bm, "recent_mean": rm, "pct_change": pct, "direction": d, "low_volume": True,
                "baseline_coverage": 1.0, "recent_coverage": 1.0, "notes": ["Düşük hacim"]}

    def err(label, msg):
        return {"source": "gdelt", "label": label, "fetch_status": "error", "result": "no_data",
                "notes": [f"Veri alınamadı (error): {msg}"]}
    rows = [ok("Kazak", 1.5, 2.3, 56.1, "up"), ok("Kot pantolon", 7.1, 7.9, 11.1, "flat"),
            ok("Palto", 4.2, 4.4, 4.2, "flat"), ok("Trençkot", 3.0, 2.7, -9.5, "flat"),
            err("Trençkot", "ReadTimeout: Read timed out"), err("Kazak", "HTTP 429: Please limit requests")]
    from trendpipe.analysis import classify
    for r in rows:
        r["signal"] = classify(r)
    return rows


def test_claim_check_catches_colab_mistakes():
    """1. Colab denemesindeki llama3.2 hataları."""
    from trendpipe.llm import check_output
    bad = ("## 1. Öne çıkan terimler\n- Palto: popülerlik kazanıyor.\n- Kazak: popülerlik kazanıyor.\n"
           "## 4. Bu veriyle söyleyemediklerimiz\n"
           "- Trençkot: Veri alınamadı (wikimedia'dan), therefore unavailable.\n")
    chk = check_output(bad, _colab_rows())
    joined = " ".join(chk["claim_issues"])
    assert not chk["ok"]
    assert "'Palto' için artış" in joined                    # yatay terime yükseliş denmiş
    assert "'Kazak' için artış yalnızca düşük hacimli" in joined
    assert "'Trençkot' için wikimedia verisi hesaplandığı halde" in joined
    assert "therefore" in joined
    assert "satış" in " ".join(check_output("## 1. X\n- Satışlar artacak.\n", _colab_rows())["claim_issues"])


def test_claim_check_on_real_run2_answer():
    """2. Colab denemesindeki gerçek llama3.2 yanıtı + aynı çalıştırmanın gerçek verisi (data/sample)."""
    import json
    from pathlib import Path
    from trendpipe.llm import check_output
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / "data/sample/20261118-231912/analysis.json").read_text(encoding="utf-8"))["rows"]
    text = (root / "tests/fixtures/llama32_run2_response.md").read_text(encoding="utf-8")
    joined = " ".join(check_output(text, rows)["claim_issues"])
    assert "'Trençkot' için gdelt verisi yokken kanıt" in joined          # 2. bölüm, veri yok
    assert "Kaynaklar birbiriyle karşılaştırılmış" in joined              # tr vs en karşılaştırması
    assert "'Hırka' için wikimedia verisi hesaplandığı halde" in joined    # 'eksik gün' iddiası
    assert "satış" in joined


def test_claim_check_accepts_correct_answer():
    from trendpipe.llm import check_output
    good = ("## 1. Öne çıkan terimler\n- Güvenilir bir değişim gösteren terim yok.\n"
            "- Kazak (wikimedia) %+56,1 arttı ancak düşük hacim nedeniyle güvenilir değil.\n"
            "## 4. Bu veriyle söyleyemediklerimiz\n- Trençkot için gdelt verisi alınamadı.\n")
    chk = check_output(good, _colab_rows())
    assert chk["ok"], chk


def _ctx():
    return {"brand": {"name": "B", "market": "TR", "season": "KŞ"},
            "window": {"baseline_start": "2026-09-22", "baseline_end": "2026-10-19",
                       "recent_start": "2026-10-20", "recent_end": "2026-11-16"},
            "sources": {"wikimedia": {"display": "Türkçe Vikipedi", "description": "x"},
                        "gdelt": {"display": "GDELT haberleri", "description": "y"}}}


def test_prompt_groups_and_reasons():
    from trendpipe.prompts import build_user_prompt
    rows = _colab_rows()
    for r in rows:
        r.update({k: v for k, v in _ctx()["window"].items()})
    p = build_user_prompt(rows, _ctx())
    assert "GÜVENİLİR YÜKSELİŞ:\n- (yok)" in p                      # Kazak düşük hacimli -> güvenilir değil
    limits = p.split("SINIRLAR")[1]
    assert "Türkçe Vikipedi: Kazak, Kot pantolon, Palto, Trençkot için hacim çok düşük" in limits
    assert "GDELT haberleri: Trençkot — kaynak zamanında yanıt vermedi" in limits
    assert "GDELT haberleri: Kazak — kaynağın istek sınırına takıldı" in limits
    assert "Read timed out" not in p                               # ham hata metni modele gitmez


def test_display_names():
    from trendpipe.prompts import display_name
    assert display_name("wikimedia_en", {"settings": {"type": "wikimedia", "project": "en.wikipedia"}}) == \
        "İngilizce Vikipedi"
    assert display_name("wikimedia", {"settings": {}}) == "Türkçe Vikipedi"
    assert display_name("gdelt") == "GDELT haberleri"


# ---------- kaynak kesintisi ve GDELT normalizasyonu ----------

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


# ---------- tekrar deneme ve çoklu kaynak örneği ----------

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


def test_offline_reanalysis_of_sample_matches_committed(tmp_path):
    """README'deki 'bağlantı olmadan tekrar' komutu, repodaki örnek analizle aynı sonucu vermeli."""
    import json
    import shutil
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "data/sample", tmp_path / "sample")
    assert cli.main(["analyze", "--config", str(root / "config/config.yaml"),
                     "--out-dir", str(tmp_path / "sample"), "--run", "latest"]) == 0

    def load(p):
        return {(r["source"], r["term_id"]): (r["result"], r.get("pct_change"))
                for r in json.loads(p.read_text(encoding="utf-8"))["rows"]}
    rel = "20261118-231912/analysis.json"
    assert load(tmp_path / "sample" / rel) == load(root / "data/sample" / rel)
