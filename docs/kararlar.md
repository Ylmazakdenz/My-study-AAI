# Karar kaydı

Her karar, onu doğuran gerçek çalıştırma ya da bulguyla birlikte yazılmıştır. Tarihler 2026.

## K1 — Model bağlantısı: hocanın yöntemi, yerel çalıştırma (19.11)

- **Bağlam:** Hocanın notebook'u Ollama'yı Colab'da (T4 GPU) kurup `ollama` Python paketiyle `localhost:11434`'e
  bağlanıyor.
- **Karar:** Aynı yöntem (`ollama` paketi + Ollama sunucusu) korunur; ana çalıştırma yeri **yerel bilgisayar**dır
  (Ollama Mac uygulaması). Colab notebook'u yedek yol olarak durur. Adres ve model `.env`'den okunur.
- **Gerekçe:** Google Trends yalnızca ev internetinden çalıştı (K4); ekip üyeleri yerelde çalışıyor; 16 GB
  M4 Mac `llama3.1:8b` için yeterli.
- **Kurulum notu:** Colab'da güncel Ollama kurulum betiği `zstd` istiyor (18.11, hocanın koduna eklendi).

## K2 — Model: `llama3.1:8b` (18.11)

- **Bulgu:** Hocanın notebook'undaki `llama3.2` (3B) iki denemede de yorumda hata yaptı: belirgin değişimi olmayan
  terimlere "popülerlik kazanıyor", verisi olan terimlere "veri alınamadı" dedi; "satışta artış" uydurdu; Türkçe ile
  İngilizceyi karıştırdı.
- **Karar:** `llama3.1:8b`. Hocanın notebook'u T4 için iki modeli de öneriyor ("Llama 3.2 (3B) or Llama 3.1 (8B)").
  İlk 8B denemesinde tutarlılık kontrolü ✅.

## K3 — Model çıktısı: serbest metin yerine JSON şeması (19.11)

- **Bulgu:** 8B model bile serbest metinde biçimi korumadı (başlıkları `## 4.` yerine `**4.**` yazdı); denetim
  regex'e dayandığı için yanlış alarm verdi.
- **Karar:** Model, Ollama `format` parametresiyle JSON şemasına uyan yanıt verir; Python alan alan doğrular,
  sorun varsa geri bildirimle bir kez daha sorar ve raporu kendisi oluşturur. Sonraki aşamada ajanlar arası veri
  aktarımı da bu biçimde olacak.

## K4 — Ana kaynak: Google Trends (19.11)

- **Bulgu:** Türkçe Vikipedi'de giyim makaleleri günde 1,5–8 görüntüleme alıyor (güvenilir değil); İngilizce
  Vikipedi dünya genelini ölçüyor. Google Trends ev internetinden 6/6 terim, 56/56 gün.
- **Karar:** Google Trends (Türkiye) ana kaynak; Vikipedi (tr + en) yedek/doğrulama.
- **Risk:** pytrends resmi değil; engellenirse hata kaydedilir, hat Vikipedi ile sürer. Kalıcı çözüm: resmi Trends
  API alfa başvurusu.
- **Etkisi:** Hırka İngilizce Vikipedi'de +%25,7 iken Türkiye aramalarında -%9,8 çıktı; Google Trends olmasaydı
  Türkiye için yanlış ürün önerilebilirdi.

## K5 — GDELT kapalı (19.11)

4 gerçek çalıştırmanın hiçbirinde karşılaştırılabilir veri alınamadı: zaman aşımı, tekrarlayan 429 (Colab ve ev
interneti), GDELT'in kendi veri kesintisi (tüm terimlerde aynı 17 gün) ve izleme hacminin yarıya düşmesi (ham
sayılar yapay olarak %35–75 "düşüyordu"). Kod duruyor; `--sources gdelt` ile denenebilir. Ayrıntı:
[kaynaklar.md](kaynaklar.md).

## K6 — Eksik veri asla sıfır sayılmaz (18–19.11)

