# 本地模型网关：项目架构与技术栈（分支 B）

> 定位一句话：网关是本地部署的统一入口。客户端（命令行助手 / 文档问答 / 以后 RuoYi 的 Java 端）只认网关，不直接认供应商。
>
> 位置（你已定的结论）：入口层 → 业务编排层 → **网关层** → 供应商。网关不做 prompt 拼装、不做工具六道关，那些留在应用层。
>
> 日期：2026-11-12；对应分支 A：`~/workspace/llm-learning/doc_qa_branch_a.py`，分支 A 仍是主线，网关是接在它后面的 B 线。

## 1. 架构总图

```
客户端
  ├─ stage1_cli_assistant.py        OpenAI SDK
  ├─ doc_qa_branch_a.py             OpenAI SDK，temperature 固定 0.2
  └─ 以后：RuoYi / Spring AI        OpenAI 兼容调用
        │  只改 3 个环境变量，不改业务代码
        ▼
┌────────────────────── 本地模型网关（localhost:4000） ──────────────────────┐
│ 入口：FastAPI                                                              │
│   鉴权（网关 key）→ 输入校验（长度/必填）→ 限流 → 路由 → 计费记账            │
│                                                                            │
│ 路由器（配置化，不写死）                                                     │
│   成本优先 / 质量优先 / 延迟优先，三种策略只改配置                           │
│   别名 → 真实模型：qa-fast / qa-quality / chat-default                     │
│                                                                            │
│ 兜底链：主模型超时/4xx/5xx → 重试 2 次 → 切备用 → 再失败才返回错误            │
│   熔断：连续失败 N 次，暂停该模型一段时间，别一直撞墙                        │
│                                                                            │
│ 供应商适配层（按供应商 SDK 拆模块，你之前定的做法）                            │
│   DeepSeek 适配器 / Qwen 适配器 / Ollama（本地模型，可选）                  │
│   每个适配器只做一件事：把统一请求翻译成该供应商的格式，再把响应翻回来        │
│                                                                            │
│ 可观测（只在网关做一次，别每个客户端各做一份）                                │
│   LangFuse SDK：trace / token / 花费 / 失败原因                             │
│   审计日志 audit.log：时间、别名、真实模型、token、花费、是否 fallback        │
└────────────────────────────────────────────────────────────────────────────┘
        │  OpenAI 兼容协议 /v1/chat/completions，流式 SSE 原样透传
        ▼
供应商：DeepSeek（deepseek-flash） / Qwen（qwen-plus） / Ollama（本地，可选）
```

### 一次请求的 9 步

1. 客户端发 `POST /v1/chat/completions`，带网关 key，`model` 写别名（如 `qa-fast`），不是真实模型名。
2. 网关校验 key、校验输入（空、超长直接拒，不进模型）。
3. 查限流和预算：本 key 今天还能用多少 token / 多少钱，超了直接拒并说明原因。
4. 路由器按策略选真实模型：默认 `qa-fast → deepseek-flash`。
5. 适配器发请求，超时 30 秒，重试最多 2 次（只重试超时/5xx，不重试参数错）。
6. 失败则走 fallback 链：`deepseek-flash → qwen-plus`，失败原因记下来，别静默吞掉。
7. 成功后记账：token 用量、花费、耗时，写进 LangFuse 和本地日志。
8. 流式请求走 SSE 透传：网关不攒完整回答再发，边收边发，`stage1` 的 `/stream` 才能保持边收边打印。
9. 返回给客户端，客户端完全不知道背后换过模型。

## 2. 技术栈

