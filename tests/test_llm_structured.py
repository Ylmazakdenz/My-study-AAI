"""Yapılandırılmış model yanıtı: şema/aday doğrulaması, öz-düzeltme döngüsü ve rapor (sahte Ollama ile)."""

from __future__ import annotations

import json
import sys
import types

import pytest

from trendpipe.analysis import Trend
from trendpipe.checks import review, validate_structured
from trendpipe.llm import _parse, interpret, render_markdown

W = {"baseline_start": "2026-09-23", "baseline_end": "2026-10-20", "recent_start": "2026-10-21",
     "recent_end": "2026-11-17", "ly_start": "2025-10-22", "ly_end": "2025-11-18"}
NAMES = {"google_trends": "Google Trends", "wikimedia_en": "İngilizce Vikipedi"}


def _rows():
    base = {**W, "fetch_status": "ok", "result": "computed", "low_volume": False, "notes": [],
            "yoy_result": "computed", "yoy_granularity": "haftalık"}
    return [
        {**base, "source": "google_trends", "label": "Palto", "baseline_mean": 35.5, "recent_mean": 58.8,
         "pct_change": 65.3, "direction": "up", "signal": "strong_up", "yoy_ly_mean": 40.0,
         "yoy_recent_mean": 60.0, "yoy_pct_change": 50.0, "yoy_direction": "up", "yoy_signal": "strong_up",
         "trend_label": Trend.ABOVE_SEASON_UP},
        {**base, "source": "google_trends", "label": "Hırka", "baseline_mean": 79.2, "recent_mean": 71.5,
         "pct_change": -9.8, "direction": "flat", "signal": "flat", "yoy_ly_mean": 70.0, "yoy_recent_mean": 72.0,
         "yoy_pct_change": 2.9, "yoy_direction": "flat", "yoy_signal": "flat", "trend_label": Trend.NO_CHANGE},
    ]


GOOD = {"ozet": "Palto aramaları geçen yılın da üzerinde.",
        "one_cikanlar": [{"terim": "Palto", "kaynak": "Google Trends",
                          "neden_onemli": "Son dönemde arttı ve geçen yılın aynı döneminden de yüksek (%+50)."}],
        "urun_katkisi": [{"terim": "Palto", "oneri": "Palto modellerini öne çıkarmayı destekleyebilir."}],
        "soyleyemediklerimiz": ["Veriler arama ilgisini ölçer; satın alma niyetini göstermez."]}


def test_valid_answer_passes():
    rev = review(GOOD, _rows(), NAMES)
    assert rev["ok"], rev


@pytest.mark.parametrize("mutate, expected", [
    (lambda d: d["one_cikanlar"][0].update(terim="Hırka"), "aday listesinde yok"),          # yatay terim seçilmiş
    (lambda d: d["one_cikanlar"][0].update(kaynak="Twitter"), "aday listesinde yok"),       # uydurma kaynak
    (lambda d: d["urun_katkisi"][0].update(terim="Kazak"), "öne çıkanlar arasında değil"),
    (lambda d: d.update(ozet="Palto satışları artacak."), "iş metriklerinden"),
    (lambda d: d["one_cikanlar"][0].update(neden_onemli="Arttı (%+80)."), "olmayan yüzdeler"),
    (lambda d: d.pop("ozet"), "'ozet' alanı eksik"),
])
def test_invalid_answers_are_caught(mutate, expected):
    data = json.loads(json.dumps(GOOD))
    mutate(data)
    rev = review(data, _rows(), NAMES)
    assert not rev["ok"] and any(expected in i for i in rev["issues"]), rev["issues"]


def test_empty_candidates_requires_empty_selection():
    rows = [r for r in _rows() if r["label"] == "Hırka"]
    assert validate_structured({**GOOD, "urun_katkisi": []}, rows, NAMES)


