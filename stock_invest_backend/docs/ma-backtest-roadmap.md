# MA 策略回测（功能1）分步实施建议

#
做两点优化：
1. **回测与实时建议共用同一套“策略定义”**（参数、信号规则统一），避免 Java/C++ 两套逻辑漂移。
2. **历史数据写 MySQL 时增加幂等约束**（`symbol + trade_date` 唯一），避免重复采集导致回测偏差。

## 分阶段任务

### Task 1（目前已完成）  2026.2.18
- 设计并落地 MySQL 表结构（`stock_daily_kline`、`strategy_backtest_result`）。
- 新增 Java 回测 API：`POST /api/backtest/ma`。
- 打通 Java -> C++ 回测调用链（先用 mock 结果）。

### Task 2（下一步）
- Java 增加“补齐近 3 个月日K”的采集任务（按 symbol 批量写入 MySQL）。
- 增加去重写入逻辑：`INSERT ... ON DUPLICATE KEY UPDATE`。

### Task 3（下一步）
- C++ 回测引擎接入 MySQL（Connector/C API），按请求参数读取区间数据。
- 实现 MA(5) 策略：上穿买入，下穿卖出；输出总信号数、胜率。

### Task 4（下一步）
- Java 持久化 C++ 回测结果到 `strategy_backtest_result`。
- 增加按 symbol/strategy 的查询接口，供前端展示。
