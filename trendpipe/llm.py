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
    out["check"] = check_output(out["content"], analysis_rows)
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


_UP = re.compile(r"yüksel|artış|arttı|artıyor|artan|kazan", re.I)
_DOWN = re.compile(r"düşüş|düştü|düşüyor|azal|kayb|geril", re.I)
_CAVEAT = re.compile(r"düşük hacim|güvenilir değil|güvenilmez|gürültü|zayıf|ihtiyat", re.I)
_MISSING = re.compile(r"alınamadı|veri yok|bulunamadı|unavailable", re.I)
_BUSINESS = re.compile(r"satış\w*|stok\w*|ciro\w*|sipariş\w*|kâr\b|gelir\w*", re.I)
_ENGLISH = re.compile(r"\b(therefore|unavailable|however|because|increase[sd]?|decrease[sd]?|popularity|"
                      r"available|insufficient|the|and|with|data)\b", re.I)


def _lower_tr(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def check_claims(text: str, rows: list[dict]) -> list[str]:
    """Modelin yön ve 'veri yok' iddialarını hesaplanan sonuçlarla karşılaştırır (basit, satır bazlı).

    - 1-3. bölümlerde bir terim için artış/düşüş iddiası, o terimin hiçbir kaynağında o yön yoksa işaretlenir.
    - Yön yalnızca düşük hacimli serilerden geliyorsa ve satırda bununla ilgili çekince yoksa işaretlenir.
    - Bir kaynak-terim için 'veri alınamadı' denmiş ama veri gelmişse işaretlenir.
    - 1-3. bölümlerde satış/stok/ciro gibi veride olmayan metrikler işaretlenir.
    - İngilizce kelimeler işaretlenir.
    """
    issues: list[str] = []
    labels = sorted({r["label"] for r in rows}, key=len, reverse=True)
    sources = sorted({r["source"] for r in rows}, key=len, reverse=True)
    body = re.split(r"^##\s*4", text, maxsplit=1, flags=re.M)[0]

    for line in body.splitlines():
        low = _lower_tr(line)
        for label in labels:
            if _lower_tr(label) not in low:
                continue
            mine = [r for r in rows if r["label"] == label and r.get("direction")]
            for regex, d, word in ((_UP, "up", "artış"), (_DOWN, "down", "düşüş")):
                if not regex.search(line):
                    continue
                matching = [r for r in mine if r["direction"] == d]
                if not matching:
                    found = ", ".join(f"{r['source']}: {r['direction']}" for r in mine) or "hesaplanmadı"
                    issues.append(f"'{label}' için {word} iddiası var ama hesaplanan yön farklı ({found}).")
                elif all(r.get("low_volume") for r in matching) and not _CAVEAT.search(line):
                    issues.append(f"'{label}' için {word} yalnızca düşük hacimli seride var; çekince belirtilmemiş.")

    for line in text.splitlines():
        if not _MISSING.search(line):
            continue
        low = _lower_tr(line)
        for label in labels:
            if _lower_tr(label) not in low:
                continue
            for src in sources:
                if src in low:
                    ok = [r for r in rows if r["label"] == label and r["source"] == src and r.get("fetch_status") == "ok"]
                    if ok:
                        issues.append(f"'{label}' için {src} verisi alındığı halde 'veri yok' denmiş.")
                    break

    biz = sorted({m.group(0).lower() for m in _BUSINESS.finditer(body)})
    if biz:
        issues.append(f"1-3. bölümlerde veride olmayan iş metriklerinden söz ediliyor: {', '.join(biz)}")

    eng = sorted({m.group(0).lower() for m in _ENGLISH.finditer(text)})
    if eng:
        issues.append(f"Yanıtta İngilizce kelimeler var: {', '.join(eng)}")
    return list(dict.fromkeys(issues))


def check_output(text: str, rows: list[dict]) -> dict:
    nums = check_numbers(text, rows)
    claims = check_claims(text, rows)
    ok = nums["ok"] and not claims
    return {**nums, "claim_issues": claims, "ok": ok,
            "note": "Yanıt hesaplanan sonuçlarla tutarlı." if ok else
                    "Yanıtta hesaplanan sonuçlarla uyuşmayan ifadeler var; aşağıdaki uyarılara bakın."}


def to_markdown(result: dict, meta: dict) -> str:
    chk = result["check"]
    lines = [
        "# Trend yorumu",
        "",
        f"- Model: `{meta['model']}` (Ollama) — sıcaklık {meta['temperature']}",
        f"- Oluşturma: {meta['created_at']} — süre {result['elapsed_sec']} sn",
        f"- Çalıştırma: `{meta['run_id']}` — dönem {meta['window']['baseline_start']} → {meta['window']['recent_end']}",
        f"- Tutarlılık kontrolü: {'✅' if chk['ok'] else '⚠️'} {chk['note']}",
    ]
    if chk["unmatched_percentages"]:
        lines.append(f"  - Hesaplanan sonuçlarda olmayan yüzdeler: "
                     f"{', '.join(f'%{v:g}' for v in chk['unmatched_percentages'])}")
    lines += [f"  - {i}" for i in chk.get("claim_issues", [])]
    lines += [
        "",
        "---",
        "",
        result["content"].strip(),
        "",
    ]
    return "\n".join(lines)


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=2)
