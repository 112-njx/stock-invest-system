# Agent 记忆文件

> 每次开启 Agent 先阅读最新记忆内容，快速重新上手。

保存时间：2026-08-21（V0.2 第一波完成后更新）
记忆内容：

1. 项目定位：量化交易软件——选股买卖决策 + DeepSeek Agent 辅助（主观交易经验转量化因子/回测），Agent 记忆本地存储。
2. 技术栈：Python(FastAPI) + PostgreSQL + Vue3(TS) + Redis + Celery + Nginx + DeepSeek + LangChain/LangGraph + ChromaDB。
3. 硬约束：前端不计算复杂指标（后端算）；回测走 Celery 不阻塞主线程；Agent 记忆本地存储（ChromaDB + HashEmbedding）；行情数据源走 DataProvider 抽象可插拔；缓存层仅 Redis+PostgreSQL（无内存缓存）。
4. 已注册 skill：quant-prod-arch（生产级架构六要素审查）、quant-trading-frontend（交易终端前端规范）。

5. V0.1 已全部完成（后端五阶段+前端五阶段，121 pytest 全绿），核心功能：
   - 后端：FastAPI 分层架构（api→services→repositories 单向依赖）、24表+K线按月分区（680分区子表）、DataProvider(东方财富)+新浪/同花顺降级、Celery三队列(sync/backtest/ai)、用户鉴权(bcrypt+JWT)、关注列表、支撑压力位、技术指标(MACD/KDJ/成交量/成交额，Redis缓存)、AI对话(LangChain ReAct+SSE流式)、本地记忆(ChromaDB+HashEmbedding)、策略生成(ast.parse校验)+CRUD、定制Agent、多智能体(LangGraph五节点：技术分析→多空辩论→风控→决策)、回测引擎(RestrictedPython沙箱+撮合+胜率/夏普/最大回撤)、Docker Compose全栈编排、Nginx反代+分级限流、Prometheus+Grafana监控(9面板+4告警)、CI/CD。
   - 前端：Vue3+TS+Vite+Pinia+lightweight-charts v5，行情双层页(E/F/G/H/I首页 + A/B/C/D详情)、AI策略页(J/K/L/M/N分区，借鉴QuantDinger)、暗黑/明亮双主题、7s轮询快照、SSE流式对话。
   - V0.1 已知 bug 已修复：固定指数预同步脚本(sync_fixed_indices.py)、指数快照 NOT NULL 兜底写0、AI对话降级条件误判(model is None)、行业指数关联ETF种子补齐。

6. V0.2 第一波（行情数据基础）已完成（2026-08-20，全库 188 pytest 全绿 + ruff 通过）：
   - 阶段四 DataProvider 可插拔：SinaProvider/THSProvider 独立拆分、DataProviderFactory 优先级链[eastmoney,sina,ths]+每源独立熔断(半开探测)、GET /api/v1/admin/providers/health、beat provider_probe 每60s恢复探测。
   - 阶段一 缓存体系：sync_status 表+entrypoint 预同步(固定指数 X/49 进度)+startup 预热、K线"最近N根"Redis缓存(kline:{symbol_id}:{period}:{limit}, TTL300s)+击穿锁(SETNX)、快照14字段Redis缓存(snapshot:{symbol_id}, TTL300s)+data_age_seconds、指标缓存键含 latest_ts 自动失效。
   - 阶段三 目录/搜索/关注：symbols.is_catalog 字段+catalog_sync(全A股约5000+ETF, 每日3:00, partial失败1h重试)+POST /admin/catalog/sync 手动触发、搜索三层(精确>已同步>仅目录)+外部回退+search:* 缓存(1h)+is_catalog/has_kline 返回、关注添加自动触发 kline_init+sync_status(pending/syncing/done/failed)、watchlist/watchlist_snap Redis 缓存。
   - 阶段二 WebSocket：/api/v1/ws/market(query token 鉴权)、ConnectionManager 多标签页共享、心跳15s ping/30s超时断连、订阅模型、realtime_poll 经 Redis pub/sub 桥接推送增量快照、sync 断线补拉(按 since 时间戳)。
   - Alembic 0004 迁移：users.is_admin、sync_status 表、symbols.is_catalog、user_watchlist.sync_status。
   - 需人工配置：ADMIN_USERNAMES（管理端点访问权限）。
   - 注意：K线 ts/快照 updated_at 列为 timestamp without time zone（DB naive，代码内 as_utc 归一）。

