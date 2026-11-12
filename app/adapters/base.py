"""供应商适配器：把统一请求翻译成该供应商的格式，再把响应翻回来。

v1 只做 OpenAI 兼容协议：DeepSeek 和 Qwen 都是这个协议，
所以两个适配器只差 base_url 和 key，逻辑共用。
"""
from __future__ import annotations

from collections.abc import Iterator

import httpx


class BaseAdapter:
    provider: str = ""
    base_url: str = ""

    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout

    def build_payload(self, model: str, body: dict) -> dict:
        """原样透传客户端字段，只换 model 名。

        关键：extra_body（比如 DeepSeek 的 thinking disabled）必须透传，
        丢了它，stage1 的 temperature 对比就看不出区别。
        """
        payload = {
            "model": model,
            "messages": body["messages"],
            "temperature": body.get("temperature", 0.7),
            "stream": bool(body.get("stream", False)),
        }
        for key in ("response_format", "tools", "tool_choice", "max_tokens"):
            if key in body:
                payload[key] = body[key]
        if "extra_body" in body:
            payload["extra_body"] = body["extra_body"]
        return payload

    def chat(self, model: str, body: dict) -> dict:
        payload = self.build_payload(model, body)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json()

    def chat_stream(self, model: str, body: dict) -> Iterator[bytes]:
        payload = self.build_payload(model, body)
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as resp:
                resp.raise_for_status()
                yield from resp.iter_bytes()
