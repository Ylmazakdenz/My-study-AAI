# Örnek çalıştırmalar

## 20261118-231912
Colab'da 18.11.2026'da gerçek kaynaklardan çekildi (Türkçe Vikipedi, İngilizce Vikipedi, GDELT).
Dönem 22.09.2026 – 16.11.2026. `raw/` ham yanıtları, `manifest.json` her isteğin kaynağını, dönemini, çekilme
zamanını ve durumunu içerir (İngilizce Vikipedi'de 2 istek 429, GDELT'te 2 terim boş yanıt — olduğu gibi bırakıldı).
`analysis.*` güncel ayarlarla (`--use-current-config`) yeniden hesaplandı. Model yorumu bu klasörde yok;
Colab'da 6a hücresiyle üretilir.

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
