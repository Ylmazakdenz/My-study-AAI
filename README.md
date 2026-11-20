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
trendpipe doctor                       # kurulum kontrolü: Python, paketler, ayarlar, Ollama ve model, klasörler
python -m pytest -q                    # testler (ağ ve model gerekmez)
```

PyCharm'da: proje açıkken *Settings → Python Interpreter* ile `.venv`'i seçin, komutları alttaki Terminal'de
çalıştırın.

## Kullanım

```bash
trendpipe all                          # veri çek → hesapla → yorumlat (ilk çalıştırma ≈5-6 dk)
trendpipe all --skip-llm               # modelsiz
trendpipe fetch                        # yalnızca veri çek        -> data/runs/<zaman>/
trendpipe analyze   --run latest       # yalnızca hesapla (ağ gerekmez)
trendpipe interpret --run latest       # analizi güncel kodla yeniler ve yorumlatır
trendpipe -v fetch                     # ayrıntılı log
trendpipe all --refresh                # önbelleği yok say, her şeyi kaynaktan yeniden çek
trendpipe clean --keep 10              # eski çalıştırmaları temizle (önce planı gösterir; silmek için --yes)
```

Aynı veri (kaynak + ayarlar + sorgu + dönem) **24 saat** içinde kaynaktan tekrar çekilmez; önbellekten gelir ve
terminalde `[ÖNB]` ile, kayıtta ilk çekilme zamanıyla işaretlenir. Yalnızca eksiksiz başarılı yanıtlar saklanır;
süresi dolan kayıtlar her çalıştırmanın başında diskten silinir.

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

## Model bağlantısı

**Hocanın kodu** (`SENG360_Agentic_AI_Search_LLMs_V1`) Ollama'yı Google Colab'a kurar, sunucuyu Colab makinesinin
**içinde** `localhost:11434`'te başlatır, `llama3.2` modelini indirir ve `ollama` Python paketiyle
`ollama.chat(...)` çağırır. Yani bağlantı uzak bir sunucuya değil, aynı makinedeki **yerel Ollama**'yadır.

**Bu projede** aynı yöntem kullanılır (`ollama` paketi + Ollama sunucusu); Ollama bilgisayara kurulur
(Mac/Windows uygulaması), adres ve model `.env`'den okunur. Anahtar ya da şifre gerekmez; `.env` repoya girmez.

| `.env` değişkeni | Değer | Not |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Yerel kurulumda ve hocanın Colab kurulumunda aynı |
| `OLLAMA_MODEL` | `llama3.1:8b` | Hocanın notebook'u T4 için `llama3.2` (3B) ve `llama3.1` (8B) önerir; 3B Türkçe yorumda hata yaptığı için 8B ([kararlar K2](docs/kararlar.md)) |
| `OLLAMA_TEMPERATURE`, `OLLAMA_TIMEOUT` | `0.2`, `300` | |

Hocanın Colab kurulumuyla çalıştırmak için: [notebooks/colab_run.ipynb](notebooks/colab_run.ipynb) (güncel Ollama
kurulumu için `zstd` paketi eklendi).

## Veri kaynakları (kısa karşılaştırma)

Aday kaynaklar güncel resmi belgelerden kontrol edildi (kontrol tarihi: **19.11.2026**). Seçilenler gerçek istekle
denendi. Ayrıntı ve gerçek deneme sonuçları: [docs/kaynaklar.md](docs/kaynaklar.md).

| Kaynak | Verinin anlamı | Otomatik erişim | Gereksinimler | Kapsam (Türkiye / tarih aralığı) | Projeye katkı | Kanıt (resmi belge, 19.11.2026) | Durum |
|---|---|---|---|---|---|---|---|
| Google Trends | Arama ilgisi (0-100, göreli) | Resmi API kapalı alfa; `pytrends` (resmi değil) | Alfa için başvuru; pytrends anahtarsız ama hız sınırlı | TR var; geçmiş dönem sorgulanabilir | Ürün/stil arama ilgisi — en güçlü sinyal | [Trends API alfa](https://developers.google.com/search/apis/trends) | **Ana kaynak** — gerçek istekle 6/6 |
| Wikimedia | Vikipedi sayfa görüntüleme (bilgi merakı) | Resmi REST API | Anahtar yok; User-Agent zorunlu | tr + en Vikipedi; 2015'ten bugüne günlük | Ürün tipine merak; Türkçe hacim çok düşük, İngilizce dünya geneli | [Analytics API](https://doc.wikimedia.org/analytics-api/) | **Yedek** — gerçek istekle 12/12 |
| GDELT | Haber görünürlüğü (haber sayısı) | Resmi uç nokta | Anahtar yok; sık istek engellenir | TR kaynaklı Türkçe haberler; son ~1 yıl | Moda gündemi | [DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | **Kapalı** — 4 denemede karşılaştırılabilir veri yok |
| Pinterest Trends | Pinterest arama hacmi | Resmi API | İşletme hesabı + uygulama onayı | TR doğrulanamadı; yalnız bugünün verisi | Stil keşfi; ama terim sorgulanamıyor | [Trends API](https://developers.pinterest.com/docs/analytics-and-reports/trends/) | Seçilmedi (onay) |
| YouTube Data API | Video izlenme/beğeni toplamları | Resmi API | Ücretsiz anahtar; günlük kota | `regionCode=TR`; geçmiş seri yok | Video ilgisi; zaman serisi yok | [videos.list](https://developers.google.com/youtube/v3/docs/videos/list) | Seçilmedi (tek seferlik toplam) |
| Reddit | Gönderi ve yorumlar | Resmi API (OAuth) | Ön onay; ticari kullanım sözleşmeli | TR kapsamı zayıf | Düşük | [Data API Terms](https://www.redditinc.com/policies/data-api-terms) | Seçilmedi (onay) |

Neden Google Trends ana kaynak: Türkiye'deki aramaları doğrudan ölçen tek kaynak; ilk çalışan kaynak Wikimedia idi
ama Türkçe Vikipedi'nin hacmi anlamlı sonuç için çok düşük, İngilizce Vikipedi ise Türkiye'yi temsil etmiyor.

## Karşılaşılan engeller

| Denenen işlem | Alınan hata | Çözüm |
|---|---|---|
| Hocanın Colab kodu: `curl -fsSL https://ollama.com/install.sh \| sh` | `ERROR: This version requires zstd for extraction` | Kuruluma `zstd` paketi eklendi (`notebooks/colab_run.ipynb`) |
| GDELT'ten veri çekme (Colab ve ev interneti) | `ReadTimeout`, `HTTP 429: Please limit requests to one every 5 seconds`; gelen veride 17 gün eksik | Zaman aşımı, bekleme ve tekrar deneme eklendi; eksik günler GDELT'in kendi kesintisi olduğu için sıfır sayılmadı; 4 denemede de karşılaştırılabilir veri alınamayınca kapatıldı |
| GDELT ham haber sayısıyla karşılaştırma | Tüm terimler %35–75 "düşüyordu" | GDELT'in izlediği toplam haber sayısı yarıya inmişti; değerler toplam habere oranlandı |
| Google Trends, aynı gün art arda çalıştırma | `TooManyRequestsError ... code 429` | İstekler arası 15 sn, 429'da 60/120 sn bekleyip tekrar; aynı veri 24 saat önbellekten; art arda 429'da kalan terimler denenmez |
| Google Trends "kaşe kaban" | Bazı günler `0` | Google'a göre 0 = "yeterli veri yok"; sıfır değil eksik sayıldı |
| Vikipedi geçen yılla karşılaştırma | Tüm makaleler geçen yıla göre %27–62 düşük | Vikipedi'nin genel trafiği düşmüş; değerler projenin toplam trafiğine oranlandı |
| Model yorumu (`llama3.2`, sonra `llama3.1:8b`) | Belirgin değişimi olmayan terime "artıyor", veride olmayan "satış artışı", Türkçe-İngilizce karışık, geçen yıldan düşük ürüne "öne çıkar" | `llama3.1:8b`; model JSON şemasıyla yanıt veriyor, yanıt hesaplanan sonuçlarla otomatik denetleniyor, sorun varsa model bir kez daha yanıtlıyor; ayrıntı: [docs/kararlar.md](docs/kararlar.md) |
| Model yorumu, 3 kaynak birlikte (20.11) | Aynı terim iki kaynaktan öne çıkarıldı, öneriler tekrarlandı; "geçen yıldan yüksek" terime "sezon üstü", sezon üstü terime "mevsimsel artış" dendi | Terim başına tek aday (öncelik Google Trends); ürün önerisi tonu etikete göre Python'da; etiket ifadeleri denetleniyor ([K17](docs/kararlar.md)) |

