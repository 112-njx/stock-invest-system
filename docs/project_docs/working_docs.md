# 生产级架构说明文档

> 目标：以「Python + FastAPI + PostgreSQL + Vue3 + Redis + Celery + Nginx + LangChain/LangGraph + 本地记忆」构建生产级量化交易软件。
> 参考开源：TradingAgents-CN（LangChain/LangGraph 多智能体）、QuantDinger（AI 量化 Agent，J/K/L 区架构可完全借鉴）。
> 核心约束：前端不计算复杂指标；回测不阻塞主线程；Agent 记忆本地存储。

## 总体架构分层

```
┌──────────────────────────────────────────────┐
│ 前端 Vue3（行情双层页 / AI策略页）             │
└───────────────┬──────────────────────────────┘
                │ HTTPS
┌───────────────▼──────────────────────────────┐
│ Nginx（静态资源 + 反向代理 + gzip + TLS）      │
└───────────────┬──────────────────────────────┘
┌───────────────▼──────────────────────────────┐
│ FastAPI（无状态 API，/api/v1 版本化）          │
│   router → service → repository 单向依赖       │
└───────┬───────────────┬──────────────┬───────┘
        │               │              │
┌───────▼─────┐  ┌──────▼─────┐  ┌─────▼──────────────┐
│ PostgreSQL  │  │  Redis     │  │ Celery（worker+beat）│
│ 业务/行情数据 │  │ 缓存/队列    │   │ 行情同步/回测/AI异步 │
└─────────────┘  └────────────┘  └─────┬──────────────┘
                                       │
                     ┌─────────────────┼─────────────────┐
                     │                 │                 │
              ┌──────▼─────┐    ┌──────▼─────┐    ┌──────▼─────────┐
              │ 东方财富API │    │ DeepSeek   │    │ 本地记忆/向量库  │
              │ (数据源适配) │    │ (LLM)      │    │ (LangChain 记忆)│
              └────────────┘    └────────────┘    └───────────────┘

可观测横切：Prometheus + Grafana + Loki + OpenTelemetry（全链路）
```

---

## 1. 可维护（Maintainable）

- **分层单向依赖**：表现层 → 应用层 → 领域层 → 基础设施层，禁止反向/循环依赖。
- **统一规范**：Ruff/Black 代码风格、OpenAPI 接口文档、Conventional Commits、统一命名约定。
- **配置管理**：环境变量 + Pydantic Settings 配置类 + `.env`，禁止硬编码密钥与地址。
- **数据库迁移**：Alembic 版本化管理 schema 变更。
- **依赖锁定**：`pyproject.toml` + `requirements.lock`，版本可复现。
- **测试保障**：pytest 单测覆盖核心逻辑（指标计算、策略解析、记忆抽取、Agent 编排），CI 强制跑测。
- **代码即文档**：类型标注 + 关键模块 docstring，接口层自动生成 Swagger。

## 2. 可扩展（Scalable / Extensible）

- **数据源可插拔**：`DataProvider` 抽象接口，东方财富为默认实现，可横向新增供应商/加密/外汇市场。
- **标的统一模型**：股票/ETF/指数共用 `symbols` 表，按 `type` 区分，天然支持新市场。
- **Agent 工具注册机制**：LangChain Tool 注册，行情快照/技术指标/回测/新闻等封装为工具，新增分析能力不改核心循环（借鉴 TradingAgents-CN tools/analysis）。
- **知识库扩展**：langchain 本地向量库（ChromaDB 本地持久化），支持追加财报、公告等文档类型入知识库（保持本地存储约束）。
- **回测引擎插件化**：策略类型、指标、撮合规则可插拔；策略参数 JSON 化，无需改代码。
- **无状态水平扩展**：FastAPI 无状态 + Nginx 负载均衡，Celery worker 按任务类型独立扩缩容。
- **前端组件化**：K 线图、指标面板、策略卡片抽为复用组件；双层页共用同一套 K 线组件。

## 3. 可演进（Evolvable）

- **API 版本化**：`/api/v1` 起步，破坏性变更升版本，老版本灰度过渡。
- **模块解耦**：模块间通过事件/接口通信，避免直接依赖具体实现，内部替换不影响外部。
- **数据库前向兼容**：迁移只加不改，字段加默认值，保证旧数据可读。
- **功能开关（Feature Flag）**：新功能灰度上线，可随时回退（如 AI 分析开关）。
- **Agent 流程可编排**：LangGraph 状态图编排（分析→多空辩论→风控→决策），流程配置化，支持升级迭代（借鉴 TradingAgents-CN trading_graph）。
- **预留 MCP 接入**：AI 能力做成 MCP 可扩展，对接外部工具/数据（对齐文档中的未来优化方向）。

