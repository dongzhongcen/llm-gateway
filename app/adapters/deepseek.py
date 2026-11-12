"""DeepSeek 适配器。

stage1 的做法：DeepSeek 默认开思考模式，关掉后 temperature 才起作用。
所以客户端没传 extra_body 时，网关在这里补一个 thinking disabled，
客户端传了就以客户端的为准，别覆盖。
"""
from __future__ import annotations

from .base import BaseAdapter


class DeepSeekAdapter(BaseAdapter):
    provider = "deepseek"
    base_url = "https://api.deepseek.com/v1"

    def build_payload(self, model: str, body: dict) -> dict:
        payload = super().build_payload(model, body)
        if model.startswith("deepseek") and "extra_body" not in payload:
            payload["extra_body"] = {"thinking": {"type": "disabled"}}
        return payload
