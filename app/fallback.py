"""重试 + fallback + 熔断。只做失败处理，不认识任何供应商。"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

T = TypeVar("T")

# 熔断：某个模型连续失败达到阈值，就冷却一段时间，别一直撞墙。
_BREAKER_THRESHOLD = 5
_BREAKER_COOLDOWN_SECONDS = 60
_failures: dict[str, int] = {}
_blocked_until: dict[str, float] = {}


def is_retryable(exc: Exception) -> bool:
    """只重试超时 / 429 / 5xx。参数错（4xx 里除 429 外）重试也没用。"""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def _breaker_open(model: str) -> bool:
    return time.time() < _blocked_until.get(model, 0)


def _record_success(model: str) -> None:
    _failures.pop(model, None)
    _blocked_until.pop(model, None)


def _record_failure(model: str) -> None:
    _failures[model] = _failures.get(model, 0) + 1
    if _failures[model] >= _BREAKER_THRESHOLD:
        _blocked_until[model] = time.time() + _BREAKER_COOLDOWN_SECONDS


def call_with_fallback(
    fn: Callable[[str, str], T],
    chain: list[tuple[str, str]],
    max_retries: int = 2,
) -> tuple[T, str, str, bool, int]:
    """按 chain 顺序调，返回 (结果, 实际用的模型, 供应商, 是否走了 fallback, 总尝试次数)。

    fn(model, provider) 是调用方注入的单次调用；这里只管重试和切换。
    全部失败时抛出最后一个异常，调用方翻译成 502。
    """
    attempts = 0
    last_exc: Exception | None = None
    for index, (model, provider) in enumerate(chain):
        if _breaker_open(model):
            continue
        for _ in range(max_retries + 1):
            attempts += 1
            try:
                result = fn(model, provider)
            except Exception as exc:  # noqa: BLE001 - 失败分类在 is_retryable 里
                last_exc = exc
                _record_failure(model)
                if is_retryable(exc):
                    continue
                break  # 不可重试的错：别浪费重试次数，直接换下一个模型
            else:
                _record_success(model)
                return result, model, provider, index > 0, attempts
    assert last_exc is not None  # chain 至少有一个模型，不会空手出来
    raise last_exc
