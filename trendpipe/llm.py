"""Model bağlantısı ve yorum adımı.

Bağlantı yöntemi hocanın notebook'undakiyle aynıdır: `ollama` Python paketi + Ollama sunucusu. Hocanın kodu
`ollama.chat(model=..., ...)` çağırır (varsayılan adres http://localhost:11434); burada aynı çağrı
`ollama.Client(host=...)` ile yapılır, böylece adres ve model .env'den değiştirilebilir (yerel Ollama ya da Colab).

Yorum adımı (interpret):
1. Python adayları, kanıtları ve sınırları hazırlar (prompts.py).
2. Model JSON şemasına uyan yanıt verir (Ollama `format` parametresi).
3. Yanıt denetlenir (checks.review). Sorun varsa model, sorunlar listelenerek bir kez daha yanıtlamaya çağrılır
   (öz-düzeltme döngüsü). En az sorunlu yanıt kullanılır; kalan sorunlar raporda açıkça yazılır.
4. Rapor (markdown) Python tarafından oluşturulur.
"""

from __future__ import annotations

import json
import time

from .checks import _norm, review
from .logs import get_logger
from .prompts import (
    CANDIDATE_LABELS,
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    TREND_TR,
    _num,
    _pct,
    build_user_prompt,
    candidates,
    evidence_line,
    limitations,
    reason_tr,
)

log = get_logger("llm")


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], settings: dict, fmt: dict | str | None = None) -> dict:
    try:
        import ollama  # type: ignore
    except ImportError as exc:
        raise LLMError("'ollama' paketi kurulu değil: pip install -r requirements.txt") from exc

    client = ollama.Client(host=settings["host"], timeout=settings.get("timeout"))
    t0 = time.monotonic()
    kwargs = {"format": fmt} if fmt is not None else {}
    try:
        resp = client.chat(model=settings["model"], messages=messages,
                           options={"temperature": settings.get("temperature", 0.2)}, **kwargs)
    except Exception as exc:  # bağlantı reddi, model yok, zaman aşımı...
        hint = ""
        msg = str(exc).lower()
        if "connect" in msg or "refused" in msg:
            hint = (" | İpucu: Ollama çalışıyor mu? Mac'te Ollama uygulamasını açın (ya da terminalde "
                    "'ollama serve'); Colab'da notebook'un sunucu hücresini çalıştırın. OLLAMA_HOST'u kontrol edin.")
        elif "not found" in msg:
            hint = (f" | İpucu: model indirilmemiş olabilir: ollama pull {settings['model']} "
                    "(ya da .env'deki OLLAMA_MODEL'i indirdiğiniz modelle değiştirin)")
        raise LLMError(f"{type(exc).__name__}: {exc}{hint}") from exc
    return {"content": resp["message"]["content"], "elapsed_sec": round(time.monotonic() - t0, 2)}


def ping(settings: dict) -> dict:
    """Bağlantıyı doğrulamak için basit istek."""
    return chat([{"role": "user", "content": "Bağlantı testi. Sadece 'Merhaba, bağlantı çalışıyor.' yaz."}],
                settings)


def _parse(content: str):
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        # Bazı modeller JSON'u ```json ... ``` içine alabiliyor
        s = content.strip().strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return None


def interpret(rows: list[dict], context: dict, settings: dict, max_attempts: int = 2) -> dict:
    names = {k: v["display"] for k, v in context["sources"].items()}
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(rows, context)}]
    attempts = []
    total = 0.0
    for i in range(max_attempts):
        try:
            out = chat(messages, settings, fmt=RESPONSE_SCHEMA)
        except LLMError as exc:
            if not attempts:
                raise
            log.warning("yorum denemesi %d başarısız (%s); önceki deneme kullanılacak", i + 1, exc)
            break
        total += out["elapsed_sec"]
        data = _parse(out["content"])
        rev = review(data, rows, names) if data is not None else \
            {"ok": False, "issues": ["Yanıt geçerli JSON değil."], "structural_issues": ["JSON değil"],
             "unmatched_percentages": [], "note": "Yanıt geçerli JSON değil."}
        attempts.append({"attempt": i + 1, "raw": out["content"], "data": data, "review": rev,
                         "elapsed_sec": out["elapsed_sec"]})
        log.info("yorum denemesi %d: %d sorun", i + 1, len(rev["issues"]))
        if rev["ok"]:
            break
        if i + 1 < max_attempts:
            messages = messages + [
                {"role": "assistant", "content": out["content"]},
                {"role": "user", "content": "Yanıtında şu sorunlar var:\n" + "\n".join(f"- {x}" for x in rev["issues"])
                 + "\nKurallara uyarak JSON yanıtını düzeltip yeniden ver."},
            ]
    # En iyi deneme: önce geçerli JSON, sonra en az kural (şema/aday) ihlali, sonra en az metin sorunu
    best = min(attempts, key=lambda a: (a["data"] is None, len(a["review"].get("structural_issues", [])),
                                        len(a["review"]["issues"])))
    return {"data": best["data"], "review": best["review"], "chosen_attempt": best["attempt"],
            "attempts": attempts, "messages": messages, "elapsed_sec": round(total, 2)}