## 4. 稳定性（Stability）

- **降级策略**：行情源不可用时回退 Redis 缓存/昨日数据；AI 不可用时返回可用行情分析（已完成性能降级）。
- **外部依赖防护**：东方财富/DeepSeek 调用统一封装（LangChain LLM 调用层）——超时 + 重试(退避) + 熔断 + 限流。
- **异步隔离**：回测、行情同步、AI 分析全部走 Celery，绝不阻塞 API 主线程。
- **幂等设计**：行情同步/回测任务幂等，重复触发不产生脏数据。
- **数据一致性**：策略保存 + 回测结果 + 记忆文件写入用事务/补偿保证原子性。
- **缓存策略**：Redis 缓存行情快照，设置合理 TTL 与失效策略，防止缓存击穿/雪崩。
- **失败兜底**：Celery 失败自动重试 + 死信队列；数据库定时备份，行情数据冷热分离。

## 5. 可观测（Observability）

- **全链路日志**：结构化 JSON 日志，`request-id` 贯穿 API→任务→AI 调用（已完成全链路日志）。
- **Agent 运行可观测**：LangGraph 执行落库 `agent_runs`/`agent_steps`，追踪各智能体步骤、token 与失败点，支撑复盘与成本统计。
- **指标采集**：Prometheus 采集 API 吞吐/延迟/错误率、任务队列深度、缓存命中率、行情数据新鲜度。
- **分布式追踪**：OpenTelemetry 链路追踪，覆盖 HTTP、Celery、Redis、AI 外部调用。
- **告警**：Grafana 告警规则（接口错误率 > 阈值、队列积压、行情延迟告警）。
- **前端监控**：错误上报 + 性能埋点（页面渲染、K 线加载耗时）。
- **可观测面**：`/metrics`、`/health`、`/ready` 端点暴露给监控与探针。

## 6. 可部署（Deployable）

- **容器化**：后端/前端/Celery 多阶段 Dockerfile + Docker Compose 一键编排。
- **环境隔离**：`dev / test / prod` 配置分离，密钥走环境变量。
- **健康检查**：存活探针 `/health`、就绪探针 `/ready`，滚动更新安全。
- **迁移自动化**：容器启动自动执行 Alembic 迁移 + 种子数据（大盘/行业指数固定列表）。
- **网关优化**：Nginx 静态资源缓存 + gzip + TLS + 反向代理，前端构建产物挂载镜像。
- **CI/CD**：GitHub Actions 流水线：lint → test → build 镜像 → 部署。
- **部署脚本**：一键安装/升级脚本，含依赖检查与回滚说明。

---

## 开发任务收尾检查

每个开发大任务结束后，按以下格式补充：

```
写入日期：
生产级架构考虑：
- 可维护：一句话
- 可扩展：一句话
- 可演进：一句话
- 稳定性：一句话
- 可观测：一句话
- 可部署：一句话
```

---

写入日期：2026-08-11（阶段五：部署闭环与生产收尾）
生产级架构考虑：
- 可维护：多阶段 Dockerfile（依赖层缓存）+ docker-compose 一键编排 + 启动入口集中处理迁移/种子，环境变量全部经 .env.docker 配置，无硬编码。
- 可扩展：容器内 db/redis 不映射宿主端口、宿主端口按需映射，api/worker 可独立扩缩容；Nginx 分级限流（行情/AI 分区）预留新接口扩展。
- 可演进：补全前端已对接但缺失的 GET /agent/runs、/memory/files 编排接口（契约对齐，前端自动生效）；/api/v1 版本化 + workflow_dispatch 手动部署灰度。
- 稳定性：容器 HEALTHCHECK（/health、/ready）+ 启动等 DB 就绪再迁移；LLM 失败熔断、回测超时兜底已接入监控；Nginx 限流防打爆。
- 可观测：/metrics 扩展 LLM 调用（次数/耗时/token）与平台指标（celery_queue_depth/redis_cache_hit_rate/market_data_freshness_seconds/backtest_queued_tasks），Prometheus 采集 + 告警规则 + Grafana provisioning 面板（9 图）。
- 可部署：GitHub Actions lint→test→build 全自动，部署为 workflow_dispatch 手动触发（secrets 待配）；部署文档与人工配置已补至 roadmap.md 下方。
