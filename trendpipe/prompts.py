"""Model istemi.

Küçük modeller (llama3.2 3B) ham JSON'u yanlış okuyabiliyor. İlk iki Colab denemesinde:
yatay terimlere "yükseliyor" dedi, verisi gelen terimlere "veri alınamadı" dedi, kaynakları birbiriyle karşılaştırdı,
"satışta artış" uydurdu. Bu yüzden Python sonuçları önce Türkçe, hazır cümlelere ve gruplara çevirir:
- kanıt satırları (2. bölüm için, kopyalanacak),
- sınırlar listesi (4. bölüm için),
model ise öne çıkanları seçer ve ürün seçimine bağlar (1. ve 3. bölüm).
"""

from __future__ import annotations

from collections import defaultdict

from .analysis import Signal

SYSTEM_PROMPT = """Sen bir giyim markasının trend analistisin. Sana Python ile hesaplanmış ölçümler, hazır kanıt
satırları ve sınırlar listesi veriliyor. Görevin bunları marka ekibi için kısa ve doğru biçimde yazmak.

KURALLAR:
1. YALNIZCA verilen bilgileri kullan. Yeni sayı, yüzde, tarih veya kaynak uydurma.
2. "Yükseliş/artış" yalnızca GÜVENİLİR YÜKSELİŞ listesindeki terimler için, "düşüş" yalnızca GÜVENİLİR DÜŞÜŞ
   listesindekiler için kullanılabilir. Listede olmayan bir terime yükseliş ya da düşüş deme.
3. Satış, stok, ciro, sipariş, fiyat veya tüketici talebi hakkında hiçbir şey söyleme; bu bilgiler veride yok.
4. Kaynakları birbiriyle karşılaştırma ("X kaynağında daha yüksek" gibi). Her kaynak farklı bir şey ölçer.
5. Tamamen Türkçe yaz; İngilizce kelime kullanma. Kısa ve maddeli yaz.

ÇIKTI BİÇİMİ (tam olarak bu dört başlık):
## 1. Öne çıkan terimler
GÜVENİLİR YÜKSELİŞ ve GÜVENİLİR DÜŞÜŞ listelerindeki terimleri yaz (kaynağıyla birlikte). İkisi de boşsa
"Güvenilir bir değişim gösteren terim yok." yaz.
## 2. Destekleyen ölçüm ve dönem
KANIT SATIRLARI'nı aynen kopyala; değiştirme, ekleme yapma.
## 3. Ürün seçimine olası katkı
Öne çıkan her terim için 1 madde: bu ilgi hangi ürün tipini öne çıkarmayı veya izlemeyi destekleyebilir.
İhtiyatlı yaz ("destekleyebilir", "izlenmeli" gibi). Satış veya talep iddiası yapma.
## 4. Bu veriyle söyleyemediklerimiz
SINIRLAR listesindeki maddeleri aynen yaz.
"""

DIRECTION_TR = {"up": "artış", "down": "düşüş", "flat": "belirgin değişim yok"}


def display_name(key: str, info: dict | None = None) -> str:
    """Kaynak anahtarını okunur Türkçe ada çevirir (manifest'teki ayarlardan)."""
    s = (info or {}).get("settings") or {}
    typ = s.get("type", key.split("_")[0] if key.startswith("wikimedia") else key)
    if typ == "wikimedia":
        lang = str(s.get("project", "en.wikipedia" if key.endswith("_en") else "tr.wikipedia")).split(".")[0]
        return {"tr": "Türkçe Vikipedi", "en": "İngilizce Vikipedi"}.get(lang, f"Vikipedi ({lang})")
    return {"gdelt": "GDELT haberleri", "google_trends": "Google Trends"}.get(typ, key)


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
    return "yüzde tanımsız" if v is None else f"%{v:+.1f}".replace(".", ",")


def _d(s: str) -> str:
    y, m, d = s.split("-")
    return f"{d}.{m}.{y}"


