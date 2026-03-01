# Backend API 文档（按当前 Java/C++ 代码整理）

> Java Base URL: `http://localhost:8081`  
> C++ Base URL: `http://localhost:8080`

## A. 行情模块（Java）

### 1) 获取实时行情
- api作用展示：按股票代码批量获取实时行情（价格、涨跌幅、成交量等）
- Method: `GET`
- Path: `/api/market/quotes`
- Body: 无（使用 Query 参数 `symbols`，逗号分隔）

```bash
curl "http://localhost:8081/api/market/quotes?symbols=sh600519,sz000001"
```

成功调用时返回结果（示例）：

```json
[
  {
    "symbol": "sh600519",
    "lastPrice": 24.34,
    "changePercent": -0.08,
    "openPrice": 24.41,
    "highPrice": 24.61,
    "lowPrice": 24.14,
    "prevClosePrice": 24.36,
    "volume": 1717998,
    "turnover": 41816071.32,
    "quoteTimestamp": 1771841204,
    "source": "eastmoney"
  },
  {
    "symbol": "sz000001",
    "lastPrice": 41.65,
    "changePercent": -0.45,
    "openPrice": 41.89,
    "highPrice": 42.09,
    "lowPrice": 41.45,
    "prevClosePrice": 41.84,
    "volume": 218906,
    "turnover": 9117434.90,
    "quoteTimestamp": 1771841204,
    "source": "eastmoney"
  }
]
```

### 2) 查看行情 Provider
- api作用展示：查看当前启用的行情数据源和可用数据源列表
- Method: `GET`
- Path: `/api/market/providers`
- Body: 无

```bash
curl "http://localhost:8081/api/market/providers"
```

成功调用时返回结果（示例）：

```json
{
  "currentProvider": "eastmoney",
  "availableProviders": [
    "eastmoney",
    "mock"
  ]
}
```

### 3) 采集并写入历史日K
- api作用展示：批量生成/采集近 N 个月日K并写入 `stock_daily_kline`（幂等 upsert）
- Method: `POST`
- Path: `/api/market/history/ingest`
- Body:

```json
{
  "symbols": ["sh600519", "sz000001"],
  "months": 3
}
```

```bash
curl -X POST "http://localhost:8081/api/market/history/ingest" \
  -H "Content-Type: application/json" \
  -d '{"symbols":["sh600519","sz000001"],"months":3}'
```

成功调用时返回结果（示例）：

```json
{
  "symbols": ["sh600519", "sz000001"],
  "months": 3,
  "affectedRows": 132,
  "note": "uses INSERT ... ON DUPLICATE KEY UPDATE"
}
```

### 4) 查询 LOF 实时溢价率
- api作用展示：按 LOF 代码返回实时溢价率，净值优先取 iopv，缺失时退化到上一交易日净值，并标记状态；当不传 `symbols` 时，符号清单优先来自 DB（失败自动降级配置）
- Method: `GET`
- Path: `/api/market/lof/premium`
- Body: 无（使用 Query 参数 `symbols`，可选，逗号分隔；不传则使用默认 2 只 LOF）

```bash
curl "http://localhost:8081/api/market/lof/premium?symbols=sz161129,sz161130"
```

成功调用时返回结果（示例）：

```json
{
  "requestId": "f0e52a14-701a-491c-b8de-01bf7f3979be",
  "generatedAt": "2026-02-27T11:22:33.111Z",
  "items": [
    {
      "symbol": "sz161129",
      "name": "原油LOF",
      "lastPrice": 0.857,
      "nav": 0.842,
      "navType": "IOPV_REALTIME",
      "premiumRate": 0.01781591,
      "status": "OK",
      "quoteTime": 1772187753,
      "navDate": "realtime",
      "cacheHit": true,
      "message": null
    },
    {
      "symbol": "sz161130",
      "name": "基金示例",
      "lastPrice": 1.102,
      "nav": 1.095,
      "navType": "PREV_DAY_NAV",
      "premiumRate": 0.00639269,
      "status": "OK",
      "quoteTime": 1772187753,
      "navDate": "previous-trading-day",
      "cacheHit": false,
      "message": "realtime iopv unavailable, fallback to previous day nav"
    }
  ]
}
```

