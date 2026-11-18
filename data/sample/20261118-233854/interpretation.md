# Trend yorumu

- Model: `llama3.1:8b` (Ollama) — sıcaklık 0.2
- Oluşturma: 2026-11-18T23:52:16+00:00 — süre 21.33 sn
- Çalıştırma: `20261118-233854` — dönem 2026-09-22 → 2026-11-16
- Tutarlılık kontrolü: ✅ Yanıt hesaplanan sonuçlarla tutarlı.

- Not: Tutarlılık kontrolü düzeltilmiş denetim sürümüyle yeniden çalıştırıldı; model yanıtı aynen korundu (bkz. interpretation.json → check_original).

---

**1. Öne çıkan terimler**

- Hırka: İngilizce Vikipedi'nde günlük ortalama 203,1'den 249,2'ye yükseldi, artış %22,7.
- Kazak: İngilizce Vikipedi'nde günlük ortalama 167,9'dan 199,9'a yükseldi, artış %19,1.
- Palto: İngilizce Vikipedi'nde günlük ortalama 123,2'den 143,9'a yükseldi, artış %16,8.

**2. Destekleyen ölçüm ve dönem**

- Hırka — İngilizce Vikipedi: günlük ortalama 203,1 (22.09.2026–19.10.2026) → 249,2 (20.10.2026–16.11.2026), değişim %+22,7
- Kazak — İngilizce Vikipedi: günlük ortalama 167,9 (22.09.2026–19.10.2026) → 199,9 (20.10.2026–16.11.2026), değişim %+19,1
- Palto — İngilizce Vikipedi: günlük ortalama 123,2 (22.09.2026–19.10.2026) → 143,9 (20.10.2026–16.11.2026), değişim %+16,8

**3. Ürün seçimine olası katkı**

- Hırka: Bu ilgiyi destekleyerek, kış aylarında sıcak ve konforlu kıyafetler olan hırka tipi ürünlerin ön plana çıkmasını destekleyebilir.
- Kazak: Bu ilgiyi destekleyerek, kış aylarında sıcak ve konforlu kıyafetler olan kazak tipi ürünlerin ön plana çıkmasını destekleyebilir.
- Palto: Bu ilgiyi destekleyerek, kış aylarında sıcak ve konforlu kıyafetler olan palto tipi ürünlerin ön plana çıkmasını destekleyebilir.

**4. Bu veriyle söyleyemediklerimiz**

- Türkçe Vikipedi: Trençkot, Palto, Hırka, Kazak, Kot pantolon, Bot / Çizme için hacim çok düşük (günlük ortalama 1,5–7,9); değişimler güvenilir değil.
- GDELT haberleri: Trençkot, Hırka, Kazak, Kot pantolon, Bot / Çizme — kaynağın istek sınırına takıldı.
- GDELT haberleri: Palto — kaynak bu dönemde eşleşen veri döndürmedi.
- İngilizce Vikipedi dünya geneli ilgiyi gösterir; Türkiye'ye özgü değildir.
- Veriler bilgi merakı ve haber görünürlüğünü ölçer; satış, stok, fiyat veya tüketici talebi hakkında bilgi içermez.
- Sonuçlar tek bir dönem karşılaştırmasına dayanır; mevsimsellik veya uzun vadeli eğilim ayrıca incelenmedi.

---

## Ek: Python'un hesapladığı sonuçlar (modelden bağımsız)

| Terim | Kaynak | Önceki ort. | Yakın ort. | Değişim | Sınıf |
|---|---|---:|---:|---:|---|
| Hırka | İngilizce Vikipedi | 203,1 | 249,2 | %+22,7 | güvenilir artış |
| Kazak | İngilizce Vikipedi | 167,9 | 199,9 | %+19,1 | güvenilir artış |
| Palto | İngilizce Vikipedi | 123,2 | 143,9 | %+16,8 | güvenilir artış |
| Bot / Çizme | İngilizce Vikipedi | 138,2 | 137,1 | %-0,8 | belirgin değişim yok |
| Kot pantolon | İngilizce Vikipedi | 494,9 | 498,7 | %+0,8 | belirgin değişim yok |
| Trençkot | İngilizce Vikipedi | 359,2 | 394,3 | %+9,8 | belirgin değişim yok |
| Bot / Çizme | Türkçe Vikipedi | 1,7 | 1,6 | %-7,8 | düşük hacim |
| Hırka | Türkçe Vikipedi | 2,1 | 1,9 | %-7,0 | düşük hacim |
| Kazak | Türkçe Vikipedi | 1,5 | 2,3 | %+56,1 | düşük hacim |
| Kot pantolon | Türkçe Vikipedi | 7,1 | 7,9 | %+11,1 | düşük hacim |
| Palto | Türkçe Vikipedi | 4,2 | 4,4 | %+4,2 | düşük hacim |
| Trençkot | Türkçe Vikipedi | 3,0 | 2,7 | %-9,5 | düşük hacim |
| Bot / Çizme | GDELT haberleri | - | - | - | veri yok (kaynağın istek sınırına takıldı) |
| Hırka | GDELT haberleri | - | - | - | veri yok (kaynağın istek sınırına takıldı) |
| Kazak | GDELT haberleri | - | - | - | veri yok (kaynağın istek sınırına takıldı) |
| Kot pantolon | GDELT haberleri | - | - | - | veri yok (kaynağın istek sınırına takıldı) |
| Palto | GDELT haberleri | - | - | - | veri yok (kaynak bu dönemde eşleşen veri döndürmedi) |
| Trençkot | GDELT haberleri | - | - | - | veri yok (kaynağın istek sınırına takıldı) |