def evidence_line(r: dict, names: dict) -> str:
    return (f"- {r['label']} — {names.get(r['source'], r['source'])}: günlük ortalama {_num(r['baseline_mean'])} "
            f"({_d(r['baseline_start'])}–{_d(r['baseline_end'])}) → {_num(r['recent_mean'])} "
            f"({_d(r['recent_start'])}–{_d(r['recent_end'])}), değişim {_pct(r.get('pct_change'))}")


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
            out.append(f"- {nm}: {', '.join(r['label'] for r in weak)} için hacim çok düşük{rng}; "
                       "değişimler güvenilir değil.")
        reasons: dict[str, list[str]] = defaultdict(list)
        for r in rs:
            if r.get("signal") in (Signal.NO_DATA, Signal.INSUFFICIENT):
                reasons[reason_tr(r)].append(r["label"])
        for reason, labels in reasons.items():
            out.append(f"- {nm}: {', '.join(labels)} — {reason}.")
        gaps = max((r.get("source_gap_days") or 0) for r in rs)
        if gaps:
            out.append(f"- {nm}: kaynağın kendisinde {gaps} günlük veri kesintisi var; bu günler hesaba katılmadı.")
    if any(k == "google_trends" or v == "Google Trends" for k, v in names.items()):
        out.append("- Google Trends değerleri her terim için kendi zirvesine göre 0-100 arasında ölçeklenir; yalnızca "
                   "aynı terimin iki dönemi karşılaştırılabilir, terimler birbiriyle kıyaslanamaz. Google aramaların "
                   "bir örneklemini kullandığı için aynı sorgu tekrarlandığında değerler biraz değişebilir.")
    if any(k.endswith("_en") or "İngilizce" in v for k, v in names.items()):
        out.append("- İngilizce Vikipedi dünya geneli ilgiyi gösterir; Türkiye'ye özgü değildir.")
    out.append("- Veriler bilgi merakı ve haber görünürlüğünü ölçer; satış, stok, fiyat veya tüketici talebi "
               "hakkında bilgi içermez.")
    out.append("- Sonuçlar tek bir dönem karşılaştırmasına dayanır; mevsimsellik veya uzun vadeli eğilim ayrıca "
               "incelenmedi.")
    return out


def build_user_prompt(rows: list[dict], context: dict) -> str:
    """context: brand, window, sources (anahtar -> {display, description}), flat_threshold_pct."""
    w = context["window"]
    thr = context.get("flat_threshold_pct", 15)
    srcs = context["sources"]
    names = {k: v["display"] for k, v in srcs.items()}
    up = sorted([r for r in rows if r.get("signal") == Signal.STRONG_UP], key=lambda r: -r["pct_change"])
    down = sorted([r for r in rows if r.get("signal") == Signal.STRONG_DOWN], key=lambda r: r["pct_change"])
    flat = [r for r in rows if r.get("signal") == Signal.FLAT]

    def term_list(rs):
        return "\n".join(f"- {r['label']} ({names.get(r['source'], r['source'])}, {_pct(r['pct_change'])})"
                         for r in rs) or "- (yok)"

    parts = [
        f"Marka: {context['brand'].get('name')} | Pazar: {context['brand'].get('market')} | "
        f"Sezon: {context['brand'].get('season')}",
        f"Önceki dönem: {_d(w['baseline_start'])}–{_d(w['baseline_end'])} | "
        f"Yakın dönem: {_d(w['recent_start'])}–{_d(w['recent_end'])}",
        f"Yöntem: yakın dönem günlük ortalaması önceki dönemle karşılaştırıldı; ±%{thr:g} içindeki değişimler "
        "'belirgin değişim yok' sayıldı; düşük hacimli seriler güvenilir sayılmadı.",
        "",
        "KAYNAKLAR:",
        *[f"- {v['display']}: {v['description']}" for v in srcs.values()],
        "",
        "GÜVENİLİR YÜKSELİŞ:", term_list(up),
        "",
        "GÜVENİLİR DÜŞÜŞ:", term_list(down),
        "",
        "BELİRGİN DEĞİŞİM YOK:", term_list(flat),
        "",
        "KANIT SATIRLARI (2. bölüme aynen kopyala):",
        "\n".join(evidence_line(r, names) for r in up + down) or "- Güvenilir değişim gösteren ölçüm yok.",
        "",
        "SINIRLAR (4. bölüme aynen kopyala):",
        "\n".join(limitations(rows, names)),
        "",
        "Dört başlığı Türkçe yaz.",
    ]
    return "\n".join(parts)
