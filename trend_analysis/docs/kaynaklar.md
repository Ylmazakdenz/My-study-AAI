# Veri kaynakları

Belgede istenen aday kaynaklar (Google Trends, Pinterest Trends, YouTube, Wikimedia, GDELT, Reddit) resmi
belgelerden kontrol edildi; seçilenler gerçek isteklerle denendi.

Kontrol tarihi: **19.11.2026** (her satırın "Kanıt" sütununda da yazılı). Kaynak: resmi belgeler; resmi olmayan
bilgiler "(ikincil kaynak)" olarak işaretlendi.

## Karşılaştırma

| Kaynak | Verinin anlamı | Otomatik erişim | Gereksinim | Kapsam (TR / dönem) | Giyime katkı | Kanıt |
|---|---|---|---|---|---|---|
| **Google Trends** | Google aramalarında göreli ilgi (0-100); 19.11.2026'da pytrends ile gerçek istekte 6/6 başarılı | Resmi API **kapalı alfa** (24.07.2025'te duyuruldu, başvuruyla). `pytrends` resmi değil; Nisan 2025'te arşivlendiği bildiriliyor (ikincil kaynak), sık 429 | Alfa için başvuru; pytrends anahtarsız ama engellenebilir | TR (`geo=TR`) var; geçmiş dönem sorgulanabilir | **En güçlü sinyal**: ürün/stil arama ilgisi | [Trends API alfa](https://developers.google.com/search/apis/trends), [duyuru](https://developers.google.com/search/blog/2025/07/trends-api) — 19.11.2026 |
| **Pinterest Trends** | Pinterest aramalarında göreli hacim; haftalık 1 yıllık seri + haftalık/aylık/yıllık büyüme | `GET /v5/trends/keywords/{region}/top/{trend_type}` | İşletme hesabı + uygulama + OAuth; uç nokta sınırlı kullanıcıya açık | Bölge listesinde TR resmi sayfada doğrulanamadı; yalnız bugünün verisi | Modaya çok uygun (stil keşfi) ama **terim sorgulanamaz**, sadece en trend listesi döner | [Trends API](https://developers.pinterest.com/docs/analytics-and-reports/trends/) — 19.11.2026 |
| **YouTube Data API v3** | Video izlenme/beğeni **toplamları** (anlık) | Resmi REST API | Ücretsiz API anahtarı; günlük 10.000 birim, `search.list` 100 birim | `chart=mostPopular` + `regionCode=TR` var (1 birim); geçmiş izlenme serisi **yok**, yalnız anlık istatistik | Stil videolarına ilgi; ama trend için zaman içinde tekrar tekrar çekmek gerekir | [Kota maliyetleri](https://developers.google.com/youtube/v3/determine_quota_cost), [videos.list](https://developers.google.com/youtube/v3/docs/videos/list) — 19.11.2026 |
| **Wikimedia Analytics** | Vikipedi makalesinin günlük görüntülenmesi (bot hariç) | Resmi REST API, `per-article` uç noktası | Anahtar yok; **User-Agent zorunlu**; istekler sırayla | tr.wikipedia ≈ Türkçe okuyucu; 2015'ten bugüne günlük | Ürün tipine (trençkot, hırka...) duyulan **merak**; satın alma niyeti değil | [Analytics API](https://doc.wikimedia.org/analytics-api/), [erişim politikası](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html) — 19.11.2026 |
| **GDELT DOC 2.0** | Haberlerde terimin geçtiği **haber sayısı** (ya da tüm haberler içindeki %); 4 gerçek çalıştırmada kullanılamadı | Resmi uç nokta `api/v2/doc/doc`, `timelinevolraw` | Anahtar yok; sık istek engellenir (biz 6 sn bekliyoruz) | `sourcecountry:turkey sourcelang:turkish`; varsayılan son 3 ay, `timespan` ile 1 yıla kadar | Medya/moda gündemi (bir ürün haberlerde konuşuluyor mu) | [DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/), [1 yıl arama](https://blog.gdeltproject.org/doc-geo-2-0-api-updates-full-year-searching-and-more/) — 19.11.2026 |
| **Reddit** | Gönderi/yorum içerikleri | Resmi Data API (OAuth) | Kullanımdan önce **açık onay** şart; ticari kullanım sözleşmeli. Yeni başvuruların 31.10.2026'da kapandığı bildiriliyor (ikincil kaynak) | Türkiye/Türkçe kapsamı zayıf | Düşük | [Data API Terms](https://www.redditinc.com/policies/data-api-terms) — 19.11.2026 |

## Seçim (gerçek isteklerle denendikten sonra, 18–19.11.2026)

| Kaynak | Durum | Gerçek deneme sonucu |
|---|---|---|
| **Google Trends** (`google_trends`) | **Ana kaynak** | Ev internetinden (Mac, 19.11.2026) 6/6 terim, 56 günün hepsi geldi. Türkiye'deki aramaları ölçtüğü için giyimde ürün seçimine en doğrudan katkı veren kaynak. |
| **İngilizce Vikipedi** (`wikimedia_en`) | Yedek / doğrulama | 4 çalıştırmada (3 Colab + 1 ev) tekrar deneme eklendikten sonra 6/6. Hacim yüksek (günde 120–500), ama dünya geneli ilgi; Türkiye'ye özgü değil. |
| **Türkçe Vikipedi** (`wikimedia`) | Açık, ama zayıf sinyal | Her çalıştırmada 6/6, ama günde yalnızca 1,5–8 görüntüleme; kod hepsini "düşük hacim — güvenilir değil" olarak işaretler. |
| **GDELT** (`gdelt`) | **Kapalı** (kod duruyor) | 4 çalıştırmanın hiçbirinde karşılaştırılabilir veri alınamadı (ayrıntı aşağıda). |
| Pinterest, YouTube, Reddit | Seçilmedi | Onay gereksinimi + terim sorgulanamıyor / geçmiş seri yok / onay kapanıyor (tablodaki gerekçeler). |

**Neden Google Trends ana kaynak?** İlk çalışan kaynak Wikimedia idi (anahtarsız, resmi). Ancak Türkçe
Vikipedi'nin hacmi anlamlı sonuç için çok düşük, İngilizce Vikipedi ise Türkiye'yi temsil etmiyor. Google Trends
resmi API'si kapalı alfa olduğundan resmi olmayan pytrends ile denendi ve çalıştı. Risk: resmi olmadığı için
ileride engellenebilir; bu durumda hata açıkça kaydedilir ve hat Vikipedi ile çalışmaya devam eder. Kalıcı çözüm:
resmi alfa erişimine başvurmak.

**Google Trends sonuçlarını okurken:** değerler her terim için kendi dönemindeki zirvesine göre 0-100 arasında
ölçeklenir. Bu yüzden yalnızca **aynı terimin** iki dönemi karşılaştırılır; terimlerin değerleri birbirine
kıyaslanamaz. Sorgu seçimi sonucu etkiler (ör. "Palto" terimi için `kaşe kaban` aranıyor; `config.yaml`).
Google'a göre **0 değeri "bu terim için yeterli veri yok"** demektir; kod bu günleri sıfır değil eksik sayar
(`analysis.zero_is_missing`). Google aramaların bir örneklemini kullandığından aynı sorgu birkaç dakika arayla
biraz farklı değer verebilir (19.11.2026'da Palto: +%78,6 ve +%78,0); sınıflandırma değişmedi.

**GDELT neden kapalı (gerçek çalıştırmalardan):**
- 1. deneme (Colab): zaman aşımı ve 429 → 90 sn zaman aşımı, istekler arası bekleme ve tekrar deneme eklendi.
- 2. deneme (Colab): 56 günün 39'unda veri; eksik günler **tüm terimlerde aynı**, o günlerde GDELT toplam izlenen
  haber sayısını (`norm`) da vermiyor → GDELT'in kendi kesintisi. Ayrıca yakın dönemde izlenen toplam haber sayısı
  yarının altına indi (ort. 95.548 → 40.766); ham sayılar bu yüzden yapay olarak %35–75 "düşüyordu". Kod artık
  değerleri izlenen toplam habere oranlar, kesinti günlerini sıfır saymaz; sonuç: "hesaplanamadı".
- 3. deneme (Colab): tüm terimler 4 denemeye rağmen 429; terim başına ~2 dk (toplam ~13 dk) → art arda 2 terim 429
  alırsa kalanlar denenmez (`stop_after_consecutive_429`).
- 4. deneme (ev interneti, 19.11.2026): yine 2 boş yanıt + 2 adet 429, kalan 2 terim denenmedi → sorun Colab'a
  özgü değil.

Kaynakların sayıları **birbirine eklenmez ve karşılaştırılmaz**; her biri kendi içinde yorumlanır.

## Yıllık karşılaştırma için kaynak davranışı

| Kaynak | Yıllık seri | Not |
|---|---|---|
| Google Trends | Tek istekte geçen yılın aynı döneminden bugüne; ~9 aydan uzun dönemde **haftalık** değer döner | Ölçekleme istek başına yapıldığı için iki dönem aynı istekten alınır |
| Wikimedia | Tek istekte ~14 ay **günlük** | Mutlak sayı; istekler arası karşılaştırılabilir |
