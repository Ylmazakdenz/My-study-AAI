"""Komut satırı.

  python -m trendpipe check-llm                     # 1. gün: model bağlantısını test et
  python -m trendpipe fetch                         # veriyi çek ve kaydet
  python -m trendpipe analyze --run latest          # değişimi hesapla
  python -m trendpipe interpret --run latest        # modele yorumlat
  python -m trendpipe all                           # hepsi sırayla
Kayıtlı veriyle (bağlantı olmadan) tekrar: analyze/interpret --run data/sample/<run_id>
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__
from .analysis import ANALYSIS_FIELDS, analyze_run, flatten_for_csv
from .config import ConfigError, Window, compute_window, llm_settings, load_config, load_env, parse_terms, user_agent
from .llm import LLMError, interpret, ping, to_markdown
from .models import FetchStatus
from .sources import build_sources
from .storage import (new_run_dir, read_json, read_timeseries, resolve_run_dir, save_raw, write_csv, write_json,
                      write_timeseries)

STATUS_ICON = {FetchStatus.OK: "OK ", FetchStatus.EMPTY: "BOŞ", FetchStatus.NOT_FOUND: "YOK",
               FetchStatus.ERROR: "HATA", FetchStatus.SKIPPED: "ATLA"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _csv_list(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


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


def cmd_fetch(args) -> Path:
    cfg = load_config(args.config)
    terms = parse_terms(cfg, _csv_list(args.terms), args.term)
    end = date.fromisoformat(args.end) if args.end else None
    window = compute_window(cfg, end=end)
    sources = build_sources(cfg, _csv_list(args.sources), user_agent=user_agent())
    if not sources:
        raise ConfigError("Açık kaynak yok. config'te 'enabled: true' yapın ya da --sources verin.")

    run_dir = new_run_dir(args.out_dir)
    print(f"Çalıştırma: {run_dir}")
    print(f"Dönem: {window.start} → {window.end}  (önceki {window.baseline_start}–{window.baseline_end}, "
          f"yakın {window.recent_start}–{window.recent_end})")
    print(f"Kaynaklar: {', '.join(s.name for s in sources)} | Terimler: {', '.join(t.label for t in terms)}\n")

    terms_by_id = {t.id: t for t in terms}
    results, records = [], []
    for src in sources:
        for t in terms:
            q = t.queries.get(src.name)
            if not q:
                res = src._result(t.id, "", window.start, window.end, status=FetchStatus.SKIPPED,
                                  error=f"Bu terim için '{src.name}' sorgusu tanımlı değil")
            else:
                res = src.fetch(t.id, q, window.start, window.end)
            raw_file = save_raw(run_dir, res)
            rec = {**res.meta(), "label": t.label, "category": t.category, "raw_file": raw_file}
            records.append(rec)
            if res.status == FetchStatus.OK:
                results.append(res)
            detail = f"{len(res.points)} gün" if res.status == FetchStatus.OK else (res.error or "")
            if res.attempts > 1:
                detail += f" ({res.attempts}. denemede)"
            print(f"  [{STATUS_ICON[res.status]:4}] {src.name:13} {t.label:18} {q!r:24} {detail[:110]}")

    write_timeseries(run_dir, results, terms_by_id)
    manifest = {
        "run_id": run_dir.name, "created_at": _now(), "tool_version": __version__,
        "config_file": str(args.config), "brand": cfg.get("brand", {}), "window": window.as_dict(),
        "analysis_settings": cfg.get("analysis", {}),
        "sources": {s.name: {"metric": s.metric, "description": s.description, "settings": s.settings}
                    for s in sources},
        "fetches": records,
    }
    write_json(run_dir / "manifest.json", manifest)
    ok = sum(r["status"] == FetchStatus.OK for r in records)
    print(f"\n{ok}/{len(records)} istek veri döndürdü. Kayıt: {run_dir}/manifest.json, raw/, processed/timeseries.csv")
    if ok == 0:
        print("[UYARI] Hiç veri alınamadı; yukarıdaki hata mesajlarına bakın.", file=sys.stderr)
    return run_dir


def _window_from_manifest(m: dict) -> Window:
    w = m["window"]
    return Window(*(date.fromisoformat(w[k]) for k in ("baseline_start", "baseline_end", "recent_start", "recent_end")))


def cmd_analyze(args, run_dir: Path | None = None) -> Path:
    run_dir = run_dir or resolve_run_dir(args.run, args.out_dir)
    manifest = read_json(run_dir / "manifest.json")
    # Analiz ayarları: --config verilirse oradan, yoksa çalıştırma anındaki ayarlar (tekrarlanabilirlik).
    cfg = load_config(args.config) if getattr(args, "use_current_config", False) else \
        {"analysis": manifest.get("analysis_settings", {})}
    rows = analyze_run(manifest, read_timeseries(run_dir), cfg, _window_from_manifest(manifest))
    write_json(run_dir / "analysis.json", {"run_id": manifest["run_id"], "created_at": _now(),
                                           "window": manifest["window"], "rows": rows})
    write_csv(run_dir / "analysis.csv", flatten_for_csv(rows), ANALYSIS_FIELDS)

    print(f"Analiz: {run_dir}/analysis.csv\n")
    print(f"  {'kaynak':13} {'terim':18} {'önceki ort':>11} {'yakın ort':>10} {'değişim':>9}  yön   durum")
    for r in sorted(rows, key=lambda r: (r["source"], -(r.get("pct_change") or -1e9))):
        pct = f"{r['pct_change']:+.1f}%" if r.get("pct_change") is not None else "-"
        bm = f"{r['baseline_mean']:.1f}" if r.get("baseline_mean") is not None else "-"
        rm = f"{r['recent_mean']:.1f}" if r.get("recent_mean") is not None else "-"
        print(f"  {r['source']:13} {r['label']:18} {bm:>11} {rm:>10} {pct:>9}  {r.get('direction') or '-':5} "
              f"{r['result']}")
    return run_dir


def cmd_interpret(args, run_dir: Path | None = None) -> int:
    run_dir = run_dir or resolve_run_dir(args.run, args.out_dir)
    manifest = read_json(run_dir / "manifest.json")
    if not (run_dir / "analysis.json").exists():
        cmd_analyze(args, run_dir)
    rows = read_json(run_dir / "analysis.json")["rows"]
    used = {r["source"] for r in rows}
    context = {"brand": manifest.get("brand", {}), "window": manifest["window"],
               "sources": {k: v["description"] for k, v in manifest["sources"].items() if k in used},
               "flat_threshold_pct": (manifest.get("analysis_settings") or {}).get("flat_threshold_pct", 15)}
    s = llm_settings()
    print(f"\nModele gönderiliyor: host={s['host']} model={s['model']} ...")
    try:
        out = interpret(rows, context, s)
    except LLMError as exc:
        print(f"[HATA] {exc}", file=sys.stderr)
        return 2
    meta = {"model": s["model"], "temperature": s["temperature"], "created_at": _now(),
            "run_id": manifest["run_id"], "window": manifest["window"]}
    # host adresi kaydedilmez (özel ağ/tünel adresi olabilir).
    write_json(run_dir / "interpretation.json", {**meta, "elapsed_sec": out["elapsed_sec"], "check": out["check"],
                                                 "prompt": out["messages"], "response": out["content"]})
    md = to_markdown(out, meta)
    (run_dir / "interpretation.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"Kayıt: {run_dir}/interpretation.md")
    return 0


def cmd_all(args) -> int:
    run_dir = cmd_fetch(args)
    print()
    cmd_analyze(args, run_dir)
    if args.skip_llm:
        return 0
    return cmd_interpret(args, run_dir)


# ---------------- argparse ----------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trendpipe", description="Giyim trend veri hattı")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, fetch=False, run=False):
        sp.add_argument("--config", default="config/config.yaml", help="ayar dosyası (varsayılan: config/config.yaml)")
        sp.add_argument("--out-dir", default="data/runs", help="çalıştırmaların kaydedileceği klasör")
        if fetch:
            sp.add_argument("--terms", help="sadece bu terim id'leri, virgülle: trenckot,hirka")
            sp.add_argument("--term", action="append", help="config dışı ek terim (tekrarlanabilir): --term 'Yelek'")
            sp.add_argument("--sources", help="kaynak seçimi, virgülle (config'teki adlar): wikimedia,gdelt")
            sp.add_argument("--end", help="dönem bitiş tarihi YYYY-MM-DD (varsayılan: bugün - end_offset_days)")
        if run:
            sp.add_argument("--run", default="latest", help="çalıştırma klasörü ya da 'latest'")
            sp.add_argument("--use-current-config", action="store_true",
                            help="analiz eşiklerini kayıttaki yerine güncel config'ten al")

    sub.add_parser("check-llm", help="model bağlantısını test et")
    common(sub.add_parser("fetch", help="veriyi kaynaklardan çek ve kaydet"), fetch=True)
    common(sub.add_parser("analyze", help="kayıtlı veride değişimi hesapla"), run=True)
    common(sub.add_parser("interpret", help="analizi modele yorumlat"), run=True)
    sp = sub.add_parser("all", help="fetch + analyze + interpret")
    common(sp, fetch=True)
    sp.add_argument("--skip-llm", action="store_true", help="model adımını atla")
    return p


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = build_parser().parse_args(argv)
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
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"[HATA] {exc}", file=sys.stderr)
        return 1
    return 1