def evidence_table(rows: list[dict], names: dict) -> str:
    """Python'un hesapladığı tüm sonuçlar (modelden bağımsız, doğrulama için)."""
    order = list(TREND_TR)
    out = ["| Terim | Kaynak | Dönemsel değişim | Yıllık değişim | Etiket |", "|---|---|---:|---:|---|"]
    for r in sorted(rows, key=lambda r: (order.index(r.get("trend_label", "veri_yok")), r["source"], r["label"])):
        lab = TREND_TR.get(r.get("trend_label"), "-")
        if r.get("signal") in ("no_data", "insufficient"):
            lab += f" ({reason_tr(r)})"
        pop = (f"{_num(r.get('baseline_mean'))} → {_num(r.get('recent_mean'))} ({_pct(r.get('pct_change'))})"
               if r.get("baseline_mean") is not None else "-")
        yoy = (f"{_num(r.get('yoy_ly_mean'))} → {_num(r.get('yoy_recent_mean'))} ({_pct(r.get('yoy_pct_change'))})"
               if r.get("yoy_pct_change") is not None else "-")
        out.append(f"| {r['label']} | {names.get(r['source'], r['source'])} | {pop} | {yoy} | {lab} |")
    return "\n".join(out)


def render_markdown(result: dict, rows: list[dict], names: dict, meta: dict) -> str:
    """Raporu Python oluşturur; modelin metinleri ilgili yerlere yerleştirilir."""
    rev = result["review"]
    data = result["data"] if isinstance(result.get("data"), dict) else {}
    w = meta["window"]
    # Eşleştirme, denetimle (checks._norm) aynı kuralla yapılır; büyük/küçük harf ve Türkçe I/İ farkı sorun olmaz.
    by_key = {(_norm(r["label"]), r["source"]): r for r in rows}
    alias = {}
    for key, disp in names.items():
        alias[_norm(key)] = key
        alias[_norm(disp)] = key
    lines = [
        "# Trend yorumu", "",
        f"- Model: `{meta['model']}` (Ollama), sıcaklık {meta['temperature']} — {meta['created_at']} — "
        f"{result['elapsed_sec']} sn, {len(result['attempts'])} deneme (kullanılan: {result['chosen_attempt']})",
        f"- Çalıştırma: `{meta['run_id']}` — yakın dönem {w['recent_start']} → {w['recent_end']}"
        + (f", geçen yılın aynı dönemi {w['ly_start']} → {w['ly_end']}" if w.get("ly_start") else ""),
        f"- Tutarlılık kontrolü: {'✅' if rev['ok'] else '⚠️'} {rev['note']}",
        *[f"  - {i}" for i in rev["issues"]],
        "",
    ]
    if data.get("ozet"):
        lines += ["## Özet", "", data["ozet"].strip(), ""]

    lines += ["## 1. Öne çıkan terimler", ""]
    chosen = []
    for it in data.get("one_cikanlar", []):
        if not isinstance(it, dict):
            continue
        src = alias.get(_norm(str(it.get("kaynak", ""))), it.get("kaynak"))
        r = by_key.get((_norm(str(it.get("terim", ""))), src))
        if not r or r.get("trend_label") not in CANDIDATE_LABELS:
            continue  # aday olmayan seçim rapora girmez (uyarılarda listelenir)
        chosen.append(r)
        lines.append(f"- **{it.get('terim')}** ({names.get(src, it.get('kaynak'))}) — "
                     f"*{TREND_TR.get(r['trend_label'])}*: {it.get('neden_onemli')}")
    chosen_terms = {_norm(r["label"]) for r in chosen}
    if not chosen:
        lines.append("- Güvenilir bir değişim gösteren terim yok." if not candidates(rows) else
                     "- Model öne çıkan terim seçmedi.")

    lines += ["", "## 2. Destekleyen ölçüm ve dönem", "", "*(Sayılar Python tarafından hesaplanmıştır.)*", ""]
    lines += [evidence_line(r, names) for r in chosen] or ["- Öne çıkan terim olmadığı için kanıt satırı yok."]

    lines += ["", "## 3. Ürün seçimine olası katkı", ""]
    lines += [f"- **{it.get('terim')}**: {it.get('oneri')}" for it in data.get("urun_katkisi", [])
              if isinstance(it, dict) and _norm(str(it.get("terim", ""))) in chosen_terms] or ["- (yok)"]

    lines += ["", "## 4. Bu veriyle söyleyemediklerimiz", ""]
    lines += [f"- {x}" for x in data.get("soyleyemediklerimiz", []) if isinstance(x, str)] or ["- (model yazmadı)"]
    lines += ["", "**Sistem notları (Python):**", ""] + [f"- {x}" for x in limitations(rows, names)]

    lines += ["", "---", "", "## Ek: Python'un hesapladığı tüm sonuçlar (modelden bağımsız)", "",
              evidence_table(rows, names), ""]
    return "\n".join(lines)
