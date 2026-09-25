# stock-invest-system

**开源 A 股量化投研与回测系统**

在一套可自行托管的系统中，将交易想法转化为 Python 策略、回测、分析与监控。

*AI 投研 → 策略生成 → 回测 → 结果监控*

![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-009688)
![Vue](https://img.shields.io/badge/Vue-3.4-42b883)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20pgvector-4169E1)
![Docker Compose](https://img.shields.io/badge/Docker%20Compose-v2-2496ED)
![License](https://img.shields.io/badge/License-Apache--2.0-blue)

> ⚠️ 本项目为**量化研究辅助工具**，不构成投资建议。AI 输出、回测结果与历史数据均不能保证未来表现。投资有风险，决策需谨慎。

## 这是什么

stock-invest-system 是面向独立交易者与量化爱好者的**开源 A 股量化投研与回测系统**。本地优先、可自行托管的架构让行情数据、策略代码与部署始终由运营者掌控。

本项目整合了：

- **A 股行情**：多周期 K 线（15m / 日 / 周 / 月）、实时快照 WebSocket 推送、技术指标、自选股与支撑压力位；
- **AI 投研**：基于 DeepSeek + LangChain/LangGraph 的投研对话、深度分析（5 节点 Agent 决策链，SSE 流式呈现节点时间线）、AI 策略代码生成；
- **服务端回测**：Python 策略沙箱（RestrictedPython + 子进程资源隔离）、佣金/印花税/滑点/成交量限制、胜率/盈亏比/夏普等指标、K 线买卖点可视化与运行历史回看；
- **向量记忆系统**：pgvector 语义检索 + AES-256-GCM 加密存储，让 AI 记住你的交易体系；
- **账户安全**：双 token（access + refresh HttpOnly Cookie）、会话管理、邮箱验证/密码重置、登录暴力保护、数据导出与账户删除；
- **部署与运维**：Docker Compose 一键部署（开发/生产双栈）、自动备份（WAL 归档 + PITR + 异地同步）、可选 Prometheus/Grafana 可观测性。

它不是黑盒信号服务。策略代码、行情数据、凭据与部署始终由运营者掌控。

## V0.3 的变化

V0.3 将项目从「个人 Demo 可用」升级为「可交付真实用户的生产级作品」，共 **22 项优化**：

- **前端 13 项**：登录页视觉重设计（三卡片 3D 交互）、注册协议勾选与法律页面、双 token 设备管理、虚拟滚动列表、AI 节点时间线、数据导出/账户删除入口、自填 API Key 与用量显示等；
- **底层 9 项**：HTTPS/安全响应头、双 token 与会话管理、记忆数据加密、备份与灾难恢复、水平扩展架构、数据库时区治理、策略沙箱加固、**向量库从 ChromaDB 迁移至 pgvector** 等。

源码版本声明在 `stock_backend/pyproject.toml`（当前 `0.1.0`，开发版本 V0.3）。

## 系统架构

```
flowchart TB
 C["浏览器 Web 客户端"]
 FE["Nginx 前端服务（静态资源 + /api 反向代理）"]
 API["FastAPI / Uvicorn"]
 PG[("PostgreSQL 16 + pgvector")]
 CACHE[("Redis 缓存 / Celery Broker")]
 WORKER["Celery Worker（backtest / sync / ai / backup）"]
 BEAT["Celery Beat"]
 PROM["Prometheus（可选）"]
 GRAF["Grafana（可选）"]

 C --> FE --> API
 API --> PG
 API --> CACHE
 WORKER --> PG
 WORKER --> CACHE
 BEAT --> CACHE
 API -. 指标 .-> PROM
 PG -. Exporter .-> PROM
 PROM --> GRAF
```

| 进程 | 职责 |
|---|---|
| `api` | FastAPI HTTP 服务：认证、参数校验、业务编排；启动时单点执行 Alembic 迁移/种子/行情预同步（dev 栈） |
| `worker` | Celery worker：backtest / sync / ai / backup 四队列；生产按队列拆分为独立 worker 实例（`--scale` 水平扩容） |
| `beat` | Celery beat：周期任务分发（行情增量同步、每日备份、用量聚合等） |
| `db` | `pgvector/pgvector:pg16`：PostgreSQL + pgvector 扩展，开启 WAL 归档（支持 PITR 时间点恢复） |
| `redis` | 缓存（db0）+ Celery Broker/Result（db1/2），AOF + RDB 双持久化 |
| `nginx / frontend` | 前端静态资源托管 + `/api` 反向代理；生产启用 TLS、安全响应头与限流 |

## 快速开始

### 方案 A：Docker Compose（推荐）

前置要求：安装支持 Compose v2 的 Docker。无需安装 Node.js 或本地 Python 环境。

开发栈（源码热挂载 + uvicorn --reload，改后端代码免重建镜像）：

```bash
cp .env.docker.example .env.docker   # 首次：按需修改 POSTGRES_PASSWORD / DEEPSEEK_API_KEY 等
bash deploy/start_dev.sh             # 一键清理 + 构建 + 启动
# 或手动：
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d --build
```

访问：

- 前端：http://127.0.0.1:8081
- 后端 API / Swagger：http://127.0.0.1:8000/docs
- API 健康检查：http://127.0.0.1:8000/health

### 方案 B：本地源码

```bash
# 后端（Windows）
cd stock_backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
cp .env.example .env                # 按本机修改 DATABASE_URL / REDIS_URL / DEEPSEEK_API_KEY
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端
cd stock_frontend
npm install
npm run dev                          # http://127.0.0.1:5173
```

首次启动前，请替换环境文件中的示例值：

| 文件 | 必填项 |
|---|---|
| `stock_backend/.env` | `DATABASE_URL`（容器库 `127.0.0.1:5433`）、`REDIS_URL`、`DEEPSEEK_API_KEY`、`MEMORY_ENCRYPTION_KEY`（记忆加密，缺失会抛错） |
| `.env.docker` | `POSTGRES_PASSWORD`、`DEEPSEEK_API_KEY`、生产环境 `CORS_ORIGINS` / `SMTP_*` / `MEMORY_ENCRYPTION_KEY` / `RCLONE_REMOTE` |

生成相互独立的密钥：

```
python -c "import secrets; print(secrets.token_hex(32))"
```

> 数据库与 Redis 使用容器：`docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d db redis`（PostgreSQL 映射宿主 5433，含 pgvector 扩展）。

## 生产环境部署

```bash
cp .env.docker.example .env.docker   # 填写生产必填项
docker compose --env-file .env.docker -f deploy/docker-compose.yml up -d --build
```

生产环境规则：

- 仅在 80/443 端口暴露 Nginx（TLS 反向代理），PostgreSQL / Redis / Prometheus / Grafana 不暴露公网；
- 不使用示例密码、空加密密钥部署；`MEMORY_ENCRYPTION_KEY` 一经使用不可更换；
- 备份 PostgreSQL（WAL 归档）与 `backenddata` 卷；异地备份配置 `RCLONE_REMOTE`；
- 生产容器以非 root 用户运行、只读挂载、资源限制（加固叠加配置）；
- 部署后检查 worker 健康与 api 就绪状态（`/health`）。

完整检查清单位于 `docs/ops/disaster_recovery.md` 与 `docs/Agent_v0.3/project_constraints_v0.3.md` 第八节。

## 本地端点

所有发布端口默认绑定回环地址（`127.0.0.1`）。

| 服务 | 默认 URL | 用途 |
|---|---|---|
| 前端（dev 栈） | http://127.0.0.1:8081 | Web 客户端 + 同源 /api 反向代理 |
| 前端（根 compose） | http://127.0.0.1:8080 | 前端容器化部署 |
| 后端 API | http://127.0.0.1:8000 | API 与 Swagger 文档 |
| PostgreSQL | 127.0.0.1:5433 | 容器库直连（DBeaver / pytest） |
| Grafana | http://127.0.0.1:3000 | 仪表盘（可选，仅监控叠加启用时） |
| Prometheus | http://127.0.0.1:9090 | 指标存储（可选） |

## 可观测性

监控服务栈按设计为可选组件：

- **Prometheus** 收集 API、worker、PostgreSQL 与 Redis 指标；
- **Grafana** 将指标转化为运维仪表盘；
- 全链路 `request-id`、结构化 JSON 日志、指标埋点（列表渲染耗时、回测耗时、备份状态等）。

监控服务保持绑定 `127.0.0.1`，远程管理请使用 VPN / SSH 隧道。

## 安全模型

- **双 token**：access token（JWT，15 分钟）+ refresh token（随机串，7 天，HttpOnly Secure Cookie），轮换 + 复用检测 + Redis 黑名单吊销；
- **记忆加密**：记忆文件与向量库 content 使用 AES-256-GCM（`MEMORY_ENCRYPTION_KEY`）加密，未配置密钥时拒绝写入而非静默降级；
- **策略沙箱**：RestrictedPython + 独立子进程执行，CPU / 内存资源隔离，死循环墙钟兜底；
- **输入防护**：前端 markdown 渲染经 DOMPurify 消毒，用户内容禁止 `v-html`，CSP / X-Frame-Options 等安全响应头；
- **备份**：PostgreSQL WAL 归档 + 每日逻辑备份 + rclone 异地同步（可选），支持 PITR；
- **容器加固**：生产容器非 root、移除系统能力、只读根文件系统、资源限制；
- 宿主机端口默认绑定回环地址，公网访问在 TLS 反向代理处终止。

请按照 [SECURITY 约定](https://github.com/112-njx/stock-invest-system/security/policy) 私下报告安全漏洞，不要在公开 Issue 中包含凭据或可利用细节。

## 核心能力

| 领域 | 当前能力 |
|---|---|
| 行情 | A 股多周期 K 线（15m/日/周/月）、实时快照 WS 推送、技术指标、自选股、支撑压力位 |
| AI | DeepSeek + LangChain/LangGraph 投研对话、5 节点深度分析（SSE 节点时间线）、AI 策略生成、向量记忆检索 |
| 回测 | Python 策略（`initialize` / `on_bar`）、佣金/印花税/滑点/成交量限制、胜率/盈亏比/夏普/年化、买卖点可视化、运行历史 |
| 账户 | 双 token 会话管理、设备管理、邮箱验证/密码重置、登录暴力保护、API Key 自填、数据导出/账户删除 |
| 合规 | 用户协议/隐私政策/免责声明、注册强制同意、AI 输出免责声明、记忆数据加密与存储说明 |
| 运维 | Docker Compose 双栈、自动备份（WAL + 异地）、CI（lint/test/build）、可选监控 |

## AI 研究 Agent

AI 页采用 5 节点 Agent 决策链（`research → indicators → analysis → memory → strategy` 等），关键特性：

- **节点时间线**：深度分析时横向展示 5 节点状态（等待/运行/完成/失败），完成节点可点击展开输出，全绿后显示「分析完成」；
- **实时流式**：SSE `agent_step` 事件驱动节点状态，无轮询；
- **运行历史回看**：分页查看历史深度分析，复用时间线组件回看完整决策链；
- **策略生成**：AI 直接生成可回测的 Python 策略代码，服务端 `ast.parse` 一次性校验；
- **记忆增强**：分析前检索用户历史记忆（pgvector 向量相似度 + 重要性过滤），记忆文件加密存储。

## 开发

后端开发使用 Python 3.12：

```bash
cd stock_backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m pytest -q                 # 跑测试前需先启动 Redis + PostgreSQL 容器
ruff check app tests && black .                       # 代码风格
```

常用仓库检查命令：

```
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml config -q
docker compose --env-file .env.docker -f deploy/docker-compose.yml config -q
```

CI（`.github/workflows/ci.yml`）执行 lint → test（依赖 PostgreSQL/Redis service 容器）→ build 镜像 → 手动部署（`workflow_dispatch`，需配置 `DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_SSH_KEY` secrets）。

## 仓库结构

```
stock-invest-system/
|-- deploy/                     # Docker Compose 编排与运维配置
|   |-- docker-compose.dev.yml  # 开发栈（源码热挂载 + reload）
|   |-- docker-compose.yml      # 生产全栈（api/worker/beat/db/redis/nginx/监控）
|   |-- nginx/nginx.conf        # TLS / 安全响应头 / 限流
|   `-- prometheus/ grafana/    # 可选可观测性配置
|-- stock_backend/              # FastAPI 后端 + Celery + Alembic
|   |-- app/
|   |   |-- main.py             # FastAPI 入口（uvicorn app.main:app）
|   |   |-- api/v1/             # 路由层：auth/market/ai/backtest/strategies/memory...
|   |   |-- services/           # 业务编排：agent/backtest/backup/email/sync...
|   |   |-- repositories/       # 数据访问层（SQLAlchemy）
|   |   |-- models/             # 声明式模型（含 pgvector 向量列）
|   |   |-- core/               # 配置/日志/响应/指标/request-id
|   |   |-- worker/             # Celery 工程（backtest/sync/ai/backup 队列）
|   |   |-- data_providers/     # 行情源抽象（默认 EastMoney / AkShare）
|   |   `-- utils/              # 引擎/会话/Redis/分区工具
|   |-- alembic/                # 数据库迁移（当前 head 0018）
|   `-- tests/                  # pytest 单测
|-- stock_frontend/             # Vue 3 + TypeScript + Vite 前端
|   |-- src/
|   |   |-- views/              # 登录/行情/AI/密码重置/邮箱验证等页面
|   |   |-- components/         # AI 面板/交易图表/虚拟滚动列表
|   |   `-- api/                # axios 封装（含 401 自动刷新）
|   `-- Dockerfile              # 多阶段构建 → nginx 托管
|-- docs/                       # 开发文档（Agent 指南、API 文档、运维手册）
`-- .github/workflows/ci.yml    # CI：lint → test → build
```

## 文档

| 主题 | 文档 |
|---|---|
| 开发参考指南（V0.3，22 项优化） | `docs/Agent_v0.3/Reference_guide_v0.3.md` |
| 项目约束与需人工配置事项 | `docs/Agent_v0.3/project_constraints_v0.3.md` |
| API 文档 | `docs/Agent_backend/api-docs.md` |
| 前端代码说明 | `docs/Agent_frontend/Agent_code.md` |
| 灾难恢复手册 | `docs/ops/disaster_recovery.md` |
| 登录页设计规格 | `docs/Agent_v0.3/login_page_design_v0.3.md` |

## 参与贡献

提交 Pull Request 前请阅读 `docs/Agent_v0.3/Reference_guide_v0.3.md` 与仓库文档约定：保持路由轻量、遵循分层依赖（`api → services → repositories`）、为高风险变更提供针对性测试。

## 许可证与法律声明

- 本项目采用 **Apache License 2.0** 许可证（见 [LICENSE](LICENSE)）。
- 本项目为**量化研究辅助工具，非证券投资咨询服务**。AI 输出、回测结果与历史数据仅供参考，不构成投资建议；投资有风险，决策需谨慎。
- 仅用于合法研究、教育与合规使用。不得用于欺诈、市场操纵、规避制裁、洗钱或其他违法活动。运营者有责任遵守其部署或使用本软件的每个司法辖区所适用的法律与数据法规。

**本项目不提供法律、税务、投资、金融或监管建议。** 历史数据、回测、模拟结果、AI 输出、指标与策略示例均不能保证未来表现。在法律允许的范围内，维护者与贡献者不对因使用或误用本软件导致的交易损失、数据丢失、服务中断、第三方故障、安全事件或监管后果承担责任。

## 致谢

本项目建立在强大的开源生态之上，特别感谢以下项目的维护者和贡献者：

- [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy](https://www.sqlalchemy.org/) · [Pydantic](https://docs.pydantic.dev/) · [Alembic](https://alembic.sqlalchemy.org/)
- [Celery](https://docs.celeryq.dev/) · [Redis](https://redis.io/) · [PostgreSQL](https://www.postgresql.org/) / [pgvector](https://github.com/pgvector/pgvector)
- [Vue](https://vuejs.org/) · [Vite](https://vitejs.dev/) · [Pinia](https://pinia.vuejs.org/) · [lightweight-charts](https://github.com/tradingview/lightweight-charts)
- [LangChain](https://www.langchain.com/) / [LangGraph](https://www.langchain.com/langgraph) · [DeepSeek](https://www.deepseek.com/) · [AkShare](https://akshare.akfamily.xyz/) · [RestrictedPython](https://github.com/zopefoundation/RestrictedPython)

<sub>如果本项目对您有帮助，一个 GitHub Star 就是最大的支持。</sub>
