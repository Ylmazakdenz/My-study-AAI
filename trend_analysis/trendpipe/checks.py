"""Model yanıtının hesaplanan sonuçlarla tutarlılık denetimi (açıklanabilirlik / güvenlik).

Sonraki aşamada Değerlendirme Ajanı'nın aracı olacak. İki katman:
1. validate_structured: JSON yanıtın şemaya ve Python'un aday listesine uyması (kesin kurallar).
2. check_output: serbest metin alanlarında uydurma yüzde, yanlış yön iddiası, veride olmayan iş metrikleri,
   kaynaklar arası karşılaştırma ve İngilizce kelime denetimi (sezgisel kurallar).
"""

from __future__ import annotations

import re

from .analysis import Trend
from .prompts import DOWN_LABELS, TREND_TR, candidates

_PCT = re.compile(r"([-+−]?\d+(?:[.,]\d+)?)\s*%|%\s*([-+−]?\d+(?:[.,]\d+)?)")


def check_numbers(text: str, rows: list[dict], tol: float = 1.0) -> dict:
    """Modelin yazdığı yüzdelerin hesapladığımız değerlerle örtüşüp örtüşmediğini kontrol eder.

    Küçük modeller sayı uydurabilir; eşleşmeyen yüzdeler raporlanır (açıklanabilirlik / güvenlik kontrolü).
    """
    allowed = []
    for r in rows:
        for key in ("pct_change", "yoy_pct_change", "baseline_coverage", "recent_coverage"):
            v = r.get(key)
            if v is None:
                continue
            allowed.append(abs(v * 100) if key.endswith("coverage") else abs(v))
    found, unmatched = [], []
    for m in _PCT.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(",", ".").replace("−", "-")
        try:
            val = abs(float(raw))
        except ValueError:
            continue
        found.append(val)
        if not any(abs(val - a) <= tol for a in allowed):
            unmatched.append(val)
    return {"percentages_found": found, "unmatched_percentages": unmatched,
            "ok": not unmatched,
            "note": ("Modelin yazdığı tüm yüzdeler hesaplanan değerlerle uyumlu." if not unmatched else
                     "Modelin yazdığı bazı yüzdeler hesaplanan sonuçlarda yok; yorum dikkatle okunmalı.")}


_UP = re.compile(r"yüksel|artış|arttı|artıyor|artan|kazan", re.I)
_DOWN = re.compile(r"düşüş|düştü|düşüyor|azal|kayb|geril", re.I)
_CAVEAT = re.compile(r"düşük hacim|güvenilir değil|güvenilmez|gürültü|zayıf|ihtiyat", re.I)
_MISSING = re.compile(r"alınamadı|veri yok|bulunamadı|unavailable|eksik gün|hesaplanmadı|hesaplanamadı|"
                      r"veri döndürmedi|veri içermiyor", re.I)
_BUSINESS = re.compile(r"satış\w*|stok\w*|ciro\w*|sipariş\w*|kâr\b|gelir\w*", re.I)
_ENGLISH = re.compile(r"\b(therefore|unavailable|however|because|increase[sd]?|decrease[sd]?|popularity|"
                      r"available|insufficient|the|and|with|data)\b", re.I)


