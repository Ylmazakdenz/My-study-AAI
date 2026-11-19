"""Komut satırı (yalnızca argüman okuma ve ekrana yazma; iş pipeline.py'de).

  trendpipe check-llm                       # model bağlantısını test et
  trendpipe fetch                           # veriyi çek ve kaydet
  trendpipe analyze --run latest            # değişimi hesapla (ağ gerekmez)
  trendpipe interpret --run latest          # modele yorumlat
  trendpipe all                             # hepsi sırayla
`trendpipe` komutu yerine `python -m trendpipe` da kullanılabilir.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__
from .cache import FetchCache
from .config import ConfigError, Window, compute_window, llm_settings, load_config, load_env, parse_terms, user_agent
from .llm import LLMError, interpret, ping, render_markdown
from .logs import attach_run_log, detach_run_log, setup_console
from .models import FetchResult, FetchStatus, Term
from .pipeline import analyze_dir, fetch_run
from .prompts import TREND_TR, display_name
from .sources import build_sources
from .storage import read_json, resolve_run_dir, write_json

STATUS_ICON = {FetchStatus.OK: "OK ", FetchStatus.EMPTY: "BOŞ", FetchStatus.NOT_FOUND: "YOK",
               FetchStatus.ERROR: "HATA", FetchStatus.SKIPPED: "ATLA"}


def _csv_list(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _pct(v) -> str:
    return f"{v:+.1f}%" if v is not None else "-"


# ---------------- komutlar ----------------

def cmd_check_llm(args) -> int:
    s = llm_settings()
    print(f"Model bağlantısı deneniyor: host={s['host']} model={s['model']}")
    try:
        out = ping(s)
    except LLMError as exc:
        print(f"[HATA] {exc}", file=sys.stderr)
        return 2
    print(f"[OK] {out['elapsed_sec']} sn — yanıt: {out['content'].strip()}")
    return 0


def _print_fetch(res: FetchResult, t: Term) -> None:
    if res.status == FetchStatus.OK:
        detail = f"{len(res.points)} nokta"
        if res.error:
            detail += f" ({res.error})"
    else:
        detail = " ".join((res.error or "").split())
    if res.attempts > 1:
        detail = f"({res.attempts}. deneme) {detail}"
    series = "yıllık" if res.series == "yoy" else "dönem"
    icon = "ÖNB" if res.from_cache else STATUS_ICON[res.status]
    if res.from_cache:
        detail += f" — önbellek: {res.fetched_at} tarihli istek"
    print(f"  [{icon:4}] {res.source:13} {series:6} {t.label:16} {res.query!r:22} {detail[:120]}")


def cmd_fetch(args) -> Path:
    cfg = load_config(args.config)
    terms = parse_terms(cfg, _csv_list(args.terms), args.term)
    window = compute_window(cfg, end=date.fromisoformat(args.end) if args.end else None)
    sources = build_sources(cfg, _csv_list(args.sources), user_agent=user_agent())
    if not sources:
        raise ConfigError("Açık kaynak yok. config'te 'enabled: true' yapın ya da --sources verin.")
    print(f"Dönem: önceki {window.baseline_start}–{window.baseline_end} | yakın {window.recent_start}–"
          f"{window.recent_end}" + (f" | geçen yıl {window.ly_start}–{window.ly_end}" if window.has_yoy else ""))
    print(f"Kaynaklar: {', '.join(s.name for s in sources)} | Terimler: {', '.join(t.label for t in terms)}\n")
    cc = cfg.get("cache") or {}
    cache = FetchCache(cc.get("dir", "data/cache"), cc.get("ttl_hours", 24), cc.get("enabled", True))
    run_dir = fetch_run(cfg, terms, window, sources, args.out_dir, config_file=args.config, on_result=_print_fetch,
                        cache=cache, refresh=args.refresh)
    m = read_json(run_dir / "manifest.json")
    ok = sum(r["status"] == FetchStatus.OK for r in m["fetches"])
    cached = sum(bool(r.get("from_cache")) for r in m["fetches"])
    note = f" ({cached} tanesi önbellekten, kaynağa gidilmedi)" if cached else ""
    print(f"\n{ok}/{len(m['fetches'])} istek veri döndürdü{note}. Kayıt: {run_dir}/ (manifest.json, raw/, "
          "processed/, run.log)")
    if cached and not args.refresh:
        print(f"Önbellek süresi {cache.ttl_hours:g} saat; kaynaktan yeniden çekmek için: --refresh")
    if ok == 0:
        print("[UYARI] Hiç veri alınamadı; yukarıdaki hata mesajlarına bakın.", file=sys.stderr)
    return run_dir


def cmd_analyze(args, run_dir: Path | None = None) -> Path:
    run_dir = run_dir or resolve_run_dir(args.run, args.out_dir)
    # Analiz ayarları varsayılan olarak GÜNCEL config'ten alınır (düzeltilen yöntemler eski kayıtlara da uygulanır);
    # --use-run-config ile çalıştırma anındaki ayarlar kullanılır. Kullanılan ayarlar analysis.json'a yazılır.
    if getattr(args, "use_run_config", False):
        a = read_json(run_dir / "manifest.json").get("analysis_settings", {})
    else:
        a = load_config(args.config)["analysis"]
    rows = analyze_dir(run_dir, a)
    print(f"Analiz: {run_dir}/analysis.csv\n")
    print(f"  {'kaynak':13} {'terim':16} {'dönemsel':>9} {'yıllık':>9}  etiket")
    for r in sorted(rows, key=lambda r: (r["source"], -(r.get("pct_change") or -1e9))):
        print(f"  {r['source']:13} {r['label']:16} {_pct(r.get('pct_change')):>9} "
              f"{_pct(r.get('yoy_pct_change')):>9}  {TREND_TR.get(r['trend_label'], r['trend_label'])}")
    return run_dir


def cmd_interpret(args, run_dir: Path | None = None, analyzed: bool = False) -> int:
    run_dir = run_dir or resolve_run_dir(args.run, args.out_dir)
    manifest = read_json(run_dir / "manifest.json")
    if not analyzed:
        # Analiz her yorumdan önce güncel kodla yeniden yapılır (çevrimdışı, saniyeler sürer); böylece eski bir
        # sürümün ürettiği analysis.json ile yorum yapılmaz.
        cmd_analyze(args, run_dir)
    analysis = read_json(run_dir / "analysis.json")
    rows = analysis["rows"]
    used = {r["source"] for r in rows}
    sources = {k: {"display": display_name(k, v), "description": v["description"]}
               for k, v in manifest["sources"].items() if k in used}
    context = {"brand": manifest.get("brand", {}), "window": manifest["window"], "sources": sources,
               "flat_threshold_pct": (analysis.get("analysis_settings") or {}).get("flat_threshold_pct", 15)}
    s = llm_settings()
    print(f"\nModele gönderiliyor: host={s['host']} model={s['model']} ...")
    handler = attach_run_log(run_dir)
    try:
        out = interpret(rows, context, s)
    except LLMError as exc:
        print(f"[HATA] {exc}", file=sys.stderr)
        return 2
    finally:
        detach_run_log(handler)
    meta = {"model": s["model"], "temperature": s["temperature"],
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "run_id": manifest["run_id"], "window": manifest["window"]}
    names = {k: v["display"] for k, v in sources.items()}
    # host adresi kaydedilmez (özel ağ/tünel adresi olabilir).
    write_json(run_dir / "interpretation.json", {**meta, "elapsed_sec": out["elapsed_sec"],
                                                 "review": out["review"], "chosen_attempt": out["chosen_attempt"],
                                                 "response": out["data"], "attempts": out["attempts"],
                                                 "prompt": out["messages"][:2]})
    md = render_markdown(out, rows, names, meta)
    (run_dir / "interpretation.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"Kayıt: {run_dir}/interpretation.md")
    return 0


def cmd_clean(args) -> int:
    """Eski çalıştırmaları ve önbelleği temizler. Varsayılan olarak yalnızca planı gösterir; silmek için --yes."""
    import shutil
    out = Path(args.out_dir)
    if "sample" in out.resolve().parts:
        print("[HATA] data/sample altındaki örnek çalıştırmalar repoya aittir; bu komutla silinmez.", file=sys.stderr)
        return 1
    runs = sorted([p for p in out.glob("*") if (p / "manifest.json").exists()]) if out.exists() else []
    old = runs[:-args.keep] if args.keep > 0 else runs
    cfg = load_config(args.config)
    cc = cfg.get("cache") or {}
    cache = FetchCache(cc.get("dir", "data/cache"), cc.get("ttl_hours", 24))
    n_cache = len(list(cache.dir.glob("*.json"))) if cache.dir.exists() else 0
    print(f"Çalıştırmalar ({out}): {len(runs)} adet; en yeni {args.keep} tanesi kalır, {len(old)} tanesi silinecek.")
    for p in old:
        print(f"  - {p.name}")
    if args.cache:
        print(f"Önbellek ({cache.dir}): {n_cache} kayıt silinecek.")
    if not args.yes:
        print("\nHiçbir şey silinmedi. Silmek için aynı komutu --yes ile çalıştırın.")
        return 0
    for p in old:
        shutil.rmtree(p)
    removed = cache.clear() if args.cache else cache.prune()
    print(f"\n{len(old)} çalıştırma silindi; önbellekten {removed} kayıt silindi.")
    return 0


def cmd_all(args) -> int:
    run_dir = cmd_fetch(args)
    print()
    cmd_analyze(args, run_dir)
    return 0 if args.skip_llm else cmd_interpret(args, run_dir, analyzed=True)


# ---------------- argparse ----------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trendpipe", description="Giyim trend veri hattı")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="store_true", help="ayrıntılı log (istekler, tekrar denemeler)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, fetch=False, run=False):
        sp.add_argument("--config", default="config/config.yaml", help="ayar dosyası (varsayılan: config/config.yaml)")
        sp.add_argument("--out-dir", default="data/runs", help="çalıştırmaların bulunduğu klasör")
        if fetch:
            sp.add_argument("--terms", help="sadece bu terim id'leri, virgülle: trenckot,hirka")
            sp.add_argument("--term", action="append", help="config dışı ek terim (tekrarlanabilir): --term 'Yelek'")
            sp.add_argument("--sources", help="kaynak seçimi, virgülle (config'teki adlar): google_trends,wikimedia")
            sp.add_argument("--end", help="dönem bitiş tarihi YYYY-MM-DD (varsayılan: bugün - end_offset_days)")
            sp.add_argument("--refresh", action="store_true",
                            help="önbelleği yok say, tüm veriyi kaynaktan yeniden çek")
        if run:
            sp.add_argument("--run", default="latest", help="çalıştırma klasörü ya da 'latest'")
            sp.add_argument("--use-run-config", action="store_true",
                            help="analiz ayarlarını güncel config yerine çalıştırma anında kaydedilenlerden al")

    sub.add_parser("check-llm", help="model bağlantısını test et")
    common(sub.add_parser("fetch", help="veriyi kaynaklardan çek ve kaydet"), fetch=True)
    common(sub.add_parser("analyze", help="kayıtlı veride değişimi hesapla"), run=True)
    common(sub.add_parser("interpret", help="analizi modele yorumlat"), run=True)
    sp = sub.add_parser("clean", help="eski çalıştırmaları ve önbelleği temizle (önce planı gösterir)")
    common(sp)
    sp.add_argument("--keep", type=int, default=10, help="saklanacak en yeni çalıştırma sayısı (varsayılan 10)")
    sp.add_argument("--cache", action="store_true", help="önbelleği tamamen temizle (yoksa yalnız süresi dolanlar)")
    sp.add_argument("--yes", action="store_true", help="planı onayla ve sil")
    sp = sub.add_parser("all", help="fetch + analyze + interpret")
    common(sp, fetch=True)
    sp.add_argument("--skip-llm", action="store_true", help="model adımını atla")
    return p


def _utf8_console() -> None:
    """Windows konsolunda (cp1254) '→', '✅' gibi karakterler hata vermesin."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    load_env()
    args = build_parser().parse_args(argv)
    setup_console(args.verbose)
    try:
        if args.cmd == "check-llm":
            return cmd_check_llm(args)
        if args.cmd == "fetch":
            cmd_fetch(args)
            return 0
        if args.cmd == "analyze":
            cmd_analyze(args)
            return 0
        if args.cmd == "interpret":
            return cmd_interpret(args)
        if args.cmd == "all":
            return cmd_all(args)
        if args.cmd == "clean":
            return cmd_clean(args)
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"[HATA] {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # çıktı `| head` gibi bir komuta verildiyse sessizce bitir
        return 0
    return 1


__all__ = ["main", "Window"]
