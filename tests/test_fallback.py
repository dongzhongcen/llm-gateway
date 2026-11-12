"""fallback 测试：重试、切换、全部失败。不调网络。"""
import httpx
import pytest

from app.fallback import call_with_fallback


def _timeout_exc():
    return httpx.TimeoutException("timed out", request=httpx.Request("POST", "https://example.com"))


def test_first_try_success_no_fallback():
    result, model, provider, fell_back, attempts = call_with_fallback(
        lambda m, p: "ok", [("deepseek-flash", "deepseek"), ("qwen-plus", "qwen")]
    )
    assert (result, model, fell_back, attempts) == ("ok", "deepseek-flash", False, 1)


def test_retry_then_success_same_model():
    calls = {"n": 0}

    def flaky(model, provider):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _timeout_exc()
        return "ok-after-retry"

    result, model, _, fell_back, attempts = call_with_fallback(
        flaky, [("deepseek-flash", "deepseek")], max_retries=2
    )
    assert result == "ok-after-retry" and model == "deepseek-flash"
    assert fell_back is False and attempts == 2


def test_main_fails_switches_to_fallback():
    def fail_main(model, provider):
        if model == "deepseek-flash":
            raise _timeout_exc()
        return "from-qwen"

    result, model, provider, fell_back, attempts = call_with_fallback(
        fail_main, [("deepseek-flash", "deepseek"), ("qwen-plus", "qwen")], max_retries=0
    )
    assert (result, model, provider, fell_back) == ("from-qwen", "qwen-plus", "qwen", True)
    assert attempts == 2


def test_non_retryable_error_skips_retry_goes_to_fallback():
    def bad_request(model, provider):
        if model == "deepseek-flash":
            resp = httpx.Response(400, request=httpx.Request("POST", "https://example.com"))
            raise httpx.HTTPStatusError("bad request", request=resp.request, response=resp)
        return "from-qwen"

    result, model, _, fell_back, attempts = call_with_fallback(
        bad_request, [("deepseek-flash", "deepseek"), ("qwen-plus", "qwen")], max_retries=2
    )
    # 400 不可重试：主模型只试 1 次就切备用，总共 2 次
    assert result == "from-qwen" and fell_back is True and attempts == 2


def test_all_fail_raises_last_error():
    with pytest.raises(httpx.TimeoutException):
        call_with_fallback(
            lambda m, p: (_ for _ in ()).throw(_timeout_exc()),
            [("deepseek-flash", "deepseek"), ("qwen-plus", "qwen")],
            max_retries=0,
        )