def _lower_tr(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def source_aliases(src: str) -> list[str]:
    """Modelin bir kaynağı yazabileceği biçimler (anahtar, proje adı, Türkçe ad)."""
    al = {src, src.replace("wikimedia", "wikipedia")}
    if src.startswith("wikimedia"):
        if src.endswith("_en"):
            al |= {"en.wikipedia", "wikipedia.en", "wikipedia_en", "ingilizce vikipedi", "ingilizce wikipedia"}
        else:
            al |= {"tr.wikipedia", "wikipedia.tr", "türkçe vikipedi", "türkçe wikipedia"}
    if src == "gdelt":
        al |= {"gdelt haberleri"}
    if src == "google_trends":
        al |= {"google trends", "google aramaları"}
    return sorted(al, key=len, reverse=True)


def mentioned_sources(line_low: str, sources: list[str]) -> list[str]:
    """Satırda geçen kaynaklar; uzun adlar önce eşlenir ('wikimedia_en' içindeki 'wikimedia' ayrıca sayılmaz)."""
    pairs = sorted(((a, s) for s in sources for a in source_aliases(s)), key=lambda x: len(x[0]), reverse=True)
    found: list[str] = []
    work = line_low
    for alias, src in pairs:
        if alias in work:
            work = work.replace(alias, " " * len(alias))
            if src not in found:
                found.append(src)
    return found


# 4. bölüm başlığı: "## 4.", "**4. ...**", "4) ..." gibi biçimlerin hepsi (model biçimi her zaman korumuyor).
_SECTION4 = re.compile(r"^\s*(?:#+\s*|\*\*\s*)?4\s*[.)]", re.M)


def split_sections(text: str) -> tuple[str, str]:
    """(1-3. bölümler, 4. bölüm)."""
    m = _SECTION4.search(text)
    return (text[:m.start()], text[m.start():]) if m else (text, "")


_YOY_PHRASE = re.compile(r"geçen yıl|önceki yıl|geçen sezon|yıllık", re.I)
_YOY_UP = re.compile(r"yüksek|fazla|üzerinde|üstünde|arttı|artış|yüksel|güçlü", re.I)
_YOY_DOWN = re.compile(r"düşük|daha az|altında|azal|düştü|düşüş|geril|zayıf", re.I)
_PROMOTE = re.compile(r"öne çıkar", re.I)
_NOT_PROMOTE = re.compile(r"çıkarılmamalı|çıkarmamak|çıkarmak için erken|yerine|değil|önermiyoruz|izlenmeli", re.I)
_CLAUSE = re.compile(r"[;.]\s|;|,\s|\b(?:ama|ancak|fakat|iken|oysa|buna karşın)\b", re.I)
# "daha fazla yıl/veri gerekir" gibi ifadeler karşılaştırma değildir (20.11.2026 yanlış alarmı).
_COMPARE = re.compile(r"daha (yüksek|düşük|fazla|az|çok)(?!\s+(?:yıl|veri|gün|dönem|zaman|kaynak))", re.I)
_COMPUTED = {"computed", "baseline_zero"}


def check_claims(text: str, rows: list[dict]) -> list[str]:
    """Modelin iddialarını hesaplanan sonuçlarla karşılaştırır (basit, satır bazlı denetim).

    - 1-3. bölüm: bir terim için artış/düşüş iddiası, o terimin hiçbir kaynağında o yön yoksa;
      yön yalnızca düşük hacimli seriden geliyor ve çekince yoksa.
    - 1-3. bölüm: verisi olmayan bir kaynak-terim kanıt olarak gösterilmişse.
    - Tüm metin: verisi hesaplanmış bir kaynak-terim için 'veri yok / eksik gün' denmişse.
    - Tüm metin: iki kaynağın değerleri 'daha yüksek/düşük' diye karşılaştırılmışsa ("daha fazla yıl gerekir" gibi
      ifadeler karşılaştırma sayılmaz).
    - 1-3. bölüm: satış/stok/ciro gibi veride olmayan metrikler. Tüm metin: İngilizce kelimeler.
    """
    issues: list[str] = []
    labels = sorted({r["label"] for r in rows}, key=len, reverse=True)
    sources = sorted({r["source"] for r in rows})
    row = {(r["label"], r["source"]): r for r in rows}
    body = split_sections(text)[0]
    body_lines = set(body.splitlines())

    for line in text.splitlines():
        low = _lower_tr(line)
        in_body = line in body_lines
        srcs = mentioned_sources(low, sources)
        missing_claim = bool(_MISSING.search(line))
        if len(srcs) >= 2 and _COMPARE.search(line):
            issues.append(f"Kaynaklar birbiriyle karşılaştırılmış ({', '.join(srcs)}): \"{line.strip()[:90]}\"")
        for label in labels:
            if _lower_tr(label) not in low:
                continue
            mine = [r for r in rows if r["label"] == label and (r.get("direction") or r.get("yoy_direction"))]
            if in_body:
                # Yön iddiası cümle parçası düzeyinde denetlenir: "palto arttı; trençkot azaldı" gibi bir cümlede
                # her terim yalnızca kendi parçasındaki fiille eşlenir.
                for clause in _CLAUSE.split(line):
                    if _lower_tr(label) not in _lower_tr(clause):
                        continue
                    # Yıllık ifade ("geçen yılın aynı döneminden yüksek") dönemsel ifadeden ayrı denetlenir.
                    m = _YOY_PHRASE.search(clause)
                    pop_text, yoy_text = (clause[:m.start()], clause[m.start():]) if m else (clause, "")
                    if yoy_text:
                        yoy_dirs = {r.get("yoy_direction") for r in mine if r.get("yoy_direction")}
                        for regex, d, word in ((_YOY_UP, "up", "geçen yıldan yüksek"),
                                               (_YOY_DOWN, "down", "geçen yıldan düşük")):
                            if regex.search(yoy_text) and yoy_dirs and d not in yoy_dirs:
                                issues.append(f"'{label}' için '{word}' iddiası var ama hesaplanan yıllık yön farklı "
                                              f"({', '.join(sorted(yoy_dirs))}).")
                    for regex, d, word in ((_UP, "up", "artış"), (_DOWN, "down", "düşüş")):
                        if not regex.search(pop_text):
                            continue
                        matching = [r for r in mine if r.get("direction") == d or r.get("yoy_direction") == d]
                        if not matching:
                            found = ", ".join(f"{r['source']}: dönemsel {r.get('direction') or '-'}, yıllık "
                                              f"{r.get('yoy_direction') or '-'}" for r in mine) or "hesaplanmadı"
                            issues.append(f"'{label}' için {word} iddiası var ama hesaplanan yön farklı ({found}).")
                        elif all(r.get("low_volume") for r in matching) and not _CAVEAT.search(line):
                            issues.append(f"'{label}' için {word} yalnızca düşük hacimli seride var; çekince yok.")
            for src in srcs:
                r = row.get((label, src))
                if r is None:
                    continue
                computed = r.get("result") in _COMPUTED
                if missing_claim and computed:
                    issues.append(f"'{label}' için {src} verisi hesaplandığı halde 'veri yok/eksik' denmiş.")
                elif in_body and not missing_claim and not computed:
                    issues.append(f"'{label}' için {src} verisi yokken kanıt olarak gösterilmiş.")

    biz = sorted({m.group(0).lower() for m in _BUSINESS.finditer(body)})
    if biz:
        issues.append(f"1-3. bölümlerde veride olmayan iş metriklerinden söz ediliyor: {', '.join(biz)}")

    eng = sorted({m.group(0).lower() for m in _ENGLISH.finditer(text)})
    if eng:
        issues.append(f"Yanıtta İngilizce kelimeler var: {', '.join(eng)}")
    return list(dict.fromkeys(issues))


def check_output(text: str, rows: list[dict]) -> dict:
    nums = check_numbers(text, rows)
    claims = check_claims(text, rows)
    ok = nums["ok"] and not claims
    return {**nums, "claim_issues": claims, "ok": ok,
            "note": "Yanıt hesaplanan sonuçlarla tutarlı." if ok else
                    "Yanıtta hesaplanan sonuçlarla uyuşmayan ifadeler var; aşağıdaki uyarılara bakın."}




def _norm(s: str) -> str:
    return re.sub(r"[^\wçğıöşü/ ]", "", _lower_tr(s)).strip()


_SEASONAL = {Trend.SEASONAL_UP, Trend.SEASONAL_UP_WEAKER, Trend.SEASONAL_DOWN, Trend.SEASONAL_DOWN_STRONGER}
# Etiket ifadesi -> bu ifadeyi taşıyabilecek etiketler. 20.11.2026 çalıştırmasında model 'geçen yıldan yüksek' olan
# terime 'sezon üstü', 'geçen yıldan düşük' olana 'mevsimsel düşüş' dedi ve her öneriye 'mevsimsel artışlar her yıl
# görülür' ekledi; yön denetimi bunları yakalamıyordu.
_LABEL_PHRASES = [
    (re.compile(r"sezon\s+üstü"), {Trend.ABOVE_SEASON_UP}, "sezon üstü"),
    (re.compile(r"sezon\s+altı"), {Trend.ABOVE_SEASON_DOWN}, "sezon altı"),
    (re.compile(r"mevsimsel\s+(?:bir\s+)?artı[şs]"), {Trend.SEASONAL_UP, Trend.SEASONAL_UP_WEAKER}, "mevsimsel artış"),
    (re.compile(r"mevsimsel\s+(?:bir\s+)?düşü[şs]"), {Trend.SEASONAL_DOWN, Trend.SEASONAL_DOWN_STRONGER},
     "mevsimsel düşüş"),
    (re.compile(r"her\s+yıl\s+görülen"), _SEASONAL, "her yıl görülen"),
]
_NEGATED = re.compile(r"^\W*(?:\w+\W+){0,2}değil")


def label_phrase_issues(text: str, term: str, allowed: set[str], rows: list[dict], sources: list[str]) -> list[str]:
    """Metindeki etiket ifadeleri ('sezon üstü', 'mevsimsel artış'...) terimin etiketine uyuyor mu?

    allowed: terimin seçilen etiket(ler)i. Bir cümle parçasında başka bir kaynak adı geçiyorsa, o kaynaktaki etiketi de
    o parçada kullanılabilir ("İngilizce Vikipedi'de ise mevsimsel artış var" gibi).
    """
    bad: list[str] = []
    for clause in _CLAUSE.split(text or ""):
        if not clause:
            continue
        low = _lower_tr(clause)
        ok = set(allowed) | {r.get("trend_label") for r in rows if _norm(r["label"]) == _norm(term)
                             and r["source"] in mentioned_sources(low, sources)}
        for rx, labels, phrase in _LABEL_PHRASES:
            for m in rx.finditer(low):
                if _NEGATED.search(low[m.end():]):
                    continue  # "mevsimsel bir artış değil" gibi olumsuzlama
                if not labels & ok and phrase not in bad:
                    bad.append(phrase)
    if not bad:
        return []
    lab = ", ".join(TREND_TR.get(x, x) for x in sorted(allowed)) or "aday değil"
    return [f"'{term}' için {', '.join(repr(b) for b in bad)} ifadesi kullanılmış ama etiketi farklı ({lab})."]


def validate_structured(data, rows: list[dict], names: dict) -> list[str]:
    """JSON yanıtın şemaya ve aday listesine uygunluğu. Boş liste = sorun yok."""
    if not isinstance(data, dict):
        return ["Yanıt bir JSON nesnesi değil."]
    issues: list[str] = []
    for key, typ in (("ozet", str), ("one_cikanlar", list), ("urun_katkisi", list), ("soyleyemediklerimiz", list)):
        if not isinstance(data.get(key), typ):
            issues.append(f"'{key}' alanı eksik ya da türü yanlış.")
    if issues:
        return issues
    cands = candidates(rows, list(names))
    allowed = {(_norm(r["label"]), r["source"]) for r in cands}
    cand_label = {_norm(r["label"]): r["trend_label"] for r in cands}
    sources = sorted({r["source"] for r in rows})
    alias = {}
    for key, disp in names.items():
        for a in (key, disp):
            alias[_norm(a)] = key
    chosen: dict[str, str] = {}   # terim -> seçilen etiket
    for item in data["one_cikanlar"]:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("terim", "kaynak",
                                                                                          "neden_onemli", "dayanak")):
            issues.append("'one_cikanlar' içinde şemaya uymayan öğe var.")
            continue
        term, src = _norm(item["terim"]), alias.get(_norm(item["kaynak"]))
        if (term, src) not in allowed:
            other = [r for r in cands if _norm(r["label"]) == term]
            hint = (f" Bu terimin adayı: {other[0]['label']} / {names.get(other[0]['source'], other[0]['source'])}."
                    if other else "")
            issues.append(f"'{item['terim']} / {item['kaynak']}' aday listesinde yok; yalnızca aday listesindeki "
                          f"terim-kaynak çiftleri seçilebilir.{hint}")
        elif term in chosen:
            issues.append(f"'{item['terim']}' öne çıkanlarda birden fazla kez yazılmış; her terim bir kez yazılır.")
        else:
            chosen[term] = cand_label[term]
            issues += label_phrase_issues(f"{item['neden_onemli']}; {item['dayanak']}", item["terim"],
                                          {chosen[term]}, rows, sources)
    if not allowed and data["one_cikanlar"]:
        issues.append("Aday listesi boş olduğu halde öne çıkan terim yazılmış.")
    seen: set[str] = set()
    for item in data["urun_katkisi"]:
        if not isinstance(item, dict) or not isinstance(item.get("terim"), str) or not isinstance(item.get("oneri"),
                                                                                                   str):
            issues.append("'urun_katkisi' içinde şemaya uymayan öğe var.")
            continue
        term = _norm(item["terim"])
        if term not in chosen:
            issues.append(f"'urun_katkisi' içindeki '{item['terim']}' öne çıkanlar arasında değil.")
            continue
        if term in seen:
            issues.append(f"'urun_katkisi' içinde '{item['terim']}' birden fazla kez yazılmış; her terim için tek "
                          "öneri yazılır.")
            continue
        seen.add(term)
        if _PROMOTE.search(item["oneri"]) and not _NOT_PROMOTE.search(item["oneri"]) and chosen[term] in DOWN_LABELS:
            issues.append(f"'{item['terim']}' ilgisi düşüyor / geçen yıldan düşük olduğu halde 'öne çıkar' "
                          "önerilmiş.")
        issues += label_phrase_issues(item["oneri"], item["terim"], {chosen[term]}, rows, sources)
    # Özet: terim adı geçen her cümle parçasında etiket ifadesi o terime uymalı.
    for clause in _CLAUSE.split(data["ozet"]):
        low = _lower_tr(clause or "")
        for label in sorted({r["label"] for r in rows}, key=len, reverse=True):
            if _lower_tr(label) not in low:
                continue
            ok = {cand_label[_norm(label)]} if _norm(label) in cand_label else \
                {r.get("trend_label") for r in rows if r["label"] == label}
            issues += label_phrase_issues(clause, label, ok, rows, sources)
    if not all(isinstance(x, str) for x in data["soyleyemediklerimiz"]):
        issues.append("'soyleyemediklerimiz' yalnızca metin maddeleri içermeli.")
    elif any(len(re.findall(r"[.;]\s+\S", x)) >= 3 for x in data["soyleyemediklerimiz"]):
        issues.append("'soyleyemediklerimiz' içinde birden çok sınır tek maddede birleştirilmiş; her sınır ayrı bir "
                      "liste öğesi olmalı.")
    return issues


