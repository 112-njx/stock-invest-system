Agent的后端编码记录,你需要按照：
编码时间： 
编码内容（描述）：
的格式对该文档进行编写，要求编码内容简练而说明主要内容，
一次编写的编码内容描述在200字以内，如果超出字数而不能说明主要内容则新开一次编码记录。
每一次阶段下的细分任务都需要新开一次编码记录。

---
编码时间：2026-08-08
编码内容（描述）：阶段一1.1项目脚手架。在 stock_backend 建 FastAPI 分层工程 app/{api,services,repositories,schemas,models,core,utils,worker,data_providers}，router→service→repository 单向依赖。pydantic-settings 读 .env（DB/Redis/Celery/DeepSeek/同步间隔/TTL 均配置化禁硬编码）。全局异常处理+统一响应 {code,msg,data}；request-id 中间件+JSON 结构化日志（1.2 底座一并落地）。pyproject.toml+requirements.lock，ruff/black 规范。依赖安装 FastAPI/SQLAlchemy/Celery/Redis/akshare 等。验收：uvicorn 启动、/docs 200、/health 200，6 个 pytest 通过。

---
编码时间：2026-08-08
编码内容（描述）：阶段一1.3数据库接入。写全量 SQLAlchemy 声明式模型（app/models：users/symbols/kline_*/snapshot/fundamentals/etf_premiums/index_valuations/support_resistance/策略/回测/任务/agent 扩展等 24 表），统一命名约定、时间 UTC。Alembic 初始化并生成初始迁移 0001（内嵌 docs/sql 01+03 DDL，保留分区/触发器/默认分区），alembic upgrade head 成功，680 个分区子表就绪。连接池参数走配置（池大小/超时/回收）。封装 K 线按月分区工具 app/utils/kline_partition.py（幂等建分区+默认分区兜底）。验收：ORM 往返+幂等去重+分区扩容实测通过。

---
编码时间：2026-08-08
编码内容（描述）：阶段一1.4 DataProvider 抽象。app/data_providers 定义抽象基类（fetch_kline/fetch_realtime/resolve_index_code）+ 标的/快照 dataclass；实现 EastMoneyProvider（akshare）：个股/ETF/指数/行业指数四类K线（15m/1d/1w/1mon）、三类实时快照批量、行业指数 code 按名称回填（TTL 缓存）。借鉴 TradingAgents-CN 反爬方案：em_utils 补丁 requests.Session.request 走 curl_cffi chrome120 指纹+同域请求间隔；统一超时/指数退避重试/数据清洗（空值、异常价、高低矛盾剔除）。验收：实机拉取贵州茅台日K 22 根并幂等入库；6 个 mock 外部源单测通过。

---
编码时间：2026-08-08
编码内容（描述）：阶段一1.5行情同步任务(Celery+Beat)。app/worker 建 Celery 工程：三队列 sync/backtest/ai（task_routes 路由），beat 调度走配置（每日收盘后增量 + 实时轮询间隔）。任务 kline_init/kline_incremental/realtime_poll，显式 @celery_app.task 注册 + set_default 保证 broker 正确。repositories 层新增 kline/snapshot/ops/symbol 查询写入（分区 upsert 幂等、快照 upsert、sync_tasks/task_logs 状态记录）。同步服务链路：分区K线upsert→snapshot_realtime→Redis缓存(TTL)；A股交易时段自判。验收：beat 触发→worker 真实拉取贵州茅台 15m/1d/1w/1mon 入库（336/22/5/2 行）→sync_tasks/task_logs 更新，18 个单测通过。

---
编码时间：2026-08-08
编码内容（描述）：阶段一1.6种子数据。新增 scripts/seed_fixed_indices.py，执行 02_seed_fixed_indices.sql 幂等入库固定大盘(14)+行业(35)共49条指数（is_fixed_index+sort_order 驱动 G/H 区顺序，行业 code 留空待同步回填）。验收：symbols 含 49 条固定指数且顺序正确（1~14 大盘、15~49 行业），seed 可重复执行。

---
编码时间：2026-08-08
编码内容（描述）：阶段一1.7行情查询API。新增 GET /api/v1/symbols（type/search/is_fixed 过滤，供下拉与 G/H 固定列表）、/symbols/search（6位代码/名称联想，精确代码优先）、/kline（15m/1d/1w/1mon，区间/分页，代码或id解析）、/snapshot（批量实时快照，按类型合并 stock_fundamentals/etf_premiums/index_valuations 特殊字段）。新增 schemas/market.py 响应模型、services/market_service.py 查询服务、repositories/snapshot 查询扩展。统一响应 {code,msg,data}。验收：四接口实测返回正确（上证指数49条、茅台22根日K/336根15m、快照合并），api-docs.md 已补，7 个单测通过。

---
编码时间：2026-08-09
编码内容（描述）：阶段二2.1用户鉴权。新增 app/core/security.py（bcrypt哈希+JWT签发校验）、schemas/user.py、repositories/user_repo.py、services/auth_service.py（register/login 签发JWT）、api/v1/auth.py+users.py（/auth/register、/auth/login、/users/me GET+PUT）。deps.py 加 get_current_user（HTTPBearer→JWT→User）。配置加 JWT_SECRET_KEY/ALGORITHM/EXPIRE_MINUTES。依赖 bcrypt+PyJWT。验收：7 个 pytest 通过（登录拿token、受保护接口校验/拒绝）。

---
编码时间：2026-08-09
编码内容（描述）：阶段二2.2重点关注股票。user_repo.py 加 user_watchlist 读写（UNIQUE(user,symbol) 幂等）；user_service.py 加 add/list/delete（列表合并 snapshot 实时价：代码/名称/最新价/涨跌幅）；api/v1/watchlist.py（GET/POST /watchlist、DELETE /watchlist/{id}），代码或id解析，user_id 强制隔离。预留 sort_order/group_name 扩展位（表结构未加列，后续按需迁移）。验收：6 个 pytest 通过。

---
编码时间：2026-08-09
编码内容（描述）：阶段二2.3支撑/压力位。support_resistance 读写（user,symbol,type=support|pressure,price,note）；api/v1/support_resistance.py（GET 按 symbol_id 过滤、POST、DELETE /{sr_id}），K线图叠加横线数据源。预留 strength/test_count 扩展位，未来 AI 自动识别在 service 层加方法即可。验收：6 个 pytest 通过。

---
编码时间：2026-08-09
编码内容（描述）：阶段二2.4技术指标服务。app/services/indicators/ 建 BaseIndicator 抽象+MACD/KDJ/成交量/成交额（借鉴 TradingAgents-CN 指标接口；MACD 柱×2 同花顺惯例、KDJ 经典递推）；indicator_service.py 拉K线→计算→Redis 缓存（key 含 symbol+period+params+最新ts，新数据自动失效）；GET /api/v1/indicators 支持 names+params。验收：10 个 pytest 通过（公式对照手算参考）。
---
编码时间：2026-08-09
编码内容（描述）：阶段三3.1会话与消息。app/repositories/conversation_repo.py（conversations/chat_messages 读写，user_id 强制隔离防越权）；app/services/conversation_service.py（创建/列表/重命名/删除、追加消息严格校验标的、按会话拉取时间升序）；app/schemas/conversation.py；api/v1/conversations.py（POST/GET /conversations、PATCH/DELETE /{id}、POST/GET /{id}/messages），绑定标的 symbol_id 可选。消息 role 用 VARCHAR 不设枚举，预留工具调用等角色。验收：4 个 pytest 通过（多会话隔离、消息顺序正确、越权 404），api-docs.md 已补。

---
编码时间：2026-08-09
编码内容（描述）：阶段三3.2 LangChain LLM 封装。app/services/llm/：providers/base.py 定义 BaseLLMProvider 抽象（ainvoke/astream 统一接口，借鉴 TradingAgents-CN llm_adapters 多适配器架构）；providers/deepseek.py 用 ChatOpenAI+base_url 直连 DeepSeek（langchain-openai 1.x 无 ChatDeepSeek）；circuit_breaker.py 熔断器（CLOSED→OPEN→HALF_OPEN 半开探测）；llm_service.py 统一入口内置超时/指数退避重试（流式已出首字不重试防重复）/熔断/令牌桶限流/token统计/结构化审计日志，available 属性判 API Key 未配置走降级。pyproject/requirements.lock 增 langchain/langgraph/chromadb 等。验收：10 个 pytest（熔断状态机、限流、假 provider 重试/流式/降级）。

---
编码时间：2026-08-09
编码内容（描述）：阶段三3.3 LangChain 工具集+上下文组装+流式对话。app/agent/：tools/{market,indicator}.py 用 @tool 封装行情快照/K线/指标（详细 description，返回结构化 dict，按请求级 db 绑定）；prompts.py 系统提示模板（角色/数据规范禁止编造/风险提示）+四类卡片模板（诊断/计划/雷达/创建策略）；context.py 组装 system+记忆+历史+提问并结构化日志（验收：请求 LLM 前日志可见工具与完整上下文）；chat_service.py 流式对话（建/取会话→存用户消息→组装→create_agent(工具绑定)→SSE 事件 start/delta/tool_call/tool_result/done/error→存 assistant+agent_runs/agent_steps，LLM 不可用走降级文案）；api/v1/chat.py SSE 端点。agent_repo.py 增 agent_runs/agent_steps 读写。验收：7 个 pytest（工具、上下文顺序、SSE 事件、消息/run 落库、工具调用步骤、降级）。另修复测试误删真实 600519 数据事故，见 fixed.md。

---
编码时间：2026-08-09
编码内容（描述）：阶段三3.4本地记忆系统。app/agent/memory/：store.py 用 ChromaDB PersistentClient（进程内按路径缓存单例，避免丢未刷盘数据）+ 离线确定性 HashEmbedding（字符 n-gram 哈希 384 维，无需下载模型，满足本地 embedding，后续可换 ONNX MiniLM），写入过滤 None 元数据；记忆文件按 data/memory/{user_id}/{type}.md 人类可读追加（M 区可打开）。memory_service.py：LLM 抽取 prompt→结构化 JSON（content/type/importance，<5 分过滤噪音）→save_memory（写文件+向量化+memory_chunks/user_memory_files 登记，best-effort 不影响主链路）→retrieve_memory TopK 注入上下文；memory_tool 封装 search_memory Agent 工具。chat_service 集成：生成结束后 aextract_facts+save_memory；请求前 retrieve_memory 注入 context。配置加 MEMORY_DIR/CHROMA_DIR/MEMORY_TOP_K/MEMORY_IMPORTANCE_MIN。验收：4 个 pytest（事实解析、落库、检索命中、工具调用）。

---
编码时间：2026-08-09
编码内容（描述）：阶段三3.5策略生成。app/agent/strategy_gen.py 用 LangChain with_structured_output（Schema=StrategyOutput）按用户描述生成策略代码+JSON参数；约束回测接口 initialize/on_bar（借鉴 AgentQuant 自然语言→策略代码 + QuantDinger 模板化），输出含 strategy_name/description/code/params(entry/stop_loss/take_profit/position)/risk_warning；生成后 ast.parse 语法校验 + on_bar 存在性校验；preflight 熔断/限流保护。schemas/strategy.py 定义 StrategyOutput/StrategyParams。api/v1/strategies.py 加 POST /strategies/generate。验收：4 个 pytest（语法校验、结构化生成注入、不可用降级、API）。

---
编码时间：2026-08-09
编码内容（描述）：阶段三3.6交易策略CRUD。repositories/strategy_repo.py + services/strategy_service.py（保存/列表/详情/更新/删除，user_id 强制隔离）；api/v1/strategies.py 补 POST/GET /strategies、GET/PUT/DELETE /strategies/{id}（generate 端点声明在 {id} 之前避免路径冲突）。预留 version/tags/score 扩展位（表结构未加列，后续按需迁移）。验收：4 个 pytest（CRUD 全流程、越权 404、鉴权），api-docs.md 已补。

---
编码时间：2026-08-09
编码内容（描述）：阶段三3.7用户定制Agent CRUD。schemas/agent.py（AgentIn/AgentUpdateIn/AgentOut）；services/agent_service.py 内置三套官方预设模板（technical/fundamental/risk_control，借鉴 TradingAgents-CN 预设分析师角色，template 创建时填充 system_prompt/tools/llm_config/memory_config，用户显式字段优先）；api/v1/agents.py（POST/GET /agents、GET/PATCH/DELETE /{id}，启停走 status）；会话发送已按 agent_id 加载配置构造 Agent（chat_service._load_agent，3.3 已接线）。验收：4 个 pytest（模板创建/CRUD、越权 404、会话选用定制 system_prompt 生效），api-docs.md 已补。

---
编码时间：2026-08-09
编码内容（描述）：阶段三3.8多智能体编排（LangGraph）。app/agent/research_graph.py 借鉴 TradingAgents-CN trading_graph 组织架构：StateGraph 五节点 技术分析师→看多研究员→看空研究员→风控经理→交易决策者（诊断/交易计划/机会雷达走不同 trader 输出要求）；run_research_graph 预取行情快照+指标拼上下文注入各节点，astream(updates) 逐节点产出；chat_service 集成 DEEP_RUN_TYPES={diagnose,plan,radar} 走深度图（每节点落 agent_steps，SSE delta 带 node），其余走轻量 ReAct。验收：3 个 pytest（图节点顺序、深度聊天 agent_steps 五步可见、轻量模式仍走 ReAct），全库 94 个全绿。

