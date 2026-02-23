# Backend API 文档（按当前 Java/C++ 代码自动整理）

> Java Base URL: `http://localhost:8081`  
> C++ Base URL: `http://localhost:8080`

## A. 行情模块（Java）

### 1) 获取实时行情
- **Method**: `GET`
- **Path**: `/api/market/quotes`
- **Query**: `symbols`（必填，逗号分隔）

```bash
curl "http://localhost:8081/api/market/quotes?symbols=sh600519,sz000001"
```
返回数据：
[
{
"changePercent": -0.08,
"highPrice": 24.61,
"lastPrice": 24.34,
"lowPrice": 24.14,
"openPrice": 24.41,
"prevClosePrice": 24.36,
"quoteTimestamp": 1771841204,
"source": "mock",
"symbol": "sh600519",
"turnover": 41816071.32,
"volume": 1717998
},
{
"changePercent": -0.45,
"highPrice": 42.09,
"lastPrice": 41.65,
"lowPrice": 41.45,
"openPrice": 41.89,
"prevClosePrice": 41.84,
"quoteTimestamp": 1771841204,
"source": "mock",
"symbol": "sz000001",
"turnover": 9117434.90,
"volume": 218906
}
]

### 2) 查看 provider
- **Method**: `GET`
- **Path**: `/api/market/providers`

```bash
curl "http://localhost:8081/api/market/providers"
```
调用返回：
{
  "availableProviders": [
  "eastmoney",
  "mock"
  ],
  "currentProvider": "mock"
}

### 3) 生成近N月日K假数据并写入MySQL
- **Method**: `POST`
- **Path**: `/api/market/history/ingest`
- **Body**（可选）:

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
调用返回(如果自动写数据库参数为false)：
{"affectedRows":0,
 "months":3,
 "symbols":["sh600519","sz000001"],
 "note":"uses INSERT ... ON DUPLICATE KEY UPDATE"
}
（如果自动写数据库参数为true）:
{
  "note": "uses INSERT ... ON DUPLICATE KEY UPDATE",
  "symbols": [
  "sh600519",
  "sz000001"
  ],
  "months": 3,
  "affectedRows": 132
}
> 写库语句为 `INSERT ... ON DUPLICATE KEY UPDATE`，可重复调用不产生重复主业务记录。

---

## B. 回测模块

### 1) Java 对外回测接口
- **Method**: `POST`
- **Path**: `/api/backtest/ma`
- **Body**（必填）:

```json
{
  "symbol": "sh600519",
  "period": 5,
  "startDate": "2025-11-01",
  "endDate": "2026-02-01"
}
```
返回数据：
{
"message": "mock result; dateRange=2025-11-01~2026-02-01",
"period": 5,
"source": "cpp-backtest-mock",
"successRate": 0.5833333333333334,
"symbol": "sh600519",
"totalSignals": 12,
"winSignals": 7
}

```bash
curl -X POST "http://localhost:8081/api/backtest/ma" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"sh600519","period":5,"startDate":"2025-11-01","endDate":"2026-02-01"}'
```

### 2) C++ 引擎接口（Java会调用它）
- **Method**: `POST`
- **Path**: `/api/backtest/ma`
- **Body**：与上面一致

```bash
curl -X POST "http://localhost:8080/api/backtest/ma" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"sh600519","period":5,"startDate":"2025-11-01","endDate":"2026-02-01"}'
```
返回数据:与上面一致

### 3) 健康检查（C++）
- **Method**: `GET`
- **Path**: `/ping`

```bash
curl "http://localhost:8080/ping"
```

返回数据：pong