import json
from typing import Any, Dict, List


def normalize_explain(raw: Any) -> Dict:
    """
    Приводит explain к единому формату.
    Никогда не падает.
    """

    result = {
        "reason": "",
        "edge": None,
        "size": None,
        "risk": {"allowed": None, "limit": None},
        "details": [],
    }

    if raw is None:
        return result

    # если пришла строка JSON
    if isinstance(raw, str):
        raw = raw.strip()

        if not raw:
            return result

        try:
            raw = json.loads(raw)
        except Exception:
            # просто текст
            result["reason"] = raw.replace("\\n", " ").strip()
            return result

    # если словарь
    if isinstance(raw, dict):

        result["reason"] = str(raw.get("reason") or raw.get("msg") or "")

        if "edge" in raw:
            try:
                result["edge"] = float(raw["edge"])
            except (ValueError, TypeError):
                pass

        if "size" in raw:
            try:
                result["size"] = float(raw["size"])
            except (ValueError, TypeError):
                pass

        risk = raw.get("risk")
        if isinstance(risk, dict):
            try:
                result["risk"]["allowed"] = float(risk.get("allowed")) if risk.get("allowed") is not None else None
                result["risk"]["limit"] = float(risk.get("limit")) if risk.get("limit") is not None else None
            except (ValueError, TypeError):
                pass

        # любые остальные поля — в details
        for k, v in raw.items():
            if k not in ("reason", "msg", "edge", "size", "risk"):
                result["details"].append(f"{k}: {v}")

    else:
        result["reason"] = str(raw)

    return result
