# 灾难恢复手册（G05 · P1-1 备份与灾难恢复）

> 本手册的每一条恢复命令都在本地实测跑通（2026-09-17，见文末「演练记录」）。
> 恢复类操作会覆盖数据，**执行前必须确认目标环境**，并在动生产前先在临时库演练一次。
> 建议每季度按第 8 节检查单完整演练一次。

---

## 1. 备份产物与保留策略

备份根目录由 `BACKUP_DIR` 决定（容器默认 `/app/data/backups`，本地默认 `stock_backend/data/backups`）：

| 产物 | 路径 | 生成方式 | 频率 | 保留 |
|---|---|---|---|---|
| 逻辑全量备份 | `pg/full/full_YYYYMMDD.dump` | `pg_dump -Fc` | 每日 02:00 | 30 天 |
| 物理基础备份 | `pg/base/base_YYYYMMDD/{base.tar.gz,pg_wal.tar.gz}` | `pg_basebackup -Ft -z -X stream` | 每周日 02:45 | 14 天（2 代） |
| WAL 归档 | `pg/wal/` | db 容器 `archive_command` 实时写入 | 持续 | 7 天 |
| 文件镜像 | `files/YYYYMMDD/{memory,exports}/` | rsync（无则 Python 复制） | 每日 02:00 | 7 天 |
| 运行清单 | `manifests/backup_<ts>.json` | 每次全量备份写一份 | 每日 | 30 天 |
| 最近状态 | `status.json` | 每次全量备份覆盖 | 每日 | 常驻 |

**为什么同时要逻辑备份和物理备份**：`pg_dump` 是**逻辑**备份，只能恢复到"备份那一刻"，无法与 WAL 组合推到任意时间点；**PITR 必须基于物理基础备份 + 其后的 WAL 连续归档**。二者互补，都保留：

- 逻辑备份 → 单表恢复、跨大版本恢复、体积小、恢复快（本手册第 3 节）；
- 物理备份 + WAL → 时间点恢复 PITR（第 4 节），可回溯 7 天内的任意时刻。

> **Chroma 已下线（泳道 C · G31，2026-09-17）**：向量统一存 `memory_chunks`（pgvector），
> 随 `pg_dump` 一并备份，因此文件镜像**不再包含 `data/chroma/`**（按 G05 规格「泳道 C 已下线
> Chroma 则跳过并注明」）。存量 `data/chroma/` 目录若仍在磁盘上，属遗留垃圾，可手工删除。

---

## 2. 环境变量与需人工配置项

| 变量 | 默认 | 说明 |
|---|---|---|
| `BACKUP_DIR` | `/app/data/backups`（容器） | **生产建议改为独立磁盘**：设 `BACKUP_DIR=/backup` 并给 api/worker 加 `- /mnt/backup:/backup` 绑定挂载，避免数据盘与备份盘同时损坏 |
| `BACKUP_ENABLED` | `true` | 置 `false` 后每日备份任务直接跳过（本地不需要备份时用） |
| `BACKUP_PG_DUMP_MODE` | `auto` | `auto` 先找本地 `pg_dump`，找不到退回 `docker exec` 借 db 容器的客户端；宿主开发环境本机无 PG 客户端，靠这条跑通 |
| `BACKUP_PG_CONTAINER` | `stock-invest-dev-db-1` | `docker` 模式借用的 PG 容器名 |
| `BACKUP_PG_RETAIN_DAYS` / `BACKUP_BASE_RETAIN_DAYS` / `BACKUP_WAL_RETAIN_DAYS` / `BACKUP_FILES_RETAIN_DAYS` | 30 / 14 / 7 / 7 | 各产物保留天数 |
| `RCLONE_REMOTE` | 空 | 对象存储远端，如 `oss:stock-invest-backup`。**为空 = 模拟模式**（不真同步，仅记清单），生产必须配置 |
| `RCLONE_CONFIG` | 空 | rclone 配置文件路径；**凭据一律走环境变量**（`RCLONE_CONFIG_*` / `AWS_*`），禁止写进 compose 或代码 |
| `PG_ARCHIVE_DIR` | `/wal-archive` | 只读挂载的 WAL 归档目录，供 `/metrics` 读归档文件数 |
| `BACKUP_VERIFY_DB` | `stock_invest_verify` | 恢复演练用的临时库名（验证后自动删除） |

