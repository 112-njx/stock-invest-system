# SDK 桥第一阶段优化（2026-11-06）

## 行为

- 缓存状态锁只保护短时间的字典操作，SDK 使用独立执行锁；已缓存的请求不再等待其他长查询。
- 同一缓存版本、同一参数的并发请求共用一个 Future：仅执行一次 SDK 计算和 JSON 序列化，共享成功结果或错误。不同参数的冷查询仍串行计算。
- 缓存保存已序列化的不可变响应，保留 300 秒 TTL、最多 32 项及原查询参数与返回格式。
- `/refresh` 立即清理缓存并递增版本；已开始的请求可以返回，但旧版本结果不会重新写入缓存。刷新后的请求不复用刷新前的 Future。
- SDK 仍逐次创建子进程，保留原 170 秒执行超时与失败回收；未引入常驻 SDK、持久化缓存或修改行情计算。

## 健康与观测

| 路径 | 含义 |
|---|---|
| `/health` | HTTP 桥进程存活，不查询 SDK |
| `/ready` | 通过现有 SDK 查询固定的已知日线样本，校验非空及 close 字段；优先使用正常的 300 秒缓存 |
| `/metrics` | JSON 统计：请求/错误数、缓存命中率、共享请求数、SDK 调用/错误/超时、在途不同请求数、各阶段累计和最大耗时、最近成功查询时间 |

Docker 健康检查改为 `/ready`。就绪缓存过期或被刷新时仍需排队执行一次真实查询，并非在 SDK 不可用时永久报告就绪。

每次 `/kline`、`/ready` 请求产生一条 JSON 日志，含参数、`source=cache/shared/sdk`、状态及耗时（毫秒）：

- `queue_ms`：等待 SDK 执行锁；`shared_wait_ms`：等待同参数结果。
- `sdk_init_ms`：子进程内导入 SDK、普通股票/ETF 客户端初始化。
- `sdk_compute_ms`：SDK 查询与计算，包含原生库内部读取及行业接口的惰性初始化，**不能据此单独区分磁盘 I/O 与 CPU 计算**。
- `sdk_total_ms`：启动子进程、SDK 操作、进程通信与回收总耗时。
- `serialize_ms`：结果 JSON 编码；`total_ms`：请求处理至响应准备完成，不包含网络发送。

`/metrics` 的内存来自 Linux cgroup v2：`current_bytes`、`peak_bytes`、`limit_bytes`；正式部署下覆盖同容器的服务端、桥与 SDK 子进程，包含文件缓存。不支持的环境返回 null。计数和耗时累计自进程启动，含就绪探针；刷新缓存不清空指标。命中率的分母为缓存命中、冷请求和共享请求之和。该接口仅容器内网可用。

## 验证

- 独立并发回归 6 项在 Windows 与 Linux 均通过：缓存绕过长查询、重复请求合并、刷新版本隔离、失败广播与重试、过期/非法 JSON、健康接口与空数据检查。
- 原本地来源、来源策略、行情缓存测试 50 项通过。执行时显式设置 `APP_ENV=test`，为手动同步测试分配随机独立 advisory lock，避免与正在运行的真实同步任务互相影响。
- 使用临时 7901 桥连接现有 7899 服务验证，没有启动第二个数据服务端，也没有复制或备份数据。
- 股票/ETF 共 8 组、274 条真实记录与迁移前 Windows 基准一致。
- 真实并发：3 个同参数行业请求只触发 1 次 SDK，2 个请求共享结果；缓存请求 0.0031 秒、就绪检查 0.0014 秒，均在 SDK 执行期间完成。
- 本轮行业请求返回 `SDK index overlap unavailable; cannot preserve index base`，旧桥相同请求也失败。新桥共享该错误，不缓存失败，也不放宽指数衔接校验；本轮未完成行业成功结果的全量复验，不能据此宣称行业查询故障已修复。

复验命令：

```powershell
D:\Pycharm\python\python.exe -m unittest discover -s scripts/tests -v
```

`scripts/verify_stockdb_bridge_concurrency.py --base-url URL` 可验证真实并发行为；会清理目标桥缓存，并报告长查询的 HTTP 状态，不把原有 SDK 错误算作数据正确性通过。`scripts/verify_stockdb_container.py` 继续用于完整结果对比。
