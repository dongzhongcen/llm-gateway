"""真调 smoke 测试：默认跳过，不花钱。

跑法（网关已启动、.env 里有真 key 之后）：
    RUN_SMOKE=1 python -m pytest tests/test_smoke.py -v
没设 RUN_SMOKE 就跳过，CI 和本地 mock 测试都不受影响。
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SMOKE") != "1", reason="真调测试默认跳过：设 RUN_SMOKE=1 才跑"
)


def test_smoke_real_gateway():
    import httpx

    resp = httpx.post(
        "http://127.0.0.1:4000/v1/chat/completions",
        json={
            "model": "qa-fast",
            "messages": [{"role": "user", "content": "只回答两个字：你好"}],
            "temperature": 0.2,
        },
        headers={"Authorization": f"Bearer {os.getenv('GATEWAY_API_KEY', '')}"},
        timeout=60,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["choices"][0]["message"]["content"]
