# 读写分离 + Redis 高可用（G11 · P1-2b）运维手册

> 本地单实例**无需任何配置**即可运行（两条链路都有降级），本文档面向生产部署。

---

## 1. PostgreSQL 读写分离

### 1.1 路由约定

| 链路 | 会话来源 | 承载 |
|---|---|---|
| **主库** | `app/api/deps.py::get_db` / `app/utils/db.py::get_session` | 一切写入 + **全部用户数据**（关注/策略/会话/记忆/通知） |
| **只读从库** | `get_read_db` / `get_read_session` | 纯行情读（K线/快照/指标/目录搜索） |

**为什么用户数据一律走主库**：数据量小、一致性要求高，且必须支持"读己之写"——
关注列表刚加完就查、策略刚存完就回测，走从库会因复制延迟出现"刚存的东西不见了"。

**为什么用显式路由而不是 SQLAlchemy 透明 `binds`**：仓储层本就以 `db: Session` 为参数，
调用方决定用哪个会话。透明 binds 会把"同一事务里读写被拆到不同节点"的隐患藏起来，
出问题时极难排查。显式路由让每条链路在代码里一眼可见。

### 1.2 启用步骤

1. 准备一个 PostgreSQL 流复制从库（`pg_basebackup` + `primary_conninfo`，或云厂商只读实例）。
   **从库需与主库同大版本**（本项目 PG16）。
2. 在 `.env.docker` 设置：
   ```
   DATABASE_READ_URL=postgresql+psycopg2://<user>:<pass>@<replica-host>:5432/stock_invest
   ```
3. 重启 api / worker。启动日志出现 `read-write splitting enabled: reads -> replica` 即生效；
   未配置时为 `DATABASE_READ_URL not set, reads fall back to primary (single-instance degrade)`。

**回滚**：删掉 `DATABASE_READ_URL` 重启即可 —— `read_engine` 会重新复用主库引擎，
行为与开启前完全一致，无需改代码。

### 1.3 注意事项

- **复制延迟**：从库落后主库期间，行情数据可能比主库旧几秒。行情本身是秒级更新，可接受；
  若发现"K线少最后一根"，先查从库延迟（`SELECT now() - pg_last_xact_replay_timestamp()`）。
- **`pool_pre_ping=True` 是必需项**：主从切换/从库重启后连接池里的旧连接会失效，
  pre_ping 保证取到的是活连接。
- **写入误路由到从库会在从库上直接报错**（只读实例会拒绝写），不会静默丢数据。

---

## 2. Redis Sentinel

### 2.1 启用步骤

一主两从 + 至少三个 Sentinel（**生产必须 ≥3 个 Sentinel**，quorum 才具备真正的容错能力）：

```yaml
# docker-compose 片段（示意，按实际拓扑调整）
  redis-master:
    image: redis:7-alpine
  redis-replica-1:
    image: redis:7-alpine
    command: ["redis-server", "--replicaof", "redis-master", "6379"]
  redis-replica-2:
    image: redis:7-alpine
    command: ["redis-server", "--replicaof", "redis-master", "6379"]
  sentinel-1:
    image: redis:7-alpine
    command: >
      sh -c 'printf "port 26379\nsentinel monitor mymaster redis-master 6379 2\n
      sentinel down-after-milliseconds mymaster 5000\nsentinel failover-timeout mymaster 10000\n
      sentinel resolve-hostnames yes\n" > /tmp/s.conf && redis-server /tmp/s.conf --sentinel'
```

`.env.docker`：
```
REDIS_SENTINEL_HOSTS=sentinel-1:26379,sentinel-2:26379,sentinel-3:26379
REDIS_SENTINEL_MASTER=mymaster
REDIS_SENTINEL_ENABLED=true
# REDIS_SENTINEL_PASSWORD=<sentinel 自身密码，如启用 requirepass>
```

### 2.2 已实测验证的内容

| 项 | 状态 |
|---|---|
| 未配置 Sentinel → 直连 `REDIS_URL`（降级，行为与改造前一致） | ✅ 自动化测试 + 真实 Redis |
| 开关打开但未配地址 → 降级直连并告警 | ✅ 自动化测试 |
| Sentinel 地址不可达 → **构造不抛错**，仅在使用时失败（不拖垮 API 启动） | ✅ 自动化测试 |
| Sentinel 主节点发现 + 经其读写数据 | ✅ 真实容器端到端（1 sentinel + 1 master，`sentinel get-master-addr-by-name` 返回主节点，应用 `_build_client()` 读写成功） |

### 2.3 ⚠️ 尚未验证：自动故障转移

**最小化本地拓扑（1 sentinel + 1 master + 2 replica）下，kill 主节点后 Sentinel 未把主标记为
`s_down`（`flags` 仍为 `master`），35s 内未发生提升**。根因未定位（已排除：Sentinel 能看到
2 个 replica、`down-after-milliseconds` 已设为 3s）。

**这意味着"一主两从自动故障转移"目前只是配置就绪，未经实证。** 上线前必须：

1. 按 2.1 搭 ≥3 Sentinel 的**真实拓扑**；
2. 手工触发一次切换：`docker kill <master>` → `sentinel get-master-addr-by-name mymaster`
   应返回新节点 → 应用侧不做任何重启，直接 `SET`/`GET` 应成功；
3. 记录切换耗时到本文档。

> 本地最小化拓扑不做故障转移验证的另一个原因：单 Sentinel 本身是单点，其切换行为不代表
> 生产拓扑（quorum/多数派语义不同），在本机"验证通过"反而可能给出错误信心。

---

## 3. 监控建议（配合 P1-7，未实现则记录待衔接）

| 指标 | 来源 | 告警阈值建议 |
|---|---|---|
| 从库复制延迟（秒） | `SELECT now() - pg_last_xact_replay_timestamp()` | > 30s |
| 当前读库角色 | `SELECT pg_is_in_recovery()` | 主库返回 false 属正常 |
| Redis 主节点地址 | `SENTINEL get-master-addr-by-name mymaster` | 变化即告警（发生了切换） |
| Sentinel 可达数 | 各 Sentinel `PING` | < 多数派 |