Görev belgesindeki kural. Uygulamada üç ayrı biçimde karşılaşıldı ve her biri ayrı ele alındı:
kaynak kesintisi (GDELT), Google Trends'in 0 = "yeterli veri yok" değeri ("kaşe kaban"da 2 gün; düzeltme Palto'yu
+%78,0'dan +%65,3'e indirdi) ve Vikipedi'nin görüntülenmesiz günü döndürmemesi. Ayrıntı: [yontem.md](yontem.md).

## K7 — Yıllık karşılaştırma (19.11)

- **Bağlam:** "Palto Kasım'da her yıl artar" — dönemsel artış tek başına trend değildir.
- **Karar:** Her terim için geçen yılın aynı dönemi de çekilir; dönemsel ve yıllık sonuç birleştirilerek
  "sezon üstü artış / mevsimsel artış" gibi etiketler üretilir.

## K8 — Analiz ayarları güncel config'ten (19.11)

- **Bulgu:** Kayıtlı örnek veri, çalıştırma anındaki eski ayarlarla yeniden analiz edilince GDELT için düzeltilmiş
  olan sahte düşüşler geri geliyordu.
- **Karar:** `analyze` varsayılan olarak güncel `config.yaml`'ı kullanır; birebir tekrar için `--use-run-config`.
  Kullanılan ayarlar her zaman `analysis.json`'a yazılır. Regresyon testi var.

## K10 — Vikipedi değerleri proje toplamına oranlanır (19.11)

- **Bulgu:** İlk yıllık karşılaştırmada (19.11, yerel) İngilizce Vikipedi'de 6 terimin **hepsi** geçen yıla göre
  %27–62 düşük çıktı (Kot pantolon -%62). Tüm makalelerde aynı yönde büyük düşüş, terimlere değil kaynağa ait bir
  değişimdir: Wikimedia 2025'te bot tespitini güncelledi ve insan görüntülemelerinde yıllık ~%8 düşüş bildirdi.
- **Karar:** Makale görüntülemesi, projenin o günkü toplam insan görüntülemesine oranlanır (milyonda). GDELT'teki
  izleme hacmi sorunuyla (K5) aynı ilke: kaynağın genel hacmi değişirse terim değişti sanılmamalı.

## K11 — Google Trends: seyrek istek + bekleyerek tekrar (19.11)

Yıllık seri istek sayısını ikiye katladı; aynı gün birkaç tam çalıştırmadan sonra 2 terimde 429 alındı. İstekler
arası 15 sn, 429'da 60/120 sn bekleyip tekrar deneme eklendi.

## K12 — Yıllık iddialar ayrı denetlenir; düşen ürüne "öne çıkar" denemez (19.11)

- **Bulgu:** `llama3.1:8b` yanıtı tutarlılık kontrolünden ✅ geçti ama yanlıştı: geçen yıldan düşük olan Kazak ve
  Palto için "geçen yılın aynı döneminden de yüksek" yazdı (istemdeki örnek cümleyi kopyaladı) ve geçen yıldan düşük
  ürünler için "öne çıkarmayı destekleyebilir" dedi. Denetim dönemsel ve yıllık yönü ayırmıyordu.
- **Karar:** Her aday satırına Python'un yazdığı ANLAMI ve YÖN eklendi; istemdeki örnek kaldırıldı. Denetim
  "geçen yıl" ifadesini ayrıca yıllık yönle karşılaştırır; düşüş etiketli terime "öne çıkar" önerisi reddedilir.
  Gerçek yanıt test olarak eklendi.

## K13 — İstek önbelleği: 24 saat (19.11)

- **Bulgu:** Google Trends 429'larının çoğu, geliştirme sırasında aynı verinin birkaç saat içinde tekrar tekrar
  çekilmesinden geldi.
- **Karar:** Başarılı yanıtlar 24 saat saklanır. Süre, verinin değişme sıklığına göre seçildi: veri günlük, dönem
  bitişi bugünden 2 gün önce ve anahtar tarihleri içerdiği için ertesi gün kendiliğinden yeniden çekilir; daha kısa
  bir süre (ör. 2 saat) aynı gün içindeki tekrar çalıştırmaları korumazdı. `--refresh` ile zorla yenilenir.
