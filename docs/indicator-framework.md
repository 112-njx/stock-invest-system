# 详情页指标框架（第一批）

当前目录仅开放 MA、MACD、KDJ、成交量、成交额；不提前开放未验证的指标。

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