### 5) 重新加载 LOF symbol 清单（DB -> 本地缓存）
- api作用展示：手动触发从 `lof_symbol_registry` 重新加载 symbol 到本地缓存；若 DB 不可用则自动降级配置清单
- Method: `POST`
- Path: `/api/market/lof/symbols/reload`
- Body: 无

```bash
curl -X POST "http://localhost:8081/api/market/lof/symbols/reload"
```

成功调用时返回结果（示例）：

```json
{
  "source": "db",
  "fallbackToConfig": false,
  "symbolCount": 186,
  "refreshedAt": "2026-02-28T05:20:10.120Z",
  "symbols": ["sz161129", "sz161130", "sh501018"]
}
```

### 6) LOF 溢价率排行（升序/降序）
- api作用展示：按溢价率返回 LOF 排行，支持升序/降序；同溢价率时按最新 `quoteTime` 优先，`premiumRate=null` 固定排最后
- Method: `GET`
- Path: `/api/market/lof/premium/rank`
- Body: 无（使用 Query 参数）

Query 参数：
- `order`：可选，`asc|desc`，默认 `desc`
- `limit`：可选，默认 `20`，范围 `1~200`
- `onlyStatusOk`：可选，默认 `false`
- `tradingOnly`：可选，默认 `false`（为 `true` 时，仅交易时段返回数据；非交易时段返回空列表）

```bash
curl "http://localhost:8081/api/market/lof/premium/rank?order=desc&limit=20&onlyStatusOk=true&tradingOnly=false"
```

成功调用时返回结果（示例）：

```json
{
  "items": [
    {
      "symbol": "sz161129",
      "name": "原油LOF",
      "lastPrice": 0.857,
      "nav": 0.842,
      "navType": "IOPV_REALTIME",
      "premiumRate": 0.01781591,
      "status": "OK",
      "quoteTime": 1772187753,
      "navDate": "realtime",
      "cacheHit": true,
      "message": null
    },
    {
      "symbol": "sz161130",
      "name": "基金示例",
      "lastPrice": 1.102,
      "nav": 1.095,
      "navType": "PREV_DAY_NAV",
      "premiumRate": 0.00639269,
      "status": "OK",
      "quoteTime": 1772187752,
      "navDate": "previous-trading-day",
      "cacheHit": true,
      "message": "realtime iopv unavailable, fallback to previous day nav"
    }
  ],
  "total": 2,
  "filtersApplied": ["onlyStatusOk"],
  "tradingWindow": "OPEN",
  "message": "ok",
  "generatedAt": "2026-03-01T10:15:00.001Z"
}
```

非交易时段且 `tradingOnly=true` 返回示例：

```json
{
  "items": [],
  "total": 0,
  "filtersApplied": ["tradingOnly"],
  "tradingWindow": "CLOSED",
  "message": "trading window is closed",
  "generatedAt": "2026-03-01T12:00:00.001Z"
}
```

---

## B. 回测模块

### 1) Java MA 回测入口
- api作用展示：调用 C++ 回测引擎，返回 MA 回测结果（含信号日期）
- Method: `POST`
- Path: `/api/backtest/ma`
- Body:

```json
{
  "symbol": "sh600519",
  "period": 5,
  "startDate": "2025-11-01",
  "endDate": "2026-02-01"
}
```

```bash
curl -X POST "http://localhost:8081/api/backtest/ma" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"sh600519","period":5,"startDate":"2025-11-01","endDate":"2026-02-01"}'
```

成功调用时返回结果（示例）：

