"""Ayar dosyası (YAML) ve ortam değişkenlerini (.env) okur."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from .models import Term

try:  # .env opsiyonel
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


class ConfigError(ValueError):
    pass


@dataclass
class Window:
    """Analiz pencereleri.

    Dönemsel karşılaştırma: [baseline_start..baseline_end] → [recent_start..recent_end] (ardışık iki dönem).
    Yıllık karşılaştırma:  [ly_start..ly_end] → [recent_start..recent_end]; ly = yakın dönemin 364 gün öncesi
    (52 hafta: haftanın günleri hizalı kalır). Mevsimsel artışı gerçek değişimden ayırmak için kullanılır.
    """

    baseline_start: date
    baseline_end: date
    recent_start: date
    recent_end: date
    ly_start: date | None = None
    ly_end: date | None = None

    @property
    def start(self) -> date:
        return self.baseline_start

    @property
    def end(self) -> date:
        return self.recent_end

    @property
    def has_yoy(self) -> bool:
        return self.ly_start is not None and self.ly_end is not None

    def as_dict(self) -> dict:
        return {k: v.isoformat() for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> Window:
        return cls(**{k: date.fromisoformat(v) for k, v in d.items() if k in cls.__dataclass_fields__})


def load_env(env_file: str | None = None) -> None:
    if load_dotenv is not None:
        load_dotenv(env_file or ".env", override=False)


def load_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Ayar dosyası bulunamadı: {p}")
    with p.open(encoding="utf-8") as f:
        try:
            cfg = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Ayar dosyası YAML olarak okunamadı ({p}): {exc}") from exc
    from .schema import validate_config
    return validate_config(cfg, source=str(p))


def parse_terms(cfg: dict, only_ids: list[str] | None = None, extra: list[str] | None = None) -> list[Term]:
    """Config'teki terimleri döndürür.

    only_ids: sadece bu id'leri al (komut satırından --terms).
    extra: komut satırından --term ile verilen ek terimler; aynı metin config'teki tüm kaynaklarda sorgulanır.
    """
    terms: list[Term] = []
    seen: set[str] = set()
    for t in cfg.get("terms") or []:
        if "id" not in t or "label" not in t:
            raise ConfigError(f"Her terimde 'id' ve 'label' olmalı: {t}")
        if t["id"] in seen:
            raise ConfigError(f"Tekrarlanan terim id: {t['id']}")
        seen.add(t["id"])
        terms.append(Term(id=t["id"], label=t["label"], category=t.get("category", ""),
                          queries=dict(t.get("queries") or {})))
    if only_ids:
        wanted = set(only_ids)
        unknown = wanted - seen
        if unknown:
            raise ConfigError(f"Config'te olmayan terim id: {', '.join(sorted(unknown))}")
        terms = [t for t in terms if t.id in wanted]
    for text in extra or []:
        tid = _slug(text)
        if tid in seen:
            raise ConfigError(f"--term '{text}' mevcut bir id ile çakışıyor: {tid}")
        seen.add(tid)
        terms.append(Term(id=tid, label=text, category="komut satırı",
                          queries={name: text for name in (cfg.get("sources") or {})}))
    if not terms:
        raise ConfigError("Sorgulanacak terim yok.")
    return terms


def compute_window(cfg: dict, today: date | None = None, end: date | None = None) -> Window:
    w = cfg["window"]
    recent = int(w.get("recent_days", 28))
    base = int(w.get("baseline_days", recent))
    if recent < 3 or base < 3:
        raise ConfigError("recent_days ve baseline_days en az 3 olmalı.")
    if end is None:
        today = today or date.today()
        end = today - timedelta(days=int(w.get("end_offset_days", 2)))
    recent_start = end - timedelta(days=recent - 1)
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=base - 1)
    ly_start = ly_end = None
    if w.get("yoy", True):
        shift = timedelta(days=int(w.get("yoy_shift_days", 364)))
        ly_start, ly_end = recent_start - shift, end - shift
    return Window(baseline_start, baseline_end, recent_start, end, ly_start, ly_end)


def llm_settings() -> dict:
    """Model bağlantı ayarları .env / ortam değişkenlerinden gelir; repoya yazılmaz."""
    return {
        "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
        "timeout": float(os.getenv("OLLAMA_TIMEOUT", "300")),
    }


PROJECT_URL = "https://github.com/Ylmazakdenz/My-study-AAI"


def user_agent() -> str:
    """Wikimedia politikası: '<istemci>/<sürüm> (<iletişim>) <kütüphane>'. İletişim bilgisi olmayan istemciler
    daha sıkı hız sınırına takılabilir; e-posta verilmezse proje adresi iletişim olarak yazılır."""
    contact = os.getenv("CONTACT_EMAIL", "").strip()
    contact_part = f"{PROJECT_URL}; {contact}" if contact else PROJECT_URL
    return f"SENG360-trendpipe/0.1 ({contact_part}) python-requests"


_TR = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosuCGIOSU_")


def _slug(text: str) -> str:
    s = text.translate(_TR).lower()
    return "".join(ch for ch in s if ch.isalnum() or ch == "_") or "terim"
