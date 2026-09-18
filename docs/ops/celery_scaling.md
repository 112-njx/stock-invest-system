# Celery 多队列多实例 + 幂等审计 + 无状态验证（G12 · P1-2c）

---

## 1. 多队列多实例

### 1.1 为什么按队列拆分 worker

拆之前是**一个** worker 消费全部 4 个队列且 `--pool=solo --concurrency=1`：
任何长任务（回测最长 45s、导出打包、备份）都会把 15s 的 `realtime_poll` **堵在队列里**，
实时行情延迟直接变成分钟级。

现在（`deploy/docker-compose.yml`）：

| 服务 | 队列 | 说明 |
|---|---|---|
| `worker-sync` | `sync,backup` | 行情同步（高频、必须低延迟）；备份任务在凌晨，共用无妨 |
| `worker-backtest` | `backtest` | 回测（长任务，子进程隔离） |
| `worker-ai` | `ai` | AI 对话/记忆/导出（长任务 + 外部 LLM 依赖） |

### 1.2 扩容

```bash
docker compose --env-file .env.docker -f deploy/docker-compose.yml up -d \
  --scale worker-sync=2 --scale worker-backtest=2 --scale worker-ai=2
```

三个服务都不映射宿主端口、无 `container_name`，可安全多实例。任务分发靠 Celery 从 Redis
队列竞争消费，**无需额外配置**（不是轮询指派，是抢占式，天然均衡）。

> 开发栈（`docker-compose.dev.yml`）保持单 worker —— 本地单实例降级可用，这是有意取舍。

---

## 2. 幂等审计

**背景**：Celery 是 **at-least-once** 语义 —— worker 被强杀、网络抖动导致 ack 丢失时，
未 ack 的任务会被**重投**。因此每个任务都必须能安全地重复执行。

| 任务 | 写库动作 | 幂等 | 依据 |
|---|---|---|---|
| `sync_tasks.kline_init` / `kline_init_fixed_indices` / `kline_incremental` | `kline_repo.upsert_bars`（UPSERT） | ✅ | 重复写同一根 K 线覆盖同值 |
| `sync_tasks.realtime_poll` | `upsert_snapshot` + Redis publish | ✅ | UPSERT；重复 publish 只是多推一帧 |
| `sync_tasks.catalog_sync` | symbols UPSERT | ✅ | 同上 |
| `sync_tasks.provider_probe` | 更新熔断状态 | ✅ | 幂等状态机 |
| **`backtest_tasks.run_backtest_task`** | `create_result` 插入新行 | ❌ → **已修复** | 见下 |
| `ai_tasks.memory_cleanup` | 删除过期低重要性记忆 | ✅ | 删除已删行为空操作 |
| `export_tasks.run_user_export` | 覆盖 ZIP + 按 task_id 更新状态行 | ✅ | 同 task_id 重跑覆盖同一文件 |
| `export_tasks.cleanup_expired_exports` | 删除过期文件 | ✅ | 同上 |
| `account_tasks.purge_deleted_accounts` | 删除超宽限期账户 | ✅ | 删除已删行为空操作 |
| `backup_tasks.*` | 写备份文件（原子改名）/ 建删临时库 | ✅ | 同名覆盖；临时库先 DROP IF EXISTS |

### 2.1 已修复：回测任务重复执行会重复落库

- **问题**：`execute_backtest` 每次执行都 `create_result`，而任务的成功态与结果在同一事务提交。
  worker 在**提交之后、ack 之前**被强杀时，Celery 会重投 → 同一个 `task_id` 再跑一遍 →
  **插入第二条 `backtest_results`**，用户在结果列表里看到两条一模一样的回测。
- **修复**：`execute_backtest` 开头加幂等短路 —— 任务已 `success` 且结果已存在时，直接返回既有
  结果（`result_id` 不变，标记 `idempotent: true`），不重算、不落库。
- **回归测试**：`tests/test_g12_idempotency.py` 2 项（重复执行命中短路且只留一条结果行；
  落库结果在重投前后逐字段一致）。
- **注意**：幂等路径返回的 `metrics` 是 `result.metrics_json`（存储形态），与首次执行的
  `compute_metrics()` 完整返回**形状不同但同源**。调用方若依赖外层字段（如 `win_rate`），
  需自行从 `metrics_json` 取或补一层转换 —— **已知不一致，记录待统一**（当前无常驻调用方：
  API 的结果端点直接读库，不经此返回值）。

---

## 3. 无状态验证

### 3.1 结论：API 可随时增减实例，**但有三处进程内状态需知晓**

| 状态 | 位置 | 判定 | 处置 |
|---|---|---|---|
| `ConnectionManager` | `app/ws/manager.py` | **有意进程内** | 每个实例只管自己的 WS 连接，消息经 Redis pub/sub 广播到所有实例（G10 已实测双实例互通）。无需迁移。 |
| `redis_client._client` | 客户端单例 | ✅ 无状态 | 只是到共享 Redis 的连接池 |
| `get_settings()` | `lru_cache` | ✅ 无状态 | 配置不可变 |
| **LLM 令牌桶 + 熔断器** | `app/services/llm/` | ⚠️ **进程内** | 见下 |
| **Provider 熔断状态** | `app/data_providers/factory.py` | ⚠️ **进程内** | 见下 |

### 3.2 ⚠️ LLM 限流/熔断是**每实例**的（记录待处理）

`LLM_RATE_LIMIT_RPM=30` 由进程内 `TokenBucket` 实现，`LLM_CIRCUIT_FAILURE_THRESHOLD` 由进程内
`CircuitBreaker` 实现。多实例下：

- **限流阈值实际变成 N×30**（N = API 实例数）—— 对 DeepSeek 的调用总量会超出预期；
- **熔断状态各实例独立** —— A 实例熔断了，B 实例仍会继续打 DeepSeek，降级不一致。

**处置**：本轮**记录未迁移**。迁移到 Redis 需要原子计数（INCR + 过期）与跨实例熔断状态同步，
是一个独立改动；当前部署规模（单实例 / 少量实例）下影响有限。
**触发迁移的条件**：API 实例数 ≥ 3，或出现 DeepSeek 侧限流投诉。

### 3.3 ⚠️ Provider 熔断同样是每实例的（影响很小）

`DataProviderFactory` 的熔断计数在进程内 → 每个 API/worker 实例独立熔断。
影响有限：熔断本身是**逐次失败累积**的保护，各实例独立熔断只是收敛稍慢，
不会导致数据错误（坏 Provider 在每个实例上都会被熔断，只是时间点不同）。
**处置**：记录，不迁移。

---

## 4. 验收对应

| 验收项 | 结果 |
|---|---|
| 队列/worker 配置支持多实例 | ✅ 三队列独立服务 + `--scale` 说明（prod compose 校验通过） |
| 幂等审计完成，不幂等任务已修复或记录 | ✅ 15 个任务全审；1 处不幂等已**修复** + 回归测试 |
| 无状态验证完成，本地状态已迁移或记录 | ✅ 三处进程内状态已识别并记录（1 处有意设计、2 处记录待处理） |
