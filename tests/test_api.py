"""API 测试：用 FakeAdapter 替换真实供应商，不花钱、不调网络。

覆盖：/health、/v1/models、正常问答、未知别名 404、没 key 401、
主模型失败自动切 fallback。
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ["GATEWAY_API_KEY"] = "test-key"

from app import main as main_module  # noqa: E402
from app.main import app  # noqa: E402


class FakeAdapter:
    """假供应商：按模型名决定成功还是抛超时。"""

    def __init__(self, api_key="", timeout=30.0):
        pass

    def chat(self, model, body):
        if model == "deepseek-flash":
            import httpx

            raise httpx.TimeoutException("timed out", request=httpx.Request("POST", "https://example.com"))
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": "你好，网关通了"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    def chat_stream(self, model, body):
        yield b"data: {}\n\n"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main_module, "make_adapter", lambda provider, api_key, timeout: FakeAdapter())
    monkeypatch.setenv("GATEWAY_API_KEY", "test-key")
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_models(client):
    data = client.get("/v1/models").json()["data"]
    ids = {m["id"] for m in data}
    assert {"qa-fast", "qa-quality", "chat-default"} <= ids


def test_chat_falls_back_to_qwen(client):
    # qa-fast 主模型是 deepseek-flash（Fake 里会超时），应自动切到 qwen-plus
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "qa-fast", "messages": [{"role": "user", "content": "你好"}]},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model"] == "qwen-plus"
    assert body["choices"][0]["message"]["content"] == "你好，网关通了"


def test_chat_unknown_alias_404(client):
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "no-such-alias", "messages": [{"role": "user", "content": "你好"}]},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 404


def test_chat_no_key_401(client):
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "qa-fast", "messages": [{"role": "user", "content": "你好"}]},
    )
    assert resp.status_code == 401


def test_chat_empty_messages_400(client):
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "qa-fast", "messages": []},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 400
