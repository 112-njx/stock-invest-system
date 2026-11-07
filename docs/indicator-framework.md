# 详情页指标框架（39/39）

当前目录开放 SDK 的全部 39 项指标/函数（含 STD、SUM、HHV、LLV、REF、ZHISHU），另有成交量、成交额两个基础副图。仅详情页提供新配置；首页保持原有行为。

## 单一指标目录

`stock_backend/app/services/indicator_catalog.json` 同时用于后端参数校验、7900 原生调用适配、详情页参数表单和副图渲染。`GET /api/v1/indicators/catalog` 返回目录版本及已开放项目。

每项登记 key、label、placement、inputs、parameters、series、reference_lines、engines。数值参数支持 integer / integer_list / number，分别声明默认值和上下界。input_fields 声明适用输入字段，cross 声明 SDK 是否支持原生交叉信号。曲线声明 field、label、color、kind（line/histogram）；多条 line 可组成通道。柱色支持按当前蜡烛涨跌或指标正负着色。原生适配声明 native 和 native_outputs，MA 动态周期、成交量均量线和合成指数保留专门适配。

目录文件与无第三方依赖的 `indicator_registry.py` 一同复制进 StockDB 镜像。7899 只读写数据，调用进程内的 zb_core 负责计算，沿用图表选择的本地历史序列。

## 配置兼容

原有 `/users/me/chart-settings` 默认 GET 与旧客户端 PUT 保留 ma/panels 形状。新版 GET 传 `version=2`，PUT 带 `version:2`，新增 `panel_options: {macd: {params: {fast:7,slow:20,signal:5}}}`。

panels 数组同时表示开启状态和排列顺序，最多三个且不得重复。关闭指标保留其 panel_options，重新开启沿用参数。旧客户端保存时合并保留已有参数，不把新版配置清空。不需要新数据库迁移，旧 JSON 按需读取升级；访客旧浏览器配置同样转换，账号设置不被访客设置覆盖。

## 加载和引擎

首页走原有请求与渲染分支。详情页按目录创建副图，每个开启的副图独立请求、发布结果和显示错误；只有失败的副图显示重试入口。MA 独立于副图。请求代次用于屏蔽旧参数、股票、周期、账号或已卸载图表的响应。

引擎选择以目录 engines 为准：全局开启 pandas 时，仅有 pandas 能力的项目走原有类；SDK-only 项目仍走原生引擎，不静默降级。缓存继续隔离计算参数和引擎设置版本。

## 接入与验证原则

核对 SDK 函数签名、输出和空值规则；添加目录项与必要原生适配；对照容器原生输出补回归；验证参数表单、多曲线、参考线、时间对齐、账号参数保存及三个副图上限。以下按批次记录已完成能力。

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

## 第四批：动量与强弱副图

新增 BIAS、PSY、DPO、MTM、ROC，均为独立副图、SDK-only；无论全局是否开启 pandas，仍用原生引擎计算。BIAS 的三条线或其余每项的两条线均只占一个副图名额，总计仍最多开启三个。默认关闭新项，现有 MA、主图叠加和默认成交量/MACD 选择保持不变。

| 指标 | SDK 默认参数 | 返回字段 | 展示参考线 |
| --- | --- | --- | --- |
| BIAS | l1=6、l2=12、l3=24 | bias1、bias2、bias3 | 0 |
| PSY | n=12、m=6 | psy、psy_ma | 25、75 |
| DPO | m1=20、m2=10、m3=6 | dpo、dpo_ma | 0 |
| MTM | n=12、m=6 | mtm、mtm_ma | 0 |
| ROC | n=12、m=6 | roc、roc_ma | 0 |

参数是1～10000的整数。PSY/DPO/MTM/ROC 的第二条线按 SDK 返回的平滑线顺序映射，不另行在项目中计算。BIAS、ROC 保留原生百分比尺度，PSY 保留0～100尺度；DPO、MTM 等正负值不截断、不取绝对值。NaN/Inf 只转 JSON null，短历史和预热不足不补零。

目录自动驱动选择器、参数编辑、图例、多线曲线和参考线。账号和访客配置沿用现有结构，关闭后保留参数；保存新副图选择时保留 MA 与主图叠加配置。详情页指标弹窗使用视口高度限制与可滚动正文，避免目录扩展后底部参数无法操作；首页样式与行为不变。

