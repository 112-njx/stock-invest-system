# 本地行情数据源

图表分别请求主图价格 MA 和附图指标，两者独立更新、独立显示错误。SDK MA 失败时只清空主图均线；开启 pandas 后，MACD/KDJ、成交量及成交额附图继续显示，且无需等待 MA 请求超时。主图价格 MA 仍固定使用 SDK，不伪造数值或自动降级。

技术指标默认经 7900 的 `POST /indicators/calculate` 计算。项目选定与图表相同的前复权历史（包括行业合成指数和 AkShare 缓存序列），将完整预热历史传入计算入口，再裁剪显示窗口。影线显示系数不参与计算。7899 负责提供行情。

### 阶段 2：统一指标入口

7900 的 `market_indicator_library.py` 分发计算请求。现有指标目录、参数、交叉信号和输出字段沿用 `zb_core`。新增公式写在项目的 `native/market_indicators` Rust + PyO3 工程中，走势特征 `forecast_features` 是首个调用。两个原生模块独立编译，可以在同一个请求中计算，调用方统一使用 `sdk_indicators.calculate`。容器就绪检查会执行两套引擎的计算。

`zhishu` 按图表周期与截止时间从项目行情读取器读取成分股的前复权历史。单成分股与多成分股共用读取路径，保留原生等权、自定义权重和 UTC 时间对齐。7900 每次启动会创建新的 `zhishu` 成分数据缓存命名空间，首次请求重新读取当前快照，同一运行期间的重复请求继续复用缓存。

Docker 构建会产出 `market_indicators.abi3.so`。独立运行 Windows 查询桥时，先用 CPython 3.12 或更高版本构建并验证导入：

```powershell
.\deploy\build_market_indicators.ps1
.\deploy\start_stockdb_sdk_bridge.ps1
```

默认使用 Rust 的 MSVC 工具链。有 MinGW 和相应 Rust 工具链的环境可指定 `-Target x86_64-pc-windows-gnu`。`.pyd` 输出到 `native/market_indicators/target/python/`，由 Windows 启动脚本加载。

管理后台数据源页提供“使用项目 pandas 计算技术指标”，默认关闭。迁移 0031 创建独立设置表；两套引擎按设置版本隔离缓存，保存后通过 WS 通知在线图表重载。SDK 超时返回 503，页面显示错误，不自动降级 pandas。SDK 保留原生精度和 KDJ 初值规则，结果可能与 pandas 不同；MACD 柱值直接使用 SDK 已乘二的结果。7900 复用现有临时原生子进程隔离模式，增加请求大小、并发和时间限制，不新增常驻进程或容器。容器健康检查同时执行指标实际计算。

行情默认从 Free-StockDB 读取。个股和 ETF 的 K 线、指标和回测使用本地历史，预测使用已确认收盘的日 K。管理中心可开启 AkShare 兜底和每日北京时间 16:30 自动更新 StockDB，两项均默认关闭。

AkShare 历史仅存入带有效期的 Redis 缓存，图表、指标和回测按窗口读取单一来源，避免混用不同复权基准。迁移 0039 删除旧 AkShare 历史行及入库策略字段。共享 K 线表继续支持固定指数。

自动和手动更新共用 StockDB 控制器。更新验证成功后触发证券目录刷新和预测跟踪。Celery Beat 只保留 StockDB 更新计划。备份和恢复校验可通过项目脚本手工执行。账户宽限期后硬删、过期导出文件回收及 AI 记忆清理已退出 Beat 调度。

### 个股分钟周期

行情详情支持个股 1m、5m、15m、30m、60m。新增的 1m/5m/30m/60m 通过 7900 SDK 桥读取前复权记录：1m 读取原始分钟数据，5m/30m/60m 使用 SDK 按交易时段聚合。SDK 先查询完整交易日，再按请求时间裁剪，避免分页边界产生半根 K 线。

新增周期仅开放给 stock；ETF 和指数沿用原周期选项。历史记录按周期独立保存、缓存和计算指标，需应用迁移 0033。分钟线左滑窗口为七天，低于接口 5000 根上限；空白初次加载仍可回溯已停牌标的的历史。所有数据目录挂载保持不变。

### 项目行情读取器

开发和生产 Compose 都从同一个 Dockerfile 构建项目行情读取器。
已有环境可继续叠加 `deploy/docker-compose.market-data.yml`，沿用镜像标签
`stock-invest-market-data-local:phase1` 和 `/tmp` 的 tmpfs 设置。单独重建开发环境的行情服务：

```powershell
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml -f deploy/docker-compose.market-data.yml up -d --build --no-deps stockdb-local
```

生产环境使用 `deploy/docker-compose.yml`，可按需叠加同一覆盖文件。

项目读取器通过固定版本的 LevelDB 和 MessagePack 读取主库 `data` 和辅助库 `data1`。`data1` 为空时，行情服务可直接从主库启动。
LevelDB 打开与 WAL 恢复需要的文件位于容器临时目录，原 SST 文件按路径只读引用，
后台压缩在此镜像中禁用。原始文件更新继续通过现有控制器先停止读取进程，
更新后再重新打开快照。7900 保留原有 SDK 的聚合、复权和指标实现，
行情输入走项目读取器。此阶段继续使用原始数据更新器和原生指标库。

在同一版数据上，切换前运行 `scripts/verify_market_data_takeover.py` 取得基准 JSON，
切换后用 `--baseline` 传入该 JSON 对比。脚本在 Compose 内网使用 7899 和 7900，
也可以通过 `--rd`、`--sdk` 指定地址。常规 K 线对比保留行顺序，跨证券区间按标的和日期对照。
