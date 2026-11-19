"""Çalıştırma klasörü düzeni ve dosya kayıtları.

data/runs/<run_id>/
  manifest.json            # çalıştırma bilgisi + her çekme için kaynak/terim/dönem/zaman/durum
  raw/<kaynak>__<terim>.json   # kaynağın ham yanıtı, olduğu gibi
  processed/timeseries.csv # düzenlenmiş günlük seri (analizin girdisi)
  analysis.json / analysis.csv
  interpretation.json / interpretation.md
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

from .models import FetchResult, Point

TS_FIELDS = ["source", "series", "metric", "term_id", "label", "category", "query", "date", "value", "extra"]


def new_run_dir(base: str | Path) -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = Path(base) / run_id
    (d / "raw").mkdir(parents=True, exist_ok=False)
    (d / "processed").mkdir(parents=True, exist_ok=True)
    return d


def resolve_run_dir(run: str, base: str | Path = "data/runs") -> Path:
    """'latest' -> en yeni çalıştırma; aksi halde verilen yol (ya da base altındaki run_id)."""
    if run == "latest":
        base = Path(base)
        runs = sorted([p for p in base.glob("*") if (p / "manifest.json").exists()]) if base.exists() else []
        if not runs:
            raise FileNotFoundError(f"{base} altında çalıştırma yok. Önce: python -m trendpipe fetch")
        return runs[-1]
    p = Path(run)
    if not p.exists() and (Path(base) / run).exists():
        p = Path(base) / run
    if not (p / "manifest.json").exists():
        raise FileNotFoundError(f"Geçerli bir çalıştırma klasörü değil (manifest.json yok): {p}")
    return p


def save_raw(run_dir: Path, res: FetchResult) -> str | None:
    if res.raw_body is None:
        return None
    suffix = "" if res.series == "main" else f"__{res.series}"
    rel = f"raw/{res.source}__{res.term_id}{suffix}.{res.raw_ext}"
    (run_dir / rel).write_text(res.raw_body, encoding="utf-8")
    return rel


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_default), encoding="utf-8")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_timeseries(run_dir: Path, results: list[FetchResult], terms_by_id: dict) -> Path:
    path = run_dir / "processed" / "timeseries.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TS_FIELDS)
        w.writeheader()
        for res in results:
            t = terms_by_id[res.term_id]
            for p in res.points:
                w.writerow({"source": res.source, "series": res.series, "metric": res.metric, "term_id": res.term_id,
                            "label": t.label, "category": t.category, "query": res.query,
                            "date": p.day.isoformat(), "value": p.value,
                            "extra": json.dumps(p.extra, ensure_ascii=False) if p.extra else ""})
    return path


def read_timeseries(run_dir: Path) -> dict[tuple[str, str, str], list[Point]]:
    """(kaynak, terim_id, seri) -> noktalar. Eski kayıtlarda 'series' sütunu yoksa 'main' kabul edilir."""
    out: dict[tuple[str, str], list[Point]] = {}
    path = run_dir / "processed" / "timeseries.csv"
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["source"], row["term_id"], row.get("series") or "main")
            out.setdefault(key, []).append(
                Point(date.fromisoformat(row["date"]), float(row["value"]),
                      json.loads(row["extra"]) if row.get("extra") else None))
    return out


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"JSON'a çevrilemiyor: {type(o)}")
