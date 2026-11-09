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

行情默认只读取 Free-StockDB。管理员在 `/admin` 独立设置 AkShare 兜底、是否保留 AkShare 历史 K 线入库、每日 16:30 自动同步，三项默认均关闭。StockDB 原有历史入库不受 AkShare 入库开关影响。配置保存在 `market_source_policy`，API 与 Worker 每次执行时读取。实时快照与指数 PE 获取链路、对应旧表和开关已删除；个股 PE TTM/PB 仍读取本地字段。最新基础行情统一由 `/api/v1/quotes/latest` 返回数据日期，不再轮询或推送实时快照。

关闭 AkShare 历史入库时，兜底取得的历史只放入按策略版本隔离的 Redis 缓存（默认一小时），禁止写入项目 K 线表，也不读取库中遗留 AkShare 行。图表分页、指标预热和回测共用完整缓存序列，按请求窗口选择整段来源，不拼接不同复权基准。页面查询和启动预热只读数据库、现有缓存，不访问外部行情源。数据缺失时由历史补拉任务优先查询 StockDB 并正常入库，确认需要 AkShare 兜底后才在后台填充完整历史缓存；回测任务同样在后台准备所需数据。缓存准备从 1900 年请求供应商实际可用的历史，不截断 2000 年之前的行情。缓存写入失败必须使任务失败，不能以零入库条数报告成功。开启入库后，后续同步可将 AkShare 数据保存到项目库；切换开关不会删除既有历史。

默认只手动同步；可显式开启工作日 16:30 同步本地源到项目的任务，不运行数据更新.exe。读取关注列表不再因本地数据日期落后于当前交易日而隐式重复刷新，首次关注、显式同步、历史补拉及任务投递恢复继续保留。

新增关注会复用运行中的任务；旧任务成功且所需历史仍可用时，直接将新关注标记完成。旧任务失败或数据不可用时，显式重新关注可重试；读取关注列表不会因缓存过期而不断重启已完成的任务。

回测冷启动和图表历史补拉共用后台历史准备流程：取得证券级事务锁，查询范围包含库中已有历史，校验返回数据覆盖完整已有区间后再原子写入，避免新旧前复权基准拼接。提交后再次失效图表和指标缓存。空图首次补拉携带 `initial=true`；近期窗口没有记录时，在后台扩大到供应商可用历史，支持长期停牌、退市标的。普通向左分页不启用这一全历史探测；两类任务分别去重。


Docker Compose 默认运行 `stockdb-local`，同容器内启动 Linux stockdb 和现有 SDK 查询桥，不再需要打开 Windows stockdb 或手动启动 7900 桥。

```powershell
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d --build
```

- RD：`STOCKDB_URL=http://stockdb-local:7899`；SDK 桥：`STOCKDB_SDK_URL=http://stockdb-local:7900`。仅容器内网可访问，不发布宿主端口。
- `STOCKDB_HOST_DIR=D:/Free_stockdb/stockdb` 下的 `data`、`data1`、`data_app`、`mydb` 分别绑定挂载到 `/opt/stockdb/` 对应目录；源目录必须存在，数据不进入镜像。
- 使用固定 SHA-256 的 v0.3.5 manylinux-x64 包及 Python 3.12；MIT 声明随镜像保留。SDK 查询、缓存、子进程隔离逻辑保持不变。
- 初始缓存配置为 256 MiB，容器总内存上限由 `STOCKDB_MEMORY_LIMIT` 控制，默认 2 GiB；缓存配置不是整个进程的内存上限。
- 服务端配置 `readonly: yes` 禁止协议写入，但 LevelDB 打开、恢复、锁文件仍可能需要文件写权限，绑定挂载不设置只读。
- **禁止 Windows 服务、另一套 Compose 服务或更新器同时打开同一数据集。**不要依赖跨 Windows/Linux 文件锁互斥。
- 更新数据：通过管理员页“一键更新原始数据”提交任务。现有容器控制进程暂停 RD/SDK 子进程，运行 Linux 更新器，校验文件后恢复服务；不要手动停止整个容器或再运行 Windows 更新器。
- `/health` 仅探测桥进程；Docker 健康检查使用 `/opt/healthcheck.py` 调用 `/ready`，通过桥发起真实 SDK 查询并优先复用正常缓存，验证 7899、SDK 和数据；`/metrics` 提供耗时、缓存、共享请求及内存指标。关键子进程退出会导致整个容器失败并重启。
- 回退：先停止 `stockdb-local`，恢复两个 URL 为 `host.docker.internal`，启动 Windows stockdb 与 `deploy/start_stockdb_sdk_bridge.ps1`，再重建后端容器以加载环境变量。生产和开发 Compose 不可同时使用同一数据目录。
- 真实数据复验：运行 `scripts/verify_stockdb_container.py --base-url URL --output result.json [--compare baseline.json]`。服务仅内网可见时可把脚本复制进容器运行；脚本对比股票、ETF、申万一级指数的日期、条数、字段和值，并验证缓存结果。

