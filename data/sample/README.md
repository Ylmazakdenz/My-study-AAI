# Örnek çalıştırmalar

`--run latest` en yeni klasörü (20261119-162956) seçer; diğerlerini `--run data/sample/<klasör>` ile verin.

## 20261119-162956 (en yeni, önerilen)
Yerel bilgisayarda (Mac, ev interneti, PyCharm) 19.11.2026'da `python -m trendpipe all --skip-llm` ile çekildi.
**18/18 istek başarılı:** Google Trends (Türkiye, ana kaynak), Türkçe ve İngilizce Vikipedi. Dönem 23.09.2026 –
17.11.2026. Google Trends'te "kaşe kaban" sorgusunda 2 gün 0 (Google'a göre "yeterli veri yok") var; analizde bu
günler eksik sayıldı. Model yorumu Colab'da 6a hücresiyle üretilir.

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
python -m trendpipe analyze   --out-dir data/sample --run latest
python -m trendpipe interpret --out-dir data/sample --run latest
```

Yeni örnek oluşturmak için (gerçek veri çeker):

```bash
python -m trendpipe all --out-dir data/sample --skip-llm
```
