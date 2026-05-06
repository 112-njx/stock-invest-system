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

### 7) LOF 事件发布预留（无对外 HTTP 接口）
- api作用展示：为“按溢价率触发策略”预留标准化事件结构，当前阶段在 Java 内部发布，默认写日志并可选启用桥接通道
- Method: `N/A`
- Path: `N/A`
- Body: `N/A`

事件结构（示例）：

```json
{
  "eventId": "2a2f4e8f-4bb5-4c74-8f1f-8cd44915d7c2",
  "eventType": "LOF_PREMIUM_ALERT",
  "symbol": "sz161129",
  "premiumRate": 0.03510213,
  "status": "OK",
  "navType": "IOPV_REALTIME",
  "quoteTime": 1772190901,
  "producedAt": "2026-03-01T12:10:11.010Z",
  "source": "lof-premium-service",
  "version": "1.0",
  "message": "threshold crossed"
}
```

配置项（示例）：
- `lof.premium.event-publish-enabled=true`
- `lof.premium.bridge-enabled=false`
- `lof.premium.alert-threshold-up=0.03`
- `lof.premium.alert-threshold-down=-0.03`
- `lof.premium.alert-cooldown-seconds=300`

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

---

## C. AI 投资分析模块（Java）

### 1) AI 投资分析
- api作用展示：接收用户自然语言分析请求；若识别到股票代码，则先由 LLM 生成标准 Tool Call，再由 Java 后端统一调用“自定义天数行情接口”和“MA5 上穿/下穿回测接口”获取真实 JSON，整理后再次调用 LLM 输出分析结论；若未识别到股票代码，则终止工具调用链路，仅返回宏观行情分析文本
- Method: `POST`
- Path: `/api/ai/invest/analyze`
- Body:

```json
{
  "prompt": "请分析一下 sh600519 最近走势，结合近30天K线和MA5上穿下穿信号给出看法"
}
```

```bash
curl -X POST "http://localhost:8081/api/ai/invest/analyze" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"请分析一下 sh600519 最近走势，结合近30天K线和MA5上穿下穿信号给出看法"}'
```

成功调用时返回结果（包含股票代码，AI 正常完成分析，示例）：

```json
{
  "requestId": "ai-invest-20260506-0001",
  "mode": "TOOL_CHAIN",
  "prompt": "请分析一下 sh600519 最近走势，结合近30天K线和MA5上穿下穿信号给出看法",
  "symbol": "sh600519",
  "usedDays": 30,
  "toolCalls": [
    {
      "toolName": "get_market_history",
      "arguments": {
        "symbol": "sh600519",
        "days": 30
      }
    },
    {
      "toolName": "get_ma5_cross_signals",
      "arguments": {
        "symbol": "sh600519",
        "period": 5
      }
    }
  ],
  "dataSources": [
    {
      "api": "/api/market/history/ingest",
      "purpose": "拉取近30天历史日K所需数据"
    },
    {
      "api": "/api/backtest/ma",
      "purpose": "获取MA5上穿/下穿信号"
    }
  ],
  "analysisText": "近30个交易日内，该标的整体仍处于震荡偏强区间，最近一次 MA5 上穿信号后价格延续性较强，但短线追高风险也在增加。本分析仅供参考，不构成任何投资建议。",
  "disclaimer": "本分析仅供参考，不构成任何投资建议。",
  "replyTime": "2026-05-06T20:10:11+08:00",
  "degraded": false,
  "fallbackReason": null,
  "rawData": {
    "marketHistorySummary": {
      "days": 30,
      "latestClose": 1688.0,
      "changePercent": 0.034
    },
    "maSignalSummary": {
      "strategyCode": "MA_CROSS_5",
      "crossUpCount": 2,
      "crossDownCount": 1
    }
  }
}
```

成功调用时返回结果（未包含股票代码，仅宏观分析，示例）：

```json
{
  "requestId": "ai-invest-20260506-0002",
  "mode": "MACRO_ONLY",
  "prompt": "最近A股市场整体怎么看",
  "symbol": null,
  "usedDays": 0,
  "toolCalls": [],
  "dataSources": [],
  "analysisText": "当前宏观层面更需要关注成交量修复、政策预期和板块轮动节奏，结论应以市场实际风险偏好变化为准。本分析仅供参考，不构成任何投资建议。",
  "disclaimer": "本分析仅供参考，不构成任何投资建议。",
  "replyTime": "2026-05-06T20:12:01+08:00",
  "degraded": false,
  "fallbackReason": null,
  "rawData": null
}
```

成功调用时返回结果（AI 超时或 Token 超限，降级返回原生数据，示例）：

```json
{
  "requestId": "ai-invest-20260506-0003",
  "mode": "TOOL_CHAIN",
  "prompt": "分析一下 sz000001",
  "symbol": "sz000001",
  "usedDays": 30,
  "toolCalls": [
    {
      "toolName": "get_market_history",
      "arguments": {
        "symbol": "sz000001",
        "days": 30
      }
    },
    {
      "toolName": "get_ma5_cross_signals",
      "arguments": {
        "symbol": "sz000001",
        "period": 5
      }
    }
  ],
  "dataSources": [
    {
      "api": "/api/market/history/ingest",
      "purpose": "拉取近30天历史日K所需数据"
    },
    {
      "api": "/api/backtest/ma",
      "purpose": "获取MA5上穿/下穿信号"
    }
  ],
  "analysisText": "AI 分析阶段超时，已返回原生行情与 MA5 信号数据供前端展示。本分析仅供参考，不构成任何投资建议。",
  "disclaimer": "本分析仅供参考，不构成任何投资建议。",
  "replyTime": "2026-05-06T20:13:45+08:00",
  "degraded": true,
  "fallbackReason": "LLM_TIMEOUT",
  "rawData": {
    "marketHistory": {
      "symbol": "sz000001",
      "days": 30
    },
    "maSignals": {
      "symbol": "sz000001",
      "strategyCode": "MA_CROSS_5"
    }
  }
}
```

接口说明补充：
- 默认分析最近 `30` 天 K 线；若后续 Tool Call 显式给出其他天数，以 Tool Call 参数为准
- LLM 调用需统一经 `AiGatewayClient` 适配器封装，业务层不得直接耦合具体厂商 SDK
- 单次 AI 总耗时建议限制在 `8~12` 秒内，并配置 Token 上限；超限时直接降级返回原生接口数据
- 所有返回都必须固定附带免责声明 `本分析仅供参考，不构成任何投资建议。` 和 `replyTime`
- 需记录全链路日志：原始 prompt、股票代码识别结果、Tool Call、下游接口耗时、AI 耗时、降级原因、最终返回模式
