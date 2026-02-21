# Market 模块接口文档（最小可用版）

> Base URL（本地）：`http://localhost:8081`

## 1) 获取实时行情

- **Method**: `GET`
- **Path**: `/api/market/quotes`
- **Query 参数**:
    - `symbols`（必填）：逗号分隔的股票代码列表。
        - 示例：`sh600519,sz000001,600000`

### 请求示例
```bash
curl "http://localhost:8081/api/market/quotes?symbols=sh600519,sz000001"
```
### 响应示例
```json
[
  {
    "symbol": "sh600519",
    "source": "mock",
    "lastPrice": 154.36,
    "changePercent": 0.29,
    "openPrice": 153.95,
    "highPrice": 154.56,
    "lowPrice": 153.75,
    "prevClosePrice": 153.91,
    "volume": 528933,
    "turnover": 81647671.88,
    "quoteTimestamp": 1739943451
  }
]
```

### 说明
- 当前返回由配置 `market.data.provider` 决定：
  - `eastmoney`：调用东方财富行情接口
  - `mock`：返回本地假数据（用于 C++ / WebSocket 链路联调）
---
## 2) 查看可用 Provider

- **Method**: `GET`
- **Path**: `/api/market/providers`
- **用途**: 查看当前启用 provider 与可切换列表。

### 请求示例

```bash
curl "http://localhost:8081/api/market/providers"
```

### 响应示例

```json
{
  "currentProvider": "mock",
  "availableProviders": [
    "eastmoney",
    "mock"
  ]
}
```

---

## 配置切换示例

`application.properties`:

```properties
market.data.provider=mock
```
