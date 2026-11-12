"""记账：只记 token 数，不猜价格。

价格每个供应商、每个模型都可能变，网关不硬编码价格表：
只按响应里的 usage（prompt_tokens + completion_tokens）记数，
按 YAML 里的 default_daily_token_limit 做每日预算。
cost 字段先留 0，等你在 models.yaml 里补了单价再算。
"""
from __future__ import annotations

import threading
from datetime import date

_lock = threading.Lock()
_usage: dict[str, dict] = {}  # key -> {"date": str, "tokens": int, "calls": int}


def _today() -> str:
    return date.today().isoformat()


def check_budget(key: str, daily_token_limit: int) -> bool:
    with _lock:
        entry = _usage.get(key)
        if not entry or entry["date"] != _today():
            return True
        return entry["tokens"] < daily_token_limit


def record_usage(key: str, tokens: int) -> dict:
    with _lock:
        entry = _usage.get(key)
        if not entry or entry["date"] != _today():
            entry = {"date": _today(), "tokens": 0, "calls": 0}
            _usage[key] = entry
        entry["tokens"] += max(tokens, 0)
        entry["calls"] += 1
        return dict(entry)


def tokens_from_response(data: dict) -> int:
    usage = data.get("usage") or {}
    try:
        return int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
    except (TypeError, ValueError):
        return 0
