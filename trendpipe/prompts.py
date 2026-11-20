"""Model istemi ve yanıt şeması.

Tasarım (gerçek denemelerden çıkan ders):
- Küçük/orta modeller serbest metinde biçimi korumuyor (başlık biçimi değişti, sayıları yanlış aktardı, kaynakları
  karşılaştırdı, "satış artışı" uydurdu). Bu yüzden model artık JSON şemasına uyan yanıt verir; Python yanıtı
  alan alan doğrular ve markdown'ı kendisi oluşturur.
- Model YALNIZCA Python'un aday listesinden terim seçebilir; sayılar ve dönemler Python'dan gelir.
- Model görev belgesindeki 4 soruyu yanıtlar: öne çıkanlar + neden (1), destekleyen ölçüm ve dönem (2, "dayanak"),
  ürün seçimine katkı (3), söyleyemediklerimiz (4) ve kısa özet. 2. sorunun yanıtındaki yüzde ve tarihler denetlenir;
  raporda yanına Python'un hesapladığı kanıt satırı da eklenir.
"""

from __future__ import annotations

from collections import defaultdict

from .analysis import Signal, Trend

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "ozet": {"type": "string"},
        "one_cikanlar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"terim": {"type": "string"}, "kaynak": {"type": "string"},
                               "neden_onemli": {"type": "string"}, "dayanak": {"type": "string"}},
                "required": ["terim", "kaynak", "neden_onemli", "dayanak"],
            },
        },
        "urun_katkisi": {
            "type": "array",
            "items": {"type": "object", "properties": {"terim": {"type": "string"}, "oneri": {"type": "string"}},
                      "required": ["terim", "oneri"]},
        },
        "soyleyemediklerimiz": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ozet", "one_cikanlar", "urun_katkisi", "soyleyemediklerimiz"],
}

SYSTEM_PROMPT = """Sen bir giyim markasının trend analistisin. Sana Python ile hesaplanmış ölçümler ve bir ADAY LİSTESİ
veriliyor. Yanıtını YALNIZCA verilen JSON şemasına uygun, Türkçe olarak ver.

KURALLAR:
1. "one_cikanlar" içine YALNIZCA ADAY LİSTESİ'ndeki terim-kaynak çiftlerini yaz; terim ve kaynak adlarını listede
   yazıldığı gibi kopyala. Aday listesi boşsa "one_cikanlar" ve "urun_katkisi" boş liste olsun.
2. "neden_onemli": adayın ANLAMI alanını kendi cümlenle yaz. ANLAMI'nda olmayan bir şey söyleme; özellikle geçen
   yılla ilgili ifadeyi ANLAMI'nda yazdığı gibi kullan (geçen yıldan yüksek / benzer / düşük).
   Yeni sayı yazma; sayı yazacaksan yalnızca aday satırındaki yüzdeleri aynen kullan.
3. "dayanak" (destekleyen ölçüm ve dönem): kaynağı, karşılaştırılan dönemleri (tarihleriyle) ve yüzde değişimi
   yaz. Yalnızca aday satırındaki yüzdeleri ve yukarıda verilen dönem tarihlerini aynen kullan.
4. "urun_katkisi": her öne çıkan terim için bir madde, adayın YÖN alanına göre:
   - YÖN "yükseliyor" ise ihtiyatlı öneri ("öne çıkarmayı destekleyebilir"); mevsimsel artışta bunun her yıl görülen
     bir artış olduğunu belirt.
   - YÖN "düşüyor" ya da "geçen yıldan düşük" ise "öne çıkar" DEME; "ilgi izlenmeli", "öne çıkarmak için erken"
     gibi yaz.
5. Satış, stok, ciro, sipariş, fiyat veya tüketici talebi hakkında hiçbir şey söyleme; bu bilgiler veride yok.
6. Kaynakları birbiriyle sayısal olarak karşılaştırma; her kaynak farklı bir şey ölçer.
7. "soyleyemediklerimiz": SINIRLAR listesindeki en önemli 3-5 maddeyi kendi cümlelerinle yaz. Veri yetersizse
   bunu açıkça yaz.
8. "ozet": en fazla 2 cümle. Tamamen Türkçe yaz; İngilizce kelime kullanma.
"""