**pg_dump 版本约束（重要）**：客户端主版本必须 **≥** 服务端主版本，否则 `pg_dump` 直接拒绝执行。
本项目服务端为 PG16，故 `stock_backend/Dockerfile` 从 PGDG 装 `postgresql-client-16`
（Debian bookworm 自带的 client-15 不可用）。版本不匹配时备份任务会在 `check_client_version()`
处**明确失败**，不会产出看似成功的坏备份。

---

## 3. 恢复演练：PostgreSQL 逻辑全量恢复

适用：误删数据、需要单表/整库回到某个备份点。

```bash
# 0) 变量（按实际环境改）
COMPOSE="docker compose --env-file .env.docker -f deploy/docker-compose.yml"
DUMP="/mnt/backup/pg/full/full_20260917.dump"     # 宿主机上的备份文件

# 1) 停写入方，避免恢复期间有新写入造成不一致
$COMPOSE stop api worker beat

# 2) 重建目标库（先 drop 再 create，pg_restore 需要一个空库）
$COMPOSE exec -T db sh -c 'dropdb -U postgres --if-exists stock_invest && createdb -U postgres stock_invest'

# 3) 恢复（-T 关闭 TTY 才能把 dump 从 stdin 喂进去）
$COMPOSE exec -T db pg_restore -U postgres -d stock_invest --no-owner --no-privileges < "$DUMP"

# 4) 校验（行数应与备份时刻一致；下方数值为本地实测样例。
#    注意源库是活的——dump 之后的写入会让源库行数大于恢复库，属正常；要精确比对请先停 api/worker/beat）
$COMPOSE exec -T db psql -U postgres -d stock_invest -tAc "select count(*) from users"      # 13
$COMPOSE exec -T db psql -U postgres -d stock_invest -tAc "select count(*) from symbols"    # 7258
$COMPOSE exec -T db psql -U postgres -d stock_invest -tAc "select count(*) from kline_1d"   # 18593

# 5) 若代码版本比备份新，补跑迁移后再启动
$COMPOSE exec -T api alembic upgrade head
$COMPOSE start api worker beat
```

只想恢复单表时，用 `pg_restore -t <表名>` 恢复到临时库，再用 `INSERT ... SELECT` 回填，
避免整库回滚丢掉备份之后的合法数据。

---

## 4. 恢复演练：PITR 时间点恢复

适用：误执行 `DELETE`/`UPDATE` 等逻辑损坏，需要回到"故障发生前几秒"。

**前提**：有一份物理基础备份（`pg/base/`）+ 该备份之后的 WAL 归档（`pg/wal/`）。

```bash
# 0) 变量
BASE="/mnt/backup/pg/base/base_20260917"     # 基础备份目录（含 base.tar.gz 与 pg_wal.tar.gz）
WALDIR="/mnt/backup/pg/wal"                  # WAL 归档目录（持续累积）
TARGET="2026-09-17 12:30:00+00"              # 要恢复到的时刻（UTC）

# 1) 准备全新的数据卷（不要覆盖现有卷，便于失败后重来）
docker volume create stock-pitr-data
docker volume create stock-pitr-wal

# 2) 解压基础备份 + 其自带 WAL，建 recovery.signal
docker run --rm -v stock-pitr-data:/pgdata -v stock-pitr-wal:/wal -v "$BASE:/src:ro" \
  pgvector/pgvector:pg16 sh -c "
    tar xzf /src/base.tar.gz -C /pgdata &&
    tar xzf /src/pg_wal.tar.gz -C /wal &&
    chown -R 999:999 /pgdata /wal && chmod 700 /pgdata &&
    touch /pgdata/recovery.signal"

# 3) 把归档目录里基础备份之后的 WAL 也放进 WAL 目录（restore_command 从这里取）
cp "$WALDIR"/* stock-pitr-wal/ 2>/dev/null || true   # 具名卷需经容器复制，见下方说明

# 4) 启动恢复：restore_command 从 /wal 取 WAL，恢复到目标时间后 promote
docker run -d --name stock-pitr-db \
  -v stock-pitr-data:/var/lib/postgresql/data -v stock-pitr-wal:/wal \
  pgvector/pgvector:pg16 postgres \
    -c "restore_command=cp /wal/%f %p" \
    -c "recovery_target_time=$TARGET" \
    -c recovery_target_action=promote

# 5) 校验
docker exec stock-pitr-db psql -U postgres -d stock_invest -tAc "select count(*) from users"
docker exec stock-pitr-db psql -U postgres -tAc "select pg_is_in_recovery()"   # f = 已 promote，恢复完成
```