- **Gözden geçirmede eklenenler:** süresi dolan kayıtlar diskten silinir (birikme yok); kısmi sonuçlar saklanmaz
  (24 saat eksik veriyle çalışılmasın); anahtara kod sürümü girer (veri işleme değişince eski kayıt kullanılmaz);
  eski çalıştırmalar için onaylı `trendpipe clean`.
- **Reddedilen seçenek — Google Trends'e toplu istek (5 terim/istek):** İstek sayısını azaltır ama Google tüm
  terimleri en popüler olana göre ölçekleyip tam sayıya yuvarladığı için küçük terimler 0–3 aralığına sıkışır ve
  çoğu "yeterli veri yok" (0) olur. Önbellek aynı kazancı veri kaybı olmadan sağladığı için eklenmedi.

## K14 — Repo denetimi (19.11)

Tüm modüller baştan sona okunarak denetlendi; bulunan sorunlar düzeltildi ve her biri için regresyon testi eklendi
(`tests/test_robustness.py`). Örnek verilerin analiz sonuçları düzeltmelerden sonra birebir aynı kaldı.

| # | Sorun | Etki | Düzeltme |
|---|---|---|---|
| F1 | Adaptörde beklenmeyen istisna (ör. kaynak liste döndürürse) | Çalıştırma yarıda kalıp manifest yazılmıyordu | İstek `error` olarak kaydedilir, çalıştırma sürer |
| F2 | Aynı saniyede iki çalıştırma | `FileExistsError` ile çökme | Klasöre `-2`, `-3` eki |
| F3 | Google Trends kalıcı hatada da bekliyordu | Terim başına ~3 dk boşa bekleme | Yalnızca geçici hatalarda tekrar |
| F4 | Vikipedi deneme sayısı | Proje toplamı isteği makale isteğinin sayısını eziyordu | Ayrı tutulur |
| F5 | Kaynak ayarlarının türü denetlenmiyordu | `samples: "iki"` çalıştırma ortasında çöküyordu | Tür denetimi ayar okunurken |
| F6 | Rapor eşleşmesi denetimle farklı kuraldaydı | Model "PALTO" yazarsa denetim ✅ ama rapor boş | Aynı normalleştirme |
| F7 | 2. model çağrısı hata verirse | 1. denemenin yanıtı kayboluyordu | Önceki deneme kullanılır |
| F8 | `interpret` eski `analysis.json`'ı kullanabiliyordu | Eski sürümün analiziyle yorum | Yorumdan önce yeniden analiz |
| F9 | `.env`'de sayı yerine metin | Anlaşılmaz hata | Açık hata mesajı |

## K15 — Profesyonellik denetimi (19.11)

"Bir uzman bu koda baksa neyi amatörce bulur?" sorusuyla ikinci denetim:

| Konu | Önce | Sonra |
|---|---|---|
| Belirgin değişim ölçütü | Yalnızca ±%15 eşiği; günlük dalgalanması büyük bir seride rastlantısal %20 "artış" sayılabilirdi | Eşik **ve** Welch t ≥ 2. Mevcut örneklerde güvenilir sayılan 6 sonucun hepsinde t > 3; hiçbir etiket değişmedi |
| Dönem uzunluğu metinleri | Modele "son 4 haftada" sabit yazılıyordu | Dönem uzunluğu ayardan gelir |
| "Bugün" | Bilgisayarın saat dilimi (Colab UTC ↔ Mac İstanbul farklı dönem üretebilirdi); Google'a sabit -180 | Pazar saat dilimi (`window.timezone`), Google tz bundan türetilir |
| Tekrarlanabilirlik | Manifestte yalnız araç sürümü | git commit, değişiklik durumu, Python, platform, paket sürümleri |
| Kurulum doğrulama | Hata alınca anlaşılıyordu | `trendpipe doctor` |
| Testler | Tek dosyada 30+ karışık test | Konulara göre dosyalar (analiz, kaynaklar, denetim, CLI, önbellek, gürültü…) |
| Çıktı sözleşmesi | Belgelenmemişti | [ciktilar.md](ciktilar.md): sonraki ajanların girdi biçimi |

