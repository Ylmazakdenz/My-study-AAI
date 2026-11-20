"""Hattın adımları — komut satırından bağımsız.

Bu fonksiyonlar cli.py tarafından çağrılır; sonraki aşamada aynı fonksiyonlar MCP araçları ya da LangGraph
düğümleri olarak da çağrılabilir. Ekrana yazmazlar; ilerlemeyi isteğe bağlı `on_result` geri çağrısıyla bildirirler.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .analysis import analyze_run
from .cache import FetchCache, cache_key
from .config import Window
from .logs import attach_run_log, detach_run_log, get_logger
from .models import FetchResult, FetchStatus, Term
from .provenance import run_environment
from .sources import Source
from .storage import new_run_dir, read_json, read_timeseries, save_raw, write_json, write_timeseries

log = get_logger("pipeline")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _skipped(src: Source, t: Term, q: str, start, end, series: str, status: str, error: str) -> FetchResult:
    return src._result(t.id, q, start, end, status=status, attempts=0, error=error, series=series)


def fetch_run(cfg: dict, terms: list[Term], window: Window, sources: list[Source], out_dir: str | Path,
              config_file: str = "", on_result: Callable[[FetchResult, Term], None] | None = None,
              cache: FetchCache | None = None, refresh: bool = False) -> Path:
    """Tüm kaynak × terim × seri isteklerini yapar, ham ve düzenlenmiş veriyi kaydeder. Çalıştırma klasörünü döndürür.

    Her terim için iki seri çekilir:
      - main: önceki dönem + yakın dönem (günlük) → dönemsel karşılaştırma
      - yoy:  geçen yılın aynı döneminden bugüne (Google Trends'te haftalık) → yıllık karşılaştırma
    Önbellekte süresi dolmamış başarılı sonuç varsa kaynağa gidilmez (refresh=True ise yok sayılır).
    """
    run_dir = new_run_dir(out_dir)
    handler = attach_run_log(run_dir)
    try:
        if cache:
            cache.prune()
        log.info("çalıştırma %s başladı; dönem %s", run_dir.name, window.as_dict())
        terms_by_id = {t.id: t for t in terms}
        results: list[FetchResult] = []
        records: list[dict] = []
        for src in sources:
            # Art arda hız sınırı (429) alan kaynakta kalan istekler denenmez; durum açıkça kaydedilir.
            limit = int(src.settings.get("stop_after_consecutive_429", 0) or 0)
            streak = 0
            do_yoy = window.has_yoy and src.settings.get("yoy", True)
            for t in terms:
                q = t.queries.get(src.name)
                plan = [("main", window.start, window.end)]
                if do_yoy:
                    plan.append(("yoy", window.ly_start, window.end))
                for series, start, end in plan:
                    if not q:
                        res = _skipped(src, t, "", start, end, series, FetchStatus.SKIPPED,
                                       f"Bu terim için '{src.name}' sorgusu tanımlı değil")
                    elif limit and streak >= limit:
                        res = _skipped(src, t, q, start, end, series, FetchStatus.ERROR,
                                       f"Denenmedi: bu kaynak art arda {streak} istekte hız sınırına (HTTP 429) "
                                       "takıldı. Daha sonra ya da başka bir ağdan tekrar deneyin.")
                    else:
                        key = cache_key(src.type_name, src.settings, q, start, end) if cache else None
                        res = cache.get(key) if (cache and not refresh) else None
                        if res is not None:
                            res.source, res.term_id, res.series = src.name, t.id, series
                        else:
                            try:
                                res = src.fetch(t.id, q, start, end)
                            except Exception as exc:  # beklenmeyen adaptör hatası çalıştırmayı yarıda bırakmasın
                                log.exception("%s/%s beklenmeyen hata", src.name, t.id)
                                res = src._result(t.id, q, start, end, status=FetchStatus.ERROR,
                                                  error=f"Beklenmeyen hata: {type(exc).__name__}: {exc}")
                            res.series = series
                            streak = streak + 1 if res.http_status == 429 else 0
                            if cache:
                                cache.put(key, res, run_dir.name)
                    log.info("%s/%s/%s: %s (%d nokta, %d deneme) %s", src.name, t.id, series, res.status,
                             len(res.points), res.attempts, res.error or "")
                    raw_file = save_raw(run_dir, res)
                    records.append({**res.meta(), "label": t.label, "category": t.category, "raw_file": raw_file})
                    if res.status == FetchStatus.OK:
                        results.append(res)
                    if on_result:
                        on_result(res, t)

        write_timeseries(run_dir, results, terms_by_id)
        manifest = {
            "run_id": run_dir.name, "created_at": utc_now(), "tool_version": __version__,
            "environment": run_environment(),
            "config_file": str(config_file), "brand": cfg.get("brand", {}), "window": window.as_dict(),
            "cache": ({"enabled": cache.enabled, "ttl_hours": cache.ttl_hours, "refresh": refresh}
                      if cache else {"enabled": False}),
            "analysis_settings": cfg.get("analysis", {}),
            "sources": {s.name: {"metric": s.metric, "description": s.description, "settings": s.settings}
                        for s in sources},
            "fetches": records,
        }
        write_json(run_dir / "manifest.json", manifest)
        log.info("çalıştırma bitti: %d/%d istek veri döndürdü", len(results), len(records))
        return run_dir
    finally:
        detach_run_log(handler)


def analyze_dir(run_dir: Path, analysis_cfg: dict) -> list[dict]:
    """Kayıtlı çalıştırmayı analiz eder, analysis.json/csv yazar ve satırları döndürür (ağ gerekmez)."""
    from .analysis import ANALYSIS_FIELDS, flatten_for_csv
    from .storage import write_csv
    manifest = read_json(run_dir / "manifest.json")
    rows = analyze_run(manifest, read_timeseries(run_dir), {"analysis": analysis_cfg},
                       Window.from_dict(manifest["window"]))
    write_json(run_dir / "analysis.json", {"run_id": manifest["run_id"], "created_at": utc_now(),
                                           "window": manifest["window"], "analysis_settings": analysis_cfg,
                                           "rows": rows})
    write_csv(run_dir / "analysis.csv", flatten_for_csv(rows), ANALYSIS_FIELDS)
    return rows
