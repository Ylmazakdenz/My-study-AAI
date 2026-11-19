"""Çalıştırma ortamı kaydı (tekrarlanabilirlik).

Her manifest.json, hangi kod sürümü (git commit), Python ve paket sürümleriyle üretildiğini yazar. Sonuçlar
farklı çıktığında "kod mu değişti, paket mi, veri mi?" sorusu buradan yanıtlanır.
"""

from __future__ import annotations

import platform
import subprocess
from importlib import metadata
from pathlib import Path

from . import __version__

KEY_PACKAGES = ("requests", "pytrends", "pandas", "pydantic", "ollama", "PyYAML")


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=Path(__file__).resolve().parent, capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def run_environment() -> dict:
    packages = {}
    for name in KEY_PACKAGES:
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    commit = _git("rev-parse", "--short", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no") if commit else None
    return {
        "trendpipe": __version__,
        "git_commit": commit,
        "git_dirty": bool(status) if status is not None else None,   # commit'lenmemiş kod değişikliği var mı
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
        "packages": packages,
    }