本批原生对照：scripts/tests/test_momentum_indicators.py，覆盖 Windows/Linux 默认、自定义、短历史、平盘和参数边界。API四周期与分页预热：stock_backend/tests/test_momentum_indicators.py；前端回归新增三副图上限、参数恢复/读回、账号切换、正负值/空值/时间标签、参考线、单项失败与重试及过期响应保护。

## 第五～七批：趋势、量价与价格通道

本次仅扩展详情页。11 项趋势及量价指标各使用一个独立副图，同时最多三个；TAQ、KTN、XSII 叠加主图价格轴，不占副图名额。新项默认关闭；MA 仍支持 1～6 条，首页配置和行为保持原样。

| 指标 | SDK 参数／页面默认值 | 返回字段（按原生顺序） | 参考线 |
| --- | --- | --- | --- |
| DMI | m1=14、m2=6 | dmi_pdi、dmi_mdi、dmi_adx、dmi_adxr | 20、40 |
| TRIX | m1=12、m2=20 | trix、trix_ma | 0 |
| DFMA | n1=10、n2=50、m=10 | dfma_dif、dfma_difma | 0 |
| MASS | n1=9、n2=25、m=6 | mass、mass_ma | 26.5、27 |
| VR | m1=26 | vr | 70、150 |
| CR | n=20 | cr | 100 |
| EMV | n=14、m=9 | emv、emv_ma | 0 |
| BRAR | m1=26 | brar_ar、brar_br | 100 |
| OBV | 无可调参数 | obv | 无 |
| MFI | n=14 | mfi | 20、80 |
| ASI | m1=26、m2=10 | asi、asi_ma | 无 |
| TAQ（主图） | n=20 | taq_up、taq_mid、taq_down | 无 |
| KTN（主图） | n=20、m=10 | ktn_up、ktn_mid、ktn_down | 无 |
| XSII（主图） | n=102、m=7 | xsii_td1、xsii_td2、xsii_td3、xsii_td4 | 无 |

整数参数统一限制为 1～10000，支持保存和恢复默认。XSII 的 n、m 是通道百分比系数，不是滚动周期，表单明确标为“通道系数 N（%）”“通道系数 M（%）”，保留原生输出，不重新排序通道线。OBV 的原生函数只有收盘价、成交量输入，没有可调参数，因此只提供开关。TAQ 原生单项函数要求显式传 n；页面采用 20，并与 SDK 的 BATCH 无参数默认结果核对。为避免 MASS 的 `ma`、BRAR 的 `ar/br`、XSII 的 `td1` 等列与其他指标混淆，接口为部分字段增加指标前缀，数值及输出顺序保持原样；OBV 等指标的原生尺度不做二次换算。参考线是固定展示提示，不是信号计算。

全部调用本地配套 SDK 指标引擎；7899 只提供 K 线存取。OHLCV 数组来自当前图表的数据源，不为指标另取行情。沿用目录驱动的参数表单、图例和渲染、账号/访客配置、独立加载和重试、过期响应保护。关闭指标保留参数，保存失败继续使用上次成功配置；通道请求独立排队，不阻塞 MA 和副图的结果发布。

验证入口：`scripts/tests/test_trend_volume_channels.py` 对照 Windows/Linux 的真实单项函数及 BATCH 默认/自定义字段顺序，包含短历史、平盘、零成交量、周期边界；`stock_backend/tests/test_trend_volume_channels.py` 覆盖四周期、历史补页、最新页、活动 K 线变化、短历史/空历史、非法参数和单项失败；`test_chart_settings.py` 覆盖所有新增参数、六条 MA 加三个副图和价格通道、账号隔离与旧客户端写回。前端两个 verify 脚本补充完整选择/参数/保存流程、价格轴及参考线、关闭全部副图、单项重试和旧通道响应丢弃。

## 第八批：基础统计函数（38/39）

STD 标准差、SUM 周期累计值、HHV 周期最高值、LLV 周期最低值、REF 前期值均使用独立副图，各占一个名额。STD/SUM/HHV/LLV 默认 n=5，REF 默认回看 n=1；整数范围1～10000。默认使用收盘价，可选择开盘价、最高价、最低价、成交量、成交额；成交量/成交额结果采用数量格式，仍保持独立坐标轴。原生 NaN/Inf 只转 null，不补零、不改变统计口径。

