后端实施规划
在实施规划后方提前写出后端软件vibe coding后需要人配置的地方或日志文件说明，要求遵循简洁的原则，一条一句话总结即可
并且每一条都必须是需要开发者手动配置或观看系统运行的。

---

## 人工配置 / 日志说明

- .env 配置：本机 PostgreSQL 连接 DATABASE_URL（postgres/123456）与 Redis REDIS_URL（见 stock_backend/.env）。
- JWT 密钥：生产/多用户需在 .env 设置强随机 JWT_SECRET_KEY（≥32 字节），dev 默认值仅限本地，否则 token 可被伪造。
- 阶段二冒烟测试：`uvicorn app.main:app` 启动后运行 `python scripts/smoke_phase2.py`，可观察注册/登录/自选/支撑压力位/指标全流程（脚本自动清理测试用户）。
- 首次启动需手动建库：`CREATE DATABASE stock_invest;`。
- Redis 需本机启动（默认 127.0.0.1:6379），未启动时 `/ready` 返回 503（`/health` 不受影响）。
- 启动命令：`uvicorn app.main:app`，Swagger 在 `/docs`。
- 日志：结构化 JSON 输出到 stdout，全链路 `request-id`（响应头 `X-Request-ID` 透传）。
- 行情源为东方财富接口（akshare），偶发反爬断连（如 17.push2 主机被节流）；已内置 curl_cffi 浏览器指纹 + 指数退避重试 + 缺数降级，观察日志 `[eastmoney] ... failed/give up` 判断，冷却后可自动恢复。
- 生产/多用户环境请在 stock_backend/.env 设置强随机 JWT_SECRET_KEY（≥32 字节），dev 默认值仅限本地。
- 阶段三 AI 聊天需在 stock_backend/.env 配置 DeepSeek API Key（DEEPSEEK_API_KEY）；未配置时 /api/v1/chat 返回降级文案而非报错。
- 本地记忆文件在 stock_backend/data/memory/{user_id}/*.md（人类可读，M 区「记忆文件」可打开），向量库持久化在 data/chroma/，首次运行自动创建。
- LLM 调用审计日志：结构化 JSON 输出到 stdout（`llm_call ok/failed`，含 prompt/响应/token/耗时/错误），用于排查 AI 调用问题。
- 阶段三冒烟测试：`uvicorn app.main:app` 启动后运行 `python scripts/smoke_phase3.py`，可观察会话/策略/定制Agent/聊天 SSE 全流程（脚本自动清理测试用户；未配 DeepSeek Key 时聊天走降级文案）。
- 回测前需先同步标的 K 线数据（贵州茅台可跑同步任务或阶段一数据），否则回测任务 failed（错误提示"请先同步行情"）。
- 回测由 Celery backtest 队列异步执行：需额外启动 `celery -A app.worker.celery_app:celery_app worker -Q backtest --pool=solo`，未启动时任务停留 queued。
- 策略代码在 RestrictedPython 沙箱执行（禁 import/网络/文件/eval），策略死循环由 Celery 任务硬超时兜底（BACKTEST_HARD_TIME_LIMIT，触发后 worker 进程被终止重启，可观察日志）。
- 阶段四冒烟测试：`uvicorn app.main:app` + 上述 backtest worker 同时运行后执行 `python scripts/smoke_phase4.py`，可观察发起回测→任务状态→结果查询全流程（脚本自动清理测试用户）。
- 回测费用/撮合参数可在 .env 配置（BACKTEST_INITIAL_CASH/佣金/印花税/撮合价/时间预算，见 stock_backend/.env 注释）。
---

## 后端开发实施方案（项目启动 → 第一版发布）

> 目标：按 docs.md 需求 + working_docs.md 六要素，自下而上（数据层→用户/指标层→AI 层→回测层→部署）交付生产级最小原型机。
> 约束：前端不计算复杂指标；回测/AI/同步走 Celery 不阻塞主线程；记忆本地存储（LangChain 本地向量库）；行情走 DataProvider 抽象（默认东方财富/Akshare）。
> 数据库：docs/sql/01_schema.sql（全部表）+ 02_seed_fixed_indices.sql（固定指数）+ 03_agent_extensions.sql（Agent 扩展）。

### 阶段一：工程基建与行情数据层

**1.1 项目脚手架**
- 建 FastAPI 分层工程 `app/{api,services,repositories,schemas,models,core}`，router→service→repository 单向依赖，禁反向/循环依赖。
- 配置：pydantic-settings 读 `.env`（DB/Redis/DeepSeek 密钥、同步间隔、缓存 TTL），禁止硬编码。
- 全局异常处理 + 统一响应结构 `{code,msg,data}`；ruff/black 规范；`pyproject.toml` + `requirements.lock` 锁依赖。
- 依赖：FastAPI/SQLAlchemy/Celery/Redis + **langchain/langgraph + langchain-community**（DeepSeek 适配、ChromaDB 本地向量库）。
- 验收：`uvicorn app.main:app` 启动、Swagger `/docs` 可访问。

**1.2 可观测底座**
- 结构化 JSON 日志（python-json-logger），中间件生成并透传 `request-id`（日志/响应头/任务）。
- 端点：`/health`（存活）、`/ready`（DB/Redis 就绪）、`/metrics`（Prometheus）。
- 验收：`/health` 返回 200，日志含 request-id。

**1.3 数据库接入**
- Alembic 初始化，迁移对齐 01_schema.sql + 03_agent_extensions.sql 全部表（users/symbols/kline_*/snapshot_realtime/支撑压力/策略/回测/任务/user_agents/agent_runs/agent_steps/memory_chunks）。
- SQLAlchemy 声明式模型 + 连接池（池大小/超时可配）；时间统一 UTC。
- 封装 K 线按月分区管理工具（调用 `create_kline_partitions` 建分区、越界写兜底）。
- 验收：`alembic upgrade head` 成功、分区表可建。