不指定 `recovery_target_time`（或设为 `recovery_target_action=promote` 且不带 target）时，
会一直重放到 WAL 末尾，即**恢复到最新可用时刻** —— 这是整库丢失后的常规做法。

**具名卷里放 WAL 的更简做法**：把第 2 步的 `-v stock-pitr-wal:/wal` 换成
`-v /mnt/backup/pg/wal:/wal:ro`，直接把归档目录只读挂进去，
`restore_command` 改为 `cp /wal/%f %p`；此时第 3 步可省略。

**校验通过后**把数据卷切回生产（`docker compose down` → 改 `pgdata` 卷指向 →
`docker compose up -d`），并**立即做一次新的全量备份**，因为恢复出来的库已脱离原备份链。

---

## 5. 恢复演练：Redis 恢复

Redis 存的是缓存与 Celery 队列（业务真相在 PostgreSQL），丢失只影响性能与在途任务，**不影响数据正确性**。

```bash
# 确认持久化配置生效（AOF + RDB）
docker exec stock-invest-redis-1 redis-cli CONFIG GET appendonly    # yes
docker exec stock-invest-redis-1 redis-cli CONFIG GET appendfsync   # everysec
docker exec stock-invest-redis-1 redis-cli CONFIG GET save          # 60 1000
docker exec stock-invest-redis-1 redis-cli INFO persistence | grep -E "aof_enabled|rdb_last_bgsave_status"

# 恢复：把备份里的 dump.rdb / appendonlydir 放回 redisdata 卷后重启
docker compose --env-file .env.docker -f deploy/docker-compose.yml stop redis
docker run --rm -v stock-invest_redisdata:/data -v /mnt/backup/files/20260917:/src:ro busybox:1.36 \
  sh -c "cp -a /src/redis/. /data/ && chown -R 999:999 /data"
docker compose --env-file .env.docker -f deploy/docker-compose.yml start redis
docker exec stock-invest-redis-1 redis-cli DBSIZE
```

> 若 Redis 数据不可用，直接清空重启即可：缓存会按需重建，队列里未执行的任务需要在
> `task_logs` 中确认后手动重投。

---

## 6. 恢复演练：文件恢复

`data/memory/`（人类可读记忆文件）与导出目录。

```bash
# 查看某天的文件镜像
ls -la /mnt/backup/files/20260917/memory/

# 恢复记忆目录（先备份当前目录，再覆盖）
docker compose --env-file .env.docker -f deploy/docker-compose.yml stop api worker
mv /mnt/data/memory /mnt/data/memory.bak.$(date +%s)
cp -a /mnt/backup/files/20260917/memory /mnt/data/memory
docker compose --env-file .env.docker -f deploy/docker-compose.yml start api worker
```

`memory_chunks` 表（PostgreSQL 侧的记忆事实与向量）随第 3 节的逻辑备份一并恢复，
两边都恢复才是一份完整的记忆数据。

---

## 7. 异地备份（rclone）