---
编码时间：2026-08-09
编码内容（描述）：阶段四4.1回测引擎。app/backtest/：sandbox.py 用 RestrictedPython 编译策略代码（AST 禁 import + 危险内置 open/eval/exec/__import__ 编译期硬拒，安全内建 min/max/sum 等补充，守卫拦截 _ 开头属性）；engine.py 撮合引擎（BacktestConfig 初始资金/佣金万分之三/印花税卖出万分之五/撮合价 close|open/时间预算，BacktestContext 提供 params/cash/pos/price/history/closes/buy/sell/flat，initialize/on_bar 回调，T+1 当日买入次日可卖，自动止损止盈按 params stop_loss/take_profit pct 触发价成交，权益曲线+交易流水，逐 bar 时间预算）。验收：双均线策略跑出交易流水，沙箱 import/open/eval 拦截，T+1/止损/费用/超时正确，9 个 pytest。

---
编码时间：2026-08-09
编码内容（描述）：阶段四4.2指标计算。app/backtest/metrics.py：FIFO 买入-卖出配对算胜率/盈亏比，夏普用权益序列逐 bar 收益率按周期（15m/1d/1w/1mon）年化折算，年化收益按首末净值与时间跨度，最大回撤遍历峰值，metrics_json 扩展（总收益/交易数/佣金/持仓bar数/年化波动/最佳最差交易），无交易返回 None 不除零。验收：已知案例对照（胜率0.5/盈亏比1.0/回撤一致/夏普为正），6 个 pytest。

---
编码时间：2026-08-09
编码内容（描述）：阶段四4.3回测任务流（Celery）。Alembic 迁移 0002 给 backtest_tasks 加 period/start_ts/end_ts/fill_on（任务自包含）；repositories/backtest_repo.py（任务状态机+结果读写）；services/backtest_service.py（create_backtest 校验策略归属/标的后建任务并 .delay 入 backtest 队列；execute_backtest 拉K线→引擎→指标→结果+success 同事务写入→best-effort 转本地记忆 memory_chunks；业务错误 BacktestFatalError 不重试）；worker/tasks/backtest_tasks.py 指数退避重试（重试前回 queued，耗尽标 failed）+ task_logs 全链路日志。验收：6 个 pytest + 真实端到端（API→Redis→worker→结果）跑通。

---
编码时间：2026-08-09
编码内容（描述）：阶段四4.4回测API。app/api/v1/backtest.py + schemas/backtest.py：POST /backtest（异步发起，返回 task_id）、GET /backtest/tasks/{id}（状态轮询）、GET /backtest/tasks（按 strategy_id 过滤）、GET /backtest/results?strategy_id=（N 区与全景K线策略指标数据源）、GET /backtest/results/{id}（详情含 metrics_json），全部 user 隔离防越权。router.py 注册。验收：6 个 pytest（完整链路/无K线失败/越权404/鉴权/参数校验/任务列表），api-docs.md 已补，冒烟 scripts/smoke_phase4.py，全库 115 个全绿。

---
编码时间：2026-08-11
编码内容（描述）：阶段五5.1容器化。stock_backend/Dockerfile 多阶段（builder 用 requirements.lock 装依赖缓存层，runner 仅拷 site-packages + 非 root app 用户 + HEALTHCHECK curl /health）；docker-entrypoint.sh 启动入口：等 DB 就绪→alembic upgrade head→seed_fixed_indices（均幂等）→exec 主进程；项目根 .dockerignore（排除 .venv/data/tests/frontend）。deploy/docker-compose.yml 全栈编排 postgres/redis/api/worker/beat/nginx/prometheus/grafana：db/redis 仅内网不映射宿主端口，宿主端口经 .env.docker 按需映射（默认 127.0.0.1），worker --pool=solo 三队列、beat 定时，共享 backenddata 卷持久化记忆/chroma。docker compose config 校验通过。

---
编码时间：2026-08-11
编码内容（描述）：阶段五5.2 Nginx。deploy/nginx/nginx.conf 覆盖前端镜像默认模板（静态来自前端 build 产物）：基于前端版本增强 API 分级限流（limit_req_zone api_limit 30r/s 常规、ai_limit 5r/s 精确匹配 /api/v1/chat SSE 更严）、安全响应头（X-Frame-Options/X-Content-Type-Options/Referrer-Policy）、gzip、静态长缓存、SPA 回退、TLS 443 可选（证书挂载 /etc/nginx/certs 并注释块启用）。envsubst 只替换已定义环境变量，nginx 内置变量安全。

---
编码时间：2026-08-11
编码内容（描述）：阶段五5.3 CI/CD。.github/workflows/ci.yml：push/PR 触发 backend-test（PostgreSQL/Redis service 容器 → pip 装 requirements.lock → ruff check+format → alembic upgrade head → seed → pytest）→ docker-build（buildx 构建后端/前端镜像）→ deploy（workflow_dispatch 手动，SSH 占位，secrets 待配）。

---
编码时间：2026-08-11
编码内容（描述）：阶段五5.4监控告警。app/core/metrics.py 增 LLM 指标（llm_calls_total{status}/llm_request_duration_seconds{status}/llm_tokens_total{kind}），llm_service._log_call 埋点（成功/失败/token/耗时）；app/core/metrics_ext.py 平台 Gauge（celery_queue_depth/redis_cache_hit_rate/market_data_freshness_seconds/backtest_queued_tasks），/metrics 端点每次 scrape 先 refresh（Redis/DB 不可用静默跳过）；deploy/prometheus（scrape api:8000 + 告警：5xx>5%、回测队列>20、行情>5min、LLM失败率>10%）；deploy/grafana provisioning 数据源+9 图面板。验收：test_metrics_ext 3 个 pytest。

---
编码时间：2026-08-11
编码内容（描述）：阶段五5.5测试补齐 + 补前端缺失接口。补齐 GET /api/v1/agent/runs（运行历史）、/agent/runs/{id}（内嵌 agent_steps）、/memory/files（记忆文件）三接口：agent_repo 增 list_runs/get_run/list_memory_files，schemas 增 AgentRunOut/AgentStepOut/MemoryFileOut（path=validation_alias file_path），agent_service 透传，api/v1/agent_ops.py 注册，user 隔离 404/401。新增 test_agent_ops（3 个：列表详情/越权鉴权/记忆文件）、test_metrics_ext（2 个：metrics 暴露新指标/LLM 埋点）。全库 120 个 pytest 全绿，ruff 通过。

---
编码时间：2026-08-11
编码内容（描述）：阶段五5.6收尾检查。working_docs.md 末尾按模板补阶段五六要素自查（六项一句话结论）；api-docs.md 补 Agent 运行记录与记忆文件 API（3 接口）；roadmap.md 下方补人工配置/日志说明（docker 部署、端口、监控入口）；Agent_code.md 补 5.1~5.6 编码记录；fixed.md 补缺失接口与测试数据清理记录。

---
编码时间：2026-08-18
编码内容（描述）：行情数据获取修复（测试工程师）。① Alembic 0003 迁移 snapshot_realtime.volume/amount 改 nullable（海外指数无成交量存 NULL、前端显示"--"，区分"缺失"与"真实零"），upsert_snapshot 不再 _not_null 兜底 volume/amount；② 特殊字段纳入 run_realtime_poll 主链路：个股总市值/PE 取自 stock_zh_a_spot_em、ETF净值/溢价取自 fund_etf_spot_em（溢价=-折价率）、指数PE 新增 provider.fetch_index_pe（乐咕 stock_index_pe_lg 覆盖沪深300/上证50/中证1000），落 stock_fundamentals/etf_premiums/index_valuations；③ 行业指数匹配改通用评分模糊匹配（BK code优先→名称精确→剥离罗马后缀→前后缀差≤3且仅≥3字词→否定词惩罚，阈值75，不硬编码映射），35行业23个正确匹配、10个无对应板块诚实"--"；④ 行业指数基本数据用日K推导补全（昨收=前根close/OHLC/量/额/振幅）。全库 133 pytest 全绿，ruff 通过。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段四 4.1 独立Provider拆分。新浪/同花顺降级逻辑从 EastMoneyProvider 抽为独立 SinaProvider（A股指数日K stock_zh_index_daily）、THSProvider（行业板块日K stock_board_industry_index_ths），均实现 BaseDataProvider（can_fetch_kline 范围判定 + 探针标的）；EastMoneyProvider 移除 sina/ths 字样与降级分支。base.py 统一 _call 重试封装（raise_on_giveup 抛 ProviderError 供熔断识别）、to_float/unavailable_quote 共享 helper。验收：三 Provider 独立可测（6 单测），EastMoney 无 sina/ths 引用。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段四 4.2 DataProviderFactory 优先级链+熔断。重写 factory.py：有序链 [eastmoney,sina,ths]（DATA_PROVIDER_PRIORITY 配置，可调序/禁用），每 Provider 独立 ProviderCircuit（连续失败N次熔断M秒、半开探测），scope 过滤跳过不适用 Provider；fetch_realtime 全失败返回对齐 unavailable 快照保 zip 契约；resolve_index_code/fetch_index_pe/fetch_catalog/search_ak_stock best-effort 委托。get_provider() 返回工厂单例，业务调用方式不变。验收：优先级/降级/熔断/半开恢复/健康 13 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段四 4.3 Provider 健康检查。Alembic 0004 users.is_admin；deps.get_current_admin 403 鉴权；GET /api/v1/admin/providers/health 返回各 Provider 状态/失败数/最近成功/冷却剩余；beat provider_probe 每60s 探测熔断 Provider（固定标的1根日K）成功恢复；ADMIN_USERNAMES 启动自动置 is_admin。验收：管理端点鉴权+状态返回 3 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段一 1.1 启动预同步+预热。Alembic 0004 新增 sync_status 表（scope/target_id/status/progress/total/message/started_at/finished_at）；docker-entrypoint 增加 presync_fixed_indices.py（检查49固定指数最新日K>1天或无→发 kline_init_fixed_indices 任务，进度写 sync_status X/49）；FastAPI lifespan 预热固定指数最近500根日K+最新快照写 Redis（APP_ENV=test 跳过）；sync_fixed_indices.py 保留手动脚本。验收：预同步触发/跳过、sync_status 落库、预热写缓存 6 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段一 1.2 K线Redis缓存。market_service.get_kline 默认区间（未显式 start/end/offset）走"最近N根"缓存 key=kline:{symbol_id}:{period}:{limit}（TTL 300），未命中查 PG 回写；缓存击穿 SET kline_lock NX EX 5 分布式锁（未获锁等待2s读缓存）；sync_service._write_bars 新K线写入后 scan 失效该标的所有周期缓存并推送末根；kline_repo.latest_bars 取最近N根升序。验收：二次命中/显式区间绕过/失效/锁互斥 4 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段一 1.3 快照缓存增强。SNAPSHOT_CACHE_TTL 5→300；market_cache.snapshot_to_cache_dict 缓存完整14字段；get_snapshots 改 Redis MGET→PG 兜底→回写，附带 data_age_seconds（naive DB 时间戳 as_utc 归一）；realtime_poll 写快照后 SETEX 300 覆盖 + 发布 WS。验收：全字段缓存/数据龄/二次命中 3 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段一 1.4 指标缓存优化。原缓存键含默认 start/end（按 now 计算致命中率≈0），改为默认区间键 indicator:{symbol_id}:{period}:{names}:{params_hash}:{latest_ts}（latest_ts 新K线自动失效），显式区间追加区间参数防串键。验收：默认键稳定/显式含区间/重复计算一致 3 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段三 3.1 全量标的目录预同步。Alembic 0004 symbols.is_catalog+(is_catalog,type)索引；EastMoneyProvider.fetch_catalog（stock_info_a_code_name 全A股 + fund_etf_spot_em ETF），symbol_repo.upsert_catalog_symbols 幂等（新 is_catalog=True、已存在保留）；catalog_sync Celery 任务（autoretry 3次退避，数量校验 A股≥4800/ETF≥500 不达标 partial 1h 后重试），beat 每日凌晨3:00；启动 maybe_catalog_sync <4000 触发；POST /api/v1/admin/catalog/sync 手动触发；完成后失效 search:*。验收：upsert/幂等/启动触发/管理端点 5 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段三 3.2 搜索三层增强。search_symbols 三层：精确代码→目录模糊（code LIKE q% / name LIKE %q%，按 is_catalog+code 排序 已同步优先）→外部回退（akshare 实时过滤入库+重查）；结果缓存 search:{type}:{keyword} TTL 3600；返回 is_catalog/has_kline（SymbolSearchOut，kline_1d 存在判定）；端点加 type/limit 参数。验收：精确优先/已同步优先/缓存/外部回退 5 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段三 3.3 关注添加自动同步。POST /watchlist 新增记录且标的无K线→置 sync_status=pending + 异步 kline_init（仅该标的）立即返回；已有K线置 done+last_synced_at；kline_init 任务内 _mark_watchlist_synced 回写 done/failed（user_repo.update_watchlist_sync_status）；WatchlistOut 增 sync_status/last_synced_at。验收：新股触发任务/已同步直接 done 2 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段三 3.4 关注列表Redis缓存。list_watchlist Redis watchlist:{user_id}→PG→回写（TTL 300，批量快照一次查询免 N+1），增删 DEL；/snapshot 带有效 token 且请求集⊆关注集时按 watchlist_snap:{user_id} 缓存（交易时段10s/非交易300s，get_current_user_optional 可选鉴权）。验收：二次命中/删除失效/关注集快照缓存 3 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段二 2.1 WS连接管理。app/ws/manager.py ConnectionManager 单例（user_id→多连接列表支持多标签页，subscribe 集合，broadcast_snapshots/kline 按订阅过滤）；app/api/v1/ws_market.py WS /api/v1/ws/market query token 鉴权（无效 4001 拒绝）；心跳每15s ping，30s 无消息（含pong）断开。验收：鉴权拒绝/心跳/订阅记录/管理器过滤 6 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段二 2.2 订阅模型与增量推送。realtime_poll 写快照后 app/ws/publisher.publish_snapshot 发 Redis pub/sub market:updates；_write_bars 新K线发布 publish_kline 末根；API 进程 lifespan 启动市场监听线程订阅转发到订阅连接（broadcast_snapshots 对比订阅集，仅推有更新的标的）；消息格式 {"type":"snapshot","data":{symbol_id:{price,change_pct,...}}} / {"type":"kline",...}。验收：广播过滤/末根推送 2 单测。