**1.4 DataProvider 抽象（行情源可插拔）**
- 定义抽象基类：`fetch_kline(symbol, period, start, end)`、`fetch_realtime(symbols)`、`resolve_index_code(name)`。
- 实现 `EastMoneyProvider`（Akshare）：个股/ETF/指数历史K线、实时快照、行业指数 code 按名称回填。
- 统一封装：请求超时、指数退避重试、幂等（symbol+ts 去重）、数据清洗（空值/停牌/异常价剔除）。
- 验收：手动跑通拉取贵州茅台日K并入库；单测 mock 外部源。

**1.5 行情同步任务（Celery + Beat）**
- 搭 Celery 工程（app/worker/beat），按队列分 `sync`（行情）/`backtest`（回测）/`ai`（AI）三队列。
- 任务：`kline_init`（首次全量历史K线）、`kline_incremental`（每日收盘后增量）、`realtime_poll`（交易时段轮询快照）。
- 写入链路：分区K线 upsert → `snapshot_realtime` → Redis 缓存（快照按 TTL）。
- 状态与日志：`sync_tasks` 记录运行状态，`task_logs` 写全链路日志；beat 调度间隔走配置。
- 验收：beat 触发 → worker 入库 → Redis 有缓存 → 状态表更新。

**1.6 种子数据**
- 执行 02_seed_fixed_indices.sql 入库固定大盘/行业指数；行业指数 code 由同步任务按名称回填（幂等）。
- 验收：`symbols` 含 49 条固定指数且顺序正确。

**1.7 行情查询 API**
- `GET /api/v1/symbols`：标的列表（type/search 过滤，供下拉与 G/H 固定列表）。
- `GET /api/v1/symbols/search`：6 位代码/名称联想（已入库优先）。
- `GET /api/v1/kline`：多周期 K 线（15m/1d/1w/1mon，区间/分页）。
- `GET /api/v1/snapshot`：批量实时快照（合并 fundamentals/etf_premiums/index_valuations 特殊字段）。
- 验收：四接口返回正确，供前端联调。

### 阶段二：用户域与技术指标服务

**2.1 用户鉴权**
- `POST /api/v1/auth/register`、`POST /api/v1/auth/login`（密码 bcrypt 哈希 → JWT）。
- 当前用户依赖注入（`Depends(get_current_user)`）；`PUT /api/v1/users/me` 更新昵称/头像。
- 验收：登录拿 token，受保护接口校验通过/拒绝。

**2.2 重点关注股票**
- `GET/POST/DELETE /api/v1/watchlist`：列表/添加/删除，`UNIQUE(user,symbol)` 幂等。
- 列表合并 snapshot 实时价返回（代码/名称/最新价/涨跌幅）。
- 验收：添加→列表含实时价→删除。

**2.3 支撑/压力位**
- `GET/POST/DELETE /api/v1/support-resistance`（user, symbol, type=support|pressure, price, note）。
- 验收：添加后 K 线图可叠加横线、删除后消失。

**2.4 技术指标服务**
- 服务端实现 MACD/KDJ/成交量/成交额计算（入参 K 线序列，输出指标序列）。
- Redis 缓存指标（key 含 symbol+period+K 线最新 ts），失效回源重算。
- 验收：指标值与已知参考一致（pytest 单测）。

### 阶段三：AI 策略页后端（LangChain Agent + 本地记忆）

**3.1 会话与消息**
- `conversations` CRUD：创建/列表/重命名/删除。
- `chat_messages`：追加消息、按会话拉取（时间升序）；带 symbol_id 绑定标的。
- 验收：多会话隔离、消息顺序正确。

**3.2 LangChain LLM 封装**
- 用 langchain 集成 DeepSeek（langchain-openai 兼容，`ChatDeepSeek`），流式输出 → SSE 透传前端。
- 外部调用防护：超时、指数退避重试、熔断（连续失败熔断 + 半开探测）、限流（借鉴 TradingAgents-CN llm_adapters）。
- 验收：流式逐字返回；模拟断流有降级文案。