```json
{
  "symbol": "sh600519",
  "strategyCode": "MA_CROSS_5",
  "period": 5,
  "totalSignals": 3,
  "winSignals": 1,
  "successRate": 0.3333333333,
  "records": 50,
  "source": "cpp-backtest-mysql",
  "message": "ok; dateRange=2025-11-01~2026-02-01",
  "crossUpDates": ["2025-12-24", "2026-01-20", "2026-01-22"],
  "crossDownDates": ["2025-12-04", "2025-12-29", "2026-01-21", "2026-01-27"],
  "signals": [
    {
      "date": "2025-12-24",
      "signalCode": "CROSS_UP",
      "signal": "上穿5日线",
      "legacySignal5": "上穿5日线",
      "closePrice": 22.69,
      "ma": 22.308
    }
  ]
}
```

### 2) Java 查询历史回测结果（前端展示）
- api作用展示：按 `symbol + strategyCode` 查询已落库回测结果（含 `payload_json` 中的信号）
- Method: `GET`
- Path: `/api/backtest/results`
- Body: 无（使用 Query 参数）

Query 参数：
- `symbol`：必填，例如 `sh600519`
- `strategyCode`：推荐填，例如 `MA_CROSS_5`
- `strategy`：兼容参数（当 `strategyCode` 为空时生效）
- `limit`：可选，默认 `20`，最大 `200`

```bash
curl "http://localhost:8081/api/backtest/results?symbol=sh600519&strategyCode=MA_CROSS_5&limit=20"
```

成功调用时返回结果（示例）：

```json
[
  {
    "id": 10,
    "strategyCode": "MA_CROSS_5",
    "symbol": "sh600519",
    "period": 5,
    "startDate": "2025-11-01",
    "endDate": "2026-02-01",
    "totalSignals": 3,
    "winSignals": 1,
    "successRate": 0.3333,
    "createdAt": "2026-02-24T21:10:11",
    "crossUpDates": ["2025-12-24", "2026-01-20", "2026-01-22"],
    "crossDownDates": ["2025-12-04", "2025-12-29", "2026-01-21", "2026-01-27"],
    "signals": [
      {
        "date": "2025-12-24",
        "signalCode": "CROSS_UP",
        "signal": "上穿5日线",
        "legacySignal5": "上穿5日线",
        "closePrice": 22.69,
        "ma": 22.308
      }
    ],
    "payloadJson": "{...}"
  }
]
```

### 3) C++ MA 回测引擎接口
- api作用展示：C++ 直接执行 MA 回测，并自动写入 `strategy_backtest_result`
- Method: `POST`
- Path: `/api/backtest/ma`
- Body: 与 Java 回测入口相同

```bash
curl -X POST "http://localhost:8080/api/backtest/ma" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"sh600519","period":5,"startDate":"2025-11-01","endDate":"2026-02-01"}'
```

成功调用时返回结果（示例）：

```json
{
  "symbol": "sh600519",
  "strategyCode": "MA_CROSS_5",
  "period": 5,
  "totalSignals": 3,
  "winSignals": 1,
  "successRate": 0.3333333333,
  "records": 50,
  "source": "cpp-backtest-mysql",
  "message": "ok; dateRange=2025-11-01~2026-02-01",
  "crossUpDates": ["2025-12-24", "2026-01-20", "2026-01-22"],
  "crossDownDates": ["2025-12-04", "2025-12-29", "2026-01-21", "2026-01-27"],
  "signals": [
    {
      "date": "2025-12-24",
      "signalCode": "CROSS_UP",
      "signal": "上穿5日线",
      "legacySignal5": "上穿5日线",
      "closePrice": 22.69,
      "ma": 22.308
    }
  ]
}
```

### 4) C++ MA 计算测试接口
- api作用展示：测试 MA 计算链路（当前为占位返回）
- Method: `POST`
- Path: `/api/analysis/ma`
- Body:

```json
{
  "symbol": "sh600519",
  "period": 5
}
```

成功调用时返回结果（示例）：

```json
{
  "symbol": "sh600519",
  "period": 5,
  "ma": 123.45
}
```

### 5) C++ 健康检查
- api作用展示：检查 C++ 服务是否在线
- Method: `GET`
- Path: `/ping`
- Body: 无

```bash
curl "http://localhost:8080/ping"
```

成功调用时返回结果：

```text
pong
```
