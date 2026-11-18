# Örnek çalıştırmalar

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
