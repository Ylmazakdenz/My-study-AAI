# Giyim Trend Veri Hattı (SENG360 — 1. aşama)

Otonom dijital prodüksiyon ve pazarlama ajansı projesinin **Trend Analizi** ajanının dayanacağı veri hattı:

```
config/config.yaml (terimler) ─► kaynaklardan gerçek veri (API) ─► ham + düzenlenmiş kayıt
        ─► Python ile değişim hesabı ─► Ollama modeli ile yorum ─► kayıt (json / csv / md)
```

Bu aşamada ürün eşleştirme, görsel üretimi ve yayınlama **yok**. Hesaplamaları Python yapar, model yalnızca
hesaplanan sonuçları yorumlar.

---

## 1. Hızlı başlangıç

Gereksinim: **Python 3.10 veya üstü** (Colab'da hazır). Model adımı için Ollama (Colab notebook'u kurar).

### A) Kendi bilgisayarında (PyCharm / terminal) — veri çekme + analiz

```bash
git clone https://github.com/Ylmazakdenz/My-study-AAI.git
cd My-study-AAI
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # Windows: copy .env.example .env

python -m trendpipe fetch                  # gerçek veriyi çek ve kaydet  -> data/runs/<zaman>/
python -m trendpipe analyze --run latest   # değişimi hesapla              -> analysis.csv / analysis.json
```

PyCharm'da: *Run → Edit Configurations → + → Python* → **Module name:** `trendpipe`,
**Parameters:** `all --skip-llm`, **Working directory:** repo klasörü.

### B) Model yorumu — hocanın Colab + Ollama kurulumu

`notebooks/colab_run.ipynb` dosyasını Colab'da açın (*File → Upload notebook* ya da GitHub sekmesi),
*Runtime → Change runtime type → T4 GPU* seçin ve hücreleri sırayla çalıştırın. Notebook:
Ollama'yı kurar ve başlatır → `llama3.2`'yi indirir → bu repoyu klonlar → `check-llm` ile bağlantıyı test eder →
`data/sample/` içindeki kayıtlı veriyi (ya da yeni çekilen veriyi) modele yorumlatır.

Ollama kendi bilgisayarınızda kuruluysa aynı komutlar yerelde de çalışır:

```bash
ollama pull llama3.2
python -m trendpipe check-llm              # model bağlantı testi
python -m trendpipe all                    # çek + hesapla + yorumlat
```

### C) Bağlantı olmadan (kayıtlı örnek veriyle) tekrar

```bash
python -m trendpipe analyze   --out-dir data/sample --run latest
python -m trendpipe interpret --out-dir data/sample --run latest   # model gerekir
```

`analyze`, analiz ayarlarını varsayılan olarak güncel `config/config.yaml`'dan alır; böylece yöntemde yapılan
düzeltmeler eski kayıtlara da uygulanır. Çalıştırma anındaki ayarlarla birebir tekrar için `--use-run-config`.
Hangi ayarların kullanıldığı her zaman `analysis.json` içine yazılır.

---

## 2. Model bağlantısı (hocanın yöntemi)

Hocanın `SENG360_Agentic_AI_Search_LLMs_V1` notebook'u:

| Adım | Ne yapıyor |
|---|---|
| `apt-get install pciutils` + `ollama.com/install.sh` | Colab sanal makinesine Ollama kurar |
| `OLLAMA_ORIGINS=* ollama serve` (thread) | Ollama sunucusunu **Colab makinesinin içinde** `localhost:11434`'te başlatır |
| `ollama pull llama3.2` | 3B parametreli Llama 3.2 modelini indirir (~2 GB, T4 GPU) |
| `pip install ollama` + `ollama.chat(model='llama3.2', ...)` | Python paketiyle aynı makinedeki sunucuya istek gönderir |

**Sonuç:** Bağlantı uzak bir okul sunucusuna değil, Colab oturumu içindeki **yerel Ollama**'yadır. Oturum
kapanınca model ve sunucu silinir; her oturumda kurulum hücreleri tekrar çalıştırılır.