TREND_TR = {
    Trend.ABOVE_SEASON_UP: "sezon üstü artış",
    Trend.SEASONAL_UP: "mevsimsel artış (geçen yılla benzer düzey)",
    Trend.SEASONAL_UP_WEAKER: "mevsimsel artış, geçen yıldan zayıf",
    Trend.UP_YOY_UNKNOWN: "artış (geçen yılla karşılaştırılamadı)",
    Trend.ABOVE_SEASON_DOWN: "sezon altı düşüş",
    Trend.SEASONAL_DOWN: "mevsimsel düşüş (geçen yılla benzer düzey)",
    Trend.SEASONAL_DOWN_STRONGER: "mevsimsel düşüş, geçen yıldan güçlü",
    Trend.DOWN_YOY_UNKNOWN: "düşüş (geçen yılla karşılaştırılamadı)",
    Trend.YEARLY_UP: "geçen yıla göre yüksek (son dönemde sabit)",
    Trend.YEARLY_DOWN: "geçen yıla göre düşük (son dönemde sabit)",
    Trend.NO_CHANGE: "belirgin değişim yok",
    Trend.WEAK: "düşük hacim — güvenilir değil",
    Trend.INSUFFICIENT: "hesaplanamadı",
    Trend.NO_DATA: "veri yok",
}

# Öne çıkan sayılabilecek etiketler (en az bir karşılaştırmada güvenilir sinyal)
_LABEL_ORDER = [Trend.ABOVE_SEASON_UP, Trend.YEARLY_UP, Trend.UP_YOY_UNKNOWN, Trend.SEASONAL_UP,
                Trend.SEASONAL_UP_WEAKER, Trend.ABOVE_SEASON_DOWN, Trend.YEARLY_DOWN, Trend.DOWN_YOY_UNKNOWN,
                Trend.SEASONAL_DOWN, Trend.SEASONAL_DOWN_STRONGER]
CANDIDATE_LABELS = set(_LABEL_ORDER)


def display_name(key: str, info: dict | None = None) -> str:
    """Kaynak anahtarını okunur Türkçe ada çevirir (manifest'teki ayarlardan)."""
    s = (info or {}).get("settings") or {}
    typ = s.get("type", key.split("_")[0] if key.startswith("wikimedia") else key)
    if typ == "wikimedia":
        lang = str(s.get("project", "en.wikipedia" if key.endswith("_en") else "tr.wikipedia")).split(".")[0]
        return {"tr": "Türkçe Vikipedi", "en": "İngilizce Vikipedi"}.get(lang, f"Vikipedi ({lang})")
    if typ == "google_trends":
        geo = s.get("geo", "TR")
        return "Google Trends" if geo == "TR" else f"Google Trends ({geo})"
    return {"gdelt": "GDELT haberleri"}.get(typ, key)


def reason_tr(row: dict) -> str:
    """Hata/durum metnini kısa Türkçe nedene çevirir (ham hata metni modele gitmez)."""
    st = row.get("fetch_status")
    if st == "not_found":
        return "kaynakta bulunamadı"
    if st == "empty":
        return "kaynak bu dönemde eşleşen veri döndürmedi"
    if st == "skipped":
        return "bu kaynak için sorgu tanımlı değil"
    note = " ".join(row.get("notes") or []).lower()
    if row.get("result") == "insufficient_data":
        if "kaynak kesintisi" in note:
            return "kaynağın kendi veri kesintisi nedeniyle karşılaştırmaya yetecek gün kalmadı"
        return "eksik gün oranı yüksek olduğu için değişim hesaplanmadı"
    if "timeout" in note or "timed out" in note:
        return "kaynak zamanında yanıt vermedi"
    if "429" in note or "too many" in note or "limit" in note:
        return "kaynağın istek sınırına takıldı"
    if "connection" in note:
        return "bağlantı hatası"
    return "veri alınamadı"


def _num(v: float | None) -> str:
    return "-" if v is None else f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: float | None) -> str:
    return "-" if v is None else f"%{v:+.1f}".replace(".", ",")


def _ndays(a: str, b: str) -> int:
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days + 1


def _d(s: str) -> str:
    y, m, d = s.split("-")
    return f"{d}.{m}.{y}"


def candidates(rows: list[dict]) -> list[dict]:
    """Modelin seçebileceği terim-kaynak çiftleri (Python belirler)."""
    c = [r for r in rows if r.get("trend_label") in CANDIDATE_LABELS]
    return sorted(c, key=lambda r: (_LABEL_ORDER.index(r["trend_label"]), -abs(r.get("pct_change") or 0)))