## Ortak kararlardan farklı yapılanlar (onayın gerekiyor)

| Ortak karar | Yapılan | Gerekçe |
|---|---|---|
| Hocanın Ollama kurulum kodu ve bağlantı yöntemi | Bağlantı yöntemi aynı (`ollama` paketi). Kurulum Colab yerine yerel Ollama uygulaması; hocanın Colab kurulumu `notebooks/colab_run.ipynb`'de çalışır halde duruyor | Google Trends yalnızca yerel bağlantıdan çalıştı; Colab oturumu her seferinde sıfırlanıyor |
| Model (hocanın kodunda `llama3.2`) | `llama3.1:8b` | 3B model yorumda hata yaptı; hocanın notebook'u 8B'yi de öneriyor. `.env`'de tek satırla değiştirilebilir |
| Güçlü yerel GPU varsaymıyoruz | GPU şart değil: 8B model GPU'suz bilgisayarda da çalışır ama yavaştır; zayıf bilgisayarda `OLLAMA_MODEL=llama3.2` ya da Colab | — |
| Aday kaynaklar | Ana kaynak resmi olmayan `pytrends` ile Google Trends; GDELT kapalı | Yukarıdaki tablo; kalıcı çözüm için resmi Google Trends API alfa başvurusu önerilir |
| Repo | Kod şu an kişisel repoda (`Ylmazakdenz/My-study-AAI`) | Takım reposu kurulunca taşınacak; değişecek yerler: `notebooks/colab_run.ipynb` (`REPO`), `trendpipe/config.py` (`PROJECT_URL`) |

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