---
编码时间：2026-08-20
编码内容（描述）：V0.2 阶段二 2.3 断线重连与增量补拉。客户端重连后发 {"action":"sync","since":"ISO"}，snapshot_repo.get_updated_after 查该时间后更新的快照（naive UTC 归一）批量返回订阅范围内标的，补齐断线缺口；重连退避与 HTTP 轮询降级为前端行为，后端提供 sync 动作即可。验收：补拉批量返回 1 单测。

## v0.2
---
编码时间：2026-08-21
编码内容（描述）：补齐 sync-status 查询端点（V0.2 1.1 缺口修复）。project_constraints.md 4.5 声明 GET /api/v1/sync-status?scope=fixed_indices 已完成但实际未注册路由（阶段一 1.1 漏了对外 API）。新增 ops_repo.get_latest_sync_status(scope) 取最新一条，market.py 增公开端点 GET /api/v1/sync-status?scope= 返回 {status/progress/total/message}，无记录返回 done/100/0 供前端判定无进行中同步；scope 支持 fixed_indices/catalog/watchlist。验收：market_api 增 2 单测（无记录默认/有记录返回最新），全库 190 pytest 全绿 + ruff 通过。api-docs.md 已补。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段五 5.1 SSE心跳与三级超时。config.py 增 SSE_KEEPALIVE_INTERVAL/FIRST_TOKEN_TIMEOUT/INTER_DELTA_TIMEOUT/TOTAL_TIMEOUT/DELTA_CACHE_* 配置。chat_service.stream_chat 用 _stream_with_timeouts 包装 Agent 事件流（首字30s/单delta15s/总120s，asyncio.wait_for 逐事件超时），超时保存已生成内容+返回 {"type":"done","truncated":true,"reason":"timeout"} 且 run 标 failed/error=timeout。chat.py event_source 改 asyncio.Queue+后台 keeper 每15s发 :keepalive 注释行（避免 wait_for 取消在途生成）。验收：新增 3 单测（超时截断/正常透传/keepalive），全库 193 pytest 全绿。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段五 5.2 delta序号与断点续传。新增 app/agent/sse.py（chat_delta:{conv} List 缓存最近100条 delta TTL600s + chat_done:{conv} done 标记 + clear/cache/read 函数，异常降级）。chat_service._stream_with_timeouts 给每个 delta 加递增 seq 并 cache_delta、done 事件 cache_done；stream_chat 新消息开始 clear_delta_cache。chat.py 增 GET /api/v1/chat/resume?conversation_id&last_seq（校验会话归属后从 Redis 补发 seq>last_seq 的 delta，缓存过期返回 {"type":"resync"}）。验收：新增 5 单测（缓存往返/过期/done/resume补发不重复/越权404），全库 198 pytest 全绿。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段五 5.3 错误帧标准化。sse.py 增 ErrorCode 枚举（NETWORK_ERROR/RATE_LIMITED/TOKEN_INVALID/TOKEN_QUOTA/CONTENT_FILTERED/PROVIDER_UNAVAILABLE/TIMEOUT）+ build_error_event 统一 {"type":"error","code","message","retryable","retry_after"?}。llm_service 增 LLMAuthError/Quota/ContentFiltered/Timeout 子类 + _classify_provider_error（沿异常链查 status_code/文本归类，鉴权402等不可重试不空转）+ classify_llm_error 映射错误帧。chat_service _yield_failure 改收异常生成标准化 error 帧（call site 传 e 而非 str(e)），stream_chat preflight 包 try/except 兜底熔断/限流。验收：新增 8 单测（类型/可重试/状态码/消息分类/流式错误帧），全库 204 pytest 全绿。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段五 5.4 错误分级降级。chat_service 增 _rule_based_analysis（熔断降级用 indicator_service 取 MACD/KDJ 生成"MACD金叉、KDJ超买，短期趋势偏多"规则文案，无数据/异常优雅降级）+ _degraded_text（按错误码分级：TOKEN_INVALID/QUOTA 返回"您的DeepSeek API Key无效或余额不足"、PROVIDER_UNAVAILABLE 返回"已切换基础分析模式"+规则文案、CONTENT_FILTERED/其他走原文案）。_yield_failure 与 not available 降级路径改走 _degraded_text（token 错误不再降级为服务端 token）。prompts.py 数据规范补工具失败标注语（"行情数据暂时不可用，以下分析基于历史数据"）。验收：新增 6 单测（规则文案格式/无标的/token文案/熔断走规则/系统提示标注），全库 210 pytest 全绿。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段六 6.1 Embedding升级ONNX MiniLM int8。新增 app/agent/memory/embedding.py：HashEmbedding 移入（kind=hash）+ MiniLMEmbedding（kind=minilm，加载 paraphrase-multilingual-MiniLM-L12-v2 int8 量化 ONNX，urllib 直连 HF 下载到 data/models，mean pooling+L2 归一 384 维，本地 CPU 推理）+ get_embedding 工厂（按 EMBEDDING_MODEL 选择，minilm 加载失败自动回退 hash）。store.py 改 collection 按 embedding kind 隔离 collection 名（hash 保持 user_memory_{id} 兼容旧数据，minilm 加 _minilm 后缀）+ update_chunk/delete_collection。config.py 增 EMBEDDING_MODEL/MODEL_NAME/MODEL_PATH/QUANTIZATION/DIM/MAX_LENGTH。新增 scripts/rebuild_embeddings.py（hash→minilm 重建）。conftest 强制 hash（测试不下载模型）。pyproject 显式声明 onnxruntime/tokenizers。验收：新增 6 单测（hash归一确定性/minilm池化归一/量化文件名/工厂hash/加载失败回退/collection隔离），全库 216 pytest 全绿。注：roadmap 6.1 原 all-MiniLM-L6-v2 英文模型中文语义失效，经确认改用多语言 MiniLM-L12（118MB 放宽≤50MB）。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段六 6.2 记忆分层与重要性。Alembic 0005 迁移 memory_chunks 加 importance 列（默认5）。MemoryChunk 模型+agent_repo.add_memory_chunk 加 importance；save_memory 写 importance 入 PG+Chroma meta。store.search 改加权检索（多取候选 k*3 后按 相似度×0.7+重要性×0.3 重排，_weighted_score）。新增 memory_service.cleanup_expired_memories（删 importance<3 且>30天，PG+Chroma 同步）+ ai_tasks.memory_cleanup 任务 + beat 每日4:00。短期记忆（最近10轮=MAX_HISTORY20）与长期记忆（TopK5 注入）原已具备，补注释明确。验收：新增 3 单测（加权分数/importance落库检索/低重要性清理），全库 219 pytest 全绿 + ruff。注：抽取仍按 MEMORY_IMPORTANCE_MIN=5 过滤，importance<3 清理为前向安全网。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段六 6.3 记忆去重合并。store.py 增 embed_text（单条向量化）+ find_duplicate（get 全量 chunks 的 embeddings，用归一向量点积算余弦相似度，>0.85 返回最相似 chunk）+ _to_list（ChromaDB list/numpy 统一）；agent_repo 增 get/update_memory_chunk_by_vector。save_memory 写入前先 find_duplicate，命中则 store.update_chunk（重嵌入）+ update_memory_chunk_by_vector（内容取较新、importance 取最大）+ 记忆文件追加"合并更新"，不新增；未命中走原新增。验收：新增 1 单测（同事实二次保存合并为1条、importance取最大9），全库 220 pytest 全绿 + ruff。

---
编码时间：2026-08-22
编码内容（描述）：V0.2 阶段六 6.4 记忆管理API。新增 app/api/v1/memory.py：GET /api/v1/memory/facts（分页 page/size + importance_min 筛选，返回 content/importance/source_type/source_id(对话ID)/created_at）、DELETE /facts/{id}（同步删 ChromaDB 向量+PG，404 兜底）、DELETE /facts（清空=delete_collection+删 memory_chunks/user_memory_files+rmtree 记忆目录）。agent_repo 增 list/count/get/delete_all memory_chunks + delete_all_memory_files；memory_service 增 list_facts/delete_fact/clear_all_facts；schemas 增 MemoryFactOut。chat_service 记忆抽取改传 source_id=conv.id 存"来源对话ID"，抽取后 yield {"type":"memory_saved","summary","importance"}（done 前）。router 注册 memory。验收：新增 4 单测（列表/筛选/删除/清空/鉴权 + memory_saved 事件），全库 223 pytest 全绿 + ruff。api-docs.md 已补 3 端点。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段七 7.1 节点输出实时SSE推送。Alembic 0006 给 agent_steps 加 summary/duration_ms/status、agent_runs 加 duration_ms。research_graph 改用 astream_events 逐节点 yield running/done（含 summary 摘要+耗时），chat_service._run_deep 消费并 push agent_step SSE 事件 + add_step 落库新字段 + finish_run 记 run 总耗时；_stream_with_timeouts 让 agent_step 事件不消耗首字超时预算。验收：5 节点 running/done 依次推送、steps 落库含 summary/耗时，全库 223 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段七 7.2 节点失败降级。research_graph._make_node 用 try/except 包裹 LLM 调用，单节点失败返回默认中性观点（_NEUTRAL_TEXT）+ ResearchState 增 failed_nodes（add reducer）/node_errors（dict merge）记录失败节点与错误；run_research_graph yield status=failed + error。chat_service._run_deep 收集 failed_nodes，add_step 记 status=failed/meta.error，最终结论追加"（部分节点异常，结论仅供参考）"、run.error 标记、done 事件带 partial=true，run 仍 success。验收：模拟 technical 节点抛异常，图完成且失败节点标 failed，全库 225 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段七 7.3 运行历史API完善。agent_repo.list_runs 增 conversation_id 筛选+分页 offset/limit、新增 count_runs；agent_service.list_runs 返回 (rows,total)；schemas/agent.py AgentRunOut 增 final_decision(validation_alias=output)/total_duration(=duration_ms)、AgentStepOut 增 node(=step_name)/status/summary/duration_ms；api/v1/agent_ops.py GET /agent/runs 改分页信封 {items,total,page,size}+conversation_id 筛选，新增 GET /agent/runs/{id}/steps（node/status/summary/content/duration_ms），保留 /{id} 详情。验收：列表/详情/筛选/分页/越权/鉴权 + steps 端点，全库 226 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段八 8.1 滑动窗口与摘要压缩。Alembic 0007 给 conversations 加 summary TEXT；conversation_repo 增 update_summary/count_messages（update_title 供 8.7 预留）。chat_service 增 _assemble_history（最近10轮完整+摘要系统消息替代早期）、_generate_conversation_summary（异步 LLM 压缩早期轮次≤200字写 summary，独立 DB 会话，best-effort）、_schedule_summary_update（asyncio.create_task 不阻塞）；stream_chat 构建历史注入摘要、每满10轮（消息数%20==0）触发异步摘要。验收：摘要注入/生成落库/仅摘要早期轮次，全库 228 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段八 8.2 Token预算控制。新增 app/agent/token_budget.py：estimate_tokens（CJK 1字/token、其余4字符/token 字符启发式，不引 tiktoken）、estimate_messages_tokens（含每条+4协议开销）、fit_window_to_budget（超 max_tokens×0.8 逐级降轮 20→16→12）。config 增 LLM_MAX_TOKENS=65536/TOKEN_BUDGET_RATIO=0.8。chat_service 组装前估算工具描述 token+裁剪窗口，_run_react/_run_deep 末尾 push {"type":"usage","prompt","completion","total"}（done 前）。验收：超长历史降轮、usage 事件含三字段且在 done 前，全库 234 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段八 8.3 策略生成三级校验。新增 app/agent/strategy_validator.py：一级 ast.parse 语法（含行号）、二级接口（initialize/on_bar 存在、on_bar 参数个数=2、禁顶层 import）、三级沙箱 dry-run（compile_strategy+_DryRunContext 用 1 根模拟 K 线执行 initialize+on_bar，traceback 提取异常行号，捕获 NameError/IndexError/ZeroDivisionError）。返回 {"valid","errors":[{"line","message"}]}。注：roadmap 写 on_bar 签名"(ctx,bar)"与引擎实际 (bar,context) 不符，按引擎位置调用只校验参数个数。验收：9 单测（好码/语法/缺函数/签名/import/三类运行时异常+行号），全库 243 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段八 8.4 生成失败自动重试。重写 strategy_gen.generate_strategy：接入 8.3 三级校验（validate_strategy 替代原 _validate_code 粗校验），校验失败把错误信息（行号+类型+消息）拼回 prompt 要求修复重生成完整策略，最多重试 STRATEGY_GEN_MAX_RETRIES=2 次，仍失败抛 LLMError("策略生成遇到问题，请尝试调整描述或基于模板创建")。config 增 STRATEGY_GEN_MAX_RETRIES。验收：坏码首轮→重试成功且重试 prompt 含校验错误、耗尽重试抛模板库提示，全库 242 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段八 8.5 策略模板库。Alembic 0008 建 strategy_templates 表 + 5 个按本项目 initialize/on_bar 沙箱接口编写的已验证模板（双均线/MACD/KDJ/布林带/成交量异动，幂等种子）。模型 StrategyTemplate、repo list/get、service list_templates/get_template(404)、schemas 列表项（不含 code）/详情（含 code）、api/v1/strategy_templates.py 两端点、router 注册。修正：模板 helper 函数名不能以下划线开头（RestrictedPython 拒绝 _ema/_k_value）。验收：5 模板均通过三级校验+真实回测、列表不含 code、详情含 code、鉴权/404，全库 246 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段八 8.6 生成→回测一键流程。chat_service 增 _run_strategy：run_type="strategy" 走 generate_strategy（8.3/8.4 校验+重试）→ strategy_service.create_strategy 保存 → delta 输出代码 → 末尾 push {"type":"strategy_ready","strategy_id","auto_backtest":true}；LLMError 走友好提示（含模板库入口）。stream_chat 增 strategy 分支（绕过流式超时，keepalive 由 API 层保证）。同时修复 7.1 偶发 bug：research_graph 由 astream_events 改为 astream(stream_mode="updates")，避免高负载下 on_chain_end 乱序导致 agent_steps 逆序落库（全库复测 6 次稳定）。验收：strategy_ready 含有效 strategy_id 且策略已保存可回测、失败提示，全库 248 pytest 全绿 + ruff。

