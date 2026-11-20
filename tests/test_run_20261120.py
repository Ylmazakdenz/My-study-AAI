"""20.11.2026 gerçek çalıştırmasından (20261120-212027) çıkan regresyon testleri.

O çalıştırmada llama3.1:8b yanıtı denetimden yalnızca 1 uyarıyla geçti ama şu sorunlar vardı:
- Aynı terim birden çok kaynaktan aday olduğu için Kazak/Palto/Bot iki kez yazıldı, öneriler tekrarlandı.
- Bot (geçen yıldan yüksek, son dönemde sabit) için 'sezon üstü' dendi; özetteki Kazak (sezon üstü) için
  'mevsimsel artış' dendi; her öneriye 'mevsimsel artışlar her yıl görülür' eklendi.
- Normalize edilmiş Vikipedi değerleri birimsiz 'günlük ortalama 1,0 → 1,3' diye gösterildi; düşük hacim aralığı
  görüntüleme sayısı yerine bu paylardan yazıldı.
"""

from __future__ import annotations

import json
from pathlib import Path

from trendpipe.checks import review
from trendpipe.llm import evidence_table, render_markdown
from trendpipe.prompts import build_user_prompt, candidates, evidence_line, limitations

FIX = Path(__file__).parent / "fixtures"
RUN = json.loads((FIX / "run_20261120_rows.json").read_text(encoding="utf-8"))
ROWS, NAMES, W = RUN["rows"], RUN["names"], RUN["window"]
D = "Dönemsel ve yıllık karşılaştırma."


def _real_answer() -> dict:
    data = json.loads((FIX / "llama31_8b_run_20261120_response.json").read_text(encoding="utf-8"))["data"]
    for it in data["one_cikanlar"]:
        it.setdefault("dayanak", D)  # o sürümde alan yoktu; diğer sorunların yakalanması test edilir
    return data


def _issues(data) -> str:
    return " | ".join(review(data, ROWS, NAMES, W)["issues"])


def test_one_candidate_per_term_from_highest_priority_source():
    c = candidates(ROWS, list(NAMES))
    by_term = {r["label"]: r["source"] for r in c}
    assert len(c) == len(by_term) == 6
    assert by_term["Palto"] == by_term["Kazak"] == by_term["Bot / Çizme"] == "google_trends"
    assert by_term["Hırka"] == by_term["Kot pantolon"] == "wikimedia_en"   # Google Trends'te değişim yok


def test_real_answer_problems_are_caught():
    issues = _issues(_real_answer())
    assert "'Bot / Çizme' için 'sezon üstü'" in issues
    assert "'Kazak / İngilizce Vikipedi' aday listesinde yok" in issues and "Bu terimin adayı: Kazak / Google" in issues
    assert "'urun_katkisi' içinde 'Kazak' birden fazla kez" in issues
    assert "'Palto' için 'mevsimsel artış', 'her yıl görülen'" in issues            # sezon üstü terime eklenen cümle
    assert "'Kazak' için 'mevsimsel artış'" in issues                               # özetteki yanlış etiket


def test_correct_answer_for_this_run_passes():
    data = {
        "ozet": "Palto ve kazak ilgisi geçen yılın da üzerinde arttı; trençkot ilgisi mevsimsel olarak azaldı.",
        "one_cikanlar": [
            {"terim": "Palto", "kaynak": "Google Trends", "dayanak": D,
             "neden_onemli": "Yakın dönemde arttı ve geçen yılın aynı döneminden yüksek; sezon üstü artış."},
            {"terim": "Kazak", "kaynak": "Google Trends", "dayanak": D,
             "neden_onemli": "Yakın dönemde arttı ve geçen yılın aynı döneminden yüksek."},
            {"terim": "Bot / Çizme", "kaynak": "Google Trends", "dayanak": D,
             "neden_onemli": "Yakın dönemde belirgin değişim yok ama geçen yılın aynı döneminden yüksek."},
            {"terim": "Hırka", "kaynak": "İngilizce Vikipedi", "dayanak": D,
             "neden_onemli": "Yakın dönemde arttı, geçen yılla benzer düzeyde; her yıl görülen mevsimsel artış."},
            {"terim": "Trençkot", "kaynak": "Google Trends", "dayanak": D,
             "neden_onemli": "Yakın dönemde azaldı, geçen yılla benzer düzeyde; mevsimsel düşüş."}],
        "urun_katkisi": [
            {"terim": "Palto", "oneri": "Öne çıkarmayı destekleyebilir; ilgi geçen yılın da üzerinde."},
            {"terim": "Kazak", "oneri": "Öne çıkarmayı destekleyebilir."},
            {"terim": "Bot / Çizme", "oneri": "İlgi izlenmeli; yakın dönemde artış yok."},
            {"terim": "Hırka", "oneri": "Sezon ürünü olarak öne çıkarmayı destekleyebilir; mevsimsel bir artış."},
            {"terim": "Trençkot", "oneri": "Öne çıkarmak için erken; ilgi izlenmeli."}],
        "soyleyemediklerimiz": ["Veriler arama ilgisini ölçer; satın alma niyetini göstermez."]}
    rev = review(data, ROWS, NAMES, W)
    assert rev["ok"], rev["issues"]