股票、ETF 的日 K 与 15 分钟 K 沿用本地适配器。周 K、月 K 分别调用官方 SDK 的 `frequency=1w/1M`、`fq=qfq`，直接保存返回记录；行情、指标与回测均读取各自周期表。没有项目内日 K 聚合周月 K 的逻辑。未结束周/月的 SDK 日期标签前移时替换同周期旧标签；原生指数在同周期返回多个日期时保留最后一条原值，不聚合 OHLC。

28 个行业目录与指数蓝图的申万一级目录一致，沿用原行情页的列表展示。行业日、周、月数据由官方 SDK 等权指数方法生成，固定初始基准为 2000 年起的 1000 点。为控制内存，SDK 在独立进程中按年查询，保留重叠周期并衔接同一基准；周月 OHLC 仍由 SDK 生成。行业 15 分钟 K 暂不支持，不请求旧行业兜底。8 个大盘指数保留目录，在本地暂不支持时显示空行情；可显式开启 AkShare 后获取。

基础信息使用本地最新日 K，包括 OHLC、昨收、涨跌幅、换手率、量比、振幅、股本、市值、PE TTM、PB、ST 状态。成交量显示单位为股，K 线存储单位仍为手。数据日期来自原始记录，缺失值保持为空。

K 线主键包含 `source`，区分 `stockdb` 和 `akshare`。默认最新页优先使用本地来源。指定区间查询时，在开启兜底的前提下，若本地窗口为空，或 AkShare 已存窗口完整包围本地窗口且覆盖更广，则整段读取 AkShare；不逐行拼接。指标预热与图表使用同一窗口选定的来源，指标缓存键同时包含来源和配置版本。覆盖历史前保留首尾覆盖校验。

迁移 `0024` 按本次授权直接删除旧行业及其关联数据，并清空此前没有来源标记的混合行情缓存，不备份。股票和 8 个大盘指数目录保留，D 盘 Free-StockDB 原始数据不受影响。迁移 0025 扩展合成指数价格精度，0026 清除非固定名单中的旧行业，0027 清理重复周期标签。该数据删除不能通过降级迁移恢复。

合成指数影线显示由管理后台统一设置，默认系数 0.5，允许 0～1。行情页申万行业指数与指数蓝图的合成指数共用该设置；股票、ETF、真实大盘指数、蓝图个股图和分时线不应用。显示最高价为 `max(open, close) + (high - max(open, close)) * 系数`，显示最低价为 `min(open, close) - (min(open, close) - low) * 系数`。蜡烛、图内高低值提示和纵轴使用显示值，原始 OHLC、指标、策略及数据库历史数据保持原值。该规则只是显示近似，不还原真实指数的日内极值。

迁移 0028 在现有配置表保存显示系数。管理员通过 `/api/v1/admin/market-display` 读写，图表通过 `/api/v1/market/display-settings` 读取。页面打开时读取设置，此后每 30 秒刷新；服务暂不可用时保留已读取的系数，首次读取前使用 0.5。配置变更不重建行情、不改变数据源开关，不增加服务进程。

迁移 0029 删除实时快照、指数估值及已废弃的实时附属表，并将 AkShare 历史入库和自动同步设为默认关闭。StockDB / AkShare 的既有 K 线表记录保留。部署时清理旧 `snapshot:*`、`watchlist_snap:*` Redis 缓存；蓝图的版本化 `Snapshot` 缓存不属于实时快照，不删除。

服务依赖：股票、ETF 日 K 和 15 分钟 K 读取 RD 7899；行情页股票、ETF 周月 K，以及申万行业指数日/周/月 K 读取 SDK 桥 7900。指数蓝图从 RD 读取成分股并在后端合成，不经过 SDK 桥。7900 不在线时既有入库数据仍可展示，需补拉的周期会明确失败，不能视作空区间或同步成功。

