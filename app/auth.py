"""鉴权：客户端只拿网关 key，不直接拿供应商 key。"""
from __future__ import annotations


def extract_bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def check_key(provided: str, expected: str) -> bool:
    """expected 为空 = 本地开发模式没配网关 key，放行（但会记一条警告日志）。

    配了 key 就必须完全一致，别做前缀匹配、别忽略大小写。
    """
    if not expected:
        return True
    return bool(provided) and provided == expected