def test_label_phrase_allowed_for_named_other_source_and_negation():
    data = json.loads(json.dumps({
        "ozet": "Palto ilgisi geçen yılın da üzerinde.",
        "one_cikanlar": [{"terim": "Palto", "kaynak": "Google Trends", "dayanak": D,
                          "neden_onemli": "Arttı ve geçen yıldan yüksek; bu mevsimsel bir artış değil. İngilizce "
                                          "Vikipedi'de ise mevsimsel artış görülüyor."}],
        "urun_katkisi": [{"terim": "Palto", "oneri": "Öne çıkarmayı destekleyebilir."}],
        "soyleyemediklerimiz": ["Veriler satın alma niyetini göstermez."]}))
    assert review(data, ROWS, NAMES, W)["ok"], _issues(data)
    data["one_cikanlar"][0]["neden_onemli"] = "Arttı; her yıl görülen mevsimsel artış."
    assert "'Palto' için 'mevsimsel artış', 'her yıl görülen'" in _issues(data)


def test_units_and_raw_volume_are_explicit():
    en_palto = next(r for r in ROWS if r["source"] == "wikimedia_en" and r["label"] == "Palto")
    gt_palto = next(r for r in ROWS if r["source"] == "google_trends" and r["label"] == "Palto")
    assert "Dönemsel (kaynak toplamındaki pay, milyonda)" in evidence_line(en_palto, NAMES)
    assert "Dönemsel (göreli ilgi, 0-100)" in evidence_line(gt_palto, NAMES)
    lim = " ".join(limitations(ROWS, NAMES))
    assert "(günlük ortalama 1,4–7,7 görüntüleme)" in lim                       # ham görüntüleme, pay değil
    assert "| Birim |" in evidence_table(ROWS, NAMES)


def test_prompt_lists_each_term_once_with_python_suggestion():
    ctx = {"brand": {"name": "B", "market": "TR", "season": "KŞ"}, "window": W, "flat_threshold_pct": 15,
           "sources": {k: {"display": v, "description": "x"} for k, v in NAMES.items()}}
    p = build_user_prompt(ROWS, ctx)
    cand = p.split("ADAY LİSTESİ")[1].split("DİĞER SONUÇLAR")[0]
    assert cand.count("terim: Kazak ") == 1 and cand.count("ÖNERİ:") == 6
    assert "YÖN: geçen yıldan yüksek" in cand                                   # Bot: son dönemde sabit
    assert "Kazak | İngilizce Vikipedi | mevsimsel artış" in p.split("DİĞER SONUÇLAR")[1]


def test_report_drops_duplicate_suggestions():
    data = _real_answer()
    out = {"data": data, "review": review(data, ROWS, NAMES, W), "attempts": [{}], "chosen_attempt": 1,
           "elapsed_sec": 1.0}
    md = render_markdown(out, ROWS, NAMES, {"model": "m", "temperature": 0.2, "created_at": "t", "run_id": "r",
                                             "window": W})
    sec1 = md.split("## 1.")[1].split("## 2.")[0]
    sec3 = md.split("## 3.")[1].split("## 4.")[0]
    assert sec1.count("**Kazak**") == 1 and "İngilizce Vikipedi" not in sec1.split("**Hırka**")[0]
    assert sec3.count("**Kazak**") == 1 and sec3.count("**Palto**") == 1
