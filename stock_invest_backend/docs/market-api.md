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

### 2) 查看 provider
- **Method**: `GET`
- **Path**: `/api/market/providers`

```bash
curl "http://localhost:8081/api/market/providers"
```
调用返回：
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
调用返回：
{"affectedRows":0,
 "months":3,
 "symbols":["sh600519","sz000001"],
 "note":"uses INSERT ... ON DUPLICATE KEY UPDATE"
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

### 3) 健康检查（C++）
- **Method**: `GET`
- **Path**: `/ping`

```bash
curl "http://localhost:8080/ping"
```
