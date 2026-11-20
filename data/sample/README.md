# Örnek çalıştırmalar

`--run latest` en yeni klasörü (20261120-212027) seçer; diğerlerini `--run <klasör>` ile verin. Örnekleri yeniden
çalıştırırken önce `data/runs/`'a kopyalayın; aksi halde repodaki örnek dosyalar değişir.

## 20261120-212027 (en yeni, önerilen — tam örnek)
Yerel bilgisayarda (Mac, ev interneti) 20.11.2026'da `trendpipe all` ile çekildi. **36/36 istek başarılı:** 3 kaynak
(Google Trends — Türkiye, Türkçe ve İngilizce Vikipedi) × 6 terim × (ana seri + geçen yılın aynı dönemi). Dönemler:
önceki 24.09–21.10.2026, yakın 22.10–18.11.2026, geçen yıl 23.10–19.11.2025. Google Trends'te 1 istek 429 aldı,
bekleyip tekrar denenince başarılı oldu. Vikipedi değerleri projenin günlük toplam trafiğine oranlandı (milyonda pay).

Öne çıkanlar (Google Trends, Türkiye): **Palto** %+72,1 (geçen yıla göre %+33,1) ve **Kazak** %+28,6 (%+15,7) sezon
üstü artış; **Bot / Çizme** son dönemde sabit ama geçen yıldan %+65,3 yüksek; **Trençkot** %−40,4 mevsimsel düşüş.

`interpretation.md`: `llama3.1:8b` yorumu (v0.3.3), tek denemede tutarlılık kontrolü ✅. Bu çalıştırmanın v0.3.0 ve
v0.3.2 ile alınan önceki yorumlarında görülen sorunlar ve düzeltmeleri: [docs/kararlar.md](../../docs/kararlar.md)
(K17); o yanıtlar `tests/fixtures/` altında regresyon testi olarak duruyor.

## 20261119-162956
Yerel bilgisayarda (Mac, ev interneti, PyCharm) 19.11.2026'da `python -m trendpipe all --skip-llm` ile çekildi.
**18/18 istek başarılı:** Google Trends (Türkiye, ana kaynak), Türkçe ve İngilizce Vikipedi. Dönem 23.09.2026 –
17.11.2026. Google Trends'te "kaşe kaban" sorgusunda 2 gün 0 (Google'a göre "yeterli veri yok") var; analizde bu
günler eksik sayıldı. Bu çalıştırmada yıllık seri yoktur (yıllık karşılaştırma sonradan eklendi); analizde "geçen yılla
karşılaştırılamadı" olarak görünür. Yıllık karşılaştırmalı tam örnek: 20261120-212027.

## 20261118-233854
Colab, 18.11.2026, tekrar deneme kodunun eklendiği sürüm. **Türkçe ve İngilizce Vikipedi'nin 12 isteğinin hepsi
başarılı.** GDELT'te 5 terim 4 denemeye rağmen 429 (hız sınırı), 1 terim boş yanıt — hata kaydı olarak olduğu gibi
bırakıldı. `interpretation.md`: `llama3.1:8b` yorumu. Model yanıtı değiştirilmedi; tutarlılık kontrolü, '**4.**'
biçimindeki başlığı tanımayan eski denetimin yanlış alarmı düzeltildikten sonra yeniden çalıştırıldı (✅).

## 20261118-231912
GDELT kesinti ve izleme hacmi düşüşü örneği.
Colab'da 18.11.2026'da gerçek kaynaklardan çekildi (Türkçe Vikipedi, İngilizce Vikipedi, GDELT).
Dönem 22.09.2026 – 16.11.2026. `raw/` ham yanıtları, `manifest.json` her isteğin kaynağını, dönemini, çekilme
zamanını ve durumunu içerir (İngilizce Vikipedi'de 2 istek 429, GDELT'te 2 terim boş yanıt — olduğu gibi bırakıldı).
`analysis.*` güncel `config/config.yaml` ayarlarıyla yeniden hesaplandı. `interpretation.md`: Colab'da
`llama3.1:8b` ile 6a hücresinde üretilen yorum (tutarlılık kontrolü ✅). `interpretation.json`'daki yanıt bu
çıktıdan birebir alındı; istem ve kontrol aynı kod sürümüyle yeniden üretildi.

Bu klasör, gerçek kaynaklardan çekilmiş ve repoya eklenmiş örnek çalıştırmaları içerir. Bağlantı sorunu
olduğunda hesaplama ve model yorumu bu verilerle tekrar denenir:

```bash
trendpipe analyze   --out-dir data/sample --run latest
trendpipe interpret --out-dir data/sample --run latest
```

Yeni örnek oluşturmak için (gerçek veri çeker):

```bash
trendpipe all --out-dir data/sample
```

Not: 18.11 tarihli iki çalıştırmanın `interpretation.*` dosyaları, model çıktısı JSON şemasına geçmeden önceki
(serbest metin) biçimdedir; tarihsel kayıt olarak bırakılmıştır.
