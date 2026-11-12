"""可观测：审计日志 + LangFuse（可选）。

审计日志只记：时间、别名、真实模型、token、是否 fallback、耗时。
不记问题内容、不记 key、不记完整回答 —— 这是安全清单里的脱敏要求。

LangFuse 只在配了 key 时才初始化，没配就静默跳过，网关照常跑。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_FILE = PROJECT_ROOT / "audit.log"

_langfuse = None
try:
    from langfuse import Langfuse  # type: ignore

    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        _langfuse = Langfuse()
except Exception:  # noqa: BLE001 - 可观测挂了不能拖垮网关
    _langfuse = None


def audit_log(record: dict) -> None:
    line = json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **record}, ensure_ascii=False)
    try:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # 日志写不进盘也不影响返回


def trace_call(*, alias: str, model: str, fell_back: bool, tokens: int, ms: int) -> None:
    if _langfuse is None:
        return
    try:
        _langfuse.trace(name="gateway-call", metadata={"alias": alias, "model": model, "fell_back": fell_back, "tokens": tokens, "ms": ms})
    except Exception:  # noqa: BLE001
        pass