def evidence_line(r: dict, names: dict) -> str:
    """2. soru (ölçüm ve dönem) için Python'un ürettiği kanıt satırı."""
    nm = names.get(r["source"], r["source"])
    parts = [f"**{r['label']} — {nm}**: {TREND_TR.get(r.get('trend_label'), '-')}."]
    if r.get("baseline_mean") is not None:
        parts.append(f"Dönemsel: günlük ortalama {_num(r['baseline_mean'])} ({_d(r['baseline_start'])}–"
                     f"{_d(r['baseline_end'])}) → {_num(r['recent_mean'])} ({_d(r['recent_start'])}–"
                     f"{_d(r['recent_end'])}), {_pct(r.get('pct_change'))}.")
    if r.get("yoy_pct_change") is not None:
        parts.append(f"Yıllık: geçen yıl aynı dönem ({_d(r['ly_start'])}–{_d(r['ly_end'])}) "
                     f"{_num(r['yoy_ly_mean'])} → bu yıl {_num(r['yoy_recent_mean'])}, {_pct(r['yoy_pct_change'])} "
                     f"({r.get('yoy_granularity')} veri).")
    else:
        parts.append("Yıllık karşılaştırma yapılamadı.")
    return "- " + " ".join(parts)


MEANING = {
    Trend.ABOVE_SEASON_UP: "yakın dönemde önceki döneme göre arttı VE geçen yılın aynı döneminden yüksek",
    Trend.SEASONAL_UP: "yakın dönemde arttı; geçen yılın aynı dönemiyle benzer düzeyde (her yıl görülen mevsimsel "
                       "artış)",
    Trend.SEASONAL_UP_WEAKER: "yakın dönemde arttı ama geçen yılın aynı döneminden DÜŞÜK (mevsimsel artış, geçen "
                              "yıldan zayıf)",
    Trend.UP_YOY_UNKNOWN: "yakın dönemde arttı; geçen yılla karşılaştırılamadı (mevsimsel olup olmadığı bilinmiyor)",
    Trend.ABOVE_SEASON_DOWN: "yakın dönemde azaldı VE geçen yılın aynı döneminden düşük",
    Trend.SEASONAL_DOWN: "yakın dönemde azaldı; geçen yılın aynı dönemiyle benzer düzeyde (her yıl görülen mevsimsel "
                         "düşüş)",
    Trend.SEASONAL_DOWN_STRONGER: "yakın dönemde azaldı ama geçen yılın aynı döneminden yüksek",
    Trend.DOWN_YOY_UNKNOWN: "yakın dönemde azaldı; geçen yılla karşılaştırılamadı",
    Trend.YEARLY_UP: "yakın dönemde belirgin değişim yok; geçen yılın aynı döneminden yüksek",
    Trend.YEARLY_DOWN: "yakın dönemde belirgin değişim yok; geçen yılın aynı döneminden düşük",
}
UP_LABELS = {Trend.ABOVE_SEASON_UP, Trend.SEASONAL_UP, Trend.SEASONAL_UP_WEAKER, Trend.UP_YOY_UNKNOWN,
             Trend.YEARLY_UP}
DOWN_LABELS = CANDIDATE_LABELS - UP_LABELS


def direction_tr(label: str) -> str:
    if label == Trend.YEARLY_DOWN:
        return "geçen yıldan düşük"
    return "yükseliyor" if label in UP_LABELS else "düşüyor"


def candidate_line(r: dict, names: dict) -> str:
    y = f", yıllık {_pct(r['yoy_pct_change'])}" if r.get("yoy_pct_change") is not None else ""
    return (f"- terim: {r['label']} | kaynak: {names.get(r['source'], r['source'])} | "
            f"ETİKET: {TREND_TR[r['trend_label']]} | YÖN: {direction_tr(r['trend_label'])} | "
            f"ANLAMI: {MEANING[r['trend_label']]} | dönemsel {_pct(r.get('pct_change'))}{y}")