**3.3 LangChain 工具集 + 上下文组装**
- 将行情快照/技术指标/记忆检索封装为 LangChain Tool（`@tool`），Agent 按需取数（借鉴 TradingAgents-CN tools/analysis）。
- 拼接 system prompt（角色 + 风险提示 + 「数据不可用须明说、不编造」）。
- 验收：请求 LLM 前日志可见工具调用与完整上下文。

**3.4 本地记忆系统（LangChain 本地向量库）**
- 记忆抽取：LangChain 从对话/策略结果抽取关键事实（交易体系/规则/偏好），写用户本地记忆文件。
- 向量化：本地 ChromaDB 持久化（切片 + embedding），`memory_chunks` 登记 chunk/vector_id/file_path，`user_memory_files` 登记文件。
- 检索：相似度检索 TopK 注入上下文（默认本地 embedding，后续可换）。
- 验收：对话后可打开本地记忆文件/向量库目录；后续请求命中相关记忆。

**3.5 策略生成（LangChain 结构化输出）**
- 定义四类 prompt 模板：诊断符号/交易计划/机会雷达/创建交易策略（入场/止损/止盈/仓位规则文案）。
- 用 LangChain `with_structured_output` 生成策略代码 + JSON 参数，schema 校验。
- 验收：点击卡片注入对应模板；生成的代码/参数可入库并直接回测。

**3.6 交易策略 CRUD**
- `trading_strategies`：保存（title/description/code/params/status）/列表/详情/更新，按 user 隔离。
- 验收：M 区列表数据源、保存后回测可用。

**3.7 用户定制 Agent（user_agents CRUD）**
- CRUD：创建/列表/启停定制 Agent，配置 system_prompt/tools/llm_config/memory_config（JSONB）。
- 会话发送时按所选 agent_id 加载配置，构造 LangChain Agent。
- 验收：可创建并保存定制 Agent，会话可选用。

**3.8 多智能体编排（LangGraph）**
- 基于 TradingAgents-CN trading_graph 构建：分析（行情/指标/新闻）→ 多空研究员辩论 → 风控 → 交易决策。
- LangGraph StateGraph 编排，条件路由/反射/信号处理，执行落 `agent_runs`/`agent_steps`。
- 与 L 区功能卡片对接：诊断/交易计划/机会雷达走不同图分支，UI 不变。
- 验收：跑通一次多智能体运行，agent_steps 可见各步骤输出。

### 阶段四：回测引擎（异步，不阻塞主线程）

**4.1 回测引擎**
- 策略代码沙箱执行：限制内置依赖/超时/内存，禁网络。
- 撮合规则（按开盘/收盘价成交）、持仓与交易流水、参数 JSON 化（入场/止损/止盈/仓位）。
- 验收：简单双均线策略可跑出交易流水。

**4.2 指标计算**
- 胜率/盈亏比/夏普/累计买入/累计卖出/年化收益率/最大回撤 + `metrics_json` 扩展字段。
- 验收：指标公式与已知案例一致（pytest）。

**4.3 回测任务流（Celery）**
- `POST /api/v1/backtest` 创建 `backtest_tasks`（queued）→ worker 执行。
- 状态机 queued→running→success/failed，`progress` 进度回写。
- 结果事务写入 `backtest_results`（与策略原子保存）；结果抽取转本地向量记忆（memory_chunks）。
- 失败自动重试 + `task_logs` 记录。
- 验收：异步返回任务 ID，前端轮询到 success 及结果。

**4.4 回测 API**
- 发起回测 / 任务状态轮询 `GET /api/v1/backtest/tasks/{id}` / 结果查询 `GET /api/v1/backtest/results?strategy=`。
- 验收：N 区与全景K线策略指标数据源可用。

### 阶段五：部署闭环与生产收尾

**5.1 容器化**
- 后端/Celery 多阶段 Dockerfile（依赖层缓存）。
- Docker Compose：postgres/redis/api/worker/beat/nginx 一键编排。
- 验收：`docker compose up` 全服务拉起。

**5.2 Nginx**
- 反向代理 `/api` → api、静态资源缓存 + gzip + TLS（证书可配）。
- 验收：经 Nginx 访问前端与 API 正常。

**5.3 CI/CD**
- GitHub Actions：lint → test → build 镜像 → 部署。
- 验收：push 触发流水线全绿。

**5.4 监控告警**
- Prometheus 指标：API 吞吐/延迟/错误率、队列深度、缓存命中率、行情新鲜度。
- Grafana 面板 + 告警（接口错误率阈值、队列积压、行情延迟）。
- 验收：面板出图、可触发告警。

**5.5 测试补齐**
- pytest：指标计算/策略解析/记忆抽取/Agent 编排（LangGraph 单测）/核心 API 冒烟。
- 验收：CI 跑测通过。

**5.6 收尾检查**
- 按 working_docs.md 六要素模板逐项自查（可维护/扩展/演进/稳定/可观测/可部署），每项一句话结论。
- 补全 docs/Agent_backend/Agent_code.md 编码记录、api-docs.md API 文档、fixed.md 修复记录。
- 验收：六要素每条有结论、三文档完整。
