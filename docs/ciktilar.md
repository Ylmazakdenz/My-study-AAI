# Çıktı dosyaları

Her çalıştırma `data/runs/<YYYYMMDD-HHMMSS>/` altında kendi başına eksiksiz bir klasördür. Sonraki aşamadaki
ajanlar (ürün eşleştirme, içerik) bu dosyaları girdi olarak kullanır; alan adları kararlı tutulur.

## manifest.json — ne, nereden, ne zaman çekildi

| Alan | Anlamı |
|---|---|
| `run_id`, `created_at` | Çalıştırma kimliği ve oluşturma zamanı (UTC) |
| `tool_version` | trendpipe sürümü |
| `environment` | `git_commit`, `git_dirty` (commit'lenmemiş değişiklik), `python`, `platform`, temel paket sürümleri |
| `brand`, `window` | Marka bilgisi; dönemler (`baseline_*`, `recent_*`, `ly_*` = geçen yılın aynı dönemi) |
| `analysis_settings` | Çalıştırma anındaki analiz ayarları |
| `cache` | Önbellek açık mıydı, süresi, `--refresh` kullanıldı mı |
| `sources` | Her kaynak: `metric`, `description` (verinin anlamı), `settings` |
| `fetches[]` | Her istek için bir kayıt (aşağıda) |

`fetches[]` kaydı:

| Alan | Anlamı |
|---|---|
| `source`, `term_id`, `label`, `category`, `query` | Kaynak ve terim |
| `series` | `main` (dönemsel) ya da `yoy` (yıllık seri) |
| `start`, `end` | İstenen dönem |
| `status` | `ok`, `empty`, `not_found`, `error`, `skipped` |
| `http_status`, `error`, `attempts` | Kaynağın yanıt kodu, hata/not, deneme sayısı (önbellekten geldiyse 0) |
| `fetched_at` | Verinin kaynaktan çekildiği zaman (UTC) |
| `from_cache`, `cache_origin_run` | Önbellekten mi geldi; geldiyse ilk hangi çalıştırmada çekildi |
| `n_points`, `raw_file`, `request_url` | Nokta sayısı, ham yanıt dosyası, istek adresi |

## processed/timeseries.csv — düzenlenmiş seriler

`source, series, metric, term_id, label, category, query, date, value, extra` — `extra` JSON'dur
(ör. `{"norm": 12345}` = kaynağın o günkü toplamı; Google Trends'te `samples`).

## analysis.json / analysis.csv — hesaplanan sonuçlar

`analysis.json` = `{run_id, created_at, window, analysis_settings, rows[]}`. Her satır bir terim × kaynak:

| Alan | Anlamı |
|---|---|
| `fetch_status`, `result` | İstek durumu; hesap sonucu (`computed`, `insufficient_data`, `baseline_zero`, `no_data`) |
| `baseline_mean`, `recent_mean`, `pct_change` | Dönemsel karşılaştırma (oranlanmış kaynaklarda kaynağın toplamına oran) |
| `pop_t_stat` | Dönemsel değişimin günlük dalgalanmaya göre büyüklüğü (Welch t) |
| `direction`, `signal` | `up/down/flat`; `strong_up/strong_down/flat/weak/insufficient/no_data` |
| `baseline_coverage`, `recent_coverage`, `source_gap_days`, `low_volume` | Veri yeterliliği |
| `yoy_*` | Yıllık karşılaştırma: `yoy_ly_mean`, `yoy_recent_mean`, `yoy_pct_change`, `yoy_t_stat`, `yoy_direction`, `yoy_signal`, `yoy_granularity` |
| `trend_label` | Birleşik etiket (bkz. [yontem.md](yontem.md#4-etiket-trend_label)) |
| `notes[]` | İnsan okunur açıklamalar (eksik gün, oranlama, gürültü testi…) |

## interpretation.json / interpretation.md — model yorumu

`interpretation.json`: `model`, `temperature`, `environment`, `review` (denetim sonucu ve sorunlar),
`chosen_attempt`, `response` (modelin JSON yanıtı: `ozet`, `one_cikanlar[]` = `terim`, `kaynak`, `neden_onemli`,
`dayanak`; `urun_katkisi[]`; `soyleyemediklerimiz[]`), `attempts[]` (her denemenin ham yanıtı ve denetimi), `prompt`.
`interpretation.md`: Python'un oluşturduğu rapor (özet, 4 bölüm, sistem notları, tüm sonuçlar tablosu).

## run.log

İstekler, tekrar denemeler, beklemeler, önbellek kullanımı ve yorum denemeleri; hata ayıklama içindir.
