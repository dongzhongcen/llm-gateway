# 快速开始（v1 最小网关）

这是 `llm-gateway` 的 v1：自建最小网关，先跑通路由 + fallback + 记账，
再到 v2 把 LiteLLM 接进来当引擎。架构说明见 `README.md`。

## 1. 安装（Windows）

```bat
cd llm-gateway
pip install -r requirements.txt
copy .env.example .env
```

然后打开 `.env` 填上真实的 key（只填你有的那一家就行）：

```env
GATEWAY_API_KEY=随便生成一串，给客户端用
DEEPSEEK_API_KEY=你的 DeepSeek key
QWEN_API_KEY=你的 Qwen key
```

注意：`.env` 不要提交 Git，`.gitignore` 里已经排除了。

## 2. 启动

双击 `start_gateway.bat`，或者：

```bat
python -m uvicorn app.main:app --host 127.0.0.1 --port 4000
```

看到 `Application startup complete` 就是起来了。先测健康检查：

```bat
curl http://127.0.0.1:4000/health
```

应返回 `{"status":"ok"}`。

## 3. 跑测试（不用真 key，不花钱）

```bat
python -m pytest tests/test_router.py tests/test_fallback.py tests/test_api.py -v
```

下面这条命令跑 16 个测试：路由 5 个、fallback 5 个、API 6 个；再加 smoke 1 个（默认跳过），一共 17 个。
真调测试默认跳过，网关启动后再跑：

```bat
set RUN_SMOKE=1
python -m pytest tests/test_smoke.py -v
```

## 4. 让现有客户端走网关（只改 3 行 .env，不改代码）

以 `stage1_cli_assistant.py` / `doc_qa_branch_a.py` 为例：

```env
LLM_API_KEY=<GATEWAY_API_KEY>
LLM_BASE_URL=http://localhost:4000/v1
LLM_MODEL=qa-fast
```

`stage1` 用 `chat-default`，`doc_qa` 用 `qa-fast`。

## 5. 已验证的 fallback

把 `DEEPSEEK_API_KEY` 故意写错一次，网关会自动切到 `qwen-plus` 并返回答案，
`audit.log` 里能看到 `fell_back: true` 的记录。

## 文件一览

| 文件 | 作用 |
|---|---|
| `app/main.py` | FastAPI 入口：`/health`、`/v1/models`、`/v1/chat/completions` |
| `app/config.py` | 读 `config/models.yaml` + `.env` |
| `app/router.py` | 别名 -> 真实模型 |
| `app/fallback.py` | 重试、fallback、熔断 |
| `app/auth.py` | 网关 key 校验 |
| `app/billing.py` | 按 key 记 token、每日预算 |
| `app/observability.py` | 审计日志 + LangFuse（可选） |
| `app/adapters/` | DeepSeek / Qwen 适配器（OpenAI 兼容协议） |
| `config/models.yaml` | 别名、fallback、超时、预算 |
| `tests/` | 通用测试：路由、fallback、API mock、smoke |