## K16 — Görev belgesine birebir uyum denetimi (20.11)

Görev belgesi teslimat açısından satır satır yeniden karşılaştırıldı:

| Belgedeki istek | Önce | Sonra |
|---|---|---|
| "Modelden şu soruları cevaplamasını iste" (4 soru) | 2. soruyu (ölçüm ve dönem) Python yazıyordu | Model 4 soruyu da yanıtlar; 2. yanıttaki yüzde ve tarihler denetlenir, yanına Python'un hesabı eklenir |
| "Kurulum, model adı ve bağlantı ayarlarını README'ye yaz" | `docs/`'a taşınmıştı | README "Model bağlantısı" |
| "README'ye kısa bir tablo ekle" (6 konu, kanıt: resmi bağlantı + tarih) | `docs/`'taydı; README'de kanıt sütunu yoktu | README'de belgedeki sütunlarla, kanıt bağlantılarıyla |
| "Denediğin işlemi, aldığın hatayı ve çözüm önerini paylaş" | Kararlar belgesine dağınık | README "Karşılaşılan engeller" (denenen işlem / hata / çözüm) |
| Ortak kararlar (hocanın kurulumu, model, kaynaklar) | Sapmalar `docs/`'ta | README "Ortak kararlardan farklı yapılanlar (onayın gerekiyor)" |
| "Bağımlılık listesi" | `requirements.txt` yalnız `-e .` | Paketler açıkça listelenir; pyproject ile uyum testle denetlenir |
| "Yapay zekâdan alınmış plan değil" | README'de "Sonraki aşamaya köprü" planı | Kaldırıldı |

## K17 — 20.11 gerçek çalıştırmasından çıkan düzeltmeler (v0.3.2)

36/36 istek başarılı oldu; analiz doğruydu ama model yorumu ve rapor metni şu sorunları gösterdi:

| Denenen işlem / gözlem | Sorun | Çözüm |
|---|---|---|
| Aday listesi terim-kaynak çiftiydi | Kazak, Palto, Bot hem Google Trends hem İngilizce Vikipedi'den aday oldu (9 aday); model terimleri ve önerileri tekrarladı, istem uzadı (294 sn) | Terim başına tek aday: config'teki kaynak sırasına göre önceliği en yüksek kaynak; diğerleri bağlam. Tekrar denetlenir, rapor tekrarı atar |
| Model etiketleri karıştırdı | Bot (geçen yıldan yüksek) için "sezon üstü", Kazak (sezon üstü) için "mevsimsel artış", her öneriye "mevsimsel artışlar her yıl görülür" | Etiket ifadesi denetimi (`checks.label_phrase_issues`); öneri tonu (`ÖNERİ`) Python'da belirlenir |
| Oranlanmış Vikipedi değerleri | Raporda birimsiz "günlük ortalama 1,0 → 1,3" (aslında kaynak toplamında milyonda pay) | Kanıt satırında ve tabloda birim yazılır (`value_unit`) |
| Düşük hacim notu | Aralık oranlanmış paydan yazıldı ("0,5–2,8") | Ham ortalamalar saklanır (`baseline_raw_mean`, `recent_raw_mean`); not ham görüntüleme sayısıyla yazılır |

Hesaplanan sonuçlar (değişim yüzdeleri, sinyaller, etiketler) değişmedi; örnek çalıştırmalar yeniden analiz edilip
karşılaştırıldı. Gerçek yanıt `tests/test_run_20261120.py`'de regresyon testi olarak tutulur.

## K9 — Ayar dosyası şemayla doğrulanır (19.11)

Yazım hataları (ör. `recent_day`, var olmayan kaynak adı, kaynağa ait olmayan ayar) eskiden sessizce görmezden
geliniyordu; artık çalıştırmadan önce açık bir hata mesajıyla reddedilir.