def limitations(rows: list[dict], names: dict) -> list[str]:
    out: list[str] = []
    by_src: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_src[r["source"]].append(r)
    for src, rs in by_src.items():
        nm = names.get(src, src)
        weak = [r for r in rs if r.get("signal") == Signal.WEAK]
        if weak:
            means = [m for r in weak for m in (r.get("baseline_mean"), r.get("recent_mean")) if m is not None]
            rng = f" (günlük ortalama {_num(min(means))}–{_num(max(means))})" if means else ""
            out.append(f"{nm}: {', '.join(r['label'] for r in weak)} için hacim çok düşük{rng}; "
                       "değişimler güvenilir değil.")
        reasons: dict[str, list[str]] = defaultdict(list)
        for r in rs:
            if r.get("signal") in (Signal.NO_DATA, Signal.INSUFFICIENT):
                reasons[reason_tr(r)].append(r["label"])
        for reason, labels in reasons.items():
            out.append(f"{nm}: {', '.join(labels)} — {reason}.")
        no_yoy = [r["label"] for r in rs if r.get("signal") not in (Signal.NO_DATA, Signal.INSUFFICIENT, Signal.WEAK)
                  and r.get("yoy_result") != "computed"]
        if no_yoy:
            out.append(f"{nm}: {', '.join(no_yoy)} için geçen yılla karşılaştırma yapılamadı; bu terimlerde "
                       "değişimin mevsimsel olup olmadığı bilinmiyor.")
        gaps = max((r.get("source_gap_days") or 0) for r in rs)
        if gaps:
            out.append(f"{nm}: kaynağın kendisinde {gaps} günlük veri kesintisi var; bu günler hesaba katılmadı.")
    if "google_trends" in names:
        out.append("Google Trends değerleri her terim için kendi zirvesine göre 0-100 arasında ölçeklenir; yalnızca "
                   "aynı terimin dönemleri karşılaştırılabilir. Google aramaların bir örneklemini kullandığı için "
                   "aynı sorgu tekrarlandığında değerler biraz değişebilir.")
    if any(k.endswith("_en") for k in names):
        out.append("İngilizce Vikipedi dünya geneli ilgiyi gösterir; Türkiye'ye özgü değildir.")
    out.append("Veriler arama ilgisi ve bilgi merakını ölçer; satış, stok, fiyat veya tüketici talebi hakkında "
               "bilgi içermez.")
    out.append("Yıllık karşılaştırma tek bir önceki yıla dayanır; uzun vadeli eğilim için daha fazla yıl gerekir.")
    return out


def build_user_prompt(rows: list[dict], context: dict) -> str:
    """context: brand, window, sources (anahtar -> {display, description}), flat_threshold_pct."""
    w = context["window"]
    thr = context.get("flat_threshold_pct", 15)
    names = {k: v["display"] for k, v in context["sources"].items()}
    cands = candidates(rows)
    other = [r for r in rows if r not in cands]
    ly = f" | Geçen yılın aynı dönemi: {_d(w['ly_start'])}–{_d(w['ly_end'])}" if w.get("ly_start") else ""
    parts = [
        f"Marka: {context['brand'].get('name')} | Pazar: {context['brand'].get('market')} | "
        f"Sezon: {context['brand'].get('season')}",
        f"Önceki dönem: {_d(w['baseline_start'])}–{_d(w['baseline_end'])} | "
        f"Yakın dönem: {_d(w['recent_start'])}–{_d(w['recent_end'])}{ly}",
        f"Yöntem: dönemsel = yakın dönem ({_ndays(w['recent_start'], w['recent_end'])} gün) ↔ önceki dönem "
        f"({_ndays(w['baseline_start'], w['baseline_end'])} gün); yıllık = yakın dönem ↔ geçen yılın aynı dönemi. "
        f"±%{thr:g} içindeki değişimler 'belirgin değişim yok' sayıldı; düşük hacimli seriler güvenilir sayılmadı.",
        "",
        "KAYNAKLAR:",
        *[f"- {v['display']}: {v['description']}" for v in context["sources"].values()],
        "",
        "ADAY LİSTESİ (one_cikanlar yalnızca bunlardan seçilir):",
        "\n".join(candidate_line(r, names) for r in cands) or "- (aday yok)",
        "",
        "ADAY OLMAYANLAR (öne çıkan sayılmaz):",
        "\n".join(f"- {r['label']} | {names.get(r['source'], r['source'])} | "
                  f"{TREND_TR.get(r.get('trend_label'), '-')}" for r in other) or "- (yok)",
        "",
        "SINIRLAR:",
        "\n".join(f"- {x}" for x in limitations(rows, names)),
    ]
    return "\n".join(parts)

