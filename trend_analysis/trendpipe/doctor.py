"""Kurulum kontrolü: `trendpipe doctor`.

Repoyu yeni açan biri (ör. ekip arkadaşı) kurulumunun doğru olup olmadığını tek komutla görür. Kaynaklara veri
isteği göndermez (hız sınırını harcamamak için); `--network` ile yalnızca sunuculara erişilebildiği denetlenir.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

OK, WARN, FAIL = "✅", "⚠️ ", "❌"
PACKAGES = (("requests", "requests"), ("PyYAML", "yaml"), ("python-dotenv", "dotenv"), ("pydantic", "pydantic"),
            ("ollama", "ollama"), ("pytrends", "pytrends"), ("pandas", "pandas"))


@dataclass
class Check:
    status: str
    name: str
    detail: str


def _python() -> Check:
    v = sys.version_info
    ok = v >= (3, 10)
    rc = " (deneme sürümü; kararlı bir sürüm önerilir)" if v.releaselevel != "final" else ""
    st = (OK if not rc else WARN) if ok else FAIL
    return Check(st, "Python", f"{sys.version.split()[0]}{rc}" + ("" if ok else " — en az 3.10 gerekli"))


def _packages() -> list[Check]:
    out = []
    for dist, mod in PACKAGES:
        try:
            __import__(mod)
            out.append(Check(OK, f"paket {dist}", metadata.version(dist)))
        except Exception as exc:  # ImportError ya da paketin kendi içindeki hata
            out.append(Check(FAIL, f"paket {dist}", f"yüklenemedi ({type(exc).__name__}) — "
                                                      "pip install -r requirements.txt"))
    return out


def _config(path: str) -> tuple[Check, dict | None]:
    from .config import ConfigError, load_config
    try:
        cfg = load_config(path)
    except ConfigError as exc:
        return Check(FAIL, "ayar dosyası", str(exc).replace("\n", " ")), None
    enabled = [n for n, s in cfg["sources"].items() if s.get("enabled")]
    st = OK if enabled else FAIL
    return Check(st, "ayar dosyası", f"{path} geçerli; açık kaynaklar: {', '.join(enabled) or 'YOK'}; "
                                     f"{len(cfg['terms'])} terim"), cfg


def _env() -> Check:
    if Path(".env").exists():
        return Check(OK, ".env", "bulundu")
    return Check(WARN, ".env", "yok; varsayılanlar kullanılacak (cp .env.example .env)")


def _ollama() -> list[Check]:
    from .config import ConfigError, llm_settings
    try:
        s = llm_settings()
    except ConfigError as exc:
        return [Check(FAIL, "model ayarları", str(exc))]
    try:
        import ollama  # type: ignore
        resp = ollama.Client(host=s["host"], timeout=10).list()
    except Exception as exc:
        return [Check(FAIL, "Ollama sunucusu", f"{s['host']} erişilemedi ({type(exc).__name__}) — Ollama "
                                               "uygulaması açık mı?")]
    models = resp.get("models", []) if isinstance(resp, dict) else getattr(resp, "models", [])
    names = set()
    for m in models:
        name = m.get("model") or m.get("name") if isinstance(m, dict) else getattr(m, "model", None)
        if name:
            names.add(name)
    want = s["model"]
    has = want in names or f"{want}:latest" in names
    installed = ", ".join(sorted(names)) or "yok"
    detail = "indirilmiş" if has else f"indirilmemiş — ollama pull {want} (kurulu: {installed})"
    return [Check(OK, "Ollama sunucusu", s["host"]), Check(OK if has else FAIL, f"model {want}", detail)]


def _writable(label: str, path: str) -> Check:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".yazma_testi"
        probe.write_text("x")
        probe.unlink()
        return Check(OK, label, str(p))
    except OSError as exc:
        return Check(FAIL, label, f"{p} yazılamıyor ({exc})")


def _network() -> list[Check]:
    import requests
    out = []
    for name, url in (("Wikimedia", "https://wikimedia.org/api/rest_v1/"),
                      ("Google Trends", "https://trends.google.com/")):
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            out.append(Check(OK if r.status_code < 500 else WARN, f"ağ {name}", f"HTTP {r.status_code}"))
        except requests.RequestException as exc:
            out.append(Check(FAIL, f"ağ {name}", f"erişilemedi ({type(exc).__name__})"))
    return out


def run(config_path: str, out_dir: str, network: bool = False, llm: bool = True) -> list[Check]:
    checks = [_python(), *_packages()]
    c, cfg = _config(config_path)
    checks += [c, _env()]
    if llm:
        checks += _ollama()
    checks.append(_writable("çalıştırma klasörü", out_dir))
    if cfg:
        checks.append(_writable("önbellek klasörü", (cfg.get("cache") or {}).get("dir", "data/cache")))
    if network:
        checks += _network()
    return checks


def report(checks: list[Check]) -> int:
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"  {c.status} {c.name:<{width}}  {c.detail}")
    fails = sum(c.status == FAIL for c in checks)
    warns = sum(c.status == WARN for c in checks)
    print(f"\n{len(checks) - fails - warns} tamam, {warns} uyarı, {fails} hata.")
    if os.name == "nt" and fails:
        print("Windows'ta komutlar: .venv\\Scripts\\activate ve copy .env.example .env")
    return 1 if fails else 0
