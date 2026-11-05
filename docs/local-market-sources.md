# 本地行情数据源

行情默认只读取 Free-StockDB。管理员在 `/admin` 设置 AkShare 兜底和实时快照，配置保存在 `market_source_policy`，API 与 Worker 每次执行时读取。实时快照需要同时开启 AkShare；关闭后不采集、不读取遗留实时快照。

Windows 上先启动 `D:\Free_stockdb\stockdb\stockdb.exe`，再启动官方 SDK 查询桥：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\stock-invest-system\deploy\start_stockdb_sdk_bridge.ps1
```

脚本默认使用 `D:\Pycharm\python\python.exe` 和 `D:\Free_stockdb\stockdb\pybao`，可通过 `-Python`、`-SdkDirectory` 指定。Python 版本须匹配 `stockdb.pyd`。Git Bash 的 `deploy/start_dev.sh` 会启动查询桥；单独执行 Docker Compose 时需要先执行上面的命令。

- RD 地址：`STOCKDB_URL`，Docker 默认 `http://host.docker.internal:7899`。
- 官方 SDK 查询桥：`STOCKDB_SDK_URL`，Docker 默认 `http://host.docker.internal:7900`。`/health` 可检查服务。
- 本地更新仍由用户运行 `数据更新.exe`，完成后点击管理后台“同步本地行情数据”。

股票、ETF 的日 K 与 15 分钟 K 沿用本地适配器。周 K、月 K 分别调用官方 SDK 的 `frequency=1w/1M`、`fq=qfq`，直接保存返回记录；行情、指标与回测均读取各自周期表。没有项目内日 K 聚合周月 K 的逻辑。未结束周/月的 SDK 日期标签前移时替换同周期旧标签；原生指数在同周期返回多个日期时保留最后一条原值，不聚合 OHLC。

28 个行业目录与指数蓝图的申万一级目录一致，沿用原行情页的列表展示。行业日、周、月数据由官方 SDK 等权指数方法生成，固定初始基准为 2000 年起的 1000 点。为控制内存，SDK 在独立进程中按年查询，保留重叠周期并衔接同一基准；周月 OHLC 仍由 SDK 生成。行业 15 分钟 K 暂不支持，不请求旧行业兜底。8 个大盘指数保留目录，在本地暂不支持时显示空行情；可显式开启 AkShare 后获取。

基础信息使用本地最新日 K，包括 OHLC、昨收、涨跌幅、换手率、量比、振幅、股本、市值、PE TTM、PB、ST 状态。成交量显示单位为股，K 线存储单位仍为手。数据日期来自原始记录，缺失值保持为空。

K 线主键包含 `source`，区分 `stockdb` 和 `akshare`。默认最新页优先使用本地来源。指定区间查询时，在开启兜底的前提下，若本地窗口为空，或 AkShare 已存窗口完整包围本地窗口且覆盖更广，则整段读取 AkShare；不逐行拼接。指标预热与图表使用同一窗口选定的来源，指标缓存键同时包含来源和配置版本。覆盖历史前保留首尾覆盖校验。

迁移 `0024` 按本次授权直接删除旧行业及其关联数据，并清空此前没有来源标记的混合行情缓存，不备份。股票和 8 个大盘指数目录保留，D 盘 Free-StockDB 原始数据不受影响。迁移 0025 扩展合成指数价格精度，0026 清除非固定名单中的旧行业，0027 清理重复周期标签。该数据删除不能通过降级迁移恢复。
