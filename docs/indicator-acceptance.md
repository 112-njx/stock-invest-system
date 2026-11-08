# 详情页39项指标完整验收

验收日期：2026-11-07。本报告对应修复提交 `9a7b8e8`；功能限于详情页，行情首页保持原有配置。测试使用本机 Docker、本地7899存取和配套 SDK 的 Linux `zb_core.abi3.so`，另在 Windows `zb_core.pyd` 复核原生适配契约。没有远程行情调用，没有用 pandas 或前端公式替代 SDK 数值。

## 范围和数据

- 39项 SDK 指标/函数全部纳入；加成交量、成交额共41项目录定义。
- 日K、周K、月K、15分钟K；默认参数和自定义参数、动态 MA、短历史、空值、分页和重复请求。
- 主图11项（含MA），副图30项；六条MA不占名额，副图0～3个。
- 账号读写、第二客户端、另一账号隔离、访客设置、旧设置裁剪、保存失败回滚、排序和独立恢复默认。
- 单项故障/重试、过期响应、最大叠加配置、反复切换、20成分股合成指数与普通 MA 并发。

数值矩阵使用300308已有本地历史，截止2026-11-05；数据库日/周/月/分钟覆盖长度不同，指标均使用当前数据源的完整预热输入。底层SDK已有2026-11-06数据，合成指数按当前图表截止时间截取，不混入未来一根。实时基本行情可能展示更新的交易日，不能据此把图表截至时间当成SDK计算错误。

## 数值和交互证据

1. 实际 HTTP 矩阵：39项 × 4周期 × 默认/自定义两组 × 32根；另核对16次尾页/重复请求，结果一致。
2. 容器原生独立对照：21,760个输出值，包括294个空值。容差为相对1e-12、绝对1e-9，空值必须严格为null。期望值直接来自原生单项函数、`BATCH_CROSS`、`ZHISHU`，不通过项目适配器生成。
3. SDK契约测试：Windows/Linux各25项，包含六种计算字段、极短历史、10000周期、平盘/零量、默认/自定义参数、11项金叉死叉和合成指数四周期/权重/UTC对齐。
4. 传输并发测试：Windows/Linux各9项，包含独立执行通道、真实spawn工作进程顺序、失败/超时清理、缓存版本失效/损坏回源/维护状态。
5. 后端相关测试321项通过。前端设置、隔离、默认标的、分页脚本及类型检查/生产构建通过。
6. 实际浏览器50项全部通过（最终一次整组运行约4.3分钟，无重试、无跳过）：40组覆盖全部指标和四周期，检查真实Canvas曲线颜色、主图图例数值、独立坐标区域、十字光标、原生交叉数量/标记与空值；另10项覆盖账号/访客、MA编辑、旧配置、股票集合、失败回滚、过期请求、缩放保留、拖动补页及性能。测试定位器对目录名称使用精确匹配，区分“成交量”和“VR 成交量比率”。

分段输入另作严格验证：两只股票、2025-01-01～2026-11-05的15分钟数据，共142,240个输入值以及完整原生指数输出，与未修改SDK批量读取完全一致；20只股票短区间另核对12,800个输入值及完整指数。优化只改变读取的进程安排和内存工作集。

## 验收发现和修复

**访客直接访问详情页被跳转登录页。** 默认标的初始化调用了私有自选接口，401触发登录跳转。现仅登录后读取账号自选；访客使用公共标的，不复用退出账号的自选缓存。直接访问和本地设置刷新持久化纳入浏览器回归。

**大合成指数使普通MA失败。** 原实现共享一把执行锁；20只股票15分钟指数超过35秒原生任务预算，普通MA等待5秒后同时503。现独立合成指数通道，最多四个子进程按成分读取，分钟数据按90自然日且不拆交易日分段，采用带本地数据版本及SDK指纹的64MiB输入缓存，并给该单项显示“计算中…”。普通指标预算不变；指数按40/45/55/60秒分别约束输入读取、原生任务、后端传输和前端请求。

## 性能实测

20只成分，起算2025-01-01，截止2026-11-05，每次并发请求未缓存周期的MA：

