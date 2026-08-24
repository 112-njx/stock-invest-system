后端实施规划
在实施规划后方提前写出后端软件vibe coding后需要人配置的地方或日志文件说明，要求遵循简洁的原则，一条一句话总结即可
并且每一条都必须是需要开发者手动配置或观看系统运行的。

---

## 人工配置 / 日志说明

v0.1阶段
- .env 配置：本机 PostgreSQL 连接 DATABASE_URL（postgres/123456）与 Redis REDIS_URL（见 stock_backend/.env）。
- JWT 密钥：生产/多用户需在 .env 设置强随机 JWT_SECRET_KEY（≥32 字节），dev 默认值仅限本地，否则 token 可被伪造。
- 阶段二冒烟测试：`uvicorn app.main:app` 启动后运行 `python scripts/smoke_phase2.py`，可观察注册/登录/自选/支撑压力位/指标全流程（脚本自动清理测试用户）。
- 首次启动需手动建库：`CREATE DATABASE stock_invest;`。
- Redis 需本机启动（默认 127.0.0.1:6379），未启动时 `/ready` 返回 503（`/health` 不受影响）。
- 启动命令：`uvicorn app.main:app`，Swagger 在 `/docs`。
- 日志：结构化 JSON 输出到 stdout，全链路 `request-id`（响应头 `X-Request-ID` 透传）。
- 行情源为东方财富接口（akshare），偶发反爬断连（如 17.push2 主机被节流）；已内置 curl_cffi 浏览器指纹 + 指数退避重试 + 缺数降级，观察日志 `[eastmoney] ... failed/give up` 判断，冷却后可自动恢复。
- 行情页固定指数数据：首次启动/重置数据库后运行 `python scripts/sync_fixed_indices.py` 补齐 49 个固定指数（大盘 14 + 行业 35）日K + 实时快照（幂等可重跑）；东方财富被限流时指数K线自动降级新浪（A股大盘）/同花顺（行业板块）。
- 指数/板块快照无成交量、成交额字段，写入 `snapshot_realtime` 时自动置 0（NOT NULL 兜底），属正常现象。
- 阶段三 AI 聊天需在 stock_backend/.env 配置 DeepSeek API Key（DEEPSEEK_API_KEY）；未配置时 /api/v1/chat 返回降级文案而非报错。
- 本地记忆文件在 stock_backend/data/memory/{user_id}/*.md（人类可读，M 区「记忆文件」可打开），向量库持久化在 data/chroma/，首次运行自动创建。
- LLM 调用审计日志：结构化 JSON 输出到 stdout（`llm_call ok/failed`，含 prompt/响应/token/耗时/错误），用于排查 AI 调用问题。
- 阶段三冒烟测试：`uvicorn app.main:app` 启动后运行 `python scripts/smoke_phase3.py`，可观察会话/策略/定制Agent/聊天 SSE 全流程（脚本自动清理测试用户；未配 DeepSeek Key 时聊天走降级文案）。
- 回测前需先同步标的 K 线数据（贵州茅台可跑同步任务或阶段一数据），否则回测任务 failed（错误提示"请先同步行情"）。
- 回测由 Celery backtest 队列异步执行：需额外启动 `celery -A app.worker.celery_app:celery_app worker -Q backtest --pool=solo`，未启动时任务停留 queued。
- 策略代码在 RestrictedPython 沙箱执行（禁 import/网络/文件/eval），策略死循环由 Celery 任务硬超时兜底（BACKTEST_HARD_TIME_LIMIT，触发后 worker 进程被终止重启，可观察日志）。
- 阶段四冒烟测试：`uvicorn app.main:app` + 上述 backtest worker 同时运行后执行 `python scripts/smoke_phase4.py`，可观察发起回测→任务状态→结果查询全流程（脚本自动清理测试用户）。
- 回测费用/撮合参数可在 .env 配置（BACKTEST_INITIAL_CASH/佣金/印花税/撮合价/时间预算，见 stock_backend/.env 注释）。
- 阶段五全栈部署：`cp .env.docker.example .env.docker && docker compose --env-file .env.docker -f deploy/docker-compose.yml up -d --build`；前端单独部署用根目录 docker-compose.yml（对接宿主后端）。
- 容器启动入口 docker-entrypoint.sh 自动执行 Alembic 迁移 + 固定指数种子（幂等），无需手动建库；db/redis 仅容器内网不映射宿主端口（避免与本机 5432/6379 冲突）。
- 宿主端口按需映射（见 .env.docker）：nginx 默认 127.0.0.1:8080/8443（HTTP/HTTPS），对外发布改 80/443 与 0.0.0.0；TLS 需挂载证书到 /etc/nginx/certs 并启用 nginx.conf 中 443 server 块。
- 监控：Prometheus 127.0.0.1:9090、Grafana 127.0.0.1:3000（初始 admin/admin，可改 .env.docker）；/metrics 含 LLM 调用与平台指标（队列深度/缓存命中率/行情新鲜度/回测积压），告警规则在 deploy/prometheus/alerts.yml。
- CI：push 触发 lint→test→build 全自动（需 PostgreSQL/Redis service 自动拉起）；部署为 GitHub Actions workflow_dispatch 手动触发，需配置 secrets（DEPLOY_HOST/DEPLOY_USER/DEPLOY_SSH_KEY）后启用。
- 行情数据修复（2026-08-18）后需重跑实时同步生效（beat `realtime_poll` 或 `scripts/sync_fixed_indices.py`）；东财实时接口偶发限流（`RemoteDisconnected`，日志 `[eastmoney] ... give up`），冷却后自动恢复。
- 行业指数实时匹配：35 个固定行业 23 个可匹配东财板块（白酒→白酒Ⅲ、游戏→游戏Ⅲ、证券→证券Ⅲ 等），10 个（创新药/文化传媒/军工/消费/细分化工/农业种植/猪肉/港口航运/公路铁路运输/汽车整车）东财无对应板块，最新价/涨跌幅显示 "--" 属数据源无对应而非 bug，接入更多数据源可补全。
- 指数成交量/成交额：海外指数（道琼斯/纳斯达克等）数据源无成交量字段，快照 volume/amount 存 NULL 前端显示 "--" 属正常；国内指数/行业指数重同步后有真实成交量。
- 指数PE/个股市值/ETF溢价：实时轮询 best-effort 填充；指数PE 仅 沪深300/上证50/中证1000 可取自乐咕 `stock_index_pe_lg`，其余指数无 PE 数据源；乐咕/东财限流时该轮跳过，不阻塞轮询。
- 数据库迁移命令：在后端根目录下使用命令.\.venv\Scripts\alembic.exe upgrade head，可以直接调用依赖链使当前数据库更新到最新版本。

v0.2阶段
- WS 实时数据推送需要同时启动 Celery worker + beat，否则 WS 连接正常但无数据推送,启动命令：
- # 启动 worker
.venv\Scripts\celery.exe -A app.worker.celery_app worker --pool=solo -l info

# 启动 beat
.venv\Scripts\celery.exe -A app.worker.celery_app beat -l info


- ADMIN_USERNAMES 环境变量（管理端点访问权限）
- 阶段六 Embedding 升级：生产需在 .env 设 `EMBEDDING_MODEL=minilm`（默认 minilm），首次启动/首次记忆操作会自动从 HuggingFace 下载 `paraphrase-multilingual-MiniLM-L12-v2` int8 量化 ONNX（约 118MB）到 `stock_backend/data/models/`，需联网；下载失败自动回退 `hash` embedding（字符 n-gram 哈希），检索退化但不报错。
- 阶段六 Embedding 可选配置：`EMBEDDING_MODEL_PATH`（模型本地目录，默认 data/models）、`EMBEDDING_QUANTIZATION`（int8 默认 / fp32）、`EMBEDDING_MODEL_NAME`（HF 模型仓库，默认多语言 MiniLM-L12）。
- 阶段六从 hash 切换到 minilm 后，需手动重建向量库（hash 与 minilm 向量不兼容）：`.venv\Scripts\python.exe scripts\rebuild_embeddings.py`（按 memory_chunks 原文重新向量化，幂等）。
- 阶段六注意：多语言 MiniLM-L12 因 25 万词表，量化后模型约 118MB（roadmap 原 6.1 估 40MB 基于英文 all-MiniLM-L6-v2，该模型中文语义失效已弃用），运行时内存约 150~250MB；如需更小模型可换 `EMBEDDING_MODEL_NAME`。
---

## 后端开发实施方案（项目启动 → v0.1）

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

#### 项目v0.2用户体验升级
** 该阶段仅为现有功能进行生产实际可用级架构补充。

> 升级目标：将行情数据体系与AI对话两大核心功能从"Demo可用"升级为"用户实际可用"。
> 行情数据解决：进入软件空白、行情延迟高、搜索范围窄、关注后无数据、缓存几乎无效。
> AI对话解决：流式中断无续传、记忆检索质量差、多智能体黑盒、降级体验差、长会话超限、策略生成失败率高。
> 约束：不新增功能模块，技术栈不变（FastAPI+PostgreSQL+Redis+Celery+LangChain+LangGraph），缓存层仅Redis+PostgreSQL。

---

## 阶段一：行情数据缓存体系

**1.1 启动预同步与缓存预热**
- 架构设计：`docker-entrypoint.sh` 增加预同步步骤——检查49条固定指数最新K线时间（`SELECT symbol_id, MAX(ts) FROM kline_1d GROUP BY symbol_id`），超过1天或无数据则向Celery发送 `kline_init` 任务（固定指数范围，不阻塞API启动）。
- 新增 `sync_status` 表：`(id, scope VARCHAR, target_id INT, status VARCHAR, progress INT, total INT, message TEXT, started_at, finished_at)`，记录固定指数/关注标的同步状态，供前端轮询展示进度。
- FastAPI startup 事件增加缓存预热：将固定指数最近500根日K批量写入Redis（`kline:{symbol_id}:1d:500`），最新快照写入Redis（`snapshot:{symbol_id}`），预热失败不阻断启动。
- `sync_fixed_indices.py` 保留为手动运维脚本，日常启动由entrypoint自动完成。
- 验收：清空Redis+重置库后 `docker compose up`，固定指数K线自动同步，前端进入时显示"数据同步中（X/49）"而非空白。

**1.2 K线Redis缓存落地**
- 架构设计：`kline_repo.get_kline()` 查询前先查Redis，缓存键 `kline:{symbol_id}:{period}:{limit}`（按最近N根，不含完整日期范围，提升命中率），TTL=`KLINE_CACHE_TTL=300`秒。
- 缓存值为JSON序列化的K线列表（ts/open/high/low/close/volume/amount），命中后直接返回，未命中查PostgreSQL分区表并回写Redis。
- 失效策略：`realtime_poll` 写入新K线后，`DEL kline:{symbol_id}:{period}:*`（按pattern删除该标的所有周期缓存）；`kline_incremental` 完成后同样清除。
- 缓存击穿保护：热点key过期时用Redis `SET kline_lock:{symbol_id}:{period} NX EX 5` 分布式锁，仅一个请求回源PG，其余等待2s后读缓存；Redis不可用时降级直查PG（已有逻辑）。
- 验收：连续请求同一标的K线，第二次起Redis命中（日志 `[kline-cache] hit`），响应时间从百毫秒级降到毫秒级；新K线写入后缓存自动失效。

**1.3 实时快照缓存增强**
- `SNAPSHOT_CACHE_TTL` 从5秒延长至300秒；缓存值从仅 `{price, updated_at}` 扩展为完整快照字段（price/open/high/low/pre_close/volume/amount/change_pct/turnover/amplitude等14项）。
- `market_service.get_snapshots()` 查询顺序改为：Redis批量 `MGET snapshot:{id}` → 未命中的查PostgreSQL `snapshot_realtime` → 回写Redis。
- `realtime_poll` 每次写入快照后 `SETEX snapshot:{id} 300` 覆盖缓存（已有逻辑，扩展字段即可）。
- 非交易时段：快照缓存命中时正常返回，附带 `data_age_seconds` 字段（当前时间 - updated_at），前端据此标注"数据时间"而非显示"--"。
- 验收：非交易时段进入软件，固定指数显示最近收盘价并标注更新时间；交易时段价格5分钟内从Redis读取。

**1.4 技术指标缓存优化**（可能已经优化过了，你看一眼）
- 当前缓存键含完整start/end/limit参数，命中率低；改为按"最新N根"缓存，键 `indicator:{symbol_id}:{period}:{names_hash}:{latest_ts}`（latest_ts为K线最新时间戳，新K线到达自动失效，已有此设计但需确认start/end不影响键生成）。
- 指标计算前先查Redis，命中直接返回；未命中从PG取K线→计算→回写Redis（TTL=300秒）。
- 验收：切换标的后5分钟内重复请求指标，Redis命中；新K线写入后指标自动重算。

---

## 阶段二：实时行情WebSocket推送

**2.1 WebSocket连接管理**
- 新增 `app/api/ws.py`，路由 `WS /api/v1/ws/market`，依赖JWT认证（query参数传token或首条消息鉴权）。
- `ConnectionManager` 单例：维护 `Dict[user_id, Set[WebSocket]]`（支持多标签页），提供 connect/disconnect/broadcast/subscribe 接口。
- 心跳机制：服务端每15秒发送 `{"type":"ping"}`，客户端需回 `{"type":"pong"}`，30秒无pong断开连接。
- 验收：前端建立WS连接，心跳正常；断开后服务端清理连接资源。

**2.2 订阅模型与增量推送**
- 客户端连接后发送订阅消息 `{"action":"subscribe","symbol_ids":[1,2,3]}`，服务端记录该连接的订阅集合；切换标的/关注列表变化时发送 `subscribe`/`unsubscribe` 更新。
- `realtime_poll` 每轮拉取并写入快照后，遍历所有活跃连接，仅推送该连接订阅范围内有更新的标的（对比 `updated_at` 变化），消息格式 `{"type":"snapshot","data":{symbol_id:{price,change_pct,...}}}`。
- 新K线写入时推送 `{"type":"kline","symbol_id":...,"period":"15m","bar":{...}}`，前端更新K线末根。
- 验收：交易时段打开页面，K线末根价格随WS推送实时跳动（延迟≤5s），无需HTTP轮询。

**2.3 断线重连与增量补拉**
- 客户端断线重连后，发送 `{"action":"sync","since":"2026-08-20T10:30:00"}`（最后收到消息的时间戳），服务端查询该时间之后更新的快照批量返回，补齐断线期间数据。
- 重连失败指数退避（1s/2s/4s/8s，最大30s），重连期间降级为HTTP轮询（7s），恢复后切回WS。
- 验收：断网10秒后恢复，WS自动重连，断线期间价格变化补齐，无数据缺口。

---

## 阶段三：标的目录与搜索关注增强

**3.1 全量标的目录预同步**
- `symbols` 表新增 `is_catalog BOOLEAN DEFAULT FALSE`（TRUE表示在目录中但未同步K线），加索引 `(is_catalog, type)`。
- 新增Celery任务 `catalog_sync`：每日凌晨3:00通过akshare `stock_info_a_code_name()` 拉取全A股约5000条（代码+名称），`fund_etf_spot_em()` 拉取ETF列表，幂等upsert到symbols表（`is_catalog=TRUE`，已同步K线的标的保持FALSE）。
- 启动时检查 `symbols WHERE is_catalog=TRUE AND type='stock'` 数量，<4000则触发一次catalog_sync。
- 失败重试：Celery任务配置 `autoretry_for=(Exception,), retry_backoff=3, retry_kwargs={'max_retries':3}`，凌晨抓取异常时自动重试3次（退避3s/9s/27s）；3次仍失败标记 `sync_status.status='failed'`，下次启动时补抓。
- 数据校验：同步完成后校验A股数量≥4800、ETF数量≥500，不达标标记 `status='partial'`，1小时后自动重试一次。
- 手动触发接口：新增 `POST /api/v1/admin/catalog/sync`（管理员权限），随时手动触发全量目录同步，返回 `{"task_id":..., "status":"queued"}`；本地开发或凌晨任务失败后可直接调用，无需等待定时或重启。
- 验收：启动后symbols表含全A股+ETF目录，搜索任意A股代码/名称均可命中；凌晨任务失败后自动重试；管理员接口可手动触发同步。

**3.2 搜索接口增强**
- `GET /api/v1/symbols/search?keyword=xxx&type=stock` 改为三层逻辑：
  1. 精确代码匹配（6位数字完全相等）→ 排最前
  2. 目录表模糊搜索：`code LIKE 'kw%' OR name LIKE '%kw%'`
  3. 排序：精确匹配 > `is_catalog=FALSE`（已同步K线） > `is_catalog=TRUE`（仅目录），再按code排序
- 外部回退：本地目录无结果时，A股调akshare `stock_info_a_code_name()` 实时过滤，结果写入symbols表（is_catalog=TRUE）+ 缓存。
- 搜索结果缓存：`search:{type}:{keyword}` → Redis，TTL=3600秒；catalog_sync完成后批量删除 `search:*`。
- 返回字段增加 `is_catalog` 和 `has_kline`（布尔），前端据此标注"已同步/未同步"。
- 验收：输入"6005"联想出贵州茅台等；输入"茅台"按名称命中；搜索结果标注同步状态。

**3.3 关注列表添加自动同步**
- `POST /api/v1/watchlist` 流程改为：校验标的存在（symbols表中存在，含is_catalog=TRUE）→ 幂等写入user_watchlist → 异步发送 `kline_init` 任务（仅该标的）→ 立即返回。
- `user_watchlist` 表新增 `sync_status VARCHAR DEFAULT 'pending'`（pending/syncing/done/failed）、`last_synced_at TIMESTAMP`。
- `kline_init` 任务开始时更新 `sync_status='syncing'`，完成更新 `done`+`last_synced_at`，失败更新 `failed`（可重试3次）。
- 关注列表查询返回sync_status，前端展示"同步中/已同步/失败"。
- 验收：搜索添加一只新股，关注列表立即出现并显示"同步中"，约10秒后K线同步完成自动变为"已同步"。

**3.4 关注列表Redis缓存**
- `GET /api/v1/watchlist` 查询顺序：Redis `watchlist:{user_id}` → PostgreSQL → 回写Redis（TTL=300秒）。
- 缓存值为关注列表完整数据（含symbol信息+最新快照合并），添加/删除关注时 `DEL watchlist:{user_id}`。
- 批量快照查询 `GET /api/v1/snapshot?symbols=` 结果也按用户关注集合缓存 `watchlist_snap:{user_id}`，TTL=10秒（交易时段）/300秒（非交易时段）。
- 验收：关注列表第二次请求Redis命中；增删后缓存自动失效。

---

## 阶段四：DataProvider可插拔升级

**4.1 独立Provider拆分**
- 将 `EastMoneyProvider` 中的新浪降级（`_fetch_sina_index_daily`）、同花顺降级（`_fetch_ths_industry_daily`）抽为独立类 `SinaProvider`、`THSProvider`，均实现 `BaseDataProvider` 接口。
- `EastMoneyProvider` 只保留东方财富主路径逻辑，降级逻辑移出。
- 验收：三个Provider独立可测，EastMoneyProvider不再包含sina/ths字样。

**4.2 DataProviderFactory优先级链**
- 新增 `DataProviderFactory`：维护有序Provider列表 `[EastMoneyProvider, SinaProvider, THSProvider]`，`fetch_kline`/`fetch_realtime` 按顺序尝试，第一个成功返回即停止，全部失败返回None。
- 每个Provider独立维护熔断状态（连续失败N次熔断M秒，半开探测），互不影响。
- 配置项 `DATA_PROVIDER_PRIORITY`（环境变量，逗号分隔，默认 `eastmoney,sina,ths`），可调整顺序或禁用某Provider。
- 验收：东方财富被限流时自动切新浪，日志记录 `[provider] eastmoney failed, fallback to sina`；新浪也失败切同花顺。

**4.3 Provider健康检查**
- 新增 `/api/v1/admin/providers/health`（管理员）返回各Provider状态：可用/熔断中/失败次数/最近成功时间。
- 后台每60秒对熔断中的Provider发一次探测请求（取一个固定标的的1根K线），成功则恢复。
- 验收：管理接口可查看Provider健康状态；熔断Provider自动恢复。

---

## 阶段五：AI流式稳定性与错误降级

**5.1 SSE心跳与超时保护**
- SSE流式接口每15秒发送注释行 `:keepalive\n\n`，防止Nginx `proxy_read_timeout`（默认60s）断开空闲连接。
- 三级超时：首字超时30秒（LLM未返回首个token）、单delta间隔超时15秒、总流式超时120秒；超时返回已生成内容+ `{"type":"done","truncated":true,"reason":"timeout"}`。
- 验收：LLM响应慢时连接不被Nginx断开；超时后前端收到部分内容而非空白。

**5.2 delta序号与断点续传**
- 每个SSE delta事件携带递增 `seq` 序号（`{"type":"delta","seq":42,"content":"..."}`）。
- 后端Redis缓存最近100条delta：`chat_delta:{conversation_id}`（List结构，TTL=600秒），新消息开始时清空旧缓存。
- 前端断线重连时带 `Last-Event-ID` 或 query `?last_seq=42`，后端从Redis读取seq>42的delta补发；缓存已过期则返回 `{"type":"resync","message_id":...}` 提示前端重新加载完整消息。
- 验收：流式输出中断网5秒，恢复后从断点继续，不重复不丢失。

**5.3 错误帧标准化**
- SSE错误事件统一格式 `{"type":"error","code":"RATE_LIMITED","message":"请求过于频繁，请30秒后重试","retryable":true,"retry_after":30}`。
- 错误码枚举：`NETWORK_ERROR`（网络错误，可重试）、`RATE_LIMITED`（限流，带retry_after）、`TOKEN_INVALID`（用户token无效）、`TOKEN_QUOTA`（余额不足）、`CONTENT_FILTERED`（内容违规，不可重试）、`PROVIDER_UNAVAILABLE`（服务端LLM不可用）、`TIMEOUT`（超时）。
- 验收：各类错误场景返回对应code和retryable，前端可区分处理。

**5.4 错误分级降级**
- LLM熔断时（`llm_service` circuit open）：不返回固定文案，而是返回"AI服务暂时不可用，已切换基础分析模式"+基于规则的技术指标状态描述（调用indicator_service取MACD/KDJ状态，生成"MACD金叉、KDJ超买，短期趋势偏多"等规则文案）。
- 用户token无效/余额不足：返回明确提示"您的DeepSeek API Key无效或余额不足，请检查配置"，不降级为服务端token（避免混淆费用归属）。
- 工具调用失败（行情/指标接口异常）：Agent继续执行，在输出中标注"行情数据暂时不可用，以下分析基于历史数据"。
- 验收：服务端LLM关闭时，AI对话仍返回基础技术分析；token错误有明确引导。

---

## 阶段六：AI记忆系统升级

**6.1 Embedding升级为ONNX MiniLM（int8量化版）**
- 替换 `HashEmbedding` 为 `MiniLMEmbedding`：加载 `all-MiniLM-L6-v2` ONNX **int8量化版**模型（约40MB，首次启动自动下载到本地models目录），384维语义向量，本地CPU推理（单条<5ms），无需外部API，保持记忆本地存储约束。
- 量化方案：ONNX Runtime int8动态量化，精度损失<1%（语义检索召回率几乎无差异），推理速度提升约40%，运行时内存占用约100-150MB（fp32版约200-300MB）。
- ChromaDB collection重建：新增迁移脚本，用新Embedding重新编码已有记忆（HashEmbedding的向量与MiniLM不兼容，需重建；记忆原文在 `memory_facts` 表保留，可重新向量化）。
- 配置项 `EMBEDDING_MODEL=minilm`（可选hash回退），`EMBEDDING_MODEL_PATH` 指定本地模型路径，`EMBEDDING_QUANTIZATION=int8`（默认int8，可选fp32完整版，机器性能够时切换）。
- 验收：记忆检索从字符匹配变为语义匹配（搜"左侧交易"能召回"逢低买入"相关记忆），检索延迟<30ms；模型文件≤50MB，启动后内存增量≤150MB。

**6.2 记忆分层与重要性**
- 短期记忆：最近10轮对话直接注入system prompt（不向量化），由 `chat_service` 从 `chat_messages` 取最近10轮。
- 长期记忆：ChromaDB向量检索TopK=5，注入system prompt。
- 记忆抽取时LLM返回重要性评分1-10（prompt中要求），存入 `memory_facts.importance`；检索排序按 `相似度×0.7 + 重要性×0.3` 加权。
- 记忆清理：重要性<3的记忆30天后自动删除（Celery定时任务，每日凌晨执行）；重要性≥3的永久保留。
- 验收：对话中AI能引用相关长期记忆；低重要性记忆自动过期。

**6.3 记忆去重合并**
- 新记忆写入前，与同用户已有记忆计算余弦相似度，>0.85时合并（更新已有记忆内容为较新表述，importance取最大值，不新增）。
- 验收：重复表达同一事实不产生多条记忆。

**6.4 记忆管理API**
- `GET /api/v1/memory/facts`：分页返回用户记忆列表（内容摘要、重要性、来源对话ID、创建时间），支持按重要性筛选。
- `DELETE /api/v1/memory/facts/{id}`：删除单条记忆（同步删ChromaDB向量+PG记录）。
- `DELETE /api/v1/memory/facts`：清空全部记忆（重建ChromaDB collection）。
- 验收：M区"记忆文件"可查看、删除记忆，删除后AI不再召回。

---

## 阶段七：多智能体可观测性增强

**7.1 节点输出实时SSE推送**
- LangGraph深度模式运行时，每个节点完成后通过SSE推送 `{"type":"agent_step","node":"technical","status":"done","summary":"MACD金叉...","duration_ms":2100}`。
- 节点开始时推送 `{"type":"agent_step","node":"bull_researcher","status":"running"}`。
- `agent_steps` 表已有，补充 `summary`（VARCHAR 500，节点输出摘要）和 `duration_ms` 字段（Alembic迁移）。
- 验收：深度分析时前端实时看到5个节点依次完成。

**7.2 节点失败降级**
- LangGraph各节点用try/except包裹，单节点失败不中断图：记录 `status='failed'`+错误信息到agent_steps，使用默认中性观点替代（如技术分析失败用"技术分析暂不可用，默认中性"），最终结论标注"部分节点异常，结论仅供参考"。
- 验收：模拟某节点抛异常，图仍能完成并返回结论，前端标注异常节点。

**7.3 运行历史API完善**
- `GET /api/v1/agent/runs?conversation_id=&page=&size=`：返回运行列表（id/conversation_id/symbol_id/final_decision/total_duration/created_at）。
- `GET /api/v1/agent/runs/{id}/steps`：返回某次运行的完整5节点输出（node/status/summary/content/duration_ms）。
- 验收：M区"运行记录"可列表、可查看详情。

---

## 阶段八：长会话上下文与策略生成可靠性

**8.1 滑动窗口与摘要压缩**
- `chat_service` 构建消息历史时：最近10轮完整取（user+assistant），第11轮起的早期对话用会话摘要替代。
- `conversations` 表新增 `summary TEXT` 字段；每满10轮，异步调用LLM生成/更新摘要（≤200字），存入 `conversations.summary`。
- 新会话加载时：有summary则注入 `{"role":"system","content":"之前对话摘要：..."}` + 最近10轮。
- 验收：50轮长对话token用量稳定（不随轮数线性增长），AI仍能记住早期关键信息。

**8.2 Token预算控制**
- 发送LLM前计算总token（system prompt + 工具描述 + 历史 + 当前问题），超过模型上限80%（DeepSeek-chat 64K×80%≈51K）时，自动减少完整轮数（10→8→6）并改用更多摘要，直到预算内。
- 响应头返回 `x-token-usage: {"prompt":...,"completion":...,"total":...}`，前端可展示。
- 验收：超长对话不触发LLM token limit错误。

**8.3 策略生成三级校验**
- 第一级：`ast.parse` 语法校验（已有）。
- 第二级：接口校验——检查 `initialize` 和 `on_bar` 函数存在、`on_bar` 参数签名为 `(ctx, bar)`、无顶层import。
- 第三级：沙箱dry-run——用1根模拟K线（构造OHLCV字典）在RestrictedPython沙箱中执行 `initialize()`+`on_bar()`，捕获运行时异常（NameError/IndexError/ZeroDivisionError等）。
- 校验结果返回前端：`{"valid":true}` 或 `{"valid":false,"errors":[{"line":12,"message":"name 'xxx' is not defined"}]}`。
- 验收：生成的策略代码100%通过语法和执行校验后才可保存/回测。

**8.4 生成失败自动重试**
- 校验失败时，将错误信息（行号+错误类型+消息）拼入prompt，要求LLM修复后重新生成，最多重试2次。
- 重试仍失败则返回用户："策略生成遇到问题，请尝试调整描述或基于模板创建"，并展示模板库入口。
- 验收：故意生成有语法错误的策略，系统自动修复并通过校验。

**8.5 策略模板库**
- 内置5个经过验证的策略模板（双均线交叉、MACD金叉死叉、KDJ超买超卖、布林带突破、成交量异动），模板代码存在数据库 `strategy_templates` 表（id/name/description/code/params_schema）。
- `GET /api/v1/strategy-templates` 返回模板列表；用户可"基于模板创建"，前端加载模板代码到编辑器，用户可修改参数后保存为自己的策略。
- 验收：5个模板均可直接回测通过；用户可基于模板修改保存。

**8.6 生成→回测一键流程**
- 策略生成并通过校验后，SSE流末尾推送 `{"type":"strategy_ready","strategy_id":...,"auto_backtest":true}`。
- 前端收到后自动调用 `POST /api/v1/backtest/tasks`（默认标的=当前选中标的，周期=1d，范围=近1年），轮询结果。
- 回测完成后在对话气泡下方内嵌展示结果卡片（胜率/盈亏比/最大回撤/年化收益+资金曲线缩略图）。
- 验收：描述策略想法→AI生成→自动回测→结果内嵌展示，全程无需手动切换页面。

**8.7 会话标题自动生成**
- 会话创建后第一条用户消息，异步调用LLM生成简短标题（≤15字），更新 `conversations.title`，通过SSE推送 `{"type":"title","title":"..."}` 通知前端。
- 验收：发送第一条消息后J区会话列表标题自动更新。

---

## 人工配置 / 日志说明（V0.2 第一波追加）

- 管理员：在 stock_backend/.env 配置 `ADMIN_USERNAMES=用户名1,用户名2`（逗号分隔），启动时自动置 is_admin=true；未配置时 /api/v1/admin/* 无管理员可用返回 403。
- WebSocket 实时推送：前端连 `ws://.../api/v1/ws/market?token=<JWT>`，交易时段价格由 realtime_poll 经 Redis pub/sub 推送（延迟≤5s）；Redis 未启动则 WS 仅心跳可用、行情走 HTTP 轮询。
- 全量目录同步：首次启动/重置库后由 entrypoint 自动触发（目录A股<4000）；也可 `POST /api/v1/admin/catalog/sync` 手动触发，或等每日凌晨3:00 beat（catalog_sync）。
- 关注添加自动同步：新增关注且无K线标的约10秒内由 kline_init 补齐K线，列表 sync_status 展示"同步中/已同步"（kline_init 失败标 failed 可重试）。
- Provider 熔断/健康：东方财富被限流自动切新浪/同花顺（日志 `[provider] eastmoney failed, fallback to ...`）；`GET /api/v1/admin/providers/health` 查看各源状态，beat 每60s 探测熔断源自动恢复。
- 缓存体系：K线/快照/搜索/关注列表均走 Redis（TTL 见 .env），Redis 不可用时自动降级直查 PostgreSQL；快照 data_age_seconds 供前端标注"数据时间"。
- 预同步脚本：`python scripts/presync_fixed_indices.py` 可手动触发固定指数/目录检查（幂等可重跑），容器启动已自动执行。
- 同步进度展示：行情页加载时调 `GET /api/v1/sync-status?scope=fixed_indices` 轮询"数据同步中（X/49）"（running 显示进度条，done 自动刷新；无记录返回 done 表示未触发预同步）。

## 人工配置 / 日志说明（V0.2 第三波追加）

- 数据库迁移：第三波新增 0006（agent_steps.summary/duration_ms/status + agent_runs.duration_ms）、0007（conversations.summary）、0008（strategy_templates 表 + 5 模板种子）。部署环境由 entrypoint 自动 `alembic upgrade head`，本地手动执行见 project_constraints_v0.2.md 迁移命令。
- 策略模板种子：`strategy_templates` 5 个模板（双均线/MACD/KDJ/布林带/成交量异动）随 0008 迁移幂等写入，无需额外手动种子；如需重置/重跑可 `alembic downgrade 0007 && alembic upgrade head`。
- 多智能体可观测：深度模式（诊断/交易计划/机会雷达）SSE 推送 `agent_step` 事件（running/done/failed 含 summary/耗时）；运行历史 `GET /api/v1/agent/runs?conversation_id=&page=&size=`、节点步骤 `GET /api/v1/agent/runs/{id}/steps`。
- Token 预算：`LLM_MAX_TOKENS`（默认 65536，DeepSeek-chat 64K）与 `TOKEN_BUDGET_RATIO`（默认 0.8）控制发送前估算，超预算自动降轮（20→16→12），估算用字符启发式（不引 tiktoken）。
- 策略生成校验+重试：`STRATEGY_GEN_MAX_RETRIES`（默认 2）控制校验失败重试次数；三级校验（语法/接口/沙箱 dry-run）全通过才保存/回测。
- 会话标题生成：`TITLE_WAIT_TIMEOUT`（默认 3 秒）控制 done 后等待标题生成的最长时间（best-effort，超时静默，标题仍会异步落库）。
- 长会话摘要：每满 10 轮（20 条消息）异步生成会话摘要（≤200 字）写入 conversations.summary，新会话加载注入「之前对话摘要」；依赖 Celery worker 常驻运行（异步任务在请求内 `asyncio.create_task`，无需额外队列）。

