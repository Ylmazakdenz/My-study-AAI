"""Model istemleri. Model yalnızca Python'un hesapladığı sonuçları yorumlar."""

from __future__ import annotations

import json

SYSTEM_PROMPT = """Sen bir giyim markasının trend analistisin. Sana Python ile hesaplanmış ölçümler veriliyor.

KURALLAR:
1. Yalnızca verilen ölçümleri kullan. Yeni sayı, yüzde, tarih veya kaynak UYDURMA.
2. Satış, stok, ciro, fiyat veya tüketici talebi hakkında bilgi verilmedi; bunlar hakkında iddiada bulunma.
3. Her kaynağın ölçtüğü şey farklıdır (sayfa görüntüleme, haber sayısı, göreli arama ilgisi). Kaynakların sayılarını
   birbirine ekleme ya da doğrudan karşılaştırma; her ölçümü kendi kaynağının anlamıyla yorumla.
4. "result" alanı "computed" olmayan satırlar için değişim hesaplanamamıştır; bunları yükseliş/düşüş olarak yorumlama,
   veri eksikliği olarak belirt.
5. "Düşük hacim" notu olan satırlarda değişimin gürültü olabileceğini söyle.
6. Veri bir sonuç için yetersizse bunu açıkça yaz.
7. Kısa ve maddeli yaz. Türkçe yaz.

ÇIKTI BİÇİMİ (tam olarak bu dört başlık):
## 1. Öne çıkan terimler
## 2. Destekleyen ölçüm ve dönem
## 3. Ürün seçimine olası katkı
## 4. Bu veriyle söyleyemediklerimiz
"""


_KEEP = ("source", "term_id", "label", "category", "query", "result", "baseline_mean", "recent_mean",
         "pct_change", "direction", "recent_slope_per_day", "baseline_coverage", "recent_coverage",
         "rank_in_source", "notes")


def compact_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        c = {k: r.get(k) for k in _KEEP if r.get(k) not in (None, [], "")}
        out.append(c)
    return out


def build_user_prompt(rows: list[dict], context: dict) -> str:
    """context: brand, season, window, sources (ad -> anlam açıklaması)."""
    parts = [
        f"Marka: {context['brand'].get('name')} | Pazar: {context['brand'].get('market')} | "
        f"Sezon: {context['brand'].get('season')}",
        f"Önceki dönem: {context['window']['baseline_start']} – {context['window']['baseline_end']}",
        f"Yakın dönem: {context['window']['recent_start']} – {context['window']['recent_end']}",
        "Karşılaştırma: yakın dönem günlük ortalaması, önceki dönem günlük ortalamasına göre yüzde değişim "
        "(pct_change). direction: up/down/flat.",
        "",
        "KAYNAKLAR VE ÖLÇTÜKLERİ:",
    ]
    for name, desc in context["sources"].items():
        parts.append(f"- {name}: {desc}")
    parts += ["", "ÖLÇÜMLER (JSON):", json.dumps(compact_rows(rows), ensure_ascii=False, indent=1), "",
              "Bu ölçümlere göre dört başlığı yanıtla."]
    return "\n".join(parts)