def structured_as_text(data: dict) -> str:
    """Serbest metin denetimi için yanıtı başlıklı metne çevirir (1-3 gövde, 4 sınırlar)."""
    lines = ["## 1. Öne çıkanlar", f"- {data.get('ozet', '')}"]
    lines += [f"- {i.get('terim')} ({i.get('kaynak')}): {i.get('neden_onemli')}"
              for i in data.get("one_cikanlar", []) if isinstance(i, dict)]
    lines += ["## 2. Destekleyen ölçüm ve dönem"]
    lines += [f"- {i.get('terim')} ({i.get('kaynak')}): {i.get('dayanak')}"
              for i in data.get("one_cikanlar", []) if isinstance(i, dict) and i.get("dayanak")]
    lines += ["## 3. Ürün katkısı"]
    lines += [f"- {i.get('terim')}: {i.get('oneri')}" for i in data.get("urun_katkisi", []) if isinstance(i, dict)]
    lines += ["## 4. Söyleyemediklerimiz"]
    lines += [f"- {x}" for x in data.get("soyleyemediklerimiz", []) if isinstance(x, str)]
    return "\n".join(lines)


_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")


def check_dates(text: str, window: dict | None) -> list[str]:
    """Yanıttaki tarihler (gg.aa.yyyy) analiz dönemlerinin sınır tarihlerinden biri olmalı."""
    if not window:
        return []
    allowed = {v for v in window.values() if isinstance(v, str)}
    bad = []
    for m in _DATE.finditer(text):
        iso = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        if iso not in allowed:
            bad.append(m.group(0))
    return [f"Analiz dönemlerinde olmayan tarih(ler): {', '.join(sorted(set(bad)))}"] if bad else []


def review(data, rows: list[dict], names: dict, window: dict | None = None) -> dict:
    """Tam denetim: şema/aday kuralları + metin denetimi (+ verilirse tarih denetimi)."""
    structural = validate_structured(data, rows, names)
    text_check = check_output(structured_as_text(data), rows) if isinstance(data, dict) else \
        {"percentages_found": [], "unmatched_percentages": [], "claim_issues": []}
    issues = structural + text_check.get("claim_issues", [])
    if isinstance(data, dict):
        issues += check_dates(structured_as_text(data), window)
    if text_check.get("unmatched_percentages"):
        issues.append("Hesaplanan sonuçlarda olmayan yüzdeler: "
                      + ", ".join(f"%{v:g}" for v in text_check["unmatched_percentages"]))
    return {"ok": not issues, "issues": issues, "structural_issues": structural,
            "unmatched_percentages": text_check.get("unmatched_percentages", []),
            "note": "Yanıt hesaplanan sonuçlarla tutarlı." if not issues else
                    "Yanıtta hesaplanan sonuçlarla uyuşmayan ifadeler var; aşağıdaki uyarılara bakın."}
