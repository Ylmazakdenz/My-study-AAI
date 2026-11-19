"""Kaynak kayıt defteri. Yeni kaynak tipi eklemek için Source alt sınıfı yazıp TYPES'a ekleyin.

Config'teki her `sources:` anahtarı bir kaynak örneğidir. Tipi `type:` ile verilir;
verilmezse anahtar adı tip kabul edilir.
Örn. aynı tipten iki kaynak:
  wikimedia:     {type: wikimedia, project: tr.wikipedia}
  wikimedia_en:  {type: wikimedia, project: en.wikipedia}
"""

from __future__ import annotations

from .base import Source
from .gdelt import GdeltSource
from .google_trends import GoogleTrendsSource
from .wikimedia import WikimediaSource

TYPES: dict[str, type[Source]] = {
    WikimediaSource.type_name: WikimediaSource,
    GdeltSource.type_name: GdeltSource,
    GoogleTrendsSource.type_name: GoogleTrendsSource,
}


def build_sources(cfg: dict, only: list[str] | None = None, user_agent: str = "SENG360-trendpipe/0.1",
                  session=None) -> list[Source]:
    """Config'te açık olan (ya da --sources ile seçilen) kaynak örneklerini oluşturur."""
    src_cfg = cfg.get("sources") or {}
    if only:
        unknown = set(only) - set(src_cfg)
        if unknown:
            raise ValueError(f"Config'te olmayan kaynak: {', '.join(sorted(unknown))}. "
                             f"Seçenekler: {', '.join(src_cfg)}")
        names = list(only)
    else:
        names = [n for n, s in src_cfg.items() if (s or {}).get("enabled")]
    out = []
    for n in names:
        settings = src_cfg.get(n) or {}
        typ = settings.get("type", n)
        if typ not in TYPES:
            raise ValueError(f"'{n}' kaynağının tipi bilinmiyor: {typ}. Tipler: {', '.join(TYPES)}")
        src = TYPES[typ](settings, session=session, user_agent=user_agent, name=n)
        src.timezone = (cfg.get("window") or {}).get("timezone", "Europe/Istanbul")
        out.append(src)
    return out


__all__ = ["TYPES", "Source", "build_sources"]