def test_parse_code_fenced_json():
    assert _parse('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse("geçersiz") is None


def _fake_ollama(monkeypatch, replies):
    calls = []

    class Client:
        def __init__(self, host=None, timeout=None):
            pass

        def chat(self, model, messages, options=None, format=None):
            calls.append({"messages": messages, "format": format})
            return {"message": {"content": replies[len(calls) - 1]}}
    mod = types.ModuleType("ollama")
    mod.Client = Client
    monkeypatch.setitem(sys.modules, "ollama", mod)
    return calls


def _ctx():
    return {"brand": {"name": "B", "market": "TR", "season": "KŞ"}, "window": W, "flat_threshold_pct": 15,
            "sources": {k: {"display": v, "description": "x"} for k, v in NAMES.items()}}


def test_self_correction_loop(monkeypatch):
    bad = {**GOOD, "one_cikanlar": [{"terim": "Hırka", "kaynak": "Google Trends", "neden_onemli": "arttı"}],
           "urun_katkisi": []}
    calls = _fake_ollama(monkeypatch, [json.dumps(bad, ensure_ascii=False), json.dumps(GOOD, ensure_ascii=False)])
    out = interpret(_rows(), _ctx(), {"host": "h", "model": "m"})
    assert len(calls) == 2 and calls[0]["format"]["type"] == "object"           # şema gönderildi
    assert "aday listesinde yok" in calls[1]["messages"][-1]["content"]          # geri bildirim modele iletildi
    assert out["chosen_attempt"] == 2 and out["review"]["ok"]


def test_best_attempt_kept_when_all_fail(monkeypatch):
    calls = _fake_ollama(monkeypatch, ["geçersiz", json.dumps({**GOOD, "ozet": "Satış artar."}, ensure_ascii=False)])
    out = interpret(_rows(), _ctx(), {"host": "h", "model": "m"})
    assert len(calls) == 2 and out["chosen_attempt"] == 2 and not out["review"]["ok"]


def test_markdown_has_four_sections_and_python_evidence(monkeypatch):
    _fake_ollama(monkeypatch, [json.dumps(GOOD, ensure_ascii=False)])
    rows = _rows()
    out = interpret(rows, _ctx(), {"host": "h", "model": "m"})
    md = render_markdown(out, rows, NAMES, {"model": "m", "temperature": 0.2, "created_at": "t", "run_id": "r",
                                             "window": W})
    for h in ("## 1.", "## 2.", "## 3.", "## 4.", "## Ek:"):
        assert h in md
    assert "35,5 (23.09.2026–20.10.2026) → 58,8" in md and "%+50,0" in md        # sayılar Python'dan
    assert "*sezon üstü artış*" in md and "✅" in md


def test_multi_term_sentence_checked_per_clause():
    """Uçtan uca denemede bulunan yanlış alarm: 'palto arttı; hırka azaldı' cümlesinde her terim kendi fiiliyle."""
    rows = _rows()
    rows[1].update(direction="down", signal="strong_down", trend_label=Trend.SEASONAL_DOWN)
    data = {**GOOD, "ozet": "Palto ilgisi arttı; hırka ilgisi azaldı."}
    assert review(data, rows, NAMES)["ok"]
    bad = {**GOOD, "ozet": "Palto ilgisi azaldı; hırka ilgisi arttı."}
    issues = " ".join(review(bad, rows, NAMES)["issues"])
    assert "'Palto' için düşüş" in issues and "'Hırka' için artış" in issues


def test_text_checks_run_even_with_schema_errors():
    data = {**GOOD, "ozet": "Satışlar artacak.",
            "one_cikanlar": [{"terim": "Hırka", "kaynak": "Google Trends", "neden_onemli": "x"}], "urun_katkisi": []}
    issues = " ".join(review(data, _rows(), NAMES)["issues"])
    assert "aday listesinde yok" in issues and "iş metriklerinden" in issues


def test_markdown_excludes_non_candidates(monkeypatch):
    bad = {**GOOD, "one_cikanlar": [{"terim": "Hırka", "kaynak": "Google Trends", "neden_onemli": "x"}],
           "urun_katkisi": [{"terim": "Hırka", "oneri": "y"}]}
    _fake_ollama(monkeypatch, [json.dumps(bad, ensure_ascii=False)] * 2)
    rows = _rows()
    out = interpret(rows, _ctx(), {"host": "h", "model": "m"})
    md = render_markdown(out, rows, NAMES, {"model": "m", "temperature": 0.2, "created_at": "t", "run_id": "r",
                                             "window": W})
    section1 = md.split("## 1.")[1].split("## 2.")[0]
    assert "Hırka" not in section1 and "⚠️" in md and "aday listesinde yok" in md


def _run5_rows():
    """19.11.2026 17:34 yerel çalıştırmasının (Vikipedi normalizasyonundan önce) İngilizce Vikipedi sonuçları."""
    def row(label, pct, d, ypct, yd, tl):
        return {**W, "source": "wikimedia_en", "label": label, "fetch_status": "ok", "result": "computed",
                "low_volume": False, "notes": [], "baseline_mean": 100.0, "recent_mean": 100.0,
                "pct_change": pct, "direction": d, "signal": {"up": "strong_up", "flat": "flat"}[d],
                "yoy_result": "computed", "yoy_ly_mean": 100.0, "yoy_recent_mean": 100.0, "yoy_pct_change": ypct,
                "yoy_direction": yd, "yoy_signal": "x", "trend_label": tl}
    return [row("Hırka", 25.7, "up", -8.8, "flat", Trend.SEASONAL_UP),
            row("Kazak", 20.9, "up", -26.6, "down", Trend.SEASONAL_UP_WEAKER),
            row("Palto", 16.1, "up", -29.8, "down", Trend.SEASONAL_UP_WEAKER),
            row("Kot pantolon", 0.6, "flat", -62.4, "down", Trend.YEARLY_DOWN)]


def test_real_run5_answer_is_caught():
    """Gerçek llama3.1:8b yanıtı ✅ almıştı ama yanlıştı: yıllık düşüşe 'geçen yıldan yüksek' dedi ve geçen yıldan
    düşük ürünlere 'öne çıkar' önerdi. Yeni denetim ikisini de yakalamalı."""
    names = {"wikimedia_en": "İngilizce Vikipedi"}
    data = {"ozet": "Bu sezon, mevsimsel artış gösteren ürünler öne çıkıyor.",
            "one_cikanlar": [{"terim": t, "kaynak": "İngilizce Vikipedi",
                              "neden_onemli": f"{t} son dönemde arttı ve geçen yılın aynı döneminden de yüksek."}
                             for t in ("Hırka", "Kazak", "Palto")] +
                            [{"terim": "Kot pantolon", "kaynak": "İngilizce Vikipedi",
                              "neden_onemli": "Geçen yıla göre düşük (son dönemde sabit)."}],
            "urun_katkisi": [{"terim": t, "oneri": "Öne çıkarmayı destekleyebilir."}
                             for t in ("Hırka", "Kazak", "Palto", "Kot pantolon")],
            "soyleyemediklerimiz": ["İngilizce Vikipedi dünya geneli ilgiyi gösterir."]}
    issues = " | ".join(review(data, _run5_rows(), names)["issues"])
    for t in ("Hırka", "Kazak", "Palto"):
        assert f"'{t}' için 'geçen yıldan yüksek' iddiası" in issues
    assert "'Kot pantolon' ilgisi düşüyor / geçen yıldan düşük olduğu halde 'öne çıkar'" in issues
    assert "'Kazak' ilgisi düşüyor" not in issues          # dönemsel artış var, öneri serbest


def test_correct_run5_answer_passes():
    names = {"wikimedia_en": "İngilizce Vikipedi"}
    data = {"ozet": "Hırka, kazak ve palto ilgisi son dört haftada arttı; bu artış mevsimsel.",
            "one_cikanlar": [
                {"terim": "Hırka", "kaynak": "İngilizce Vikipedi",
                 "neden_onemli": "Son dönemde arttı, geçen yılın aynı dönemiyle benzer düzeyde; mevsimsel artış."},
                {"terim": "Kazak", "kaynak": "İngilizce Vikipedi",
                 "neden_onemli": "Son dönemde arttı ama geçen yılın aynı döneminden düşük."},
                {"terim": "Kot pantolon", "kaynak": "İngilizce Vikipedi",
                 "neden_onemli": "Son dönemde sabit, geçen yılın aynı döneminden düşük."}],
            "urun_katkisi": [{"terim": "Hırka", "oneri": "Sezon ürünü olarak öne çıkarmayı destekleyebilir."},
                             {"terim": "Kazak", "oneri": "Öne çıkarmayı destekleyebilir; ilgi geçen yıldan zayıf."},
                             {"terim": "Kot pantolon", "oneri": "İlgi izlenmeli, öne çıkarmak için erken."}],
            "soyleyemediklerimiz": ["Veriler satın alma niyetini göstermez."]}
    rev = review(data, _run5_rows(), names)
    assert rev["ok"], rev["issues"]