---
编码时间：2026-08-23
编码内容（描述）：V0.2 阶段八 8.7 会话标题自动生成。chat_service 增 _TITLE_PROMPT/_generate_conversation_title（异步 LLM 生成≤15字标题，更新 conversations.title，始终在 finally 向队列放结果/哨兵避免空等）/ _schedule_title_update；stream_chat 首条消息（count_messages==1）且 llm 可用时 create_task 触发，done 后 wait_for(TITLE_WAIT_TIMEOUT=3s) 从队列取 title 事件 push {"type":"title","title","conversation_id"}（失败/超时静默）。config 增 TITLE_WAIT_TIMEOUT。验收：首条消息生成标题并 push title 事件+落库、第二条不触发、无 3s 空等，全库 250 pytest 全绿 + ruff。

---
编码时间：2026-08-26
编码内容（描述）：修复第一波实时快照大面积缺失。①降频规避限流：REALTIME_POLL_INTERVAL 默认 5→15（config.py/.env/.env.example 三处），降低东财风控触发概率。②新浪实时降级源：SinaProvider 实现 fetch_realtime（A股 stock_zh_a_spot + 指数 stock_zh_index_spot_sina，代码去 sh/sz 前缀匹配），can_fetch_realtime=True、can_fetch_realtime_type 限 stock/index。③同花顺实时降级源：THSProvider 实现 fetch_realtime（行业一览表 stock_board_industry_summary_ths，均价近似现价+涨跌幅/量/额）+ resolve_index_code（stock_board_industry_name_ths 名称→881xxx 板块代码，TTL 缓存），can_fetch_realtime=True。④base.py 增 can_fetch_realtime_type 默认委托。验收：sina/ths 实时与回填 4 单测。

---
编码时间：2026-08-26
编码内容（描述）：修复实时快照缺失（续）。⑤工厂按资产类型路由：factory.fetch_realtime 重写为按 asset_type 分组逐类型走优先级链（首个含 available 结果即采用，全 unavailable/异常/熔断降级），使 sina(股票+指数)+ths(行业) 在东财限流时分别兜底而非整批截断；_provider_params 识别 BK/881 前缀（同花顺行业代码）避免回填破坏行业路由。⑥K线推导兜底：sync_service 增 derive_snapshot_from_kline（最新日K收盘推导全字段，updated_at=K线时间标注 data_age_seconds）；run_realtime_poll 对 unavailable 标生成兜底快照；run_fixed_indices_sync 同步K线后直接生成快照（预同步完成即有空快照）。⑦一次性接口 POST /api/v1/fetch-all 免鉴权同步执行全量同步。验收：全库 257 pytest 全绿 + ruff，api-docs 已补。

---
编码时间：2026-08-26
编码内容（描述）：修复运行记录耗时全为 null 的 bug（审计发现问题2）。根因：agent_runs.duration_ms 仅深度模式 _run_deep 写入，其余路径（ReAct/strategy/失败/降级/超时）不写，落库 NULL，前端 total_duration 显示"--"。修复：stream_chat 创建 run 后记 run._started_monotonic，_save_result 在 duration_ms 未显式传入时按该起始时间统一计算（覆盖所有路径）；同步移除 _run_deep 局部耗时计算以统一「run 创建→结束」口径。验收：新增 2 测试（ReAct 成功路径 + 失败路径均写非空 duration_ms），全库 259 pytest 全绿 + ruff。

---

编码时间：2026-08-26
编码内容（描述）：修复策略生成 LLM 400（This response_format type is unavailable now）。根因：strategy_gen.generate_strategy 调 with_structured_output(StrategyOutput) 用 langchain-openai 1.x 默认 method="json_schema"（发 response_format={"type":"json_schema"}），DeepSeek 仅支持 text/json_object、不支持 json_schema 故 400。修复：显式传 method="function_calling"（改走 tools+tool_choice，DeepSeek 原生支持，schema 字段经 tool JSON Schema 传给模型）。验收：test_strategies 7 通过 + test_chat 28 通过。

---

编码时间：2026-08-27
编码内容（描述）：修复 LLM 非流式输出（审计 bug2）。根因：chat_service._run_react 用 create_agent().astream(stream_mode="updates") 节点级输出，整条 AI 消息作单个 delta 一次性推送，LLM 生成期间前端无任何输出、完成后整段蹦出。修复：改 stream_mode="messages" token 级流式，逐 token 产出 delta；用 isinstance(chunk, AIMessage) 兜住 AIMessageChunk.type="AIMessageChunk"（非 "ai"）的坑；tool_calls/tool_call_chunks 与 ToolMessage 分别转 tool_call/tool_result 事件；新增 _merge_tool_call_chunks/_flush_tool_call_buf/_tool_call_event 合并流式工具调用，删除废弃 _emit_update。验收：流式模型经 _run_react 逐 token 产出 4 个 delta，全库 259 pytest 全绿 + ruff。

---

编码时间：2026-08-27
编码内容（描述）：审计修复 策略生成偶发失败（重试耗尽抛「策略生成遇到问题」）。根因：LLM 生成代码违反沙箱约束——RestrictedPython 禁属性增强赋值（context.pos += 1 编译失败「Augmented assignment of attributes is not allowed」）、给只读属性 context.closes 赋值（property 无 setter 报 AttributeError），三级校验拒后重试 2 次仍失败。修复：strategy_gen._GENERATE_PROMPT 增「沙箱约束」段明示红线（禁增强赋值、closes/is_holding 只读禁赋值、仓位仅 buy/sell/flat、自定义状态仅 initialize），接口文档补 closes/is_holding 只读说明。验收：全库 261 pytest 全绿 + ruff。

---

编码时间：2026-08-27
编码内容（描述）：审计修复 深度模式多空分析非流式（问题3）。根因：research_graph 节点用 model.ainvoke 单次取整段，astream(stream_mode="updates") 仅节点级，每步分析一次性吐出。修复：节点改 _stream_llm_text 用 model.astream 逐 token + get_stream_writer 推带 node 的 delta；run_research_graph 改 stream_mode=["updates","custom"] 透传 token delta 与节点 done（保持顺序确定性）；chat_service._run_deep 转发 token delta（{"type":"delta","node"}）并移除原节点级整段 delta。测试 _RoleModel 补 astream。验收：全库 261 pytest 全绿 + ruff。

---

编码时间：2026-08-27
编码内容（描述）：审计修复 策略生成无流式反馈（问题3 方案A）。根因：_run_strategy 单次 ainvoke 生成（含三级校验重试）期间零 SSE 输出，前端空白等待、完成后代码整段蹦出。方案A（低风险，保留结构化输出不做逐字）：生成前 yield 一条进度 delta「正在生成策略代码，请稍候…」，让流式气泡从「AI 思考中…」变为有反馈。验收：全库 261 pytest 全绿 + ruff。

---
编码时间：2026-09-04
编码内容（描述）：修复多源 Provider 与 akshare1.18.83 不匹配致降级链打穿。eastmoney._fetch_min_kline 行业分支移除 stock_board_industry_hist_min_em 不支持的 start_date/end_date（该接口仅收 symbol/period，取近期全量后按 start<=ts<=end 过滤）；sina.fetch_kline 日期列改用 _pick_col 兼容 date/日期、缺列返回空，消除 row["date"] KeyError；ths 新增 _resolve_board_name，fetch_kline 前用 _industry_score 归一化板块名（半导体设备→半导体，无匹配返回空），规避 akshare 内部 code_map KeyError。验收：三 provider 正常导入、归一化离线用例通过。

---
编码时间：2026-09-04
编码内容（描述）：修复 api/worker/beat 并发迁移竞态。docker-compose.dev.yml 抽 x-backend-env 公共锚点，仅 api 置 RUN_MIGRATIONS=1 单点执行 alembic upgrade+seed+presync；新增 scripts/wait_for_migrations.py（轮询 alembic_version==head 0008，最长120s）；docker-entrypoint.sh 按 RUN_MIGRATIONS 分流，worker/beat 只等 DB 与迁移完成再启动。消除并发建表撞 pg_type_typname_nsp_index、presync 重复出两个 task_id。验收：compose config 通过，日志仅 api 迁移、worker/beat 打印 migrations ready 后启动。

---
编码时间：2026-09-04
编码内容（描述）：新增容器种子数据引导 deploy/seed_from_local.py。宿主 psycopg2 读本机 PG18、经 docker exec -i psql 写容器 PG16（绕开 pg_dump 版本差）；以容器表为准自动发现普通表/分区子表（排除分区父表与 alembic_version），等迁移就绪、users 非空即跳过（幂等，--force 覆盖），导入前 stop worker/beat 防并发写，TRUNCATE RESTART IDENTITY CASCADE 后逐表 CSV COPY，DO 块 setval 对齐全部自增序列到 max(id)，finally 恢复容器。验收：导入362表 users=13/symbols=52，nextval 不撞主键。