参数沿用 JSON `params`：`{"std":{"n":7,"field":"volume"}}`。EMA/SMA/WMA/DMA 同样支持价格字段选择，主图仅提供 OHLC，避免非价格结果与股价共轴。MA 仍固定使用收盘价，保留1～6条规则。

## 第九批：ZHISHU 合成指数（39/39）

合成指数是特殊副图，不等同于当前股票的普通指标。选择1～20只不重复股票，默认等权；可以改为自定义固定权重，权重按比例使用，0 表示不参与，全部为0不合法。基点默认1000，起算日期默认2020-01-01，分别可配置；修改起算日期会改变基准，跨股票、周期沿用同一配置。首次开启时先配置股票集合；只配置、不点击开启时不会增加副图。多条 MA、主图叠加不占名额，合成指数占一个。

示例参数：`{"zhishu":{"members":[{"code":"600519","weight":3},{"code":"300502","weight":1}],"weighting":"custom","base":1000,"start":"2025-01-01"}}`。保存在 `panel_options.zhishu.params`，不用新数据库迁移；旧客户端写回继续保留配置。

SDK 桥从本地7899读取成分股的原生 OHLCV 等数组，调用配套 `zhibiao.ZHISHU` / `zb_core`。等权使用 method=1；固定自定义权重作为原生权重输入向量，使用 method=2，由引擎完成加权收益和基点递推，没有项目自写指数公式，也不把用户权重称为真实流通市值。日/周/月/15分钟均按对应周期原生 K 线计算，不本地聚合。沿用底层函数原始输出，不额外套用高层包装器的切片；初始基准根无原生结果时显示空值。

参与成分数量、不同上市日期和停牌时的计算规则以原生结果为准；所选股票在起算日期后完全没有本地数据时提示失败，不静默移除。输出 `zhishu_close` 和 `zhishu_count` 对齐当前图表的 UTC 时间标签，分钟标签从上海时区转换；不会覆盖当前股票 OHLCV，不新增图表时间轴标签。仅当前股票缺少的时点也不强行补入。起算日期晚于当前显示区间时为空值。读取前后检查本地数据版本与维护状态；版本切换丢弃结果。合成指数不复用只看当前股票最新时间的指标缓存，避免遗漏成分股更新。

## 第十批：增强交互

原生 `BATCH_CROSS` 实测支持 MACD、KDJ、DMI、TRIX、EMV、DPO、DFMA、MTM、MASS、ROC、ASI。仅这些项目提供“金叉死叉标记”开关，默认关闭；启用时强制走 SDK，即使全局打开 pandas 也不会用前端或 pandas 重算信号。返回各自的 `<key>_cross`（1金叉、-1死叉、0无信号），图中在原生信号对应 K 线位置绘制红/绿点，图例显示截至十字光标位置的累计数。没有原生交叉配对的项目不提供开关。首页 MACD 保持原有展示。

副图选择器按实际排列提供上移/下移，边界按钮禁用；顺序写入 panels 并同步账号。独立恢复默认只重置该项的参数、计算字段和交叉开关，保留开关状态、排列以及其他指标。合成指数恢复默认保留股票集合，将其恢复等权、基点1000、起算日期2020-01-01。参数编辑器内的恢复默认先修改草稿，点击保存才生效；外部单项恢复默认直接保存，失败继续显示上次成功配置。

验证：`scripts/tests/test_statistics_composite.py` 使用真实 Windows/Linux 原生模块，对照六种输入字段、短历史/周期边界、全部11种交叉信号，以及四周期等权/3:1固定权重和 UTC 对齐；容器本地行情另对照了贵州茅台、新易盛在四周期的实际指数结果。`stock_backend/tests/test_statistics_composite.py` 覆盖 API 校验、pandas 开关、补页、空数据、成分股变化时缓存隔离和指标字段共存。两个前端 verify 脚本覆盖股票搜索/集合、零权重、参数/开关读回、排序/单项重置、保存回滚、账号切换以及权重/字段/股票/周期变化后的过期响应保护。