`trendpipe/llm.py` aynı çağrıyı `ollama.Client(host=OLLAMA_HOST).chat(...)` ile yapar; adres ve model adı
`.env` dosyasından gelir:

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Colab'da ve yerel kurulumda aynı |
| `OLLAMA_MODEL` | `llama3.2` | Colab notebook'unda varsayılan `llama3.1:8b`. Hocanın notebook'u T4 için iki modeli de önerir ("Llama 3.2 (3B) or Llama 3.1 (8B)"); 3B model Türkçe yorumda hata yaptığı için 8B seçildi |
| `OLLAMA_TEMPERATURE` | `0.2` | Düşük = daha tutarlı, daha az uydurma |
| `CONTACT_EMAIL` | boş | Wikimedia User-Agent için önerilir |

Anahtar/şifre gerekmez; `.env` repoya girmez.

---

## 3. Veri kaynakları karşılaştırması

Kontrol tarihi: **19.11.2026** (her satırın "Kanıt" sütununda da yazılı). Kaynak: resmi belgeler; resmi olmayan
bilgiler "(ikincil kaynak)" olarak işaretlendi.

| Kaynak | Verinin anlamı | Otomatik erişim | Gereksinim | Kapsam (TR / dönem) | Giyime katkı | Kanıt |
|---|---|---|---|---|---|---|
| **Google Trends** | Google aramalarında göreli ilgi (0-100); 19.11.2026'da pytrends ile gerçek istekte 6/6 başarılı | Resmi API **kapalı alfa** (24.07.2025'te duyuruldu, başvuruyla). `pytrends` resmi değil; Nisan 2025'te arşivlendiği bildiriliyor (ikincil kaynak), sık 429 | Alfa için başvuru; pytrends anahtarsız ama engellenebilir | TR (`geo=TR`) var; geçmiş dönem sorgulanabilir | **En güçlü sinyal**: ürün/stil arama ilgisi | [Trends API alfa](https://developers.google.com/search/apis/trends), [duyuru](https://developers.google.com/search/blog/2025/07/trends-api) — 19.11.2026 |
| **Pinterest Trends** | Pinterest aramalarında göreli hacim; haftalık 1 yıllık seri + haftalık/aylık/yıllık büyüme | `GET /v5/trends/keywords/{region}/top/{trend_type}` | İşletme hesabı + uygulama + OAuth; uç nokta sınırlı kullanıcıya açık | Bölge listesinde TR resmi sayfada doğrulanamadı; yalnız bugünün verisi | Modaya çok uygun (stil keşfi) ama **terim sorgulanamaz**, sadece en trend listesi döner | [Trends API](https://developers.pinterest.com/docs/analytics-and-reports/trends/) — 19.11.2026 |
| **YouTube Data API v3** | Video izlenme/beğeni **toplamları** (anlık) | Resmi REST API | Ücretsiz API anahtarı; günlük 10.000 birim, `search.list` 100 birim | `chart=mostPopular` + `regionCode=TR` var (1 birim); geçmiş izlenme serisi **yok**, yalnız anlık istatistik | Stil videolarına ilgi; ama trend için zaman içinde tekrar tekrar çekmek gerekir | [Kota maliyetleri](https://developers.google.com/youtube/v3/determine_quota_cost), [videos.list](https://developers.google.com/youtube/v3/docs/videos/list) — 19.11.2026 |
| **Wikimedia Analytics** | Vikipedi makalesinin günlük görüntülenmesi (bot hariç) | Resmi REST API, `per-article` uç noktası | Anahtar yok; **User-Agent zorunlu**; istekler sırayla | tr.wikipedia ≈ Türkçe okuyucu; 2015'ten bugüne günlük | Ürün tipine (trençkot, hırka...) duyulan **merak**; satın alma niyeti değil | [Analytics API](https://doc.wikimedia.org/analytics-api/), [erişim politikası](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html) — 19.11.2026 |
| **GDELT DOC 2.0** | Haberlerde terimin geçtiği **haber sayısı** (ya da tüm haberler içindeki %); 4 gerçek çalıştırmada kullanılamadı | Resmi uç nokta `api/v2/doc/doc`, `timelinevolraw` | Anahtar yok; sık istek engellenir (biz 6 sn bekliyoruz) | `sourcecountry:turkey sourcelang:turkish`; varsayılan son 3 ay, `timespan` ile 1 yıla kadar | Medya/moda gündemi (bir ürün haberlerde konuşuluyor mu) | [DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/), [1 yıl arama](https://blog.gdeltproject.org/doc-geo-2-0-api-updates-full-year-searching-and-more/) — 19.11.2026 |
| **Reddit** | Gönderi/yorum içerikleri | Resmi Data API (OAuth) | Kullanımdan önce **açık onay** şart; ticari kullanım sözleşmeli. Yeni başvuruların 31.10.2026'da kapandığı bildiriliyor (ikincil kaynak) | Türkiye/Türkçe kapsamı zayıf | Düşük | [Data API Terms](https://www.redditinc.com/policies/data-api-terms) — 19.11.2026 |

### Seçim (gerçek isteklerle denendikten sonra, 18–19.11.2026)

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

---

## 4. Terimleri değiştirme

Kod değişmeden:

- `config/config.yaml` → `terms:` listesine ekleyin. Her terim her kaynakta farklı sorgulanır
  (Vikipedi makale başlığı / GDELT İngilizce ifade / Google Trends Türkçe arama). Bir kaynak için sorgu yoksa o
  kaynak o terimde `skipped` olur.
- Komuttan: `--terms trenckot,hirka` (sadece bu id'ler) ve `--term "Yelek"` (config dışı, aynı metin tüm kaynaklarda).
- Kaynak seçimi: `--sources wikimedia` · dönem sonu: `--end 2026-11-15` · başka marka/ayar: `--config config/x.yaml`

---

## 5. Çıktılar

```
data/runs/<YYYYMMDD-HHMMSS>/
├── manifest.json             # marka, dönem, kaynak ayarları; her istek için: kaynak, terim, sorgu,
│                             #   kapsanan dönem, çekilme zamanı (UTC), HTTP kodu, durum, hata, istek URL'si
├── raw/<kaynak>__<terim>.json   # kaynağın ham yanıtı, olduğu gibi
├── processed/timeseries.csv  # düzenlenmiş günlük seri (analizin girdisi)
├── analysis.json / .csv      # hesaplanan karşılaştırma
└── interpretation.json / .md # model yorumu + kullanılan istem + sayı kontrolü
```

`data/runs/` repoya girmez. Repoya giren örnek çalıştırma `data/sample/` altındadır.

### İstek durumları (eksik veri asla 0 sayılmaz)

| Durum | Anlamı |
|---|---|
| `ok` | Veri geldi |
| `empty` | İstek başarılı, kaynak veri döndürmedi |
| `not_found` | Terim/makale kaynakta yok (ör. Vikipedi 404) |
| `error` | Bağlantı, zaman aşımı, hız sınırı, beklenmeyen yanıt (mesaj kaydedilir) |
| `skipped` | Bu terim için o kaynağa sorgu tanımlı değil |

### Hesaplama

- Son **28 gün** (yakın dönem) ortalaması ile hemen önceki **28 gün** ortalaması karşılaştırılır → `pct_change`.
  Bitiş tarihi, geç yayımlanan veriyi dışlamak için bugünden 2 gün öncedir.
- Pencerelerden birinde günlerin **%80'inden azı** varsa değişim hesaplanmaz (`insufficient_data`).
  Not: Wikimedia görüntülenmesi olmayan günü hiç döndürmez; bu da eksik sayılır (temkinli yaklaşım).
- Önceki dönem ortalaması 0 ise yüzde tanımsızdır (`baseline_zero`).
- `direction`: ±%15 eşiği (config'te değiştirilebilir) · `recent_slope_per_day`: yakın dönemdeki eğim ·
  düşük hacimli serilere uyarı notu · sıralama **yalnızca aynı kaynak içinde**.
- `signal`: Python'un sınıflandırması — `strong_up`, `strong_down`, `flat`, `weak` (düşük hacim),
  `insufficient`, `no_data`. Model yalnızca bu sınıflara göre "yükseliş/düşüş" diyebilir.
- Tek seferlik toplamdan "yükseliyor" sonucu çıkarılmaz; her sonuç iki dönemin karşılaştırmasıdır.

### Model yorumu ve güvenlik kontrolleri

Modele ham JSON değil, Python'un Türkçe cümlelere çevirip **gruplara ayırdığı** sonuçlar gönderilir
(güvenilir yükseliş / düşüş / değişim yok / düşük hacim / hesaplanamadı / veri yok). Ham hata metinleri de
kısa Türkçe nedenlere çevrilir. İstem şunları ister: öne çıkan terimler, destekleyen ölçüm ve dönem, ürün
seçimine katkı, **bu veriyle söyleyemediklerimiz**. Satış, stok, talep veya fiyat uydurmak yasaktır.

Yanıt otomatik denetlenir; sorun varsa `interpretation.md` başında ⚠️ ile listelenir:
- hesaplanan sonuçlarda olmayan yüzdeler,
- yönü farklı hesaplanmış bir terim için "artış/düşüş" iddiası (ya da düşük hacimli seride çekincesiz iddia),
- verisi gelmiş bir kaynak-terim için "veri alınamadı" denmesi,
- 1-3. bölümlerde satış, stok, ciro gibi veride olmayan metrikler,
- İngilizce kelimeler.

`interpretation.md` sonuna, modelden bağımsız olarak Python'un hesapladığı tüm sonuçların tablosu eklenir;
model yanılsa da okuyucu doğru sayıları görür.

Bu denetim, ilk Colab denemesinde `llama3.2`'nin yaptığı hataların (yatay terimlere "popülerlik kazanıyor",
verisi olan terimlere "veri alınamadı", Türkçe-İngilizce karışık yanıt) yakalanması için eklendi
(`tests/test_pipeline.py::test_claim_check_catches_colab_mistakes`).

---

## 6. Proje yapısı

```
trendpipe/
├── cli.py            # komutlar: check-llm, fetch, analyze, interpret, all
├── config.py         # YAML + .env okuma, dönem hesabı
├── models.py         # ortak veri yapıları ve durum kodları
├── sources/          # her kaynak bir adaptör: fetch(term, query, start, end) -> FetchResult
│   ├── google_trends.py (ana)  ├── wikimedia.py (tr + en)  └── gdelt.py (kapalı)
├── storage.py        # klasör düzeni, ham/düzenlenmiş kayıt
├── analysis.py       # dönem karşılaştırması
├── prompts.py        # model istemi
└── llm.py            # Ollama bağlantısı + sayı kontrolü
config/config.yaml    # terimler ve ayarlar (gizli bilgi yok)
notebooks/colab_run.ipynb
tests/                # ağa çıkmayan testler: python -m pytest
```

Kaynak adaptörleri hata fırlatmaz, sonucu durum koduyla döndürür. Bu tasarım, sonraki aşamada aynı
fonksiyonların **MCP aracı** olarak sunulmasına uygundur.

### Testler

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

---

## 7. Bilinen sınırlar / sonraki adımlar

- Takım reposuna taşırken değiştirilecek iki yer: `notebooks/colab_run.ipynb` (4. hücre, `REPO`) ve
  `trendpipe/config.py` (`PROJECT_URL`, Wikimedia User-Agent iletişim adresi).
- Mevsimsellik: Eylül→Kasım artışı her yıl görülen mevsimsel artış olabilir; geçen yılın aynı dönemiyle
  karşılaştırma eklenmeli (Wikimedia 2015'ten beri veri veriyor).

- Örnek çalıştırmalar: `data/sample/` (Colab, 18.11.2026; iki gerçek çalıştırma, açıklama klasördeki README'de).
- Google Trends resmi API alfa başvurusu yapılmalı (pytrends resmi değil, engellenebilir).
- Sonraki aşama: MCP sunucusu olarak veri araçları, RAG (marka kataloğu), ürün eşleştirme.