| 层 | 选型 | 为什么选这个 | 备注 |
|---|---|---|---|
| 语言 | Python 3.11+ | 和你 stage 1 / 分支 A 同一栈，Anaconda 就能跑，不用另学一门 | 和你 Windows + Jupyter 环境一致 |
| Web 框架 | FastAPI + Uvicorn | 原生支持 SSE 流式、OpenAPI 文档、Pydantic 校验，写网关够用 | 启动：`uvicorn app.main:app --port 4000` |
| 数据校验 | Pydantic v2 | 请求体、配置都用它校验，错的配置启动时就报错，别等运行时炸 | 配置文件先校验再加载 |
| 路由/供应商核心 | LiteLLM（v2 用）+ 自建薄层（v1 先做） | 见第 3 节两条路线。LiteLLM 管多供应商兼容，你只管路由、预算、审计 | 不要自己重写每个供应商的重试和格式转换 |
| HTTP 客户端 | httpx（异步） | 流式透传、超时控制比 `requests` 顺手 | 自建适配器时用；用 LiteLLM 时它在内部 |
| 配置 | YAML（`config/models.yaml`）+ `.env` | 模型、别名、fallback 链、预算放 YAML，改配置不用改代码；key 只放 `.env` | YAML 改完重启网关生效，v2 再做热加载 |
| 限流/预算 | Redis 7（可选）→ 降级 SQLite / 内存 | Redis 挂了要有兜底，你安全清单里已定：Redis 挂了走本地/数据库兜底 | 学习阶段先用 SQLite + 内存，跑通再上 Redis |
| 持久化 | SQLite（学习）/ PostgreSQL（以后上生产） | 用量、花费、审计先存 SQLite 一个文件，够查、够备份 | 别一上来就搭 Postgres，增加调试成本 |
| 可观测 | LangFuse SDK + 结构化日志 | 你 2026-11-12 已定的接法：自己的网关正常走，代码里加 SDK 观测，数据集测评在 LangFuse 上跑 | trace 里不记 key、不记密码、不记完整敏感输入 |
| 本地模型（可选） | Ollama | 真正的“本地模型”接法：不用 key，走 `http://localhost:11434/v1` | 先不装也行，网关留一个 Ollama 适配器位置即可 |
| 部署 | 本地直跑 + Docker Compose（可选） | 学习先直跑，一键 `.bat` 启动；以后要给别人演示再包 Docker | 端口固定 4000，别和 RuoYi 的 8080 / 前端 80 撞 |
| 测试 | pytest + mock / smoke test | 你 2026-11-11 已讨论过的 CI/CD 做法：mock 供应商、smoke 测通路 | 每个 fallback 分支至少一个测试 |

**不选什么（先说清楚，免得走弯路）：**
- 不用 Java / Spring Cloud Gateway 来写这个网关：你的客户端是 Python，网关先用 Python 写最顺；Java 端以后只作为客户端调网关，Spring AI 放在 RuoYi 里调 `http://localhost:4000/v1` 即可。
- 不用 Nginx / Kong 先做网关：它们是反向代理，路由、fallback、按模型记账、LangFuse 观测都要你自己再包一层，学习成本高于收益。
- 不直接用 LangFuse AI Gateway 当主力：它是 beta，你已知的另一条路。先用自己的网关 + LangFuse SDK 观测，稳定后再试它。

## 3. 两条实现路线（先定这个，再写代码）

### 路线 1（推荐起手）：自建最小网关 v1 —— 学原理

只做 4 件事，约 200–300 行，先跑通再加功能：

1. 一个 FastAPI 入口，兼容 `/v1/chat/completions` 和 `/v1/models`。
2. 一个 YAML 路由表：别名 → 真实模型 → fallback 链。
3. 两个适配器：DeepSeek、Qwen，都走 OpenAI 兼容协议（和你 stage 1 的 `OpenAI(api_key, base_url)` 同款做法）。
4. 一个记账器：每次调用写一行日志（时间、别名、真实模型、token、是否 fallback）。

好处：路由、重试、熔断、记账的逻辑都在你自己手里，面试能讲清楚每一层。坏处：供应商一多，适配代码会变多。

### 路线 2（v2 升级）：LiteLLM Proxy 做引擎 + 你的薄层