---
编码时间：2026-09-04
编码内容（描述）：start-dev.bat 集成种子引导为 [4/4] 步：up -d --build 后检测后端 venv，存在则调 stock_backend\.venv\Scripts\python.exe deploy\seed_from_local.py，无 venv 则跳过。保持文件原 UTF-8/CRLF 编码与既有字节（历史中文转码已损坏，仅插入纯 ASCII 行避免乱码复发），步骤号 [1/3]~[3/3] 同步改为 /4。验收：双击一键启动后自动引导，重复运行命中”种子数据已存在，跳过”，前端行情页打开即有重点关注/K线/指数快照。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道A G01——CORS 白名单修正+Cookie 安全+Nginx 安全响应头+HTTPS 重定向机制。main.py CORS 从 allow_origins=[“*”] 改为环境变量 CORS_ORIGINS 逗号分隔白名单（空值安全降级禁凭证）；config.py 新增 CORS_ORIGINS/COOKIE_SECURE/COOKIE_SAMESITE/ACCESS_TOKEN_COOKIE_NAME 四项配置；security.py 新增 set_access_token_cookie/clear_access_token_cookie 工具函数（为 G19 预留）；nginx.conf 补充 HSTS/CSP/X-Frame-Options DENY/nosniff/Referrer-Policy 五项安全响应头+$ssl_redirect 环境变量控制 80→443 重定向+443 TLS 完整配置（注释待启用）；前端 http.ts 加 withCredentials=true+TODO(G19) 标记；user.ts 四处 localStorage 操作加 TODO(G19) 标记；.env.example/.env.docker.example/docker-compose.yml/docker-compose.dev.yml 同步新增环境变量。测试 test_g01_security.py 9 项全绿（CORS 白名单/拒绝未知源/禁通配/Cookie 属性/Secure 标志/清除 Cookie/配置项/向后兼容登录）。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道B G02——邮件服务（SMTP+模板+email_logs）。config.py 新增 SMTP_HOST/PORT/USER/PASS/FROM_NAME/FROM_EMAIL/USE_TLS/TIMEOUT 八项配置（HOST 为空时自动启用模拟模式）；新增 EmailLog 模型（Alembic 0009 迁移，recipient/template/subject/error/created_at）；app/services/email_service.py 封装 send_email(db,recipient,template_name,context)：Jinja2 渲染 HTML+纯文本双格式→smtplib 发送（STARTTLS/SSL 双模式）→写 email_logs，SMTP_HOST 未配时落盘 data/email_outbox/*.eml 并标注 [SIMULATED]；四种模板（verify_email/password_reset/login_alert/system_notice）各含 HTML+纯文本版本；pyproject 新增 jinja2 依赖。验收：16 单测全绿（模板渲染×6、模拟发送×4、日志持久化×3、SMTP 发送×2、自定义主题×1）。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道D G06——回测正确性回归测试（P0-10a 测试先行）。新增 tests/test_backtest_correctness.py：9 个确定性场景覆盖费用影响/分批配对/期末持仓/平手交易/涨停不买入/跌停不卖出/同bar止损再入/微利毛赚净亏/滑点/成交量限制。每场景锁定修复前基线值（15 baseline PASS）+ 修复后目标期望值（10 target xfail）。基线数值经引擎逐bar追踪验证，fixed.md 记录修复前6项口径缺陷。验收：回测子集 30 passed+10 xfailed，现有 test_backtest_engine.py 15 项无回归。


---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道B G23——邮箱验证+密码重置+登录暴力保护（P0-4a）。users 表加 email_verified（Alembic 0012）；新增 app/services/email_token.py（验证/重置专用 JWT，派生密钥 JWT_SECRET_KEY+"|email_verify"/"|password_reset"+type 字段，防跨用途滥用，验证 10min/重置 1h）；RegisterIn.email 改必填+邮箱唯一性（重复 40002），注册后 best-effort 发验证邮件；新增 GET /auth/verify-email、POST /auth/forgot-password（无论邮箱存在均返成功防枚举）、POST /auth/reset-password（更新密码+复用 G19 session_service.revoke_all_user_sessions 吊销全部 refresh）；登录暴力保护 Redis login_fail:{username} 连续 5 次锁 15min 返 423(42301)、成功清零、Redis 不可用降级放行；UserOut 加 email_verified。验收：18 单测全绿，全库 340 passed（5 个 memory 失败为泳道C pgvector 环境问题，非本步引入）。

---
编码时间：2026-09-17
编码内容（描述）：G23 连带改造——注册 email 必填的测试夹具同步。16 个测试文件（test_admin_api/agent_ops/agents/backtest_api/catalog_search/chat/conversations/memory/research_graph/sse/strategies/strategy_templates/support_resistance/watchlist/ws_market）的注册调用统一补 email=f"{username}@test.local"，共 19 处；test_auth.py 的 _register 帮助函数默认补 email 参数。属 email 必填契约变更的机械适配，不改变测试语义。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道C G04（P1-12a）——pgvector 扩展 + memory_chunks 加列 + HNSW 索引。新增 Alembic 0009_pgvector_memory：CREATE EXTENSION IF NOT EXISTS vector → memory_chunks 加 embedding vector(384)（nullable，迁移期存量行为空待 G31 回填）+ embedding_kind varchar(16)（hash/minilm，等价原 Chroma collection 名后缀隔离）→ HNSW 索引 ix_memory_chunks_embedding_hnsw（vector_cosine_ops）+ 复合索引 ix_memory_chunks_user_embedding_kind（user_id+embedding_kind 行级过滤）。downgrade 逆序删索引/列（不 DROP EXTENSION，避免影响他表）。MemoryChunk 模型同步加两列 + EMBEDDING_DIM=384 常量。依赖：pyproject/requirements.lock 加 pgvector==0.5.0；deploy 两个 compose 的 db 镜像 postgres:16-alpine → pgvector/pgvector:pg16。新增 tests/test_pgvector.py 11 项（5 模型元数据 + 6 集成：扩展/列类型/长度/HNSW/复合索引/向量写入与余弦距离，后者无 pgvector 时 skipif 优雅跳过）。验收：pgvector/pgvector:pg16 容器实测 11/11 全绿，迁移链 0001→0012 线性无分叉，test_memory/test_models/test_embedding 17 项无回归。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道D G20（P0-10b）——回测引擎正确性修复。engine.py：新增 FIFO 成本队列 `_fifo_cost`（统一成本法，止损止盈触发价改用首批成本，加权平均保留供策略参考）；`_is_limit_up/_is_limit_down` 一字板涨跌停判定（支持 bar 显式 limit_up/limit_down 覆盖）→ 涨停禁买、跌停禁卖；新增 `max_volume_pct` 单笔成交量占比上限；`_auto_exited_this_bar` 标记使自动止损/止盈平仓后当根 bar 禁止再开同向仓；`_output` 新增 `open_position`（shares/fifo_cost/last_close）。metrics.py：`_pair_trades` 按股数占比分摊买卖费用输出 `net_pnl` + `round_close` 回合闭合标记；`compute_metrics` 新增 `open_position` 参数做期末浮动结算，win/loss 按净盈亏、平手单列 `draws` 且胜率分母排除平手、`total_trades` 改完整回合口径、best/worst_trade 用净盈亏，metrics_json 新增 draws/unrealized_pnl/unrealized_count。backtest_service 传 open_position。验收：correctness 23 项 + engine 15 项 + api 6 项全绿，修复前后对比见 fixed.md。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道D G20 连带测试适配。tests/test_backtest_engine.py：`make_bars` 默认 high/low 加 ±0.1% 价差（避免 o=h=l=c 一字板形态被新涨跌停检查误拦）；`test_auto_stop_loss` 的 bar0 补非一字板 OHLC；`test_metrics_known_case` 移除 fee 字段使净盈亏==毛盈亏（聚焦指标计算，费用分摊由 correctness 测试覆盖）。tests/test_backtest_api.py 的 `_register` 补 email（配合泳道B G23 email 必填契约）。验收：三文件 44 项全绿。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道A G19——双 token + 会话管理（P0-1）。config 新增 ACCESS_TOKEN_EXPIRE_MINUTES(15)/REFRESH_TOKEN_EXPIRE_DAYS(7)/REFRESH_TOKEN_COOKIE_NAME；security.py 重构：access token 加 jti+iat、新增 generate_refresh_token(token_urlsafe48)/hash_refresh_token(sha256)、Redis 黑名单 4 函数(token_blacklist:{jti} / refresh_blacklist:{hash})、set/clear_refresh_token_cookie(Path=/api/v1/auth)；新增 models/session.py UserSession 表 + Alembic 0010；新增 services/session_service.py(创建/查询/吊销/轮换/复用检测)；auth_service 改造 register/login/refresh/logout/get_sessions/revoke_session_by_id；auth.py 新增 POST /refresh、POST /logout、GET /sessions、DELETE /sessions/{id}；deps.py get_current_user 加黑名单检查 + Cookie 回退。验收：test_g19_dual_token.py 13 项全绿。

---
编码时间：2026-09-17
编码内容（描述）：G19 修复 refresh 复用检测失效（严重）。根因：session_service.validate_refresh_token 的检查顺序把 revoked_at 排在 Redis 黑名单之前，而轮换时旧 session 同时被 revoke_session + 入黑名单，导致复用请求永远命中"已吊销"分支短路，revoke_all_user_sessions 从不执行——即同一 refresh token 被盗用后无法触发全设备踢出。修复：把 is_refresh_token_blacklisted 检查提到 find_session 之后第一位（黑名单是"已轮换"的唯一信号），revoked_at 降为第二位。实测修复前 active=2（复用未触发）、修复后 active=0（全踢出）。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道A G29——WS 鉴权 token 不在 URL（P0-5）。ws_market.py 移除 query token 鉴权，改为：① 浏览器路径——握手从 HttpOnly Cookie 读 access_token，校验 JWT+Redis 黑名单+用户存在，失败直接拒绝握手 4001；② 非浏览器兜底——无 Cookie 时先 accept，5s 内等首条 {"action":"auth","token":...}，通过则注册否则 4001；③ 心跳复查 jti 黑名单，登出/踢出后 ≤15s 内断开已建立连接。manager.py ConnectionState 加 jti 槽位 + 新增 register()（仅注册不重复 accept）。auth.py 补齐 access_token Cookie 的种/清（login/register/refresh 用 _set_auth_cookies 双写，logout 双清）——G19 只种了 refresh Cookie，浏览器 WS 无法带 header，必须补此链路。验收：test_ws_market.py 13 项全绿。

---
编码时间：2026-09-17
编码内容（描述）：G29 Nginx 日志脱敏。deploy/nginx/nginx.conf 新增 map $request_uri $safe_request_uri 正则把 token 参数值替换为 ***（兼容历史客户端/第三方脚本仍带 token 的情况），定义 log_format masked 用 $safe_request_uri 替代 $request_uri，80 与 443 两个 server 块均设 access_log ... masked。注意 map 值中的 $1/$2 不会被镜像 envsubst 误替换（envsubst 只替换已定义环境变量名，数字不是合法变量名）。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道B G33（后端部分）——已登录态改密/改邮箱。规划缺口：P0-4 只定义未登录 forgot/reset，未定义已登录改密/改邮箱端点，但 G33 验收要求「入口且可用」，故补两端点（已在 project_constraints 记录待确认）。新增 PUT /users/me/password（ChangePasswordIn：old_password+new_password，校验旧密码 40003、新旧相同 40004 → 复用 session_service.revoke_all_user_sessions 吊销全部会话）与 PUT /users/me/email（ChangeEmailIn：password+new_email，校验密码 40003、与当前相同 40005、被他人占用 40002 → 置 email_verified=false + best-effort 发验证邮件）；user_service 增 change_password/change_email。验收：test_users_g33.py 11 单测全绿。

---
编码时间：2026-09-17
编码内容（描述）：G33 跨泳道问题记录（非本步引入）。全库 pytest 9 failed/353 passed，失败均为「不带 Authorization header 应 401」类用例，根因是泳道A G19（d8e1abb）在 deps.py::_extract_token 增加 access_token Cookie 回退 + 登录/注册下发 Cookie，TestClient 会话内 Cookie 持久化使「无 header」请求被 Cookie 认证通过；另 test_ws_market 两项属 G29 进行中的 WS 鉴权改造（query token→Cookie）。建议泳道A 在 conftest client 夹具清空 Cookie。已记入 project_constraints_v0.3.md 第八章第 4 条，本轮未越权修改泳道A 文件。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道D G32（P1-11）后端——回测结果可视化数据链路。新增 Alembic 0013 给 backtest_results 加 equity_curve/trades（JSONB，可空，up/down 已验证可逆）；models/strategy.py 加两列映射；backtest_repo.create_result 加两可选入参、list_results_by_strategy 加 defer() 不取大列；backtest_service 新增 _iso/_serialize_curve/_serialize_trades（datetime→ISO8601）+ _realized_pnl_by_sell（复用 metrics._pair_trades 给每笔卖出分摊已实现净盈亏，与胜率同口径，避免前端自算口径漂移），execute_backtest 落库两序列；schemas 拆 BacktestResultBriefOut（列表，不含大字段）/BacktestResultOut（详情，含两字段）；api/v1/backtest 列表端点改 BriefOut。验收：test_backtest_visualization.py 5 项 + 回测三文件 44 项全绿。

---
编码时间：2026-09-17
编码内容（描述）：G32 手工端到端验证（真实 K 线）。用 symbol_id=92 的 509 根日K 跑双均线策略：curve 509 点、流水 137 笔、胜率 36.76%、68 个回合。关键校验两项均通过——① 时间轴对齐：trades/curve 的 ts（`2024-08-19T08:00:00+00:00`）与 /api/v1/kline 下发的 naive ts（`2024-08-19T08:00:00`）按 epoch 秒比对 0 处错位（前端 toUtcSeconds 对两种写法解析结果一致）；② 口径一致：逐笔 realized_pnl 合计 == metrics._pair_trades 的 net_pnl 合计。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道A G30——用户输入校验 + 数据隔离审查（P0-6）。新增 app/schemas/validators.py：SafeText/SafeTextOptional（禁 C0/C1 控制字符，放行 \t\n\r）、HttpUrlTextOptional（仅 http/https/站内路径，拒 javascript:/data:/vbscript:）。各 schema 补限长：system_prompt 8000、策略 description 2000/code 20000、消息与聊天 content 20000、LoginIn username64/password128、token512、symbol 32、SR note 禁控制字符、agent name 禁控制字符、avatar_url 协议白名单；ChatIn.run_type 收敛为枚举。隔离审查结论：API 可达路径全部 WHERE user_id 隔离（服务层校验），未发现可利用遗漏；仓储层 backtest_repo/agent_repo.list_steps 无 user_id 属纵深防御缺口（当前调用方均先校验），已记录待后续加固。验收：test_g30_isolation.py 13 项全绿。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道B G16（后端）——通知中心+系统公告（P1-8b）。Alembic 0014 建 notifications（user_id/type/title/content/is_read/created_at/read_at，FK CASCADE + 未读优先复合索引）与 admin_announcements（title/content/type/is_active/expires_at）两表；新增 models/notification.py、repositories/notification_repo.py（多租户强制 user_id 过滤）、services/notification_service.py（创建/列表/已读/公告发布分发 + best-effort WS 推送）、schemas/notification.py、api/v1/notifications.py（GET 列表未读优先、GET unread-count、PATCH {id}/read、PATCH read-all）、api/v1/announcements.py（GET active 公开、GET 历史、POST /admin/announcements is_admin 鉴权，ADMIN_USERNAMES 定稿方案）。WS 推送：ConnectionManager 新增 set_loop/get_loop/broadcast_all，main.py lifespan 记录主事件循环，服务层经 run_coroutine_threadsafe 跨线程推送 {"type":"notification","data":{...}}。通知类型 system/backtest_complete/agent_complete/security；回测完成/失败（backtest_service）与深度分析完成（chat_service._save_result 仅 DEEP_RUN_TYPES）写通知。验收：test_notifications.py 19 单测全绿。

---
编码时间：2026-09-17
编码内容（描述）：G16 环境说明——本地 PostgreSQL 缺 pgvector 致迁移 0009 无法执行，0014 亦无法经 alembic 落库；已按 0009/0012 同样方式手工建表（notifications/admin_announcements + 索引）供本地测试，正式环境须在装好 pgvector 后执行 alembic upgrade head 补 0009~0014。已记入 project_constraints_v0.3.md 第八章第 1 条。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道B G17——用户数据导出（P1-5a 数据复制权）。Alembic 0015 建 export_tasks 表（user_id/status/progress/file_path/file_size/error/created_at/finished_at/expires_at，FK CASCADE + user_id/status 索引）；新增 models/export_task.py、repositories/export_repo.py（强制 user_id 隔离 + list_expired 过期扫描）、services/export_service.py（build_export_zip 打包全量 ZIP：user.json/watchlist.json/support_resistance.json/strategies/strategies.json+strategies/code/*.py/backtest.json/conversations.json/agents.json/memory/facts.json+memory/files/*.md；cleanup_expired_exports 删文件置 expired）、services/export_token.py（独立派生密钥 JWT 含 task_id+user_id，30min）、worker/tasks/export_tasks.py（run_user_export + cleanup_expired_exports）。端点：POST /users/me/export（异步提交）、GET /users/me/export/{id}（状态+签名下载链接）、GET /users/me/export/{id}/download?token=（FileResponse）。config 增 EXPORT_DIR/EXPORT_TTL_HOURS/EXPORT_DOWNLOAD_TOKEN_MINUTES；beat 增每日 4:30 清理。验收：test_export.py 20 单测全绿。

---
编码时间：2026-09-17
编码内容（描述）：G17 待确认项——导出任务队列归属。worker 启动命令为 `-Q backtest,sync,ai`，新增独立 export 队列必须同步修改 deploy/docker-compose.yml 与 docker-compose.dev.yml（跨泳道文件）；放 sync 队列会阻塞 15s 实时轮询，放 backtest 语义不符。当前决策：task_routes 将 export_tasks 路由到 **ai 队列**（低频用户触发长任务，与 ai 队列特性相近，零部署改动）。若后续导出量大需隔离，请在两个 compose 的 worker command 加 `export` 队列并改路由。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道B G18——账户删除（P1-5b 删除权）。Alembic 0016 给 users 加 is_deleted/deleted_at（+索引）；user_service 增 delete_account（软删+复用 G19 session_service.revoke_all_user_sessions 吊销全部会话）/restore_account（宽限期内校验用户名密码恢复，超期 410/41001）/hard_delete_account（DB 层 11 张关联表均 ON DELETE CASCADE，db.delete(user) 即级联；另删导出文件与 data/memory/{user_id}/ 目录）/purge_expired_deleted_accounts（扫描超 30 天）。端点：DELETE /api/v1/users/me（软删）、POST /api/v1/auth/restore-account（恢复+签发双 token）。deps.get_current_user 增 is_deleted 检查（access token 即时失效，401/40103）；auth_service.login 遇软删用户返回 403/40310。worker/tasks/account_tasks.py 硬删任务 + beat 每日 4:45。验收：test_account_delete.py 13 单测全绿。

---
编码时间：2026-09-17
编码内容（描述）：G18 规划差异记录——P1-5「硬删除：级联删除…user_usage」中提到的 user_usage 表在本项目中不存在（全库 models 无该表，DB 中亦无）。实际需级联的用户关联表为 11 张：user_watchlist/support_resistance/trading_strategies/conversations/user_agents/agent_runs/memory_chunks/user_memory_files/user_sessions/notifications/export_tasks（均已核实为 ON DELETE CASCADE）；chat_messages/backtest_tasks/backtest_results/agent_steps 经中间表（conversations/trading_strategies/agent_runs）级联。无需额外建表。
---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道F G05——备份 + 灾难恢复（P1-1）。新增 services/backup_service.py（pg_dump -Fc 全量、pg_basebackup 物理基线、归档可读性校验、保留期清理、文件镜像、rclone 异地、恢复到临时库验证、WAL 归档状态、磁盘用量、status.json 与清单，含 CLI 入口）；scripts/backup_pg.sh 与 scripts/verify_backup.sh（薄封装，供人工/cron 独立执行）；worker/tasks/backup_tasks.py 四个任务 + beat 注册（02:00 全量 / 周日 02:45 物理基线 / 02:30 异地 / 周日 03:30 恢复演练）+ 新增 backup 独立队列（两个 compose 的 worker -Q 同步加 backup）；config 新增 BACKUP_* 与 RCLONE_* 共 15 项（全有默认值，向后兼容）；Dockerfile 装 postgresql-client-16（PGDG，带回退）+ rsync + rclone；两个 compose 开 PG archive_mode/wal_level/archive_timeout=300 + pgwal 归档卷（配 wal-init 一次性 sidecar 改属主，否则 postgres(999) 写不进 root 属主的卷）+ Redis AOF(everysec)+RDB(60 1000)；metrics_ext 增 4 个备份 Gauge；alerts.yml 增 BackupStale/BackupDiskSpaceLow/WalArchiveStalled；新增 docs/ops/disaster_recovery.md。验收：test_backup.py 33 项全绿，全库 485 passed。

---
编码时间：2026-09-17
编码内容（描述）：G05 规划缺口修正——补物理基础备份。Reference_guide P1-1 只写「pg_dump 每日全量 + WAL 归档 → 支持 PITR」，但 pg_dump 是逻辑备份，只能恢复到备份那一刻，无法与 WAL 归档组合做时间点恢复；PITR 必须基于物理基础备份（pg_basebackup）+ 其后的连续 WAL。若照原方案实现，disaster_recovery.md 的 PITR 步骤将不可执行。故新增 run_base_backup()：pg_basebackup -Ft -z -X stream -c fast，产物 pg/base/base_YYYYMMDD/{base.tar.gz,pg_wal.tar.gz}，保留 14 天（2 代）。用 -X stream 而非 -X fetch：fetch 在备份窗口内未发生 WAL 段切换时不产出 pg_wal.tar.gz，基线无法可靠用于 PITR（实测踩到）。docker 模式下先落盘容器 /tmp 再 docker cp 取回（-D - 流式到 stdout 时 tar 有两个成员，无法直接解压）。实测：全量 1.8MB/0.56s、基线 7.3MB/1.68s、逻辑恢复演练 6.19s 三表行数全等、PITR 恢复出 users=13/symbols=7258/kline_1d=18593 且 pg_is_in_recovery()=f。

---
编码时间：2026-09-17
编码内容（描述）：G05 跨泳道协调——Chroma 备份跳过（泳道 C 的 G31 已完成）。G05 规格要求「data/chroma/ 在 P1-12 完成前一并备份，如泳道 C 已下线 Chroma 则跳过并注明」。编码期间泳道 C 落地 G31（store.py 注明 Chroma 依赖 / CHROMA_DIR / MEMORY_DUAL_WRITE 均已下线，PG 为向量唯一真源），并同步移除了本步 config 里的 BACKUP_CHROMA 与 backup_service.file_sources() 的 chroma 分支。本步按规格跳过 Chroma 文件备份并注明：文件镜像只含 memory/exports，向量随 pg_dump 统一备份。已清理本步早先手工跑出的 data/backups/files/*/chroma/ 残留；磁盘上遗留的 data/chroma/ 目录属泳道 C 的清理范围，本步未动。

