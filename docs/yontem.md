# Yöntem

Hesaplamaları Python yapar; model yalnızca hesaplanan sonuçları yorumlar.

## 1. Veri çekme

Her terim × kaynak için iki seri çekilir:

| Seri | Dönem | Amaç |
|---|---|---|
| `main` | önceki 28 gün + yakın 28 gün (günlük) | dönemsel karşılaştırma |
| `yoy` | geçen yılın aynı döneminden bugüne (Google Trends'te haftalık) | yıllık karşılaştırma |

Bitiş tarihi, geç yayımlanan veriyi dışlamak için bugünden 2 gün öncedir. Geçen yılın dönemi yakın dönemin
**364 gün** (52 hafta) öncesidir; böylece haftanın günleri hizalı kalır (hafta sonu etkisi karışmaz).

Her istek `manifest.json`'a kaynak, terim, sorgu, dönem, çekilme zamanı (UTC), HTTP kodu, deneme sayısı ve durumla
yazılır; ham yanıt `raw/` altında olduğu gibi saklanır; ayrıntılı istek kaydı `run.log`'dadır.

### İstek durumları

| Durum | Anlamı |
|---|---|
| `ok` | Veri geldi |
| `empty` | İstek başarılı, kaynak veri döndürmedi |
| `not_found` | Terim/makale kaynakta yok (ör. Vikipedi 404) |
| `error` | Bağlantı, zaman aşımı, hız sınırı (429), beklenmeyen yanıt — mesaj kaydedilir |
| `skipped` | Bu terim için o kaynağa sorgu tanımlı değil |

Geçici hatalarda (zaman aşımı, 429, 5xx) artan beklemeyle tekrar denenir; sunucu `Retry-After` verirse ona uyulur.
Bir kaynak art arda N istekte 429 alırsa kalan istekler denenmez ve "Denenmedi" olarak kaydedilir
(`stop_after_consecutive_429`).

### Önbellek

Aynı veri 24 saat içinde kaynaktan tekrar çekilmez (`cache.ttl_hours`). Anahtar: kaynak tipi + veriyi etkileyen
ayarlar (proje, bölge, dil, örnek sayısı) + sorgu + başlangıç/bitiş tarihi. Veri günlük ve dönem bitişi bugünden
2 gün önce olduğu için aynı gün içinde değişmez; ertesi gün dönem kayar ve anahtar kendiliğinden değişir.
Yalnızca eksiksiz başarılı yanıtlar saklanır; hata/429/boş yanıt ve kısmi sonuçlar (ör. Vikipedi proje toplamı
alınamadı) sonraki çalıştırmada yeniden denenir. Anahtara kod sürümü de girer; veri işleme değiştiğinde eski kayıtlar
kullanılmaz. Süresi dolan kayıtlar her çalıştırmanın başında diskten silinir (önbellek birikmez); eski çalıştırma
klasörleri `trendpipe clean --keep N --yes` ile temizlenir (`data/sample` korunur). Önbellekten gelen
sonuç `manifest.json`'da `from_cache`, ilk `fetched_at` ve `cache_origin_run` ile işaretlenir; ham yanıt yeni
çalıştırmanın klasörüne de yazılır. `--refresh` önbelleği yok sayar.

## 2. Eksik veri: asla sıfır sayılmaz

- Gelmeyen gün **eksik**tir. Bir pencerede günlerin %80'inden azı varsa değişim hesaplanmaz (`insufficient_data`).
- **Kaynak kesintisi:** bir kaynağın tüm terimlerinde aynı gün eksikse bu kaynağın kendi kesintisidir; o günler
  paydadan çıkarılır (en az 3 başarılı seri gerekir).
- **Google Trends 0 değeri:** Google'a göre "bu terim için yeterli veri yok" demektir → eksik sayılır
  (`analysis.zero_is_missing`).
- **Vikipedi:** görüntülenmesi olmayan günü hiç döndürmez → eksik sayılır (temkinli yaklaşım).
- **Kaynağın genel hacmi:** değer kaynağın o günkü toplamına oranlanır (`analysis.normalize_by_norm`):
  Vikipedi'de projenin toplam insan görüntülemesine (milyonda), GDELT'te izlenen toplam habere (10.000'de).
  Böylece kaynağın genel trafiğindeki değişim (ör. Vikipedi'nin yıllık trafik düşüşü) terim değişimi sanılmaz.
  Toplamı çok düşük günler bozuk sayılıp çıkarılır.

## 3. Karşılaştırmalar

**Dönemsel:** yakın dönem günlük ortalaması ↔ önceki dönem günlük ortalaması → `pct_change`.

**Yıllık:** yakın dönem ↔ geçen yılın aynı dönemi → `yoy_pct_change`. İki dönem **aynı seriden** alınır (Google
Trends'te ölçekleme istek başına yapıldığı için şart). Haftalık seride yalnızca 7 günü de pencereye düşen haftalar
sayılır (28 günlük pencerede 3–4 hafta).

Her iki karşılaştırmada:
- ±%15 içi → "belirgin değişim yok" (`analysis.flat_threshold_pct`)
- ortalamalar düşük hacim eşiğinin altındaysa → "düşük hacim — güvenilir değil" (`analysis.low_volume`)

## 4. Etiket (`trend_label`)

Giyimde ilgi mevsimle değişir (palto her Kasım artar). Dönemsel artış tek başına trend demek değildir; yıllık
karşılaştırma bunu ayırır:

| Dönemsel | Yıllık | Etiket | Anlamı |
|---|---|---|---|
| artış | artış | **sezon üstü artış** | Son dönemde arttı ve geçen yılın aynı döneminden de yüksek |
| artış | değişim yok | mevsimsel artış | Mevsimin olağan artışı, geçen yılla benzer düzey |
| artış | düşüş | mevsimsel artış, geçen yıldan zayıf | |
| değişim yok | artış | geçen yıla göre yüksek | Son dönemde sabit ama yıllık bazda yüksek |
| düşüş | düşüş | **sezon altı düşüş** | |
| düşüş | değişim yok | mevsimsel düşüş | |
| değişim yok | değişim yok | belirgin değişim yok | |
| — | hesaplanamadı | artış/düşüş (geçen yılla karşılaştırılamadı) | |

Düşük hacim, hesaplanamadı ve veri yok durumları etiket olarak aynen geçer.

## 5. Model yorumu

1. Python, **aday listesini** (güvenilir sinyali olan terim-kaynak çiftleri), kanıtları ve sınırları hazırlar.
2. Model (Ollama), bir **JSON şemasına** uyan yanıt verir: öne çıkanlar + neden, ürün katkısı,
   söyleyemediklerimiz, özet.
3. Yanıt denetlenir (`trendpipe/checks.py`):
   - öne çıkanlar yalnızca aday listesinden mi; ürün önerileri yalnızca seçilen terimler için mi
   - hesaplanan sonuçlarda olmayan yüzde var mı
   - hesaplanan yönle çelişen artış/düşüş iddiası var mı; "geçen yıl" ifadeleri ayrıca yıllık yönle karşılaştırılır
   - düşüş / geçen yıldan düşük etiketli terime "öne çıkar" önerisi var mı
   - verisi olan kaynak için "veri yok" ya da verisi olmayan kaynak kanıt olarak gösterilmiş mi
   - kaynaklar sayısal olarak karşılaştırılmış mı; satış/stok/ciro gibi veride olmayan metrik var mı; İngilizce kelime
4. Sorun varsa sorunlar modele geri bildirilip **bir kez daha** yanıt istenir (öz-düzeltme). En az sorunlu yanıt
   kullanılır; kalan sorunlar raporun başında ⚠️ ile listelenir.
5. Rapor (`interpretation.md`) Python tarafından oluşturulur. 2. sorunun (ölçüm ve dönem) sayıları ve raporun
   sonundaki tüm sonuç tablosu modelden bağımsızdır.

## 6. Sağlamlık

- Bir kaynak beklenmeyen bir hata verse de çalıştırma yarıda kalmaz; o istek `error` olarak kaydedilir.
- Google Trends'te yalnızca geçici hatalarda (429, zaman aşımı, bağlantı, 5xx) beklenip tekrar denenir; kalıcı
  hatalarda (ör. 400) beklenmez.
- Ayar dosyasındaki kaynak ayarlarının hem adı hem türü denetlenir (ör. `samples: "iki"`, `geo: turkiye`).
- `interpret`, yorumdan önce analizi güncel kodla yeniden yapar; eski bir sürümün analizi kullanılmaz.
- Aynı saniyede başlayan iki çalıştırma birbirinin klasörünü ezmez (`-2` eki).

## 7. Bilinen sınırlar

- Göreli ilgi ve bilgi merakı ölçülür; satış, stok, fiyat veya talep verisi yoktur.
- Google Trends resmi değildir (pytrends) ve örnekleme kullanır; aynı sorgu biraz farklı değer verebilir.
- Sorgu seçimi sonucu etkiler (ör. "Palto" için `kaşe kaban`).
- Yıllık karşılaştırma tek bir önceki yıla dayanır.
- İngilizce Vikipedi dünya geneli ilgiyi gösterir; Türkiye'ye özgü değildir.
- Vikipedi görüntülemesi makale başlığına göre sayılır; başlık bir yönlendirme sayfasıysa yalnızca yönlendirmenin
  görüntülemesi gelir. `config.yaml`'daki başlıklar asıl makale başlığı olmalıdır.