把 v1 的适配器换成 LiteLLM：它内部已经接了 100+ 供应商，你的 FastAPI 只留鉴权、限流、预算、审计、LangFuse 观测。

- 客户端还是调你的 FastAPI，不直接调 LiteLLM 的 4000 端口（避免两套 key、两套记账）。
- 或者反过来：LiteLLM Proxy 直接当前端，你的 FastAPI 做成它的前置中间件。两种都行，v2 再定，v1 不用纠结。

**建议顺序：先 v1（自建最小版），再 v2（接 LiteLLM）。** v1 跑通后，你才知道 LiteLLM 帮你省了什么，面试讲起来也有对比。

## 4. 目录结构（v1）

```
llm-gateway/                      # 和 llm-learning 平级的新项目，别混进 stage1 目录
├── app/
│   ├── main.py                   # FastAPI 入口：/v1/chat/completions、/health、/v1/models
│   ├── config.py                 # 读 .env + YAML，Pydantic 校验，启动时就报错
│   ├── router.py                 # 别名解析 + 策略选择（成本/质量/延迟）
│   ├── fallback.py               # 重试、fallback 链、熔断
│   ├── auth.py                   # 网关 key 校验、每 key 预算
│   ├── billing.py                # token 换算花费、记账
│   ├── observability.py          # LangFuse 初始化、trace 上报、日志脱敏
│   └── adapters/
│       ├── base.py               # 统一接口：chat(messages, model, temperature, stream)
│       ├── deepseek.py           # base_url https://api.deepseek.com/v1
│       └── qwen.py               # base_url https://dashscope.aliyuncs.com/compatible-mode/v1
├── config/
│   └── models.yaml               # 别名、真实模型、fallback、超时、预算（见第 5 节）
├── tests/
│   ├── test_router.py            # 别名解析、策略选择
│   ├── test_fallback.py          # 主模型失败切备用（mock 供应商）
│   └── test_smoke.py             # 真调一次 qa-fast，只看通不通
├── .env.example                  # 只放 key 的名字，不放真实 key
├── .env                          # 真实 key，只在本地，不提交 Git
├── requirements.txt              # fastapi、uvicorn、pydantic、httpx、pyyaml、python-dotenv、langfuse
├── start_gateway.bat             # Windows 一键启动（照你 RuoYi 的 BAT 做法）
└── gateway.log / audit.log       # 运行日志 / 审计日志，和分支 A 的 audit.log 同款格式
```

## 5. 配置示例（核心就这一份 YAML）

```yaml
# config/models.yaml —— 改这里，不改代码
aliases:
  qa-fast:        # 文档问答默认走这个，temperature 0.2 在客户端定，网关不改
    model: deepseek-flash
    provider: deepseek
    fallback: [qwen-plus]        # 主模型失败才切，别一上来就轮询
    timeout_seconds: 30
    max_retries: 2

  qa-quality:     # 问答里需要更稳的回答时，客户端把 model 改成这个别名
    model: qwen-plus
    provider: qwen
    fallback: [deepseek-flash]
    timeout_seconds: 45
    max_retries: 2

  chat-default:   # stage1 命令行助手默认走这个
    model: deepseek-flash
    provider: deepseek
    fallback: [qwen-plus]
    timeout_seconds: 30
    max_retries: 2

budgets:
  default_daily_token_limit: 200000
  default_daily_cost_limit_usd: 2.0   # 先设一个小上限，跑超了网关直接拒并提示

# 注意：deepseek-chat 已不在 DeepSeek 官方价格表上，用它会报 404，
# 所以 fallback 别写 deepseek-chat，写 qwen-plus（stage1 里已验证过的另一条路）。
```

`.env`（网关侧，客户端不再直接拿供应商 key）：

```env
GATEWAY_API_KEY=你在本地随便生成的一串 key，给客户端用
DEEPSEEK_API_KEY=你的 DeepSeek key
QWEN_API_KEY=你的 Qwen key
LANGFUSE_PUBLIC_KEY=（可选，有再填）
LANGFUSE_SECRET_KEY=（可选，有再填）
```

