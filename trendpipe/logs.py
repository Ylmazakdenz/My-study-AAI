"""Log kaydı: her çalıştırmanın klasörüne run.log yazılır (istekler, tekrar denemeler, bekleme süreleri).

Konsola yalnızca uyarılar gider; kullanıcıya dönük tablolar cli.py'de basılır.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER_NAME = "trendpipe"
_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def setup_console(verbose: bool = False) -> None:
    root = get_logger()
    root.setLevel(logging.DEBUG)
    if not any(getattr(h, "_trendpipe_console", False) for h in root.handlers):
        h = logging.StreamHandler()
        h._trendpipe_console = True  # type: ignore[attr-defined]
        h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(h)
    for h in root.handlers:
        if getattr(h, "_trendpipe_console", False):
            h.setLevel(logging.INFO if verbose else logging.WARNING)


def attach_run_log(run_dir: Path) -> logging.Handler:
    """run_dir/run.log dosyasına ayrıntılı kayıt ekler; işi bitince detach_run_log ile kaldırılır."""
    h = logging.FileHandler(Path(run_dir) / "run.log", encoding="utf-8")
    h.setLevel(logging.DEBUG)
    h.setFormatter(logging.Formatter(_FMT))
    get_logger().addHandler(h)
    get_logger().setLevel(logging.DEBUG)
    return h


def detach_run_log(handler: logging.Handler) -> None:
    get_logger().removeHandler(handler)
    handler.close()
