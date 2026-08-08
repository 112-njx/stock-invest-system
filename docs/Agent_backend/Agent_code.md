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