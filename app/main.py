"""本地模型网关 v1 入口。

只做网关的事：鉴权 -> 校验 -> 预算 -> 路由 -> fallback -> 记账。
不拼 prompt、不做工具六道关 —— 那些留在应用层（入口层/业务编排层）。

启动：uvicorn app.main:app --host 127.0.0.1 --port 4000
Windows 一键：双击 start_gateway.bat
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import auth, billing, observability
from .adapters.base import BaseAdapter
from .adapters.deepseek import DeepSeekAdapter
from .adapters.qwen import QwenAdapter
from .config import GatewayConfig, gateway_api_key, load_config
from .fallback import call_with_fallback
from .router import provider_chain, resolve_alias

app = FastAPI(title="llm-gateway v1")

ADAPTER_CLASSES: dict[str, type[BaseAdapter]] = {
    "deepseek": DeepSeekAdapter,
    "qwen": QwenAdapter,
}

MAX_MESSAGES_LEN = 5000  # 单条消息长度上限，超了直接拒，不进模型


def make_adapter(provider: str, api_key: str, timeout: float) -> BaseAdapter:
    """可被测试 monkeypatch 的接缝：测试里换成 FakeAdapter，不用真调供应商。"""
    try:
        cls = ADAPTER_CLASSES[provider]
    except KeyError:
        raise ValueError(f"unknown provider: {provider!r}") from None
    return cls(api_key=api_key, timeout=timeout)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/models")
def list_models() -> dict:
    cfg = load_config()
    return {"data": [{"id": alias, "object": "model"} for alias in cfg.aliases]}


@app.post("/v1/chat/completions")
def chat_completions(body: dict[str, Any], request: Request, authorization: str | None = Header(default=None)):
    started = time.time()
    cfg: GatewayConfig = load_config()

    # 1. 鉴权
    if not auth.check_key(auth.extract_bearer(authorization), gateway_api_key()):
        raise HTTPException(status_code=401, detail="invalid gateway key")

    # 2. 输入校验：空消息、超长直接拒
    alias = body.get("model", "")
    messages = body.get("messages") or []
    if not alias or not messages:
        raise HTTPException(status_code=400, detail="model and messages are required")
    if any(len(str(m.get("content", ""))) > MAX_MESSAGES_LEN for m in messages if isinstance(m, dict)):
        raise HTTPException(status_code=400, detail="message too long")

    # 3. 路由
    try:
        alias_cfg = resolve_alias(cfg, alias)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    chain = provider_chain(alias_cfg)

    # 4. 预算（按网关 key 记）
    key_label = auth.extract_bearer(authorization) or "no-key"
    if not billing.check_budget(key_label, cfg.budgets.default_daily_token_limit):
        raise HTTPException(status_code=429, detail="daily token budget exceeded")

    # 5. 调用 + fallback。stream 模式下，fallback 只在开始流式之前生效，
    #    流到一半失败是没法换模型的 —— 这是 SSE 的固有限制，不是 bug。
    is_stream = bool(body.get("stream", False))

    def _call_once(model: str, provider: str):
        adapter = make_adapter(provider, cfg.provider_key(provider), alias_cfg.timeout_seconds)
        if is_stream:
            return adapter  # 流式：先返回适配器，真正拉流在下面做
        return adapter.chat(model, body)

    try:
        if is_stream:
            adapter, used_model, used_provider, fell_back, _ = call_with_fallback(
                lambda m, p: _call_once(m, p), chain, alias_cfg.max_retries
            )
            # 注意：这里 adapter.chat_stream 是生成器，出错会在拉流时才抛，
            # 所以 fallback 只能覆盖“建连失败”，流中断不在兜底范围内。
            chunks = adapter.chat_stream(used_model, body)
            return StreamingResponse(chunks, media_type="text/event-stream")
        result, used_model, _provider, fell_back, _attempts = call_with_fallback(
            _call_once, chain, alias_cfg.max_retries
        )
    except Exception as exc:  # noqa: BLE001 - 全部供应商失败，统一报 502
        raise HTTPException(status_code=502, detail=f"all providers failed: {exc}") from None

    # 6. 记账 + 审计
    tokens = billing.tokens_from_response(result)
    billing.record_usage(key_label, tokens)
    ms = int((time.time() - started) * 1000)
    observability.audit_log(
        {"alias": alias, "model": used_model, "fell_back": fell_back, "tokens": tokens, "ms": ms}
    )
    observability.trace_call(alias=alias, model=used_model, fell_back=fell_back, tokens=tokens, ms=ms)
    return JSONResponse(content=result)
