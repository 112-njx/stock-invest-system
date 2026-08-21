# 项目约束与遗留问题

> 集中维护项目的已知遗留问题、技术决策、环境配置注意事项、后端能力对接清单。
> 每波开发完成后追加新问题，已解决的标记 [已解决] 并注明版本，不删除（保留历史追溯）。
> 所有波次的开发提示词均应引用本文件，开发Agent必须阅读并规避相关约束。

---

## 一、已知遗留问题

### 2. K线 ts / 快照 updated_at 列为 timestamp without time zone（naive）
- **状态**：未解决，代码层用 as_utc 归一规避
- **影响范围**：所有涉及时间比较、缓存失效、WS增量推送、数据新鲜度计算的开发
- **说明**：ORM 声明 `tz=True` 但实际 PostgreSQL 列为 naive（迁移 0001 遗留）。当前在比较/序列化边界用 `as_utc()` 归一，未改表结构（改动面大、风险高）。
- **处理建议**：若后续统一为 timestamptz，需另做迁移评估，涉及所有时间字段的存量数据转换。开发中涉及时间比较时，必须调用 `as_utc()` 归一后再比较，禁止直接比较 naive 和 aware datetime。

### 3. WS 推送未做 updated_at 变化去重
- **状态**：未解决，当前由订阅集合过滤
- **影响范围**：前端WS接入、WS优化
- **说明**：roadmap 2.2 建议"对比 updated_at 变化仅推更新的"，当前实现是 realtime_poll 每轮写入即发布、由订阅集合过滤（每5s一轮，量小可接受）。
- **处理建议**：如需精确去重，可在 publisher 层加"价格变化才发布"逻辑，或前端收到后自行 diff。当前不影响功能正确性，仅可能有少量冗余推送。

### 4. WS 依赖跨进程桥接（Celery worker 发布，API 进程监听转发）
- **状态**：设计如此，非bug
- **影响范围**：前端WS接入、本地开发调试
- **说明**：realtime_poll 在 Celery worker 进程运行，通过 Redis pub/sub 发布；API 进程监听 Redis 频道后转发给 WebSocket 客户端。单进程本地开发（仅 uvicorn，无 worker/beat）时不会主动产生行情推送。
- **处理建议**：本地开发WS功能时，必须同时启动 Celery worker + beat，或前端降级为 HTTP 轮询（7s间隔）。前端WS客户端必须实现断线降级逻辑。

### 5. catalog_sync 手动端点在无 worker 环境任务停留 queued
- **状态**：设计如此，非bug
- **影响范围**：涉及 Celery 任务的开发、本地调试
- **说明**：`POST /api/v1/admin/catalog/sync` 会真实入队，但如果没有启动 Celery worker，任务会停留在 queued 状态不执行。
- **处理建议**：本地调试涉及 Celery 异步任务的功能时，必须启动 worker。生产环境 worker 常驻运行，无此问题。

---

## 二、已确认的技术决策

1. **缓存层仅 Redis + PostgreSQL，不引入进程内内存缓存**——所有缓存数据走 Redis，避免多进程状态不一致。
2. **DataProvider 优先级链**：`[eastmoney, sina, ths]`，每源独立熔断（半开探测），可通过 `DATA_PROVIDER_PRIORITY` 环境变量调整。
3. **K线缓存键设计**：`kline:{symbol_id}:{period}:{limit}`（按最近N根，不含完整日期范围），TTL 300s，新K线写入时删除对应键。
4. **快照缓存**：`snapshot:{symbol_id}`，TTL 300s，存完整14字段，非交易时段正常返回并标注 data_age_seconds。
5. **前端不计算复杂指标**：MACD/KDJ等技术指标全部后端计算，前端只渲染。
6. **Agent 记忆本地存储**：ChromaDB + HashEmbedding（V0.2第二波计划升级为 ONNX MiniLM），不写入中心数据库。

---

## 三、环境配置注意事项