Model yorumu görev belgesindeki dört soruyu yanıtlar: 1. öne çıkan terim/konu · 2. destekleyen ölçüm ve dönem ·
3. giyim mağazasının ürün seçimine katkısı · 4. bu veriyle söyleyemediklerimiz (+ kısa özet). Hesaplamaları Python
yapar; modelin yanıtındaki terim, yüzde ve tarihler hesaplanan sonuçlarla otomatik denetlenir. Raporda 2. sorunun
yanına Python'un hesabı, sonuna tüm sonuçların tablosu eklenir.

## Belgeler

| Belge | İçerik |
|---|---|
| [docs/kaynaklar.md](docs/kaynaklar.md) | 6 aday kaynağın resmi belgelerle karşılaştırması ve gerçek denemelere göre seçim |
| [docs/yontem.md](docs/yontem.md) | Eksik veri kuralları, dönemsel/yıllık karşılaştırma, etiketler, model denetimi |
| [docs/kararlar.md](docs/kararlar.md) | Alınan kararlar ve onları doğuran gerçek çalıştırma bulguları |
| [docs/ciktilar.md](docs/ciktilar.md) | Çıktı dosyalarının alan alan açıklaması (sonraki ajanların girdisi) |
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
├── schema.py        # ayar dosyası doğrulaması (adlar ve türler)
├── doctor.py        # kurulum kontrolü
├── provenance.py    # çalıştırma ortamı kaydı (git commit, Python, paketler)
├── cache.py         # istek önbelleği (24 saat, yalnız başarılı yanıtlar)
├── config.py · storage.py · logs.py · models.py
config/config.yaml   # marka, dönem, kaynaklar, terimler (gizli bilgi yok)
.env.example         # model adresi/adı (gizli bilgiler .env'de, repoya girmez)
```

## Geliştirme

```bash
python -m pytest -q          # 100+ test; ağ ve model gerekmez (sahte oturum / sahte Ollama)
ruff check trendpipe tests   # kod denetimi
```

- Her `push`'ta GitHub Actions testleri ve lint'i Python 3.10 / 3.12 / 3.13'te çalıştırır.
- Veri işleme (kaynak ayrıştırma, oranlama, analiz) değişirse `trendpipe/__init__.py`'deki sürümü artırın: önbellek
  anahtarı sürümü içerir, böylece eski biçimde işlenmiş veri kullanılmaz.
- Gerçek çalıştırmada bulunan her hata için önce o durumu yeniden üreten bir test yazılır
  (`tests/test_checks.py`, `tests/test_robustness.py` örnekleri).
- Kararlar gerekçe ve kanıtıyla `docs/kararlar.md`'ye eklenir.
