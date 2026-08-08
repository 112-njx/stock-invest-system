# stock-backend 量化回测软件后端

FastAPI + Celery + Redis + PostgreSQL 生产级分层工程。

## 目录结构

```
stock_backend/
├── app/
│   ├── main.py            # FastAPI 入口（uvicorn app.main:app）
│   ├── api/               # 表现层：router → v1 端点 + deps 依赖
│   ├── services/          # 应用层：业务编排
│   ├── repositories/      # 数据访问层：SQLAlchemy 查询
│   ├── schemas/           # Pydantic 请求/响应模型
│   ├── models/            # SQLAlchemy 声明式模型
│   ├── core/              # 配置/日志/异常/响应/指标/request-id
│   ├── data_providers/    # 行情源抽象（可插拔，默认 EastMoney/Akshare）
│   ├── worker/            # Celery 工程（sync/backtest/ai 三队列）
│   └── utils/             # 引擎/会话/Redis/分区工具
├── alembic/               # 数据库迁移（对齐 docs/sql/*.sql）
└── tests/                 # pytest 单测
```

依赖方向：`api → services → repositories`，禁反向/循环依赖。

## 启动

```bash
# 1. 准备环境（Windows）
"D:\Pycharm\python\python.exe" -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
cp .env.example .env   # 按本机修改 DATABASE_URL / REDIS_URL

# 2. 初始化数据库（需 PostgreSQL 已启动，先建 stock_invest 库）
.venv/Scripts/python.exe -m alembic upgrade head

# 3. 启动 API
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Swagger: http://127.0.0.1:8000/docs
```

## 规范

- 代码风格：ruff + black（`ruff check . && black .`）
- 统一响应：`{code, msg, data}`（成功 code=0）
- 日志：结构化 JSON，全链路 `request-id`
