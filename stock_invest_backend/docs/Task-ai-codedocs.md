# AI 投资分析模块 — 开发日志

---

## Task AI-1：接口契约与 Tool Call 编排层

### 完成内容

**新增接口：`POST /api/ai/invest/analyze`**

接收用户自然语言 `prompt`，自动识别股票代码后进入工具调用链路，最终返回 AI 分析结果。

**处理流程：**

```
用户 prompt
    │
    ├─ 提取股票代码 (regex: sh|sz|bj + 6位数字)
    │
    ├─ 无代码 → MACRO_ONLY 模式
    │         → 直接调用 LLM 做宏观分析
    │
    └─ 有代码 → TOOL_CHAIN 模式
              ├─ ① 调用 LLM (function calling) 生成标准 Tool Call JSON
              ├─ ② Java 解析 Tool Call → 调用内部 API 取真实数据
              │     ├─ get_market_history → 写入+查询 stock_daily_kline 表
              │     └─ get_ma5_cross_signals → 调用 C++ 回测引擎
              ├─ ③ 整理真实 JSON → 构造二次 prompt
              └─ ④ 调用 LLM 生成最终分析文本
```

**新增文件：**

| 文件 | 说明 |
|------|------|
| `ai/config/DeepSeekProperties.java` | DeepSeek API 配置属性类 |
| `ai/config/AiConfig.java` | WebClient Bean 配置 |
| `ai/dto/AiInvestAnalyzeRequest.java` | 请求体（prompt） |
| `ai/dto/AiInvestAnalyzeResponse.java` | 统一返回模型（15 个字段） |
| `ai/dto/ToolCall.java` | 标准 Tool Call 结构 |
| `ai/dto/DataSource.java` | 数据源描述 |
| `ai/controller/AiInvestController.java` | REST 控制器 |
| `ai/service/AiInvestService.java` | 核心编排服务 |

**Tool Call 标准结构：**

```json
{
  "toolName": "get_market_history",
  "arguments": {
    "symbol": "sh600519",
    "days": 30
  }
}
```

**统一返回模型字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `requestId` | String | 全链路追踪 ID，格式 `ai-invest-YYYYMMDD-NNNN` |
| `mode` | String | `TOOL_CHAIN` / `MACRO_ONLY` |
| `prompt` | String | 原始用户输入 |
| `symbol` | String | 识别到的股票代码（无则为 null） |
| `usedDays` | int | 实际使用的 K 线天数（默认 30） |
| `toolCalls` | List | LLM 生成的 Tool Call 列表 |
| `dataSources` | List | 调用的下游数据源说明 |
| `analysisText` | String | AI 分析文本 |
| `disclaimer` | String | 免责声明（每条必含） |
| `replyTime` | OffsetDateTime | 回复时间（Asia/Shanghai） |
| `degraded` | boolean | 是否降级 |
| `fallbackReason` | String | 降级原因 |
| `rawData` | Map | 原生数据摘要 |

**修改文件：**

| 文件 | 改动 |
|------|------|
| `market/history/repository/StockDailyKlineRepository.java` | 新增 `findBySymbolAndDays` 接口 |
| `market/history/repository/MySqlStockDailyKlineRepository.java` | 实现 `findBySymbolAndDays`（JDBC 查询） |
| `application.properties` | 新增 DeepSeek 配置项 |

**降级策略：**

- LLM Tool Call 生成失败 → 使用默认 Tool Call（30 天 K 线 + MA5）
- 单个 Tool Call 执行失败 → 标记 error 放入 aggregatedData，其他继续
- 最终分析 LLM 超时 → `degraded=true`，返回原生数据供前端展示
- 无股票代码 → 跳过所有工具调用，直接宏观分析模式

---

## Task AI-2：AiGatewayClient 适配器与真实数据聚合层

### 完成内容

**引入 AiGatewayClient 适配器抽象层**，将 LLM 调用逻辑从业务层完全解耦。

**架构变化：**

```
重构前：AiInvestService → WebClient + DeepSeekProperties（直连）
重构后：AiInvestService → AiGatewayClient（接口）
                              └── DeepSeekAiGatewayClient（实现）
                                       └── WebClient
```

