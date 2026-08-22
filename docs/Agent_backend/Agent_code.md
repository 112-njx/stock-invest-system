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