7. 开发环境：
   - Python 3.14（D:\Pycharm\python），venv 在 stock_backend/.venv
   - PostgreSQL 本机 5432（postgres/123456，库 stock_invest）
   - Redis Docker 容器 stock-redis（redis:7-alpine，端口 6379，需先启动 Docker Desktop）
   - 前端：stock_frontend，npm run dev（端口 5173），vite 代理 /api 到后端 8000
   - 启动后端：cd stock_backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   - 启动 Celery worker：.venv/Scripts/celery.exe -A app.worker.celery worker --pool=solo -l info
   - 启动 Celery beat：.venv/Scripts/celery.exe -A app.worker.celery beat -l info
   - 跑测试：.venv/Scripts/python.exe -m pytest tests/ -v

8. 参考开源项目（须借鉴避免造轮子）：
   - TradingAgents-CN：C:\Users\112\Desktop\TradingAgents-CN-main\TradingAgents-CN-main（MongoDB+Redis 双层缓存、数据源优先级链、全量标的预同步、新鲜度容错匹配）
   - QuantDinger：C:\Users\112\Desktop\QuantDinger-main\QuantDinger-main（内存LRU+Redis可选+PG 三层缓存、全量目录搜索+别名表、关注列表验证+名称解析、AI策略页 J/K/L/M/N 分区）

9. 关键文档索引：
   - 需求：docs/project_docs/docs.md
   - 架构：docs/project_docs/working_docs.md（生产级六要素）
   - 后端规划：docs/Agent_backend/roadmap.md（V0.1 五阶段 + V0.2 八阶段）
   - 前端规划：docs/Agent_frontend/roadmap.md（V0.1 五阶段 + V0.2 七阶段）
   - API 文档：docs/Agent_backend/api-docs.md
   - 编码记录：docs/Agent_backend/Agent_code.md、docs/Agent_frontend/Agent_code.md
   - 修复记录：docs/Agent_backend/fixed.md、docs/Agent_frontend/fixed.md
   - 数据库：docs/sql/（01_schema.sql 建表、02_seed_fixed_indices.sql 固定指数种子、03_agent_extensions.sql Agent 扩展表）
   - 增强提示词：docs/Agent/enhanced_prompt.md（V0.2 开发用，强制设计验证→编码→自我审查→测试→报告流程）

10. V0.2 后续规划（第二至四波，待开发，审计通过后开启）：
    - 第二波：AI 流式稳定性与错误降级（SSE 心跳+delta序号断点续传+三级超时+错误码标准化+分级降级：LLM挂了返回规则分析）、AI 记忆系统升级（HashEmbedding→ONNX MiniLM、短期/长期分层+重要性评分1-10、去重合并、记忆管理 CRUD API）。
    - 第三波：多智能体可观测性（agent_step 实时 SSE 推送、节点失败降级不中断、运行历史 API）、长会话上下文管理（滑动窗口+LLM 摘要压缩、Token 预算控制在模型上限80%）。
    - 第四波：策略生成可靠性（三级校验：语法→接口→沙箱dry-run、失败自动重试2次、5个策略模板库、生成→回测一键内嵌结果卡片）、会话标题自动生成。
    - 前端 V0.2 七阶段：数据加载同步进度体验、WebSocket 客户端+多标签页共享、搜索关注同步状态增强、AI 流式错误分级 UI、记忆管理可视化抽屉、多智能体时间线、长会话 token 用量+策略回测内嵌。

11. 当前状态：V0.2 第一波已完成并通过 188 测试，等待代码审计。下一波开发前必须阅读 docs/Agent/enhanced_prompt.md，严格执行强制流程：强制代码阅读→设计验证(等确认)→编码→10项自我审查→测试(100%通过)→细分任务报告。
