请你用中文回答我

该项目是一个策略回测平台，功能例如：
（1）设置各种策略（例如MA突破买入，跌破卖出等买入卖出策略），根据历史数据显示该策略在每个股票的成功率。
（2）显示一些lof基金实时溢价率
（3）根据策略，实时根据数据为用户提供投资建议

当前开发思路：
以 C++ 为性能核心、以 Java 微服务为业务编排、以 Redis 为状态与加速层的股票分析后端系统

当前部分开发思路：目前已实现：api调用加上相应股票代码，返回股票数据。
这里以简单的MA策略战法为例（股价超过五日线买入，跌破五日线卖出）来实现应用相应的功能，调用后：
（1）对于策略回测成功率生成：创建mysql存储历史数据，C++计算引擎直接从mysql中获取数据，然后C++计算引擎返回策略成功率。
（2）对于实时买入建议生成：取决于相应的策略，以上面的MA策略为例，使用Redis存最新价 + 发布事件，
同时将redis中的数据存储到mysql中变成历史数据，Java 收到 tick 后把标准化 JSON 推给 C++ 服务（HTTP/gRPC），C++ 返回信号，Java 通过 WebSocket 推送前端。

项目数据流：
      东方财富接口 / AkShare（Python）
      ↓
      数据清洗 / 标准化
      ↓
      数据库（MySQL / PostgreSQL）
      ↓
      Spring Boot（读取 + 业务决策）
      ↓
      C++ 分析服务（纯计算）

【会话记录约定】
每次会话结束，我将把“关键上下文/进度/下一步”追加到本文件，便于下次恢复协作。
每次对话结束，你将补充market-api.md文件，每个api包括：,api作用展示,Method, Path, Body,成功调用时返回结果，格式参考文档中已经编辑好的api格式。
【会话记录 2026-02-23】
关键上下文：实现 C++ 回测引擎按 Java POST /api/backtest/ma 参数从 MySQL 读取区间日K，并补齐 MA 策略计算与信号日期返回。
进度：
- 已新增 C++ 数据模型：DailyBar / MaSignal / MaBacktestResult。
- 已新增 MA 指标计算：SMA 序列（滚动窗口）。
- 已新增 MA 回测服务：识别上穿/下破信号，计算 totalSignals / winSignals / successRate。
- 已新增 MySQL 仓储：按 symbol + [startDate,endDate] 查询 stock_daily_kline 并返回有序日K。
- 已改造 /api/backtest/ma：
  - 读取请求参数并校验；
  - 连接 MySQL 读取区间数据；
  - 调用回测服务计算结果；
  - 返回 crossUpDates/crossDownDates/signals（含日期与价格）；
  - 保留兼容字段 legacySignal5（上穿5日线/下破5日线）。
- 已更新 CMake：可选链接 MySQL 客户端库（未检测到时会给出运行时错误提示）。
下一步：
- 在本机安装并配置 MySQL C 客户端开发库，确保 CMake 能找到 mysql.h 和 mysqlclient/libmysql。
- 用真实数据联调 Java -> C++ /api/backtest/ma，确认 Java DTO 是否需要新增 signals 字段展示明细。
- 需要时将信号文本从“legacySignal5”逐步迁移为 signalCode + signal（按 period 动态）。
