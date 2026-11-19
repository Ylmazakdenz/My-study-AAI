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

## K9 — Ayar dosyası şemayla doğrulanır (19.11)

Yazım hataları (ör. `recent_day`, var olmayan kaynak adı, kaynağa ait olmayan ayar) eskiden sessizce görmezden
geliniyordu; artık çalıştırmadan önce açık bir hata mesajıyla reddedilir.