## 6. 客户端怎么接（只改 3 行，不改逻辑）

以你现有的两个脚本为例，`.env` 改成这样就能走网关：

```env
LLM_API_KEY=<GATEWAY_API_KEY>              # 原来是供应商 key，现在是网关 key
LLM_BASE_URL=http://localhost:4000/v1     # 原来是 https://api.deepseek.com/v1
LLM_MODEL=qa-fast                          # 原来是 deepseek-flash，现在是别名
```

- `stage1_cli_assistant.py`：`LLM_MODEL=chat-default`，其余不动。`_deepseek_kwargs` 里 `thinking disabled` 那个 `extra_body`，网关要原样透传给 DeepSeek，别在网关把它丢掉——丢了 temperature 对比就看不出区别。
- `doc_qa_branch_a.py`：`LLM_MODEL=qa-fast`，其余不动。`temperature 0.2`、`top3 召回`、`audit.log` 都还在客户端，网关只负责选模型、兜底、记账。
- 以后 RuoYi / Spring AI：`application.yml` 里把 base-url 写成 `http://localhost:4000/v1`，model 写别名，key 写网关 key，Java 代码不用为每个供应商各写一套。

## 7. 安全与可观测（对照你 2026-11-12 的安全清单）

| 清单里的项 | 在网关里落到哪 |
|---|---|
| 密钥集中在网关一处 | 供应商 key 只在网关 `.env`；客户端只拿网关 key，丢了只换网关 key，不用换供应商 key |
| 路由配置化 | 别名、fallback、超时、重试全在 `models.yaml`，不写死在代码里 |
| fallback 链 | 主模型失败自动切备用，失败原因记下来，别静默吞掉 |
| 超时/重试/熔断 | 超时 30 秒、重试 2 次、连续失败熔断；只重试超时/5xx，不重试参数错 |
| 日志脱敏 | 日志只记问题长度、token、花费，不记完整敏感输入、不记 key |
| LangFuse 观测 | 在网关加一次 SDK 就够了：每次调用一条 trace，含别名、真实模型、token、花费、是否 fallback；错误 case 100% 采样 |
| 审计 | `audit.log` 每行一条：时间、key（脱敏后 4 位）、别名、真实模型、token、花费、fallback 与否 |

## 8. 验收（v1 跑通的标准）

- [ ] `GET /health` 返回 ok；`GET /v1/models` 能列出 `qa-fast / qa-quality / chat-default` 三个别名。
- [ ] 命令行助手改 3 行 `.env` 后能正常对话，`/stream` 还是边收边打印。
- [ ] 文档问答改 3 行 `.env` 后，`--selftest` 和正常问答都通，回答仍带 `[来源]`。
- [ ] 把 DeepSeek key 故意写错一次，网关自动切到 `qwen-plus` 并返回答案，日志里能看到 fallback 记录。
- [ ] 同一天超预算后，网关拒绝请求并提示超限，而不是继续扣费。
- [ ] LangFuse 里能看到一条 trace：别名、真实模型、token、花费都对得上。
- [ ] `.env` 没进 Git，`gateway.log` / `audit.log` 里没有真实 key。

## 9. 下一步（等你选）

- **A. 先写 v1 最小网关代码**：按第 4 节目录，先给 `main.py + router.py + fallback.py + 两个适配器`，跑通上面 7 条验收。
- **B. 直接上 LiteLLM Proxy 版**：跳过自建适配器，用 LiteLLM 当引擎，你只写鉴权、预算、审计那层薄壳。
- **C. 先只定架构、不写代码**：这份文档就是定稿，下次写代码时再按它开工。

建议选 A：v1 代码量不大，跑通后你对路由、fallback、记账都有手感，v2 接 LiteLLM 时才知道它省了什么，面试也能讲出两条路线的取舍。
