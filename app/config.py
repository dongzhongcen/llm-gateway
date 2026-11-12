"""网关配置：YAML 管模型，.env 管 key。

规则（和架构文档一致）：
- 别名、fallback 链、超时、重试、预算都放 config/models.yaml，改配置不改代码。
- 供应商 key 只放 .env，绝不写进代码、绝不提交 Git。
- deepseek-chat 会 404，别把它写进 fallback，见 models.yaml 注释。
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "models.yaml"

PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://localhost:11434/v1",
}

PROVIDER_KEY_ENV = {
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "QWEN_API_KEY",
    "ollama": "",  # 本地 Ollama 不用 key
}


class AliasConfig(BaseModel):
    model: str
    provider: str
    fallback: list[str] = Field(default_factory=list)
    timeout_seconds: int = 30
    max_retries: int = 2


class Budgets(BaseModel):
    default_daily_token_limit: int = 200000
    default_daily_cost_limit_usd: float = 2.0


class GatewayConfig(BaseModel):
    aliases: dict[str, AliasConfig]
    budgets: Budgets = Budgets()

    def provider_key(self, provider: str) -> str:
        env_name = PROVIDER_KEY_ENV.get(provider, "")
        return os.getenv(env_name, "").strip() if env_name else ""

    def provider_base_url(self, provider: str) -> str:
        return PROVIDER_BASE_URLS[provider]


def load_config(path: Path = CONFIG_PATH) -> GatewayConfig:
    """每次调用都重读 YAML 和环境变量，方便测试用 monkeypatch 改 env。"""
    # .env 只在本地读一次：没有 python-dotenv 也不报错
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return GatewayConfig(**raw)


def gateway_api_key() -> str:
    return os.getenv("GATEWAY_API_KEY", "").strip()
