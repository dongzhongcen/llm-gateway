"""路由：别名 -> 真实模型。只做这一件事，不调供应商。"""
from __future__ import annotations

from .config import AliasConfig, GatewayConfig


def resolve_alias(cfg: GatewayConfig, alias: str) -> AliasConfig:
    """查不到别名就报 KeyError，调用方翻译成 404，别让它穿透成 500。"""
    try:
        return cfg.aliases[alias]
    except KeyError:
        raise KeyError(f"unknown model alias: {alias!r}") from None


def provider_chain(alias_cfg: AliasConfig) -> list[tuple[str, str]]:
    """返回 [(真实模型, 供应商), ...]：主模型在前，fallback 在后。

    fallback 里写的是真实模型名（如 qwen-plus），供应商按名字推断：
    deepseek-* 走 deepseek，qwen-* 走 qwen，其余默认走 deepseek 兼容协议
    的话调用方要显式指定 —— v1 只认这两家，别的先报错，别猜。
    """
    chain: list[tuple[str, str]] = [(alias_cfg.model, alias_cfg.provider)]
    for name in alias_cfg.fallback:
        if name.startswith("deepseek"):
            chain.append((name, "deepseek"))
        elif name.startswith("qwen"):
            chain.append((name, "qwen"))
        else:
            raise ValueError(f"fallback 模型 {name!r} 不知道走哪个供应商，先在 router 里登记")
    return chain
