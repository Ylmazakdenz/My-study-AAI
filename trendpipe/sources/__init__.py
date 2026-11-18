"""Kaynak kayıt defteri. Yeni kaynak eklemek için Source alt sınıfı yazıp buraya ekleyin."""

from __future__ import annotations

from .base import Source
from .gdelt import GdeltSource
from .google_trends import GoogleTrendsSource
from .wikimedia import WikimediaSource

REGISTRY: dict[str, type[Source]] = {
    WikimediaSource.name: WikimediaSource,
    GdeltSource.name: GdeltSource,
    GoogleTrendsSource.name: GoogleTrendsSource,
}


def build_sources(cfg: dict, only: list[str] | None = None, user_agent: str = "SENG360-trendpipe/0.1",
                  session=None) -> list[Source]:
    """Config'te açık olan (ya da --sources ile seçilen) kaynakları oluşturur."""
    src_cfg = cfg.get("sources") or {}
    if only:
        unknown = set(only) - set(REGISTRY)
        if unknown:
            raise ValueError(f"Bilinmeyen kaynak: {', '.join(sorted(unknown))}. Seçenekler: {', '.join(REGISTRY)}")
        names = list(only)
    else:
        names = [n for n in REGISTRY if (src_cfg.get(n) or {}).get("enabled")]
    return [REGISTRY[n](src_cfg.get(n) or {}, session=session, user_agent=user_agent) for n in names]


__all__ = ["REGISTRY", "Source", "build_sources"]
