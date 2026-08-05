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

---

## Task AI-3：性能降级、风控文案与全链路日志

### 完成内容

**1. 全局超时控制（8~12 秒）**

在 `AiInvestService` 层引入 `ExecutorService` + `Future.get(timeout)` 机制：

- 超时阈值通过 `ai.analysis.timeout-seconds` 配置（默认 10 秒）
- 超时后通过 `future.cancel(true)` 中断执行线程
- 超时返回 `degraded=true`、`fallbackReason=GLOBAL_TIMEOUT` 的降级响应
- Controller 层额外设置 +5 秒安全网超时，防止 Executor 自身挂死

**2. Token 上限控制**

在 `DeepSeekAiGatewayClient` 的 `buildChatRequest()` 中，每次 LLM 请求均携带 `max_tokens` 参数：

```java
body.put("max_tokens", properties.getMaxTokens());  // 默认 4096
```

配置：`ai.deepseek.max-tokens=4096`

超限时 DeepSeek API 会返回错误，Gateway 层通过 `normalizeError()` 统一映射为 `LLM_ERROR`，Service 层降级返回。

**3. 免责声明与风控文案**

- 所有返回固定附带 `disclaimer`：`本分析仅供参考，不构成任何投资建议。`
- 所有返回固定附带 `replyTime`（Asia/Shanghai 时区）
- 降级场景的 `analysisText` 在服务端硬编码中文降级文案，不直接暴露 LLM 原始错误（避免展示技术细节给用户）

**4. 全链路日志**

每条请求以 `[requestId]` 为前缀，覆盖以下节点：

| 日志节点 | 关键字 | 记录内容 |
|----------|--------|---------|
| 请求入口 | `REQUEST_START` | 原始 prompt（截断至 200 字符）、股票代码识别结果、provider |
| 宏观 LLM 调用 | `MACRO_LLM_START` / `MACRO_LLM_END` | provider、耗时、Token 消耗、成功/失败 |
| Tool Call LLM 调用 | `TOOL_CALL_LLM_START` / `TOOL_CALL_LLM_END` | provider、耗时、Token 消耗、工具数量 |
| 单个 Tool Call 内容 | `TOOL_CALL_ITEM` | toolName、arguments |
| 下游接口执行 | `TOOL_EXEC_START` / `TOOL_EXEC_END` | toolName、arguments、耗时 |
| 下游接口失败 | `TOOL_EXEC_FAIL` | toolName、耗时、异常信息 |
| 最终分析 LLM | `ANALYSIS_LLM_START` / `ANALYSIS_LLM_END` | provider、耗时、Token 消耗、成功/失败 |
| LLM 调用失败 | `TOOL_CALL_LLM_FALLBACK` / `MACRO_LLM_FAIL` / `ANALYSIS_LLM_FAIL` | 归一化错误码 |
| 全局超时 | `GLOBAL_TIMEOUT` | 总耗时、超时阈值 |
| 致命错误 | `FATAL_ERROR` | 异常信息、总耗时 |
| 响应完成 | `RESPONSE` | mode、degraded、总耗时 |

**示例日志链路：**

```
[ai-invest-20260516-0001] REQUEST_START | prompt="请分析一下 sh600519..." | stockCode=sh600519 | provider=deepseek
[ai-invest-20260516-0001] TOOL_CALL_LLM_START | provider=deepseek
[ai-invest-20260516-0001] TOOL_CALL_LLM_END | success=true | latencyMs=1234 | promptTokens=520 | completionTokens=85 | toolCount=2
[ai-invest-20260516-0001] TOOL_CALL_ITEM | toolName=get_market_history | args={symbol=sh600519, days=30}
[ai-invest-20260516-0001] TOOL_CALL_ITEM | toolName=get_ma5_cross_signals | args={symbol=sh600519, period=5}
[ai-invest-20260516-0001] TOOL_EXEC_START | tool=get_market_history | args={symbol=sh600519, days=30}
[ai-invest-20260516-0001] TOOL_EXEC_END | tool=get_market_history | latencyMs=156
[ai-invest-20260516-0001] TOOL_EXEC_START | tool=get_ma5_cross_signals | args={symbol=sh600519, period=5}
[ai-invest-20260516-0001] TOOL_EXEC_END | tool=get_ma5_cross_signals | latencyMs=2340
[ai-invest-20260516-0001] ANALYSIS_LLM_START | provider=deepseek
[ai-invest-20260516-0001] ANALYSIS_LLM_END | success=true | latencyMs=3456 | promptTokens=1520 | completionTokens=280
[ai-invest-20260516-0001] RESPONSE | mode=TOOL_CHAIN | degraded=false | totalLatencyMs=7234
```

**5. 日志安全——敏感信息保护**

- LLM API Key 不出现在任何日志中（仅存储于配置文件，日志只打印 provider 名称）
- 用户 prompt 日志截断至 200 字符（避免超长输入撑爆日志）
- K 线原始数据不写入日志（只记录 records 数量）
- 归一化错误码只在日志中展示错误码，原始异常信息在 Service 层被包装

**6. 降级矩阵**

| 异常场景 | 响应 mode | degraded | fallbackReason | analysisText |
|----------|-----------|----------|---------------|-------------|
| 全局超时 | TOOL_CHAIN / MACRO_ONLY | true | `GLOBAL_TIMEOUT` | 固定降级文案 |
| LLM 调用失败 | 原 mode | true | 归一化错误码 | 固定降级文案 |
| Tool Call 解析失败 | TOOL_CHAIN | false | — | 正常分析（使用默认 tools） |
| 单个 Tool 执行失败 | TOOL_CHAIN | false | — | 正常分析（该 tool 标记 error） |
| 未知错误 | TOOL_CHAIN / MACRO_ONLY | true | `FATAL_ERROR: {msg}` | 固定降级文案 |

### 配置变更

**新增配置：**

```properties
# 全局超时（秒），建议 8~12
ai.analysis.timeout-seconds=10

# LLM 单次调用 max_tokens 上限
ai.deepseek.max-tokens=4096
```

**环境变量形式（容器化部署）：**

```bash
AI_ANALYSIS_TIMEOUT_SECONDS=10
AI_DEEPSEEK_MAX_TOKENS=4096
```

### 修改文件清单

| 文件 | 改动 |
|------|------|
| `ai/service/AiInvestService.java` | 新增 `ExecutorService` 超时控制、全链路结构化日志、`buildTimeoutFallback`、`buildErrorFallback`、`truncatePrompt` |
| `ai/controller/AiInvestController.java` | 新增 Mono 安全网超时（+5s），`onErrorResume` 兜底 |
| `ai/gateway/DeepSeekAiGatewayClient.java` | `max_tokens` 传入请求体、成功 case 新增 INFO 日志（含耗时/Token） |
| `ai/config/DeepSeekProperties.java` | 新增 `maxTokens` 字段 |
| `application.properties` | 新增 `ai.analysis.timeout-seconds`、`ai.deepseek.max-tokens` |

### 验收点对照

| 验收标准 | 实现情况 |
|----------|---------|
| AI 异常时接口仍可用，能稳定返回原生数据或宏观分析文本 | 所有异常路径均有降级响应，HTTP 200 始终返回 |
| 每条返回都带固定免责声明与回复时间 | `DISCLAIMER` + `replyTime` 在 `buildBaseResponse()` 中固化 |
| 可通过日志还原一次完整调用链路 | 每个关键节点以 `[requestId]` 前缀记录结构化日志，覆盖 10 个日志节点 |