迁移 0030 移除已无调用方的缺口修补交易日日历缓存表并失效旧行情缓存，不删除任何 K 线记录。`stock_backend/scripts/sync_fixed_indices.py` 仅同步历史 K 线并遵守当前数据源策略，不再保留快照参数或绕过策略直接访问新浪。旧快照诊断脚本、新鲜度 Grafana 面板及其运行配置已清理；历史迁移与历史设计文档中的旧表名保留，用于迁移重放和历史记录。

SDK 桥第一阶段采用独立缓存锁与 SDK 执行锁，同参数并发请求合并，缓存命中不再排队等待长计算。缓存刷新采用版本隔离，旧请求不会回填新缓存。观测口径与验证限制见 `docs/ops/stockdb_bridge_stage1.md`。

原始数据更新入口、容器控制器、数据版本与完整行业结果缓存见 `docs/ops/stockdb_update_and_cache.md`。页面“一键更新原始数据”与“同步本地行情”是两个独立步骤；前者不自动导入项目库，后者不运行更新器。


容器原始数据更新：`supervise.py` 保持控制器和心跳在线，Linux 更新器仅通过现有 D 盘 bind mounts 读写原始文件，不复制数据入容器、不备份。`data1`、`data_app`、`mydb` 挂载配置保持原样。`sync_url.txt` 额外只读挂载，控制目录可写；旧 Windows 启动入口已禁用。

更新事件持久化至项目控制目录的 `update-events.sqlite3`。管理员接口 `/admin/local-market/update/events` 按任务和递增序号分页，支持 `after_seq` 增量及 `before_seq` 历史回看。页面显示当前阶段、更新器可观测的文件数量/下载量/速度、文件续传状态、校验结果及完整事件记录；没有输出的统计显示“—”，不估算下载速度。运行日志固定高度，向上查看暂停跟随，返回最新后恢复。退出码 0 不代表成功：必须具有原生完成标记、通过文件校验和真实 RD/SDK 查询。中断或失败保持维护状态，允许显式重试，不自动重跑更新器。

### 个股分钟周期

行情详情支持个股 1m、5m、15m、30m、60m。新增的 1m/5m/30m/60m 通过 7900 SDK 桥读取前复权记录：1m 读取原始分钟数据，5m/30m/60m 使用 SDK 按交易时段聚合。SDK 先查询完整交易日，再按请求时间裁剪，避免分页边界产生半根 K 线。

新增周期仅开放给 stock；ETF 和指数沿用原周期选项。历史记录按周期独立保存、缓存和计算指标，需应用迁移 0033。分钟线左滑窗口为七天，低于接口 5000 根上限；空白初次加载仍可回溯已停牌标的的历史。所有数据目录挂载保持不变。

### 阶段 1：项目行情读取器

`deploy/docker-compose.market-data.yml` 将原 Compose 服务 `stockdb-local` 切换为独立镜像
`stock-invest-market-data-local:phase1`。两个模式使用相同的服务名、数据挂载和控制目录，
Compose 切换时会替换原容器。开发环境启动候选模式：

```powershell
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml -f deploy/docker-compose.market-data.yml up -d --build --no-deps stockdb-local
```

恢复发行版模式时，运行同一命令并移除 `-f deploy/docker-compose.market-data.yml`。
生产环境使用基础文件 `deploy/docker-compose.yml`，并按需叠加同一覆盖文件。

项目读取器通过固定版本的 LevelDB 和 MessagePack 读取原 `data` 与 `data1`。
LevelDB 打开与 WAL 恢复需要的文件位于容器临时目录，原 SST 文件按路径只读引用，
后台压缩在此镜像中禁用。原始文件更新继续通过现有控制器先停止读取进程，
更新后再重新打开快照。7900 保留原有 SDK 的聚合、复权和指标实现，
行情输入走项目读取器。此阶段继续使用原始数据更新器和原生指标库。

在同一版数据上，切换前运行 `scripts/verify_market_data_takeover.py` 取得基准 JSON，
切换后用 `--baseline` 传入该 JSON 对比。脚本在 Compose 内网使用 7899 和 7900，
也可以通过 `--rd`、`--sdk` 指定地址。常规 K 线对比保留行顺序，跨证券区间按标的和日期对照。
