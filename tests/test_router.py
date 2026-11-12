"""路由测试：别名解析、fallback 链。不调网络、不调供应商。"""
import pytest

from app.config import AliasConfig, GatewayConfig
from app.router import provider_chain, resolve_alias


def _cfg():
    return GatewayConfig(
        aliases={
            "qa-fast": AliasConfig(model="deepseek-flash", provider="deepseek", fallback=["qwen-plus"]),
            "chat-default": AliasConfig(model="deepseek-flash", provider="deepseek", fallback=[]),
        }
    )


def test_resolve_known_alias():
    cfg = _cfg()
    assert resolve_alias(cfg, "qa-fast").model == "deepseek-flash"


def test_resolve_unknown_alias_raises():
    with pytest.raises(KeyError):
        resolve_alias(_cfg(), "no-such-alias")


def test_provider_chain_main_then_fallback():
    chain = provider_chain(resolve_alias(_cfg(), "qa-fast"))
    assert chain == [("deepseek-flash", "deepseek"), ("qwen-plus", "qwen")]


def test_provider_chain_no_fallback():
    chain = provider_chain(resolve_alias(_cfg(), "chat-default"))
    assert chain == [("deepseek-flash", "deepseek")]


def test_provider_chain_unknown_fallback_provider():
    cfg = GatewayConfig(
        aliases={"x": AliasConfig(model="deepseek-flash", provider="deepseek", fallback=["some-unknown-model"])}
    )
    with pytest.raises(ValueError):
        provider_chain(resolve_alias(cfg, "x"))