### 必须配置
- **ADMIN_USERNAMES**：逗号分隔的用户名列表（如 `admin,user1`），启动时自动对应用户置 `is_admin=True`。不配则所有 `/admin/*` 端点返回 403。
- **DEEPSEEK_API_KEY**：AI对话功能必需，不配则走降级文案。
- **JWT_SECRET_KEY**：用户鉴权必需。

### 有默认值（无需强制改）
| 配置项 | 默认值 | 说明 |
|---|---|---|
| DATA_PROVIDER_PRIORITY | eastmoney,sina,ths | DataProvider优先级链 |
| PROVIDER_CIRCUIT_FAILURE_THRESHOLD | 3 | 熔断失败阈值 |
| PROVIDER_CIRCUIT_COOLDOWN | 60 | 熔断冷却时间（秒） |
| PROVIDER_PROBE_INTERVAL | 60 | 熔断恢复探测间隔（秒） |
| SNAPSHOT_CACHE_TTL | 300 | 快照缓存TTL（秒） |
| KLINE_CACHE_TTL | 300 | K线缓存TTL（秒） |
| SEARCH_CACHE_TTL | 3600 | 搜索结果缓存TTL（秒） |
| WATCHLIST_CACHE_TTL | 300 | 关注列表缓存TTL（秒） |
| REALTIME_POLL_INTERVAL | 5 | 实时行情轮询间隔（秒） |

```

---

## 四、后端能力对接清单（前端开发参考）

> V0.2 第一波后端已完成的能力，前端 V0.2 对应阶段开发时必须对接。

### 4.1 WebSocket 实时行情推送（对应前端阶段二）

**后端状态**：已完成（V0.2第一波阶段二）

| 项目 | 说明 |
|---|---|
| 端点 | `ws://{host}/api/v1/ws/market?token={jwt_token}` |
| 鉴权 | query 参数 `token`（JWT），或连接后首条消息 `{"action":"auth","token":"..."}` |
| 心跳 | 服务端每 15s 发 `{"type":"ping"}`，客户端需回 `{"type":"pong"}`，30s 无响应服务端断开 |
| 订阅 | `{"action":"subscribe","symbol_ids":[1,2,3]}` |
| 取消订阅 | `{"action":"unsubscribe","symbol_ids":[1,2]}` |
| 断线补拉 | 重连后发 `{"action":"sync","since":"2026-08-21T10:30:00Z"}`，服务端返回该时间后更新的快照 |
| 推送消息 | `{"type":"snapshot","data":{"1":{"price":...,"change_pct":...,"updated_at":"..."}}}` |
| K线推送 | `{"type":"kline","symbol_id":1,"period":"15m","bar":{"ts":...,"open":...}}` |
| 错误消息 | `{"type":"error","code":"AUTH_FAILED","message":"..."}` |
| 降级策略 | WS不可用时降级为 HTTP 轮询 `GET /api/v1/snapshot?symbols=id1,id2`（7s间隔），重连成功后切回WS |
| 本地开发注意 | 必须同时启动 Celery worker + beat，否则WS无数据推送（realtime_poll 在 worker 中运行） |

### 4.2 搜索接口增强（对应前端阶段三）

