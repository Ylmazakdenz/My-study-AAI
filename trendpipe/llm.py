"""Model bağlantısı — hocanın notebook'undaki yöntem (`ollama` Python paketi + Ollama sunucusu).

Hocanın kodu `ollama.chat(model='llama3.2', ...)` çağırır; bu varsayılan olarak http://localhost:11434 adresine gider.
Burada aynı çağrıyı `ollama.Client(host=...)` ile yapıyoruz; böylece adres .env'den değiştirilebilir:
  - Colab'da (hocanın kurulumu): OLLAMA_HOST=http://localhost:11434
  - Kendi bilgisayarınızda Ollama kuruluysa: yine http://localhost:11434
"""

from __future__ import annotations

import json
import re
import time

from .prompts import SYSTEM_PROMPT, build_user_prompt


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], settings: dict) -> dict:
    try:
        import ollama  # type: ignore
    except ImportError as exc:
        raise LLMError("'ollama' paketi kurulu değil: pip install -r requirements.txt") from exc

    client = ollama.Client(host=settings["host"], timeout=settings.get("timeout"))
    t0 = time.monotonic()
    try:
        resp = client.chat(model=settings["model"], messages=messages,
                           options={"temperature": settings.get("temperature", 0.2)})
    except Exception as exc:  # bağlantı reddi, model yok, zaman aşımı...
        hint = ""
        msg = str(exc).lower()
        if "connect" in msg or "refused" in msg:
            hint = (" | İpucu: Ollama sunucusu çalışıyor mu? Colab'da notebook'un 'ollama serve' hücresini, "
                    "yerelde 'ollama serve' komutunu çalıştırın ve OLLAMA_HOST'u kontrol edin.")
        elif "not found" in msg:
            hint = f" | İpucu: model indirilmemiş olabilir: ollama pull {settings['model']}"
        raise LLMError(f"{type(exc).__name__}: {exc}{hint}") from exc
    content = resp["message"]["content"]
    return {"content": content, "elapsed_sec": round(time.monotonic() - t0, 2)}


def ping(settings: dict) -> dict:
    """1. gün: bağlantıyı doğrulamak için basit istek."""
    return chat([{"role": "user", "content": "Bağlantı testi. Sadece 'Merhaba, bağlantı çalışıyor.' yaz."}],
                settings)


def interpret(analysis_rows: list[dict], context: dict, settings: dict) -> dict:
    user_prompt = build_user_prompt(analysis_rows, context)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
    out = chat(messages, settings)
    out["check"] = check_numbers(out["content"], analysis_rows)
    out["messages"] = messages
    return out


_PCT = re.compile(r"([-+−]?\d+(?:[.,]\d+)?)\s*%|%\s*([-+−]?\d+(?:[.,]\d+)?)")


def check_numbers(text: str, rows: list[dict], tol: float = 1.0) -> dict:
    """Modelin yazdığı yüzdelerin hesapladığımız değerlerle örtüşüp örtüşmediğini kontrol eder.

    Küçük modeller sayı uydurabilir; eşleşmeyen yüzdeler raporlanır (açıklanabilirlik / güvenlik kontrolü).
    """
    allowed = []
    for r in rows:
        for key in ("pct_change", "baseline_coverage", "recent_coverage"):
            v = r.get(key)
            if v is None:
                continue
            allowed.append(abs(v * 100) if key.endswith("coverage") else abs(v))
    found, unmatched = [], []
    for m in _PCT.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(",", ".").replace("−", "-")
        try:
            val = abs(float(raw))
        except ValueError:
            continue
        found.append(val)
        if not any(abs(val - a) <= tol for a in allowed):
            unmatched.append(val)
    return {"percentages_found": found, "unmatched_percentages": unmatched,
            "ok": not unmatched,
            "note": ("Modelin yazdığı tüm yüzdeler hesaplanan değerlerle uyumlu." if not unmatched else
                     "Modelin yazdığı bazı yüzdeler hesaplanan sonuçlarda yok; yorum dikkatle okunmalı.")}


def to_markdown(result: dict, meta: dict) -> str:
    chk = result["check"]
    lines = [
        "# Trend yorumu",
        "",
        f"- Model: `{meta['model']}` (Ollama) — sıcaklık {meta['temperature']}",
        f"- Oluşturma: {meta['created_at']} — süre {result['elapsed_sec']} sn",
        f"- Çalıştırma: `{meta['run_id']}` — dönem {meta['window']['baseline_start']} → {meta['window']['recent_end']}",
        f"- Sayı kontrolü: {'✅' if chk['ok'] else '⚠️'} {chk['note']}"
        + (f" (eşleşmeyen: {', '.join(f'%{v:g}' for v in chk['unmatched_percentages'])})" if not chk["ok"] else ""),
        "",
        "---",
        "",
        result["content"].strip(),
        "",
    ]
    return "\n".join(lines)


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=2)
