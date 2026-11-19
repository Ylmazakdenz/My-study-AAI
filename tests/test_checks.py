"""Model yanıtı denetimi ve istem: gerçek Colab/yerel denemelerde görülen hatalar regresyon olarak."""

from __future__ import annotations

from trendpipe.checks import check_numbers


def test_check_numbers():
    rows = [{"pct_change": 42.3, "baseline_coverage": 1.0, "recent_coverage": 1.0}]
    assert check_numbers("Trençkot %42,3 arttı.", rows)["ok"]
    bad = check_numbers("Satışlar %80 artacak.", rows)
    assert not bad["ok"] and bad["unmatched_percentages"] == [80.0]



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
    from trendpipe.checks import check_output
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

    from trendpipe.checks import check_output
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / "data/sample/20261118-231912/analysis.json").read_text(encoding="utf-8"))["rows"]
    text = (root / "tests/fixtures/llama32_run2_response.md").read_text(encoding="utf-8")
    joined = " ".join(check_output(text, rows)["claim_issues"])
    assert "'Trençkot' için gdelt verisi yokken kanıt" in joined          # 2. bölüm, veri yok
    assert "Kaynaklar birbiriyle karşılaştırılmış" in joined              # tr vs en karşılaştırması
    assert "'Hırka' için wikimedia verisi hesaplandığı halde" in joined    # 'eksik gün' iddiası
    assert "satış" in joined



def test_claim_check_accepts_correct_answer():
    from trendpipe.checks import check_output
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
    from trendpipe.analysis import trend_label
    from trendpipe.prompts import build_user_prompt
    rows = _colab_rows()
    for r in rows:
        r.update({k: v for k, v in _ctx()["window"].items()})
        r["trend_label"] = trend_label(r["signal"], None)
    p = build_user_prompt(rows, _ctx())
    assert "ADAY LİSTESİ (one_cikanlar yalnızca bunlardan seçilir):\n- (aday yok)" in p   # Kazak düşük hacimli
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



def test_claim_check_bold_headings_real_run3():
    """3. Colab denemesi (llama3.1:8b): başlıklar '**4. ...**' biçiminde geldi; eski denetim 4. bölümü
    ayıramadığı için sınırlar listesini hata sanıyordu (yanlış alarm). İçerik doğru olduğundan ✅ beklenir."""
    import json
    from pathlib import Path

    from trendpipe.checks import check_output, split_sections
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / "data/sample/20261118-233854/analysis.json").read_text(encoding="utf-8"))["rows"]
    text = (root / "tests/fixtures/llama31_8b_run3_response.md").read_text(encoding="utf-8")
    assert "kaynağın istek sınırına takıldı" in split_sections(text)[1]
    chk = check_output(text, rows)
    assert chk["ok"], chk