| 场景 | 修复前 | 修复后首次 | 修复后输入缓存命中 |
|---|---:|---:|---:|
| 日线指数 | 4.43秒，200 | 7.12秒，200 | 1.04秒，200 |
| 同时日线MA | 4.87秒，200 | 0.84秒，200 | 0.37秒，200 |
| 15分钟指数 | 37.77秒，503 | 40.26秒，200 | 2.39秒，200 |
| 同时15分钟MA | 5.05秒，503 | 0.48秒，200 | 0.33秒，200 |

日线首次读取因独立SDK进程初始化增加耗时；普通指标的延迟和失败隔离改善，重复读取由输入缓存加速。这个结果不等于所有合成指数都能秒回。更长历史、更多数据或机器负载可能超过有限预算，届时只该项报错并允许重试/修改起算日，不裁剪数据、不改变公式。20成分测试期间容器内存峰值约1.00GiB，未发生OOM。

浏览器性能采用相同Edge、1600×1000、10项主图叠加加3副图，每轮5次关闭/开启，共3轮。页面指标响应全部到齐后计时，切换后等待所有曲线完成再GC测量：

| 浏览器指标 | 修复前3轮 | 修复后最终3轮 |
|---|---:|---:|
| 全指标就绪范围 | 2.16～6.40秒 | 2.15～2.26秒 |
| 就绪中位数 | 2.23秒 | 2.16秒 |
| 每轮5次关/开耗时 | 4.31～4.68秒 | 4.37～5.55秒 |
| 切换后GC保留堆 | 32.7～34.2MiB | 32.7～34.0MiB |
| 最长主线程长任务 | 74ms | 95ms |
| 三轮长任务总个数（≥50ms） | 4 | 1 |

就绪和内存阈值均通过；保留堆未呈逐轮累积趋势。个别切换轮次和最长长任务有波动，因此不把单次更快解释为整体优化。样本量只用于本机回归检查，不宣称生产负载容量或统计显著性。

## 复现和产物

在仓库根目录PowerShell执行；真实验收需要本地数据库和SDK容器运行。两个临时账号仅供测试，完成后务必清理：

```powershell
Push-Location stock_backend
./.venv/Scripts/python.exe ../scripts/indicator_acceptance_accounts.py create --file ../.artifacts/indicators/accounts.credentials.json
./.venv/Scripts/python.exe ../scripts/accept_indicator_api.py --out ../.artifacts/indicators/api-final
Pop-Location

docker cp scripts/accept_indicator_oracle.py stock-invest-dev-stockdb-local-1:/tmp/accept_indicator_oracle.py
docker cp .artifacts/indicators/api-final/api-matrix.json stock-invest-dev-stockdb-local-1:/tmp/indicator-api-matrix.json
docker exec stock-invest-dev-stockdb-local-1 python -B /tmp/accept_indicator_oracle.py /tmp/indicator-api-matrix.json

Push-Location stock_frontend
npm run verify:default-symbol
npm run verify:indicators
npm run test:indicators
Pop-Location

# 选择一个尚未请求过的MA周期，避免普通MA命中结果缓存。
& D:/Pycharm/python/python.exe -B scripts/accept_indicator_load.py --ma-period 197 --out .artifacts/indicators/index-load.json

Push-Location stock_backend
./.venv/Scripts/python.exe ../scripts/indicator_acceptance_accounts.py cleanup --file ../.artifacts/indicators/accounts.credentials.json
Pop-Location
```

浏览器默认使用Windows Edge；Linux需安装Playwright浏览器或指定`PLAYWRIGHT_EXECUTABLE_PATH`。可用`INDICATOR_TEST_URL`指定浏览器目标地址，`INDICATOR_TEST_ACCOUNTS`指定临时凭据文件。API脚本与负载脚本支持`--url`。

产物在`.artifacts/indicators`：`api-final/api-matrix.json`、`browser-results.json`、四周期截图、`performance-baseline.json`/`performance-current.json`、`index-load-baseline.json`/`index-load-final-cold.json`/`index-load-final-warm.json`。凭据不进入提交，清理后删除。

## 交付

功能修复已推送`njx-branch`，重建并重启前端和SDK桥容器，重启后端及相关工作服务。最终浏览器运行时各服务稳定；先前一次运行受到共享环境部署重启影响出现502，已在稳定环境整组重跑，未计作通过。

测试入口：`http://127.0.0.1:8081/market/detail?symbol=300308`。321项后端测试是指标与图表设置相关回归，不代表全仓所有业务测试。上述性能是当前本机与数据快照实测；更大负载仍受合成指数预算约束。
