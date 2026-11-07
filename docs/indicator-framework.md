# 详情页指标框架（第一批）

当前目录开放 MA、MACD、KDJ、RSI、WR、CCI、ATR、BOLL、EMA、EXPMA、BBI、WMA、SMA、DMA，以及成交量、成交额；技术指标进度为 14/39，不提前开放未验证的项目。

## 单一指标目录

`stock_backend/app/services/indicator_catalog.json` 同时用于后端参数校验、7900 原生调用适配、详情页参数表单和副图渲染。`GET /api/v1/indicators/catalog` 返回目录版本及已开放项目。

每项登记 key、label、placement、inputs、parameters、series、reference_lines、engines。参数当前支持 integer / integer_list，分别声明默认值和上下界。曲线声明 field、label、color、kind（line/histogram）；多条 line 可组成通道。柱色支持按当前蜡烛涨跌或指标正负着色。原生适配声明 native 和 native_outputs，MA 动态周期与成交量均量线保留专门适配。

目录文件与无第三方依赖的 `indicator_registry.py` 一同复制进 StockDB 镜像。7899 只读写数据，调用进程内的 zb_core 负责计算，沿用图表选择的本地历史序列。

## 配置兼容

原有 `/users/me/chart-settings` 默认 GET 与旧客户端 PUT 保留 ma/panels 形状。新版 GET 传 `version=2`，PUT 带 `version:2`，新增 `panel_options: {macd: {params: {fast:7,slow:20,signal:5}}}`。

panels 数组同时表示开启状态和排列顺序，最多三个且不得重复。关闭指标保留其 panel_options，重新开启沿用参数。旧客户端保存时合并保留已有参数，不把新版配置清空。不需要新数据库迁移，旧 JSON 按需读取升级；访客旧浏览器配置同样转换，账号设置不被访客设置覆盖。

## 加载和引擎

首页走原有请求与渲染分支。详情页按目录创建副图，每个开启的副图独立请求、发布结果和显示错误；只有失败的副图显示重试入口。MA 独立于副图。请求代次用于屏蔽旧参数、股票、周期、账号或已卸载图表的响应。

引擎选择以目录 engines 为准：全局开启 pandas 时，仅有 pandas 能力的项目走原有类；SDK-only 项目仍走原生引擎，不静默降级。缓存继续隔离计算参数和引擎设置版本。

## 下一批接入步骤

核对 SDK 函数签名、输出和空值规则；添加目录项与必要原生适配；对照容器原生输出补回归；验证参数表单、多曲线、参考线、时间对齐、账号参数保存及三个副图上限。下一批为 RSI、WR、CCI、ATR。

验证入口：后端 test_indicator_registry / test_chart_settings / test_indicators / test_price_ma，前端 scripts/verify-detail-chart-settings.mjs 与 scripts/verify-indicator-isolation.mjs，原生 scripts/tests/test_price_ma.py。

## 第二批：RSI / WR / CCI / ATR

四项均为 SDK-only，开启全局 pandas 开关也不会改用 pandas 重算；仅在详情页目录中提供，每项占一个副图名额。目录驱动现有参数编辑器、账号设置、图例、曲线与参考线，无需修改首页或增加逐项渲染分支。

| 指标 | 原生签名 | 输出字段 | 默认参考线 |
| --- | --- | --- | --- |
| RSI | RSI(close, n=24) | rsi | 30、70 |
| WR | WR(close, high, low, n=10, n1=6) | wr1、wr2 | 20、80 |
| CCI | CCI(close, high, low, n=14) | cci | -100、0、100 |
| ATR | ATR(close, high, low, n=20) | atr | 无 |

WR 原生输出使用正向 0～100，不转换为负值。RSI 使用 SDK 默认单线 24 周期；WR 两条线合计一个名额。原生 NaN/Inf 仅转为 JSON null；保留原始数值、初始化和预热规则，例如 ATR 默认首个有限值需要前置有效收盘价，不本地补零或补公式。参数可独立修改、恢复默认并随账号保存，关闭再开启保留参数。

数值对照验证：`scripts/tests/test_common_indicators.py`（Windows/Linux 实际原生模块）；API、四周期路由、分页预热及引擎开关验证：`stock_backend/tests/test_common_indicators.py`。现有前端回归增加了四项的选择上限、参数持久化、账号切换、四种时间标签、参考线、空值显示及独立失败重试检查。

## 第三批：主图均线与布林带

新增七项均叠加到主图右侧价格轴，不创建新 pane、不占三个副图名额，MA 仍保持1～6条设置。每项可以单独开启/关闭、编辑参数及恢复默认。主图图例显示各曲线值；十字光标按同一时间标签选择数据，预热不足保留原生 null，不补零。

| 指标 | 默认参数 | 返回字段 |
| --- | --- | --- |
| BOLL | n=20、p=2.0 | boll_upper、boll_mid、boll_lower |
| EMA | n=5 | ema |
| EXPMA | n1=12、n2=50 | expma1、expma2 |
| BBI | m1=3、m2=6、m3=12、m4=20 | bbi |
| WMA | n=5 | wma |
| SMA | n=5、m=1 | sma |
| DMA | a=0.1 | dma |

BOLL 的原生输出顺序是上轨、中轨、下轨，倍数 p 支持小数（0<p<=100）；DMA 的 a 是平滑系数，支持小数（0<a<=1），本批不把它误当成周期。EMA/WMA/SMA 的5周期沿用配套 Python 包基础指标默认周期；DMA 原生函数无默认 a，项目显式取0.1。SMA 权重为整数，1<=m<=n。参数类型、上下界、开区间和关联校验写在共享目录，前后端与原生桥接使用同一份约束。

账号与访客设置新增 overlays（开启顺序）和 overlay_options（各项参数），继续使用既有 JSON 存储，不需要新迁移。旧版 GET 仍仅返回 ma/panels；旧版或较旧的 v2 客户端省略新增字段保存时，服务端保留已存的叠加配置。关闭叠加项保留参数；目录暂不可用时独立保存 MA 也保留叠加配置。

叠加请求与 MA/副图独立，按队列逐项调用本地 SDK，及时发布已完成结果；单项失败只显示自己的错误与重试入口。重试不清空其他叠加线，不重发 MA/副图请求。股票、周期、参数、账号或组件生命周期变化使旧响应失效；离开旧队列后不再启动剩余请求。只把当前已加载 K 线时间范围中的叠加数据交给主图，避免扩张横轴。

本批原生对照：scripts/tests/test_main_overlays.py（Windows/Linux）；API与四周期预热：stock_backend/tests/test_main_overlays.py；前端回归包含共享价格轴、七项全开不占副图名额、小数与关联校验、参数读回/恢复、账号切换、旧客户端保留、异常重试和队列失效。
