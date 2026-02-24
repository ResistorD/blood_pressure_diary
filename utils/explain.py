from __future__ import annotations

from typing import Any, Dict, Mapping

DEFAULT_LANG = "ru"

# Single, canonical dictionary of message templates.
# Goal: NO "зоопарк" — all agents use keys + params, and we can render RU/EN consistently.
_T: Dict[str, Dict[str, str]] = {
    # --- Common ---
    "common.ok": {
        "ru": "ОК",
        "en": "OK",
    },
    "common.no_data": {
        "ru": "Недостаточно данных",
        "en": "Not enough data",
    },

    # --- Quant ---
    "quant.filtered": {
        "ru": "Фильтр качества: liq={liq:.0f}, spread={spread:.3f}",
        "en": "Quality filter: liq={liq:.0f}, spread={spread:.3f}",
    },
    "quant.good": {
        "ru": "Качество рынка ок: liq={liq:.0f}, spread={spread:.3f}",
        "en": "Market quality ok: liq={liq:.0f}, spread={spread:.3f}",
    },

    # --- Scout ---
    "scout.pair_found": {
        "ru": "Найдена связка: «{a}» ↔ «{b}» (score={score:.2f})",
        "en": "Candidate pair: “{a}” ↔ “{b}” (score={score:.2f})",
    },
    "scout.group_hint": {
        "ru": "Группа: {group}",
        "en": "Group: {group}",
    },

    # --- Logic ---
    "logic.implication": {
        "ru": "Импликация: P({a}) ≤ P({b}) (reason={reason})",
        "en": "Implication: P({a}) ≤ P({b}) (reason={reason})",
    },
    "logic.mutex": {
        "ru": "Взаимоисключение: {a} XOR {b} (reason={reason})",
        "en": "Mutual exclusion: {a} XOR {b} (reason={reason})",
    },
    "logic.threshold": {
        "ru": "Порог: {metric} {op} {value} (actual={actual})",
        "en": "Threshold: {metric} {op} {value} (actual={actual})",
    },

    # --- Risk ---
    "risk.blocked_total": {
        "ru": "Риск-стоп: превышен общий лимит notional (total={total:.2f} > max={max_total:.2f})",
        "en": "Risk stop: total notional limit exceeded (total={total:.2f} > max={max_total:.2f})",
    },
    "risk.blocked_group": {
        "ru": "Риск-стоп: превышен лимит по группе (group={group}, total={total:.2f} > max={max_group:.2f})",
        "en": "Risk stop: per-group limit exceeded (group={group}, total={total:.2f} > max={max_group:.2f})",
    },
    "risk.blocked_market": {
        "ru": "Риск-стоп: превышен лимит по рынку (market={market_id}, total={total:.2f} > max={max_market:.2f})",
        "en": "Risk stop: per-market limit exceeded (market={market_id}, total={total:.2f} > max={max_market:.2f})",
    },

    # --- Auditor ---
    "auditor.anomaly": {
        "ru": "Аномалия данных: {what} (details={details})",
        "en": "Data anomaly: {what} (details={details})",
    },
}


def _render(lang: str, key: str, params: Mapping[str, Any]) -> str:
    lang = (lang or DEFAULT_LANG).lower()
    tmpl = _T.get(key)
    if not tmpl:
        # Unknown key: keep it explicit, but stable
        return f"[{key}] {dict(params)}"
    text = tmpl.get(lang) or tmpl.get(DEFAULT_LANG) or next(iter(tmpl.values()))
    try:
        return text.format(**params)
    except Exception:
        # Never crash agents because of formatting mismatch.
        return f"[{key}] {dict(params)}"


def bundle(key: str, *, params: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    params = dict(params or {})
    return {
        "key": key,
        "params": params,
        "text": {
            "ru": _render("ru", key, params),
            "en": _render("en", key, params),
        },
    }


def pick_text(b: Mapping[str, Any], lang: str = DEFAULT_LANG) -> str:
    try:
        return (b.get("text") or {}).get(lang) or (b.get("text") or {}).get(DEFAULT_LANG) or ""
    except (AttributeError, TypeError):
        return ""


def ensure_claim_explain(claim: Dict[str, Any], key: str, params: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Attach canonical explain bundle into claim and also return it."""
    b = bundle(key, params=params)
    claim["explain"] = b
    return b
