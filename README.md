# trendpipe — Giyim Trend Veri Hattı

SENG360 Agentic AI projesinin (otonom dijital prodüksiyon ve pazarlama ajansı) **Trend Analizi** katmanı.
Bir giyim markası için güncel trend verisini gerçek kaynaklardan çeker, değişimi Python ile hesaplar, mevsimsel
artışı gerçek değişimden ayırır ve sonuçları yerel bir LLM'e (Ollama) yorumlatır.

```
config/config.yaml ─► Google Trends (TR) + Vikipedi ─► ham + düzenlenmiş kayıt
   ─► dönemsel ve yıllık karşılaştırma (Python) ─► etiket: sezon üstü / mevsimsel artış …
   ─► Ollama (JSON şeması) ─► tutarlılık denetimi + öz-düzeltme ─► rapor
```

Bu aşamada ürün eşleştirme, görsel üretimi ve yayınlama **yok**.

## Kurulum

Gereksinimler: **Python 3.10+**, model adımı için **[Ollama](https://ollama.com/download)**.

```bash
git clone https://github.com/Ylmazakdenz/My-study-AAI.git
cd My-study-AAI
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt    # projeyi, `trendpipe` komutunu ve test araçlarını kurar
cp .env.example .env                   # Windows: copy .env.example .env

ollama pull llama3.1:8b                # model (~5 GB); .env'deki OLLAMA_MODEL ile aynı olmalı
trendpipe check-llm                    # model bağlantı testi
python -m pytest -q                    # testler (ağ ve model gerekmez)
```

PyCharm'da: proje açıkken *Settings → Python Interpreter* ile `.venv`'i seçin, komutları alttaki Terminal'de
çalıştırın.

## Kullanım

```bash
trendpipe all                          # veri çek → hesapla → yorumlat (≈3-4 dk)
trendpipe all --skip-llm               # modelsiz
trendpipe fetch                        # yalnızca veri çek        -> data/runs/<zaman>/
trendpipe analyze   --run latest       # yalnızca hesapla (ağ gerekmez)
trendpipe interpret --run latest       # yalnızca yorumlat
trendpipe -v fetch                     # ayrıntılı log
```

Bağlantı olmadan, repodaki gerçek örnek veriyle:

```bash
trendpipe analyze   --out-dir data/sample --run latest
trendpipe interpret --out-dir data/sample --run latest
```

`trendpipe` yerine `python -m trendpipe` da kullanılabilir.

### Terim ve kaynak seçimi (kod değişmeden)

- `config/config.yaml` → `terms:` listesi. Her terim her kaynakta ayrı sorgulanır (Google Trends Türkçe arama,
  Vikipedi makale başlığı). Ayar dosyası çalıştırmadan önce doğrulanır; yazım hataları açıkça bildirilir.
- Komuttan: `--terms trenckot,hirka`, `--term "Yelek"`, `--sources google_trends`, `--end 2026-11-15`,
  başka marka için `--config config/marka_b.yaml`.

## Çıktılar

```
data/runs/<YYYYMMDD-HHMMSS>/
├── manifest.json            # her istek: kaynak, terim, sorgu, dönem, çekilme zamanı, durum, deneme sayısı
├── run.log                  # istek / tekrar deneme / bekleme kaydı
├── raw/                     # kaynakların ham yanıtları (…__yoy.json = yıllık seri)
├── processed/timeseries.csv # düzenlenmiş seriler
├── analysis.json / .csv     # dönemsel + yıllık değişim, etiket, notlar
└── interpretation.json/.md  # model yanıtı, denetim sonucu, rapor
```

Örnek rapor bölümleri: özet · 1. öne çıkan terimler · 2. destekleyen ölçüm ve dönem (Python) · 3. ürün seçimine
katkı · 4. söyleyemediklerimiz · ek: tüm sonuçlar tablosu (Python).

## Belgeler

| Belge | İçerik |
|---|---|
| [docs/kaynaklar.md](docs/kaynaklar.md) | 6 aday kaynağın resmi belgelerle karşılaştırması ve gerçek denemelere göre seçim |
| [docs/yontem.md](docs/yontem.md) | Eksik veri kuralları, dönemsel/yıllık karşılaştırma, etiketler, model denetimi |
| [docs/kararlar.md](docs/kararlar.md) | Alınan kararlar ve onları doğuran gerçek çalıştırma bulguları |
| [data/sample/README.md](data/sample/README.md) | Repodaki gerçek örnek çalıştırmalar |
| [notebooks/colab_run.ipynb](notebooks/colab_run.ipynb) | Hocanın Colab + Ollama kurulumuyla alternatif çalıştırma |

## Proje yapısı

```
trendpipe/
├── cli.py           # komut satırı (yalnızca argüman ve ekran)
├── pipeline.py      # adımlar: fetch_run, analyze_dir — ileride MCP aracı / LangGraph düğümü
├── sources/         # kaynak adaptörleri: google_trends (ana), wikimedia (tr+en), gdelt (kapalı)
├── analysis.py      # dönemsel + yıllık karşılaştırma, etiketler
├── prompts.py       # aday listesi, kanıt satırları, JSON şeması
├── llm.py           # Ollama bağlantısı, öz-düzeltme döngüsü, rapor
├── checks.py        # model yanıtı denetimi — ileride Değerlendirme Ajanı'nın aracı
├── schema.py        # ayar dosyası doğrulaması
├── config.py · storage.py · logs.py · models.py
config/config.yaml   # marka, dönem, kaynaklar, terimler (gizli bilgi yok)
.env.example         # model adresi/adı (gizli bilgiler .env'de, repoya girmez)
```

## Sonraki aşamaya köprü

| Ders bileşeni | Bu katmandaki karşılığı |
|---|---|
| API | Google Trends, Wikimedia (gerçek veri) |
| LLM | Ollama, JSON şemalı yanıt |
| MCP | `pipeline.fetch_run` / `analyze_dir` ve kaynak adaptörleri araç olarak açılmaya hazır |
| Değerlendirme / güvenlik | `checks.review` + öz-düzeltme döngüsü |
| RAG, LangGraph | henüz yok (sonraki aşama: marka kataloğu, ajan grafiği) |
