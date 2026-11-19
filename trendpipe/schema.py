"""Ayar dosyası şeması (pydantic). Yazım hataları ve yanlış türler çalıştırmadan önce yakalanır.

Örn. `recent_day: 28` (s eksik), `enabled: evet`, terimde var olmayan bir kaynak adı ya da kaynağa ait olmayan
bir ayar (`geoo: TR`) açık bir hata mesajıyla reddedilir; eskiden bunlar sessizce görmezden geliniyordu.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Kaynak tipine özgü ayarlar: hem ad hem tür denetlenir
# (ör. samples: "iki" çalıştırma sırasında değil, burada yakalanır)
class WikimediaOpts(_Strict):
    project: str = Field("tr.wikipedia", pattern=r"^[a-z\-]+\.wikipedia$")
    access: Literal["all-access", "desktop", "mobile-app", "mobile-web"] = "all-access"
    agent: Literal["user", "spider", "automated", "all-agents"] = "user"
    normalize_by_project: bool = True


class GdeltOpts(_Strict):
    source_country: str = ""
    source_lang: str = ""
    mode: Literal["timelinevolraw", "timelinevol"] = "timelinevolraw"


class GoogleTrendsOpts(_Strict):
    geo: str = Field("TR", pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")
    hl: str = "tr-TR"
    samples: int = Field(1, ge=1, le=5)


TYPE_OPTS: dict[str, type[_Strict]] = {"wikimedia": WikimediaOpts, "gdelt": GdeltOpts,
                                       "google_trends": GoogleTrendsOpts}
TYPE_KEYS: dict[str, set[str]] = {k: set(v.model_fields) for k, v in TYPE_OPTS.items()}


class BrandCfg(_Strict):
    name: str
    market: str = "TR"
    season: str = ""


class WindowCfg(_Strict):
    recent_days: int = Field(28, ge=3)
    baseline_days: int = Field(28, ge=3)
    end_offset_days: int = Field(2, ge=0)
    yoy: bool = True
    yoy_shift_days: int = Field(364, ge=300, le=400)


class AnalysisCfg(_Strict):
    @field_validator("normalize_by_norm", mode="before")
    @classmethod
    def _list_to_dict(cls, v):
        return {k: 10_000 for k in v} if isinstance(v, list) else v

    min_coverage: float = Field(0.8, ge=0, le=1)
    flat_threshold_pct: float = Field(15, gt=0)
    min_window_days_ratio: float = Field(0.5, ge=0, le=1)
    # kaynak -> oran birimi (ör. gdelt: 10000 = "10.000 haberde", wikimedia: 1000000 = "milyon görüntülemede")
    normalize_by_norm: dict[str, float] = {}
    min_norm_ratio: float = Field(0.2, ge=0, le=1)
    zero_is_missing: list[str] = []
    low_volume: dict[str, float] = {}


class SourceCfg(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str | None = None
    enabled: bool = False
    yoy: bool = True
    request_interval_sec: float = Field(0, ge=0)
    timeout_sec: float = Field(30, gt=0)
    max_retries: int = Field(0, ge=0, le=10)
    retry_backoff_sec: float = Field(0, ge=0)
    stop_after_consecutive_429: int = Field(0, ge=0)


class CacheCfg(_Strict):
    enabled: bool = True
    ttl_hours: float = Field(24, ge=0)
    dir: str = "data/cache"


class TermCfg(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str
    category: str = ""
    queries: dict[str, str] = {}


class AppCfg(_Strict):
    brand: BrandCfg
    window: WindowCfg = WindowCfg()
    analysis: AnalysisCfg = AnalysisCfg()
    cache: CacheCfg = CacheCfg()
    sources: dict[str, SourceCfg]
    terms: list[TermCfg] = Field(min_length=1)

    @field_validator("sources")
    @classmethod
    def _source_types(cls, v: dict[str, SourceCfg]) -> dict[str, SourceCfg]:
        for name, sc in v.items():
            typ = sc.type or name
            if typ not in TYPE_KEYS:
                raise ValueError(f"'{name}' kaynağının tipi bilinmiyor: {typ} (tipler: {', '.join(TYPE_KEYS)})")
            unknown = set(sc.model_extra or {}) - TYPE_KEYS[typ]
            if unknown:
                raise ValueError(f"'{name}' kaynağında bilinmeyen ayar: {', '.join(sorted(unknown))} "
                                 f"({typ} için geçerli olanlar: {', '.join(sorted(TYPE_KEYS[typ]))})")
            try:
                TYPE_OPTS[typ].model_validate(sc.model_extra or {})
            except ValidationError as exc:
                e = exc.errors()[0]
                raise ValueError(f"'{name}' kaynağında '{'.'.join(str(x) for x in e['loc'])}' geçersiz: "
                                 f"{e['msg']}") from None
        return v

    @model_validator(mode="after")
    def _cross_refs(self) -> AppCfg:
        names = set(self.sources)
        ids = [t.id for t in self.terms]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"Tekrarlanan terim id: {', '.join(sorted(dup))}")
        for t in self.terms:
            bad = set(t.queries) - names
            if bad:
                raise ValueError(f"'{t.id}' teriminde tanımsız kaynak adı: {', '.join(sorted(bad))} "
                                 f"(kaynaklar: {', '.join(sorted(names))})")
        a = self.analysis
        for field, keys in (("low_volume", a.low_volume), ("normalize_by_norm", a.normalize_by_norm),
                            ("zero_is_missing", a.zero_is_missing)):
            bad = set(keys) - names
            if bad:
                raise ValueError(f"analysis.{field} içinde tanımsız kaynak adı: {', '.join(sorted(bad))}")
        return self


def validate_config(cfg: dict, source: str = "config") -> dict:
    """Doğrulanmış ayarları sözlük olarak döndürür (varsayılanlar doldurulmuş)."""
    from .config import ConfigError
    try:
        model = AppCfg.model_validate(cfg)
    except ValidationError as exc:
        lines = []
        for e in exc.errors():
            loc = ".".join(str(x) for x in e["loc"])
            msg = e["msg"].replace("Value error, ", "")
            if e["type"] == "extra_forbidden":
                msg = "bilinmeyen alan (yazım hatası olabilir)"
            elif e["type"] == "missing":
                msg = "zorunlu alan eksik"
            lines.append(f"  - {loc or '(kök)'}: {msg}")
        raise ConfigError(f"Ayar dosyası geçersiz ({source}):\n" + "\n".join(lines)) from None
    out = model.model_dump()
    for name, sc in model.sources.items():
        out["sources"][name] = {**sc.model_dump(), "type": sc.type or name}
    return out