---
编码时间：2026-09-17
编码内容（描述）：G05 关键坑与待确认项。① pg_dump 客户端主版本必须 ≥ 服务端主版本，否则 pg_dump 直接拒绝执行——本项目服务端 PG16，Debian bookworm 自带 client-15 不可用，Dockerfile 改从 PGDG 装 postgresql-client-16（apt 失败自动回退发行版包并打印提示）；check_client_version() 每次备份前校验，版本不匹配明确失败而非产出坏备份。② 本机（Windows 开发机）无任何 PG 客户端（pg_dump/psql 均不在 PATH，C:\Program Files\PostgreSQL 不存在），故 BACKUP_PG_DUMP_MODE 默认 auto：先探测本地，找不到退回 docker exec -i <容器> pg_dump，本地实测走 docker 模式跑通全部备份与恢复。③ 备份任务由 Celery 直接调用 backup_service，不转发 shell——worker 需在 Windows 宿主与 Linux 容器都可跑，依赖 bash 会引入平台差异；.sh 脚本保留给人工/cron/容器内独立调用，两者共用同一实现。④ 待确认：生产 BACKUP_DIR 应指向独立磁盘（默认落 backenddata 卷内，与数据同盘）；RCLONE_REMOTE 与对象存储凭据未提供，异地备份处模拟模式。⑤ 另发现现存 bug 一处（留待 G24）：metrics_ext._refresh_market_freshness 报 can't subtract offset-naive and offset-aware datetimes，即 K 线/快照 naive 时间与 datetime.now(UTC) 相减失败，行情新鲜度指标实际一直采集失败——正是 P1-3 要修的 naive/aware 混用。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道C G21——store.py 去 Chroma，改 SQLAlchemy + pgvector，检索全链路下推 SQL。store.py 重写为 memory_chunks 行级增删改查（add/update/delete_chunk、delete_chunk_by_id、delete_collection 按 user_id 删）；search 两段式下推（子查询按 `<=>` 余弦距离取候选 limit max(k,min(3k,30)) → 外层按 score 排序 limit k）；find_duplicate 0.85 阈值下推为 `1 - 余弦距离 > threshold` ORDER BY 相似度 DESC LIMIT 1；以 user_id + embedding_kind 行级过滤替代 per-user collection。embedding.py 去除 chromadb.api.types 依赖，EmbeddingFunction 改为项目自有协议（保留 name/get_config）。memory_service 由「store 写 Chroma + agent_repo 写 PG」双写合并为 store 一次落库。验收：test_memory 18 项 + test_embedding 8 项 + test_pgvector 11 项全绿。

---
编码时间：2026-09-17
编码内容（描述）：G21 召回口径锁定（G31 对比基准，勿改）。旧实现 `_weighted_score` 写 `1 - distance/2`，Chroma 默认 hnsw:space=l2 返回**平方 L2 距离**，向量已 L2 归一（L2² = 2 - 2cos），故 `1 - distance/2` 化简即 `cos` —— 旧代码实际算的就是余弦相似度。pgvector `<=>` 返回余弦距离（1 - cos），新式 `similarity = 1 - 余弦距离`，与旧式数学等价。已用真实 Chroma 实测验证：chroma distance == 平方 L2（误差 <1e-5）、1 - d/2 == 点积余弦。新口径：score = (1 - 余弦距离)×0.7 + importance/10×0.3，去重阈值 0.85。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道C G31——存量 Chroma 向量回填 pgvector + 验证 + 下线。新增 scripts/backfill_memory_vectors.py（按 (user_id, vector_id) 左连接回填 embedding/embedding_kind，幂等可重跑，--dry-run/--force）与 scripts/compare_memory_topk.py（旧 Chroma vs 新 PG 逐 query 比对 TopK 与 score）。回填实测：PG 3 行、Chroma 1442 collection 中仅 2 个非空、共 4 条向量；回填 3 条（embedding_kind=minilm）、跳过 1 条孤儿（user 554 已注销）；复跑 skipped_existing=3 证明幂等；TopK 对比 4/4 一致、0 差异。

---
编码时间：2026-09-17
编码内容（描述）：G31 下线清理。删除 app/agent/memory/chroma_legacy.py（迁移期适配层）、两个迁移脚本、tests/test_memory_dual_write.py；删除 data/chroma/ 目录；config 移除 CHROMA_DIR / MEMORY_DUAL_WRITE / BACKUP_CHROMA；backup_service.file_sources 只保留 memory/exports（向量随 pg_dump 备份）；pyproject.toml 与 requirements.lock 移除 chromadb；.env.example / 两个 compose / .env.docker.example 移除 CHROMA_DIR；test_backup.py 同步去掉 chroma 源断言。**验证方式：venv 内 pip uninstall chromadb 后全库 483 passed**，证明导入链已无 Chroma 依赖。