**后端状态**：已完成（V0.2第一波阶段三）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/symbols/search?keyword=xxx&type=stock&limit=20` |
| 新增参数 | `type`（stock/etf/index，可选）、`limit`（默认20） |
| 新增返回字段 | `is_catalog`（bool：是否仅在目录中未同步K线）、`has_kline`（bool：是否已有K线数据） |
| 搜索逻辑 | 三层：精确代码匹配 > 已同步K线标的 > 仅目录标的；本地无结果时外部回退（akshare） |
| 前端展示建议 | 分组展示：第一组"已同步"（has_kline=true），第二组"未同步"（is_catalog=true，灰色标注"添加后同步"） |
| 搜索缓存 | 后端已缓存 `search:{type}:{keyword}`，TTL 1h，前端无需额外缓存 |

### 4.3 关注列表同步状态（对应前端阶段三）

**后端状态**：已完成（V0.2第一波阶段三）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/watchlist` |
| 新增返回字段 | `sync_status`（pending/syncing/done/failed）、`last_synced_at`（ISO时间） |
| 自动同步 | 添加关注时后端自动触发 `kline_init` 异步任务，无需前端手动调用 |
| 前端展示建议 | 每行显示同步状态图标：syncing=旋转loading，done=无图标，failed=黄色感叹号（hover提示"点击重试"） |
| 重试 | 失败行点击可重新触发同步（需前端调用对应接口或后端提供重试端点） |
| 关注列表缓存 | 后端已缓存 `watchlist:{user_id}` + `watchlist_snap:{user_id}`，TTL 300s |

### 4.4 快照数据新鲜度（对应前端阶段一/三）

**后端状态**：已完成（V0.2第一波阶段一）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/snapshot?symbols=id1,id2` |
| 新增返回字段 | `data_age_seconds`（int：当前时间与 updated_at 的差值，秒） |
| 前端展示建议 | 交易时段：`data_age < 300` 显示"HH:MM:SS更新"（绿色），`> 300` 显示黄色"数据延迟"；非交易时段：显示"收盘 HH:MM更新"（灰色），不显示"--" |
| 非交易时段 | 后端正常返回缓存快照（TTL 300s），前端不应因非交易时段显示空白 |

### 4.5 固定指数预同步状态（对应前端阶段一）

**后端状态**：已完成（V0.2第一波阶段一）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/sync-status?scope=fixed_indices` |
| 返回 | `{status: running/done/failed, progress: 35, total: 49, message: "..."}` |
| 触发时机 | docker-entrypoint.sh 启动时自动检查，超过1天无数据则触发预同步 |
| 前端展示建议 | 行情页加载时先查此接口，running 时显示顶部进度条"数据同步中（X/49）"，G/H区显示骨架屏，done后自动刷新 |

### 4.6 DataProvider 健康状态（管理端点）

**后端状态**：已完成（V0.2第一波阶段四）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/admin/providers/health`（需管理员权限） |
| 返回 | 各Provider状态：available/circuit_open/failed，失败次数，最近成功时间 |
| 用途 | 运维排查行情数据异常时使用，前端普通用户无需对接 |

### 4.7 标的目录手动同步（管理端点）

**后端状态**：已完成（V0.2第一波阶段三）

| 项目 | 说明 |
|---|---|
| 端点 | `POST /api/v1/admin/catalog/sync`（需管理员权限） |
| 功能 | 手动触发全A股+ETF目录同步（akshare），异步任务 |
| 注意 | 无 worker 环境任务停留 queued，需启动 worker |
| 定时 | Celery beat 每日凌晨 3:00 自动执行 |

---

## 五、数据库迁移记录

| 版本 | 文件 | 内容 | 状态 |
|---|---|---|---|
| 0001 | 初始建表 | 24表+K线分区 | 已执行 |
| 0002 | backtest_tasks 扩展 | period/start_ts/end_ts/fill_on | 已执行 |
| 0003 | agent_extensions | user_agents/agent_runs/agent_steps/memory_chunks | 已执行 |
| 0004 | 0004_v02_wave1.py | users.is_admin、sync_status表、symbols.is_catalog+索引、user_watchlist.sync_status/last_synced_at | 已执行（本地），部署环境由 entrypoint 自动迁移 |

迁移执行命令：
```powershell
cd D:\stock-invest-system\stock_backend
.venv\Scripts\alembic.exe current    # 查看当前版本
.venv\Scripts\alembic.exe history    # 查看迁移链
.venv\Scripts\alembic.exe upgrade head  # 升级到最新
```

---

## 六、变更日志

- **2026-08-21**：初始创建，整理 V0.2 第一波遗留问题5项、技术决策6项、环境配置、后端能力对接清单7项、迁移记录。