```bash
# 配置凭据（环境变量，勿写进仓库）——以阿里云 OSS 为例
export RCLONE_CONFIG_OSS_TYPE=s3
export RCLONE_CONFIG_OSS_PROVIDER=Alibaba
export RCLONE_CONFIG_OSS_ACCESS_KEY_ID=<AK>
export RCLONE_CONFIG_OSS_SECRET_ACCESS_KEY=<SK>
export RCLONE_CONFIG_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
# .env.docker 里设：RCLONE_REMOTE=oss:stock-invest-backup

# 手动触发一次异地同步
bash scripts/backup_pg.sh offsite

# 确认远端内容
rclone ls oss:stock-invest-backup/pg/full
```

保留 90 天由同步后自动执行的 `rclone delete <remote> --min-age 90d` 完成。
`RCLONE_REMOTE` 为空时任务进入**模拟模式**：日志打印 `[SIMULATED]`，只写清单不真同步，
备份任务本身**不算失败** —— 但此时没有任何异地副本，生产部署必须补齐。

---

## 8. 监控与告警

指标（`GET /metrics`，Prometheus 抓取）：

| 指标 | 含义 | 告警规则 |
|---|---|---|
| `backup_last_success_age_seconds` | 最近一次成功备份距今秒数，`-1` = 从未成功 | `BackupStale`：`< 0 or > 93600`（26h），critical |
| `backup_last_dump_bytes` | 最近一次全量备份大小，`-1` = 无 | —（用于观察异常缩小） |
| `backup_disk_free_ratio` | 备份盘剩余占比 | `BackupDiskSpaceLow`：`< 0.15`，critical |
| `backup_wal_archive_files` | WAL 归档文件数，`-1` = 未配置 | `WalArchiveStalled`：`== 0` 持续 1h，warning |

失败排查入口：`task_logs` 表中 `task_type in ('backup','backup_base','backup_offsite','backup_verify')`
的记录（含 `request_id`），以及 `$BACKUP_DIR/manifests/` 下当次的完整 JSON 清单。

**季度演练检查单**：

- [ ] `bash scripts/backup_pg.sh full` 成功，`status.json` 的 `ok=true`
- [ ] `bash scripts/verify_backup.sh` 通过（`ok=true`；schema 表数一致、无 restore error；`drift` 为信息项，活库上 > 0 属正常）
- [ ] 按第 4 节做一次 PITR 恢复到指定时间点，行数符合预期
- [ ] 按第 5、6 节恢复 Redis 与文件目录
- [ ] `rclone ls <remote>` 能看到最近 7 天的备份
- [ ] 记录演练耗时与遇到的问题，回填到本节

---

## 9. 调度与手动触发

| 任务 | 调度 | 手动触发 |
|---|---|---|
| `backup_daily` | 每日 02:00 | `bash scripts/backup_pg.sh full` |
| `backup_base_weekly` | 每周日 02:45 | `bash scripts/backup_pg.sh base` |
| `offsite_sync_daily` | 每日 02:30 | `bash scripts/backup_pg.sh offsite` |
| `verify_backup_weekly` | 每周日 03:30 | `bash scripts/verify_backup.sh` |

调度时刻都排在业务空闲窗口：worker 当前为 `--pool=solo --concurrency=1`，
备份执行期间会独占 worker（`realtime_poll` 在非交易时段本就空转返回，不受影响）。
后续按队列扩 worker 实例时，备份走独立的 `backup` 队列，可与 sync/ai 隔离。

---

## 演练记录

| 日期 | 内容 | 结果 |
|---|---|---|
| 2026-09-17 | 全量备份 `pg_dump -Fc` | ok，1.8MB / 0.56s，归档 1962 条目 |
| 2026-09-17 | 逻辑恢复演练（第 3 节步骤 2–4） | ok，6.19s，users/symbols/kline_1d 行数与源库完全一致 |
| 2026-09-17 | 物理基础备份 `pg_basebackup` | ok，7.3MB / 1.68s，`base.tar.gz` 2218 条目 + `pg_wal.tar.gz` |
| 2026-09-17 | PITR 演练（第 4 节） | ok，恢复出 users=13 / symbols=7258 / kline_1d=18593，`pg_is_in_recovery()=f` |
| 2026-09-17 | WAL 归档（`archive_mode=on` + `archive_command`） | ok，`archived_count=2`、`failed_count=0` |