---
编码时间：2026-09-17
编码内容（描述）：G31 双写灰度可开关（验收项）。store.py 增 MEMORY_DUAL_WRITE 开关：开启时 PG 写入镜像到 Chroma（惰性导入，失败只告警不影响主链路），关闭时 Chroma 零写入。新增 tests/test_memory_dual_write.py 2 项验证「关→无写入 / 开→add·update·delete·clear 全镜像」，实测通过。因迁移与验证在同一会话内完成，开关与遗留路径一并按计划下线，测试证据记入本文件。
---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道F G24（P1-3 数据库时区统一）——经确认**跳过不实施**，本步未写任何代码。决策：产品暂不解决 naive → timestamptz 问题，四簇（迁移脚本 / as_utc() 清理 / 连接时区 UTC / 抽样验证与回滚）均不做。现状保持：K线 ts、快照 updated_at 等仍为 timestamp without time zone，代码层继续用 as_utc() 归一规避。已知代价三项：① 行情新鲜度指标失效（metrics_ext._refresh_market_freshness 用 aware 减 naive 抛 TypeError，market_data_freshness_seconds 从未上报，MarketDataStale 告警永不触发，属监控盲区）；② 非 UTC+8 时区部署时 P1-3 的静默数据错误会重现（缓存失效/WS 增量推送/data_age_seconds/回测区间）；③ 新代码处理这些时间列仍需 as_utc() 归一。触发重做条件与重做要点（迁移编号须用 0016 而非规划文档的 0005、存量 UTC 抽样验证、kline_* 四个分区父表 DO 块循环、迁移前须有 G05 备份）已完整记入 project_constraints_v0.3.md 第八节第 19 条，泳道表处亦加了范围变更注记。G05 的备份能力保留（后续步骤与运维仍用），只是本轮不再作为时区迁移的前置被消费。需人工操作：无。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道C G15——记忆文件加密 + audit_log + 存储说明（P0-3a）。新增 app/core/crypto.py（AES-256-GCM：ENC1 魔数 + 12B nonce + tag；密钥取 MEMORY_ENCRYPTION_KEY，支持 64 位 hex 或 32 字节原文，长度不符直接报错；**未配置抛 EncryptionKeyMissing 不降级明文**）。store.py 记忆文件改为加密落盘（append = 解密→拼接→重加密），读取自动解密且兼容存量明文 .md。新增 models/audit.py + repositories/audit_repo.py + Alembic 0017 建 audit_log 表（user_id FK CASCADE / action / memory_id / ip / created_at + (user_id, created_at DESC) 索引）。memory_service 的 save/retrieve/delete/clear 全部写审计（best-effort，失败不阻断主链路），API 端点透传 X-Forwarded-For 首段 IP。新增 GET /api/v1/memory/audit 分页端点。前端 MemoryFilesDialog 加「数据存储说明」提示条（仅加提示，未改面板结构）；PrivacyView 移除「本地存储设计」表述、改为服务端加密存储并补审计说明。新增 cryptography>=42 依赖（pyproject + requirements.lock）。验收：test_memory_crypto.py 13 项全绿，vue-tsc -b --noEmit 通过。

---
编码时间：2026-09-17
编码内容（描述）：V0.3 泳道C G34——memory_chunks.content 加密（P0-3b）。实现方式为 SQLAlchemy `TypeDecorator`（app/models/types.py::EncryptedText，Text 列绑定参数加密、结果解密），而非在各读写点手工加解密：**所有读取方（记忆管理 API / 数据导出 / 重嵌入脚本 / 后台任务）零改动即拿到明文**，不会漏掉某个出口把密文吐给用户。密文以 base64 文本落库，列类型仍为 Text，**无需迁移**；embedding 保持明文向量（加密后无法计算相似度）。存量明文行按「非密文头则原样返回」兼容读取。验收：test_memory_crypto.py 覆盖 content 直读原始列为密文、ORM 读出为明文、检索/去重返回解密原文、API 返回明文、embedding 仍为 384 维明文、存量明文行可读。

---
编码时间：2026-09-17
编码内容（描述）：G15 需要人类配置项——MEMORY_ENCRYPTION_KEY 未配置。按约束 5「未配置前用环境变量占位，禁止硬编码密钥」实现：config 中该字段默认空串，代码路径无任何硬编码兜底，未配置时加密写入直接抛 EncryptionKeyMissing。已为本机开发环境生成 32 字节随机密钥写入 stock_backend/.env（该文件被 .gitignore，不入库），并在 .env.example 留空占位 + 生成命令注释。**生产部署必须自行生成并注入该密钥**，否则记忆写入与 content 落库会失败（详见 project_constraints_v0.3.md）。另：测试侧在 tests/conftest.py 用 secrets.token_hex(32) 注入一次性随机密钥，使测试自包含、不依赖本机 .env。

---
编码时间：2026-09-18
编码内容（描述）：V0.3 泳道C G14——用户自填 API Key + token 用量（P0-2 简化版）。Alembic 0018 给 users 加 api_key_encrypted（Text，复用 G34 的 EncryptedText TypeDecorator 密文落库）/ llm_tokens_prompt / llm_tokens_completion。新增 services/llm/user_key.py：validate_api_key（sk- 前缀 + 32 位以上形态校验）、get_user_api_key（ORM 自动解密）、record_usage（原子自增累计）、build_llm_service_for_user（用户 key 优先 + 用量回调，回调走独立 SessionLocal 避免与请求事务耦合）。LLMService 增 api_key / usage_sink / with_api_key（派生实例**共享**进程级熔断器与限流桶）；DeepSeekProvider 支持 api_key 覆盖并开 stream_usage=True，流式也能取到 usage；上游无 usage 时用 token_budget.estimate_tokens 本地估算并标记 estimated。端点：GET/PUT /api/v1/users/me/api-key（**只回掩码不回明文**，传空串清除）；UserOut 增 has_api_key 与三项 token 字段（改 from_user 构造，避免下发密文）。chat_service.stream_chat 装配用户级 LLMService。前端 SettingsPanel 增「AI 模型设置」区块（Key 输入/更换/清除 + 累计 token 展示）。验收：test_user_api_key.py 19 项全绿，全库 528 passed，vue-tsc 通过。

---
编码时间：2026-09-18
编码内容（描述）：G14 简化版边界说明（按规划「服务端限流/额度分层不做」）。用户自填 key 仅改变「用谁的 key 计费」，**不改变服务端防护**：熔断器与令牌桶仍是进程级共享（with_api_key 显式复用同一 breaker/bucket 实例），避免每个用户各有一套状态导致熔断保护形同虚设。token 用量为**估算值**（优先取 DeepSeek usage 字段，缺失时字符启发式兜底），仅供用户自估成本，非精确计费——前端已明确标注。用户 key 只做形态校验（sk- 前缀），不做联网有效性验证：真实有效性由首次调用时的 401 分类为 LLMAuthError 并给出「API Key 无效」提示。

---
编码时间：2026-09-18
编码内容（描述）：V0.3 泳道G G09——列表分页 + 消息游标分页（P1-6a）。新增 app/schemas/pagination.py：PageParams（page≥1 / size 1~100，offset 属性）+ page_envelope（{items,total,page,size,total_pages}，空列表 total_pages=0）+ cursor_envelope（{items,has_more,next_cursor}）+ 消息 limit 常量（默认 50 / 上限 200）。5 个列表端点统一接入信封：GET /conversations、/strategies、/agents、/backtest/tasks（后四者原为裸数组），/agent/runs 原已分页、本轮补齐 total_pages。仓储层加 offset/limit 与 count 配套函数（list_* 的 offset/limit 默认 None 保持内部全量调用不变，如 backtest_service 取全部策略 id、chat_service 取全量消息组装 LLM 上下文）。消息端点改游标分页：不传 before 取最新 limit 条，传 before 取更早一页；排序键 (created_at,id)，游标过滤用「created_at < ? OR (created_at = ? AND id < ?)」双分支而非行值比较（SQLite 测试库不支持 `(a,b)<(c,d)`），多取一条判 has_more，返回前 reverse 保证对外升序（与旧全量接口一致，前端渲染顺序不变）。游标 message_id 不属于该会话或不存在 → 400/40005（防跨会话越权探测）。验收：新增 tests/test_pagination.py 11 项全绿；5 个既有测试文件（test_conversations / test_agents / test_strategies / test_chat / test_backtest_api）的分页消费点同步改为 ["data"]["items"]；全库 528 passed。
---
编码时间：2026-09-18
编码内容（描述）：V0.3 泳道F G08——策略子进程隔离 + 资源限制（P1-4a）。新增 `app/backtest/runner.py`：策略从 worker 主进程移到**独立子进程**执行，父进程只做调度与 DB 写入（进度经管道回传，事务语义不变）；子进程施加 `RLIMIT_CPU`/`RLIMIT_AS`，父进程墙钟超时（`BACKTEST_TIME_BUDGET + BACKTEST_SUBPROCESS_GRACE` = 30+15s，显著小于 Celery 软超时 120s）后 terminate→kill，**worker 与其它任务不受影响**。新增 `app/services/backtest_quota.py`：per-user 并发用 **Redis ZSET + Lua 原子取配额**（而非 INCR 计数器——后者在 worker 崩溃时永久泄漏会把用户锁死；ZSET 按 stale 阈值自愈），队列积压超阈值直接 429。`create_backtest` 加两道 429（42901 用户并发上限 / 42902 队列繁忙）且不产生任务行；槽位在任务终态释放，重试中不释放。config 新增 8 项 BACKTEST_* 限额。`execute_backtest` 改走 `run_isolated`（`BACKTEST_SUBPROCESS_ENABLED=false` 可退回进程内，作逃生开关）。验收：`test_backtest_isolation.py` 36 项（Windows 34 passed/2 skipped，Linux 35 passed/1 skipped），全库 562 passed/2 skipped，ruff 全绿。

---
编码时间：2026-09-18
编码内容（描述）：G08 关键设计坑（务必记住）。① **RLIMIT_AS 不能直接设成预算值**：worker 进程 import 了 chromadb/onnxruntime，fork 后子进程继承父进程地址空间（VSZ 可能 1GB+），直接设 512MB 会让子进程**任何新分配立即失败**，策略连第一行都跑不起来。实现改为「读子进程当前 VSZ + 预算」，语义变成"策略自身额外增长不超过 N MB"，自校准。② **不用 fork，用 forkserver**：Celery worker 是多线程进程，fork 出的子进程可能继承其它线程在 fork 瞬间持有的锁而死锁（Python 3.12 起发 `DeprecationWarning`，3.14 在 Linux 已默认改 forkserver）。实测容器内该告警确实触发，改用 forkserver 后 `-W error::DeprecationWarning` 下全绿；代价是 bars 需 pickle（8k 根约 30ms，相对回测耗时可忽略）。`BACKTEST_SUBPROCESS_START_METHOD=fork` 可显式退回（自担风险）。③ **平台差异必须如实回报而非假装一致**：Windows 无 `resource` 模块，CPU/内存硬上限**不生效**，只有 terminate 兜底；`_subprocess.limits.enforced` 如实回报，测试按平台分别断言（POSIX 专属用例在 Windows skip、在 Linux 容器实跑通过）。④ **spawn/forkserver 要求 `__main__` 可导入**：用 `python - <<EOF`（stdin）方式跑测试脚本会报 `OSError: Invalid argument: '<stdin>'`——这是宿主脚本的问题，Celery 控制台脚本与 pytest 入口都有 `if __name__ == "__main__"` 守卫，不受影响；写验证脚本请落成真实文件。

---
编码时间：2026-09-18
编码内容（描述）：G08 顺带修复两个缺陷（详见 fixed.md 同日两条）。① **沙箱不支持增强赋值**：RestrictedPython 8.4 的 transformer 仍把 `x += 1` 编译成 `_inplacevar_('+=', x, 1)`，但该守卫已从包内移除（旧实现直通 `operator.iadd` 是已知逃逸向量），本项目 `_build_globals()` 从未提供 → **策略里任何 `+=`/`-=`/`*=` 运行时 NameError**。已在 `sandbox.py` 按**操作数类型白名单**补回 `_guarded_inplacevar`（放行内建安全类型，其余抛 TypeError，不重开逃逸面），并修正 `strategy_gen.py` 提示词里"对 context 属性 += 会编译失败"的错误描述。② **容器内整个应用无法导入**（跨泳道，泳道 C 的 G14 引入）：`llm_service.py` 类体内自引用注解 `-> LLMService` 在 Python 3.12 急切求值 → NameError，api/worker/beat 全部起不来；本地 3.14 惰性注解不报错。已加 `from __future__ import annotations`（与 store.py 同处置）。已记入 project_constraints 第 23 条。

---
编码时间：2026-09-18
编码内容（描述）：G08 安全审计结论（RestrictedPython 8.4，版本已在 requirements.lock 锁定）。实测逃逸向量全部被拦：`__class__`/`__bases__`/`__subclasses__`/`__globals__`/`__mro__`/`__code__`/`__dict__` 属性访问**编译期**拒（`invalid attribute name`）；`getattr(x,'__class__')` 无法绕过——`getattr` 根本不在受限内建里（运行时 NameError）；`'{0.__class__}'.format(x)` 与 `format_map` 运行时 `NotImplementedError`；`import`/`__import__`/`open`/`eval`/`exec` 编译期硬拒。审计向量已固化为 `tests/test_backtest_isolation.py` 的回归用例（参数化 7+5+2 项）。已知限制（非安全洞，供 G25 提示词参考）：受限内建不含 `getattr`，策略不能用它；`bytearray` 等未列入安全内建，策略里不可用。

---
编码时间：2026-09-18
编码内容（描述）：G08 跨泳道改动披露。① `tests/test_backtest_api.py`（泳道 D）改 1 行：Celery mock 由 `delay=lambda task_id: None` 改为 `delay=lambda task_id, quota_token=None: None` —— 本步给 `run_backtest_task` 加了第二个参数，不改 mock 会让该测试静默走"入队失败"分支（不再覆盖真实入队路径）。② `app/services/llm/llm_service.py`（泳道 C）加 1 行 `from __future__ import annotations`，修复上述容器导入崩溃。③ `app/agent/strategy_gen.py`（泳道 B/E 的 AI 链路）改 2 行提示词，修正 `+=` 的错误描述。均已在提交信息与 project_constraints 中如实披露，未回退任何他人改动。另：`backtest_service.py` 只改执行层调用点（`BacktestEngine.run` → `run_isolated`）与入队/配额，**未动撮合、配对、metrics、序列化逻辑**（泳道 D G20/G32 的产出），符合跨泳道边界约定。