**新增文件：**

| 文件 | 说明 |
|------|------|
| `ai/gateway/AiGatewayClient.java` | LLM 网关统一接口 |
| `ai/gateway/DeepSeekAiGatewayClient.java` | DeepSeek 实现（封装 HTTP/解析/错误归一化） |
| `ai/gateway/model/GatewayToolDefinition.java` | 工具定义模型 |
| `ai/gateway/model/GatewayToolCallResult.java` | Tool Call 返回模型 |
| `ai/gateway/model/GatewayAnalysisResult.java` | 分析返回模型 |

**AiGatewayClient 接口方法：**

| 方法 | 用途 | 返回 |
|------|------|------|
| `requestToolCalls(sysPrompt, userPrompt, tools)` | 请求 LLM 生成 Tool Call | `GatewayToolCallResult` |
| `generateAnalysis(sysPrompt, userPrompt)` | 请求 LLM 生成文本分析 | `GatewayAnalysisResult` |
| `getProviderName()` | 返回厂商名称 | `"deepseek"` |

**归一化返回模型字段：**

两者均包含：
- `latencyMs` — 调用耗时（毫秒）
- `promptTokens` / `completionTokens` — Token 消耗
- `success` — 是否成功
- `errorMessage` — 归一化错误码

**错误码归一化：**

| 原始异常 | 归一化错误码 |
|----------|-------------|
| timeout | `LLM_TIMEOUT` |
| HTTP 401/403 | `LLM_AUTH_ERROR` |
| HTTP 429 | `LLM_RATE_LIMITED` |
| HTTP 5xx | `LLM_UPSTREAM_ERROR` |
| 其他 | `LLM_ERROR: {message}` |

**修改文件：**

| 文件 | 改动 |
|------|------|
| `ai/service/AiInvestService.java` | 移除 WebClient/DeepSeekProperties，改为注入 AiGatewayClient |
| `ai/config/AiConfig.java` | 新增 `AiGatewayClient` Bean 注册 |
| `application.properties` | 新增 `ai.provider=deepseek` |
| `pom.xml` | 新增 `jackson-databind` 依赖，配置 Lombok annotation processor |
| `lof/service/LofPremiumSourceService.java` | 移除文件头 BOM 字符（修复编译阻塞） |

---

## 配置说明

### application.properties 新增配置

```properties
# AI provider: deepseek (默认，后续可扩展 openai / qwen 等)
ai.provider=deepseek

# DeepSeek API 配置
ai.deepseek.base-url=https://api.deepseek.com
ai.deepseek.api-key=                    # 必填：在 DeepSeek 开放平台申请
ai.deepseek.model=deepseek-chat         # 模型名称
ai.deepseek.timeout-millis=30000        # 超时时间（毫秒）
```

### 使用前必须配置

1. **申请 DeepSeek API Key**：访问 https://platform.deepseek.com 注册并获取 API Key
2. **填入配置**：将 API Key 写入 `application.properties` 的 `ai.deepseek.api-key` 字段
3. **确保 MySQL 可用**：`market.history.mysql.enabled=true`，数据库 `invest_stock_system` 已建表 `stock_daily_kline`
4. **确保 C++ 回测引擎运行**：`backtest.engine.base-url=http://localhost:8080`（MA5 信号依赖）

### pom.xml 新增依赖

```xml
<!-- JSON 序列化（AI 模块数据聚合用） -->
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
```

### 编译配置（pom.xml build 节点）

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.projectlombok</groupId>
                <artifactId>lombok</artifactId>
                <version>1.18.42</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
```

---

## 接口调用示例

### 带股票代码（TOOL_CHAIN 模式）

```bash
curl -X POST "http://localhost:8081/api/ai/invest/analyze" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"请分析一下 sh600519 最近走势，结合近30天K线和MA5上穿下穿信号给出看法"}'
```

### 无股票代码（MACRO_ONLY 模式）

```bash
curl -X POST "http://localhost:8081/api/ai/invest/analyze" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"最近A股市场整体怎么看"}'
```
