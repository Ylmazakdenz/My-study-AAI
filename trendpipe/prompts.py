"""Model istemi.

Küçük modeller (llama3.2 3B) ham JSON'u yanlış okuyabiliyor (ilk denemede yatay terimlere "yükseliyor" dedi,
veri gelen terimlere "veri alınamadı" dedi). Bu yüzden Python sonuçları önce Türkçe, açık cümlelere ve hazır
gruplara çevirir; model yalnızca bunları yorumlar ve ürün seçimine bağlar.
"""

from __future__ import annotations

from .analysis import Signal

SYSTEM_PROMPT = """Sen bir giyim markasının trend analistisin. Sana Python ile hesaplanmış ölçümler ve bunların hazır
sınıflandırması veriliyor. Görevin bunları marka ekibi için yorumlamak.

KURALLAR:
1. YALNIZCA verilen ölçümleri kullan. Yeni sayı, yüzde, tarih veya kaynak uydurma. Sayıları aynen aktar.
2. "Yükseliş" veya "artış" ifadesini YALNIZCA "Güvenilir yükseliş" grubundaki terimler için kullan.
   "Düşüş" ifadesini YALNIZCA "Güvenilir düşüş" grubundaki terimler için kullan.
   "Anlamlı değişim yok" grubundakiler için "belirgin değişim yok" de.
   "Düşük hacim" grubundakiler için değişimin güvenilir olmadığını söyle.
3. "Veri alınamadı" yalnızca "Veri yok" grubunda listelenen kaynak-terim çiftleri için geçerlidir.
4. Satış, stok, ciro, fiyat veya tüketici talebi hakkında bilgi verilmedi; bunlar hakkında iddiada bulunma.
5. Kaynakların sayılarını birbirine ekleme ya da birbiriyle karşılaştırma; her kaynak farklı bir şey ölçer.
6. Tamamen Türkçe yaz; İngilizce kelime kullanma. Kısa ve maddeli yaz.

ÇIKTI BİÇİMİ (tam olarak bu dört başlık):
## 1. Öne çıkan terimler
(Güvenilir yükseliş/düşüş gösteren terimler. Hiç yoksa bunu açıkça yaz.)
## 2. Destekleyen ölçüm ve dönem
(Her öne çıkan terim için: kaynak, önceki → yakın günlük ortalama, yüzde değişim, dönemler.)
## 3. Ürün seçimine olası katkı
(Bu sinyaller hangi ürün tiplerini öne çıkarmayı ya da izlemeyi destekler; ihtiyatlı yaz.)
## 4. Bu veriyle söyleyemediklerimiz
(Ölçümlerin sınırları, düşük hacim, alınamayan veriler, satış/talep hakkında bilgi olmaması.)
"""

DIRECTION_TR = {"up": "artış", "down": "düşüş", "flat": "belirgin değişim yok"}

GROUP_TITLES = [
    (Signal.STRONG_UP, "Güvenilir yükseliş"),
    (Signal.STRONG_DOWN, "Güvenilir düşüş"),
    (Signal.FLAT, "Anlamlı değişim yok"),
    (Signal.WEAK, "Düşük hacim — değişim güvenilir değil"),
    (Signal.INSUFFICIENT, "Eksik günler nedeniyle hesaplanamadı"),
    (Signal.NO_DATA, "Veri yok"),
]


def reason_tr(row: dict) -> str:
    """Hata/durum metnini kısa Türkçe nedene çevirir (ham hata metni modele gitmez)."""
    st = row.get("fetch_status")
    if st == "not_found":
        return "kaynakta bulunamadı"
    if st == "empty":
        return "kaynak veri döndürmedi"
    if st == "skipped":
        return "bu kaynak için sorgu tanımlı değil"
    note = " ".join(row.get("notes") or []).lower()
    if "timeout" in note or "timed out" in note:
        return "kaynak zamanında yanıt vermedi"
    if "429" in note or "limit" in note:
        return "kaynağın istek sınırına takıldı"
    if "connection" in note:
        return "bağlantı hatası"
    if row.get("result") == "insufficient_data":
        return "eksik gün oranı yüksek"
    return "veri alınamadı"


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fact_line(r: dict) -> str:
    name = f"{r['label']} ({r['source']})"
    if r.get("baseline_mean") is None:
        return f"- {name}: {reason_tr(r)}"
    pct = f"%{r['pct_change']:+.1f}".replace(".", ",") if r.get("pct_change") is not None else "yüzde tanımsız"
    return (f"- {name}: günlük ortalama {_fmt(r['baseline_mean'])} → {_fmt(r['recent_mean'])}, değişim {pct}, "
            f"{DIRECTION_TR.get(r.get('direction'), '-')}")


def build_user_prompt(rows: list[dict], context: dict) -> str:
    """context: brand, season, window, sources (ad -> anlam), flat_threshold_pct."""
    w = context["window"]
    thr = context.get("flat_threshold_pct", 15)
    parts = [
        f"Marka: {context['brand'].get('name')} | Pazar: {context['brand'].get('market')} | "
        f"Sezon: {context['brand'].get('season')}",
        f"Önceki dönem: {w['baseline_start']} – {w['baseline_end']} | Yakın dönem: {w['recent_start']} – {w['recent_end']}",
        f"Yöntem: yakın dönem günlük ortalaması önceki dönemle karşılaştırıldı. ±%{thr:g} içindeki değişimler "
        "'belirgin değişim yok' sayıldı.",
        "",
        "KAYNAKLAR (her biri farklı bir şey ölçer):",
    ]
    for name, desc in context["sources"].items():
        parts.append(f"- {name}: {desc}")
    parts.append("")
    parts.append("ÖLÇÜMLER (Python tarafından hesaplandı ve gruplandı):")
    for sig, title in GROUP_TITLES:
        group = [r for r in rows if r.get("signal") == sig]
        parts.append(f"\n### {title} ({len(group)})")
        if not group:
            parts.append("- (yok)")
            continue
        group.sort(key=lambda r: -(r.get("pct_change") or 0))
        parts += [fact_line(r) for r in group]
    parts += ["", "Bu ölçümlere göre dört başlığı Türkçe yanıtla."]
    return "\n".join(parts)
