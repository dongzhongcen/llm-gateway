"""Qwen（通义）适配器：OpenAI 兼容模式，不用特殊处理。"""
from __future__ import annotations

from .base import BaseAdapter


class QwenAdapter(BaseAdapter):
    provider = "qwen"
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