---
---
编码时间：2026-09-18
编码内容（描述）：G08 收尾加固——Windows 内存限制失效修复（跨平台 RSS 看门狗）。首版用 `resource.setrlimit` 实现 CPU/内存上限，但 `resource` 是 Unix-only，Windows 上 `BACKTEST_MEMORY_LIMIT_MB` **被完全忽略**。实测（Windows 本机）：64MB 预算下有界策略吃到 1.2GB 未被拦；无界策略 **6 秒吃掉 3.7GB**（约 600MB/s），按默认墙钟 45s 外推可达 ~25GB，足以拖垮整机。修复：新增**零依赖**的父进程侧 `child_rss_bytes()`（Windows `OpenProcess`+`GetProcessMemoryInfo`，Linux `/proc/<pid>/statm`），父进程每 0.05s 采样 RSS，超预算即 terminate。两处关键细节：① 预算语义 =「策略自身额外增长」，**基线 RSS 由子进程 ready 消息自报**（早期用父进程侧"运行期最小 RSS"启发式会把 import 开销算进预算、误伤正常策略）；② 采样间隔 0.2s→0.05s（0.2s×600MB/s 单次超调可达数百 MB：实测 128MB 预算冲到 848MB，收紧后 232MB）。POSIX 保留 `RLIMIT_AS` 作内核级第二道。实测效果：512MB 预算约 1s 拦下、32MB 预算 0.5s 拦下（超调 +34MB）。另新增 `_subprocess.peak_rss_bytes`（内存峰值）——**G25 回测监控的内存峰值数据源已就绪**。验收：test_backtest_isolation.py 40 项（Windows 38 passed/2 skipped，Linux 容器 39 passed/1 skipped），全库 566 passed/2 skipped，ruff 全绿。

---
编码时间：2026-09-18
编码内容（描述）：G08 加固的测试经验（供后续参考）。① **跨平台断言要断言"行为"而非"机制"**：内存失控在两平台由不同机制拦截（Windows 看门狗 / POSIX RLIMIT_AS），但都必须**快速拦下且父进程存活**——用例断言 `BacktestError` + `elapsed < 30`，再按平台追加机制断言（Windows 必须命中 `内存增长超过上限` 分支）。② **spawn 要求 `__main__` 可导入且有 `if __name__ == "__main__"` 守卫**：临时验证脚本用 `python - <<EOF`（stdin）或漏写守卫都会报 `OSError: Invalid argument: '<stdin>'` / 递归重跑——本步踩了两次，写探针请落成真实文件并加守卫。③ 引擎既有行为记录：`BacktestContext.__init__` 用 `params or {}`，**空 dict 会被替换成新对象**，故策略对 `context.params` 的写入在 params 为空时不回传（与本步无关，测试断言时需注意）。

---
---
编码时间：2026-09-18
编码内容（描述）：V0.3 泳道F G25——策略校验增强 + 回测监控 + 队列繁忙提示（P1-4b，前置 G08 已完成）。① **三级校验强制化**：`create_backtest` 在创建任务前跑三级校验（语法→接口→沙箱 dry-run），不通过返回 400/40031 且**不创建任务行、不占用并发配额**；结果按代码哈希缓存 1h（`strategy_valid:{sha256}`）。② **dry-run 移入子进程**：`strategy_validator._dry_run` 改用 G08 的 `run_isolated`，1 根模拟 K 线跑**真实引擎**，限制 CPU 1s / 内存 64MB。原实现是进程内 + 自造的 `_DryRunContext`（与真实 `BacktestContext` 在 T+1/费用/持仓语义上并不一致，"校验通过"不等于"回测能跑"），且**死循环策略会挂住 AI 队列 worker**。③ **新增 services/backtest_monitor.py**：4 个 Prometheus 指标（耗时分布/内存峰值/失败原因分类/异常策略）+ 结构化日志 + 连续失败判定（Redis 计数，成功清零，达 `BACKTEST_ABNORMAL_FAIL_STREAK`=3 判为异常策略）；接入 `execute_backtest` 与 `mark_task_failed`；alerts.yml 增 `BacktestFailureRateHigh` / `BacktestAbnormalStrategy`。④ **队列繁忙提示**：后端 429 的 msg 增「预计等待约 X 分钟」（`estimate_wait_minutes`，口径 = 积压数 × 单任务耗时估算，**放后端算**——前端不做业务计算，且并发度是后端配置）；前端 `backtestBusyNotice()` 识别 42901/42902，在 N 区回测模块加**常驻**提示（通用 toast 只闪现一次），AI 页自动回测失败文案也改用后端 msg（原 `(e as Error).message` 只有 "Request failed with status code 429"，对用户无信息量）。验收：test_backtest_monitor.py 18 项 + test_backtest_isolation.py 42 项全绿；全库 588 passed/2 skipped；前端 vue-tsc + build 通过。

---
编码时间：2026-09-18
编码内容（描述）：G25 两个关键设计决策（务必记住）。① **校验器自身故障必须 fail-open**：dry-run 改成子进程后，新增区分「策略自身问题」与「基础设施故障」——只有 `StrategyRuntimeError`/`StrategyResourceError` 才判策略不合格；其余 `BacktestError`（子进程起不来、目标模块无法导入）**放行并告警**。这条兜底不是纸上谈兵：实现过程中用 `python - <<EOF`（stdin）跑探针时，spawn 无法重导入 `__main__`，导致**所有**策略都被判"校验不通过"——若照原样上线，整站回测将不可用。② **CPU rlimit 改为相对当前用量**：`_apply_limits` 原先设绝对值，但 spawn/forkserver 会**先导入目标模块再调用入口**，import 的 CPU 开销被算进策略预算——dry-run 预算仅 1s，会被 import 吃光而误杀正常策略。改为 `soft = 已用 CPU + cpu_seconds`。③ 校验器要求 `initialize` 而**引擎不要求**（`compile_strategy` 中它是可选的），强制校验存在理论回归风险；实测库中 5 条策略仅 1 条不通过且是**空代码**（本就跑不了），0 条因缺 initialize 被拒，故保持校验器现状并记录。

---
---
编码时间：2026-09-18
编码内容（描述）：V0.3 泳道F G10——WS 多实例 + Nginx 负载均衡（P1-2a）。前置阅读结论：**Redis pub/sub 桥接已存在且天然支持多实例**（ws/publisher.py 发布 market:updates → 各实例的 _market_listener_loop 订阅 → 广播给本实例 ConnectionManager），代码层架构已就位，缺的是验证与 Nginx 层。本次交付：① **修复 P0 bug——WS 实时推送从未生效**（详见 fixed.md 同日条）：main.py 给监听线程自建 loop 且从未 run_forever，run_coroutine_threadsafe 投递的协程永不执行；改为调度到 uvicorn 主循环。② **Nginx 补 WS 升级头**：deploy/nginx/nginx.conf 新增 location = /api/v1/ws/market（Upgrade/Connection 头 + proxy_read_timeout 3600s + 关缓冲）——此前 /api/ location 无升级头，**经 Nginx 的 WS 握手会失败**（此前"WS 可用"走的是 vite dev 代理，Docker 路径未验证）；同时新增 upstream api_upstream（least_conn + keepalive 32），/api/ 与 /api/v1/chat 改走 upstream；注释掉的 443 块同步更新，避免启用 HTTPS 时回归。③ **生产 compose 迁移单点化**：新增一次性 migrate 服务（RUN_MIGRATIONS=1），api/worker/beat 等它成功退出再启动——多实例 --scale api=3 不能让每个副本都跑迁移（撞 pg_type 唯一约束，见 deploy_fixed 问题三）；**顺带修复**：本文件此前**没有任何服务设 RUN_MIGRATIONS**，全新库无法自举。环境变量锚点提到顶层 x-backend-env（migrate 在 api 之前引用，YAML 锚点须先定义）。④ **新增 tests/test_ws_multi_instance.py**：真实起两个 API 进程（不同端口、共享 Redis），各连一个 WS 客户端，发布一次快照断言**两边都收到**，并断言未订阅的实例收不到。验收：该文件 2 项全绿、全库 pytest 通过、nginx -t 通过（按真实用法：模板 + envsubst + --add-host api）、两个 compose config 校验通过。

---
---
编码时间：2026-09-18
编码内容（描述）：V0.3 泳道F G11——PG 读写分离 + Redis Sentinel（P1-2b）。① **PG 读写分离**：`app/utils/db.py` 新增 `build_engines()` 工厂（返回主库/读库引擎；`DATABASE_READ_URL` 为空时**读库就是主库同一对象**，本地零行为差异）与 `ReadSessionLocal`/`get_read_session()`；`app/api/deps.py` 新增 `get_read_db()`；`app/api/v1/market.py` 的 5 个纯行情读端点（/symbols、/symbols/search、/kline、/snapshot、/sync-status）改走只读会话。路由用**显式**方式而非 SQLAlchemy 透明 binds——仓储层本就以 `db: Session` 为参数，透明 binds 会把"同一事务读写被拆到不同节点"的隐患藏起来。用户数据（关注/策略/会话）一律走主库，保证"读己之写"。② **Redis Sentinel**：`redis_client._build_client()` 支持 Sentinel（`master_for` 主节点发现，故障转移后自动重连，无需重启），socket_timeout 收紧以免故障窗口内挂住请求线程；未配置时直连 `REDIS_URL`（降级）；开关打开但未配地址则告警并降级；地址不可达时**构造不抛错**（只在用时失败，不拖垮 API 启动）。config 新增 `DATABASE_READ_URL` + 5 项 `REDIS_SENTINEL_*`。③ 新增 `docs/ops/read_write_splitting.md` 运维手册（路由约定/启用步骤/回滚/注意事项/监控建议/故障转移验证清单）。验收：`tests/test_g11_routing.py` 8 项全绿（含**真实路由证明**：捕获只读引擎上实际执行的 SQL，断言 /kline 走读引擎而 /watchlist 不走）；Sentinel 主节点发现 + 经其读写已用真实容器端到端验证通过。

---
编码时间：2026-09-18
编码内容（描述）：G11 **未完成的验证项（必须如实记住）**：Redis Sentinel 的**自动故障转移未经实证**。实测（最小化本地拓扑：1 sentinel + 1 master + 2 replica，`down-after-milliseconds=3000`）——`docker kill` 主节点后 Sentinel **未把主标记为 s_down**（`sentinel master mymaster` 的 flags 仍为 `master`），35s 内未发生提升，客户端连接旧主超时。已排除：Sentinel 能看到 2 个 replica（`num-slaves=2`）、`resolve-hostnames yes` 已设、replica 侧 `master_link_status` 正确变为 down。**根因未定位，本轮不再深挖**（超出合理成本）。已完整记录到 `docs/ops/read_write_splitting.md` 第 2.3 节，含上线前必做的三步真实验证清单。补充判断依据：单 Sentinel 本身是单点，其切换行为**不代表**生产拓扑（quorum/多数派语义不同），在本机"验证通过"反而可能给出错误信心——故未强行调通并宣称可用。另：`docs/ops/read_write_splitting.md` 第 3 节的监控项依赖 P1-7（未实现），按惯例记录待衔接。

---
---
编码时间：2026-09-18
编码内容（描述）：V0.3 泳道F G12——Celery 多队列多实例 + 幂等审计 + 无状态验证（P1-2c，泳道 F 最后一步）。① **多队列多实例**：生产 compose 把单个 worker 拆成 `worker-sync`（sync,backup）/ `worker-backtest` / `worker-ai` 三个服务，各自可独立 `--scale`。拆的理由：拆前 `--pool=solo --concurrency=1` 下任何长任务（回测最长 45s / 导出打包 / 备份）都会把 15s 的 realtime_poll 堵在队列里，实时行情延迟直接变分钟级。开发栈保持单 worker（本地单实例降级，有意取舍）。② **幂等审计**：15 个 Celery 任务逐一审计（Celery 是 at-least-once，worker 强杀后未 ack 任务会重投）。14 个天然幂等（K线/快照/目录走 UPSERT、删除类为幂等空操作、备份走同名原子改名、导出按 task_id 覆盖）。**发现并修复 1 处不幂等**：`run_backtest_task` 重复执行会重复落库 `backtest_results`（worker 在提交后 ack 前被杀 → 重投 → 用户看到两条重复回测结果）；修复为 `execute_backtest` 开头幂等短路（任务已 success 且结果存在则直接返回既有 result_id，标记 idempotent）。③ **无状态验证**：API 可随时增减实例；识别出三处进程内状态——`ConnectionManager`（**有意**进程内，消息经 Redis 广播，G10 已实测双实例互通）、**LLM 令牌桶 + 熔断器**（⚠️ 多实例下限流阈值变成 N×30、熔断各实例独立）、**Provider 熔断状态**（⚠️ 每实例独立，影响很小）。后两者**记录未迁移**（迁移需要 Redis 原子计数与跨实例状态同步，属独立改动；已写明触发条件）。④ 新增 `docs/ops/celery_scaling.md`（拆分理由/扩容命令/完整幂等审计表/无状态验证结论）。验收：`tests/test_g12_idempotency.py` 2 项全绿；prod compose config 校验通过（services 含 worker-sync/worker-backtest/worker-ai）。

---
编码时间：2026-09-18
编码内容（描述）：G12 已知不一致（记录待统一）：回测任务的**幂等路径**返回的 `metrics` 是 `result.metrics_json`（存储形态），与**首次执行**返回的 `compute_metrics()` 完整返回（含外层 win_rate/profit_loss_ratio/sharpe/annual_return/max_drawdown 等字段）**形状不同但同源**。当前无常驻调用方受影响（API 的结果端点直接读库、不经此返回值；Celery 任务层只用 task_id/result_id），故未强行统一；若后续有调用方依赖该返回值的字段，需补一层转换或让幂等路径重建完整结构。

---
