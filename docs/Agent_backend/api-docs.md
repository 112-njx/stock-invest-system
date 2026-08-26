api文档，你需要按照：
大标题api分类，分类下的序号
接口名称：
请求 Method：
请求 Path：
接口作用：
请求 Body：有无（参数位置：Query/Path/Body-JSON） --->上面到这些,需要符合简洁的特征,均一句话或一个单词概括
请求示例（curl）
成功返回示例
进行编写所有的软件api.

---

# 行情查询 API（Market）

## 1. 标的列表

- **接口名称**：标的列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/symbols
- **接口作用**：标的列表（type/search/is_fixed 过滤），供下拉选择与 G/H 区固定指数列表。
- **请求 Body**：无（Query：type=stock|etf|index、search、is_fixed=0|1）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/symbols?type=index&is_fixed=1"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":70,"code":"000001","name":"上证指数","type":"index","market":"SSE","etf_linked":"","is_fixed_index":true,"sort_order":1},...]}
```

## 2. 标的搜索联想

- **接口名称**：标的搜索联想
- **请求 Method**：GET
- **请求 Path**：/api/v1/symbols/search
- **接口作用**：6位代码/名称联想（已入库优先，精确代码优先）。
- **请求 Body**：无（Query：q=代码或名称）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/symbols/search?q=600519"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":125,"code":"600519","name":"贵州茅台","type":"stock","market":"SSE"}]}
```

## 3. K线查询

- **接口名称**：K线查询
- **请求 Method**：GET
- **请求 Path**：/api/v1/kline
- **接口作用**：多周期K线（15m/1d/1w/1mon，区间/分页），时间 UTC。
- **请求 Body**：无（Query：symbol=代码、period、start、end、limit、offset）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/kline?symbol=600519&period=1d"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"ts":"2026-08-07T08:00:00","open":1308.66,"high":1315.28,"low":1301.0,"close":1309.22,"volume":24976,"amount":3266919421.0},...]}
```

## 4. 批量实时快照

- **接口名称**：批量实时快照
- **请求 Method**：GET
- **请求 Path**：/api/v1/snapshot
- **接口作用**：批量实时快照（合并特殊字段：个股 market_cap/pe、ETF nav/premium、指数 pe）。
- **请求 Body**：无（Query：symbols=逗号分隔的 symbol_id）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/snapshot?symbols=70,125"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"symbol_id":70,"code":"000001","name":"上证指数","type":"index","price":null,"extra":{}},...]}
```

## 5. 同步状态查询

- **接口名称**：同步状态查询
- **请求 Method**：GET
- **请求 Path**：/api/v1/sync-status
- **接口作用**：查询某同步范围（fixed_indices/catalog/watchlist）的最新同步进度，行情页加载时轮询展示"数据同步中（X/49）"。
- **请求 Body**：无（Query：scope=fixed_indices|watchlist|catalog）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/sync-status?scope=fixed_indices"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"status":"running","progress":35,"total":49,"message":"已同步 35/49"}}
```

（无进行中同步时返回 `{"status":"done","progress":100,"total":0,"message":"无进行中的同步"}`）

## 6. 一次性全量同步

- **接口名称**：一次性全量同步
- **请求 Method**：POST
- **请求 Path**：/api/v1/fetch-all
- **接口作用**：免鉴权，同步执行固定指数K线+快照 + 全量实时快照（本地测试无 Celery/beat 时一次性补齐数据）。
- **请求 Body**：无

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/fetch-all"
```

**成功返回示例**

```json
{"code":0,"msg":"全量同步完成","data":{"fixed_indices":{"000001":{"1d":1,"1w":1,"1mon":1}},"realtime":{"synced":49}}}
```

# 用户鉴权 API（Auth）

## 1. 用户注册

- **接口名称**：用户注册
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/register
- **接口作用**：注册新用户（密码 bcrypt 哈希入库），成功后签发 JWT。
- **请求 Body**：有（Body-JSON：username、password、email?、nickname?）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/register" -H "Content-Type: application/json" -d '{"username":"alice","password":"pass123456","nickname":"Alice"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"token":"eyJhbGciOi...","user":{"id":1,"username":"alice","email":null,"nickname":"Alice","avatar_url":null,"created_at":"2026-08-09T05:00:00Z"}}}
```

## 2. 用户登录

- **接口名称**：用户登录
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/login
- **接口作用**：用户名+密码校验，成功签发 JWT。
- **请求 Body**：有（Body-JSON：username、password）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" -H "Content-Type: application/json" -d '{"username":"alice","password":"pass123456"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"token":"eyJhbGciOi...","user":{"id":1,"username":"alice"}}}
```

# 用户信息 API（Users）

## 1. 当前用户信息

- **接口名称**：当前用户信息
- **请求 Method**：GET
- **请求 Path**：/api/v1/users/me
- **接口作用**：获取当前登录用户信息。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/users/me" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"username":"alice","email":null,"nickname":"Alice","avatar_url":null,"created_at":"2026-08-09T05:00:00Z"}}
```

## 2. 更新当前用户

- **接口名称**：更新当前用户
- **请求 Method**：PUT
- **请求 Path**：/api/v1/users/me
- **接口作用**：更新昵称/头像。
- **请求 Body**：有（Body-JSON：nickname?、avatar_url?）

**请求示例（curl）**

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/users/me" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"nickname":"新昵称"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"username":"alice","nickname":"新昵称","avatar_url":null}}
```

# 重点关注股票 API（Watchlist）

## 1. 关注列表

- **接口名称**：关注列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/watchlist
- **接口作用**：当前用户重点关注股票列表（合并实时快照：代码/名称/最新价/涨跌幅）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/watchlist" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"symbol_id":125,"code":"600519","name":"贵州茅台","type":"stock","price":1309.22,"change":4.57,"change_pct":0.35,"updated_at":"2026-08-09T05:00:00Z","created_at":"2026-08-09T05:00:00Z"}]}
```

## 2. 添加关注

- **接口名称**：添加关注
- **请求 Method**：POST
- **请求 Path**：/api/v1/watchlist
- **接口作用**：添加标的到关注列表（UNIQUE(user,symbol) 幂等，重复添加不报错）。
- **请求 Body**：有（Body-JSON：symbol=标的代码或 symbol_id）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/watchlist" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"symbol":"600519"}'
```

**成功返回示例**

```json
{"code":0,"msg":"添加成功","data":{"id":1,"symbol_id":125,"code":"600519","name":"贵州茅台","type":"stock","price":null,"change":null,"change_pct":null,"updated_at":null,"created_at":"2026-08-09T05:00:00Z"}}
```

## 3. 删除关注

- **接口名称**：删除关注
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/watchlist/{watchlist_id}
- **接口作用**：按关注记录 id 删除（仅本人可删）。
- **请求 Body**：无（Path：watchlist_id）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/watchlist/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 支撑/压力位 API（Support-Resistance）

## 1. 支撑压力位列表

- **接口名称**：支撑压力位列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/support-resistance
- **接口作用**：当前用户支撑/压力位（可按标的过滤），K 线图叠加横线数据源。
- **请求 Body**：无（Query：symbol_id?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/support-resistance?symbol_id=125" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"symbol_id":125,"type":"support","price":1200.0,"note":"强支撑","created_at":"2026-08-09T05:00:00Z"}]}
```

## 2. 添加支撑压力位

- **接口名称**：添加支撑压力位
- **请求 Method**：POST
- **请求 Path**：/api/v1/support-resistance
- **接口作用**：添加支撑/压力位（type=support|pressure）。
- **请求 Body**：有（Body-JSON：symbol=标的代码或 symbol_id、type、price、note?）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/support-resistance" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"symbol":"600519","type":"support","price":1200,"note":"强支撑"}'
```

**成功返回示例**

```json
{"code":0,"msg":"添加成功","data":{"id":1,"symbol_id":125,"type":"support","price":1200.0,"note":"强支撑","created_at":"2026-08-09T05:00:00Z"}}
```

## 3. 删除支撑压力位

- **接口名称**：删除支撑压力位
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/support-resistance/{sr_id}
- **接口作用**：删除支撑/压力位记录（仅本人可删）。
- **请求 Body**：无（Path：sr_id）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/support-resistance/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 技术指标 API（Indicators）

## 1. 技术指标查询

- **接口名称**：技术指标查询
- **请求 Method**：GET
- **请求 Path**：/api/v1/indicators
- **接口作用**：服务端计算 MACD/KDJ/成交量/成交额（前端只渲染不计算），Redis 缓存（key 含 K 线最新 ts，新数据到达自动失效）。
- **请求 Body**：无（Query：symbol=代码或 id、period=15m|1d|1w|1mon、names=逗号分隔指标名、start?、end?、limit?、params?=JSON 指标参数）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/indicators?symbol=600519&period=1d&names=macd,kdj&params=%7B%22kdj%22%3A%7B%22n%22%3A9%7D%7D"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"ts":"2026-08-07T08:00:00","open":1308.66,"high":1315.28,"low":1301.0,"close":1309.22,"volume":24976,"amount":3266919421.0,"macd_dif":29.46,"macd_dea":33.11,"macd_hist":-7.30,"kdj_k":44.22,"kdj_d":59.02,"kdj_j":14.63},...]}
```

# 会话与消息 API（Conversations）

## 1. 创建会话

- **接口名称**：创建会话
- **请求 Method**：POST
- **请求 Path**：/api/v1/conversations
- **接口作用**：创建新会话（默认标题「新会话」），J区历史会话数据源。
- **请求 Body**：有（Body-JSON：title?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/conversations" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{}'
```

**成功返回示例**

```json
{"code":0,"msg":"创建成功","data":{"id":1,"title":"新会话","created_at":"2026-08-09T05:00:00Z","updated_at":"2026-08-09T05:00:00Z"}}
```

## 2. 会话列表

- **接口名称**：会话列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/conversations
- **接口作用**：当前用户会话列表（按更新时间倒序）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/conversations" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"title":"新会话","created_at":"...","updated_at":"..."}]}
```

## 3. 重命名会话

- **接口名称**：重命名会话
- **请求 Method**：PATCH
- **请求 Path**：/api/v1/conversations/{conversation_id}
- **接口作用**：重命名会话（仅本人）。
- **请求 Body**：有（Body-JSON：title；Path：conversation_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/conversations/1" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"title":"贵州茅台研究"}'
```

**成功返回示例**

```json
{"code":0,"msg":"重命名成功","data":{"id":1,"title":"贵州茅台研究","created_at":"...","updated_at":"..."}}
```

## 4. 删除会话

- **接口名称**：删除会话
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/conversations/{conversation_id}
- **接口作用**：删除会话及其全部消息（仅本人）。
- **请求 Body**：无（Path：conversation_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/conversations/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

## 5. 追加消息

- **接口名称**：追加消息
- **请求 Method**：POST
- **请求 Path**：/api/v1/conversations/{conversation_id}/messages
- **接口作用**：向会话追加消息（user/assistant/system），可绑定标的 symbol_id。
- **请求 Body**：有（Body-JSON：role、content、symbol?=代码或symbol_id、tokens?；Path：conversation_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/conversations/1/messages" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"role":"user","content":"分析贵州茅台","symbol":"600519"}'
```

**成功返回示例**

```json
{"code":0,"msg":"发送成功","data":{"id":1,"conversation_id":1,"role":"user","symbol_id":125,"content":"分析贵州茅台","tokens":null,"created_at":"2026-08-09T05:00:00Z"}}
```

## 6. 拉取消息

- **接口名称**：拉取消息
- **请求 Method**：GET
- **请求 Path**：/api/v1/conversations/{conversation_id}/messages
- **接口作用**：按会话拉取消息（时间升序），前端渲染历史对话。
- **请求 Body**：无（Path：conversation_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/conversations/1/messages" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"conversation_id":1,"role":"user","symbol_id":125,"content":"分析贵州茅台","tokens":null,"created_at":"..."}]}
```

# AI 聊天 API（Chat）

## 1. 流式对话

- **接口名称**：流式对话（SSE）
- **请求 Method**：POST
- **请求 Path**：/api/v1/chat
- **接口作用**：AI 流式对话（SSE 透传前端）。保存消息→组装上下文（系统提示+历史+工具）→ReAct Agent 取数→流式输出；落库 chat_messages + agent_runs/agent_steps。LLM 不可用/失败返回降级文案。
- **请求 Body**：有（Body-JSON：content、conversation_id?、symbol?=代码或symbol_id、agent_id?、run_type?=diagnostic|plan|radar|strategy|custom；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -N -X POST "http://127.0.0.1:8000/api/v1/chat" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"content":"分析贵州茅台趋势","symbol":"600519","run_type":"diagnose"}'
```

**成功返回示例（SSE data 行）**

```
data: {"type":"start"}
data: {"type":"tool_call","tool":"market_snapshot","input":{"symbol":"600519"}}
data: {"type":"delta","seq":1,"content":"..."}
data: {"type":"delta","seq":2,"content":"..."}
data: {"type":"done","message_id":9,"conversation_id":2,"run_id":3}
```

**SSE 事件协议（V0.2 阶段五增强）**

| 事件 | 字段 | 说明 |
|---|---|---|
| `start` | — | 流开始 |
| `delta` | `seq`(递增序号)、`content`、`node`?(深度模式) | 文本增量；seq 用于断点续传 |
| `tool_call` | `tool`、`input` | Agent 调用工具 |
| `tool_result` | `tool`、`preview` | 工具返回预览 |
| `agent_step` | `node`、`status`、`summary`?、`duration_ms`?、`error`? | 深度模式多智能体节点状态：`running`（开始）/`done`（完成，带 summary+耗时）/`failed`（失败，带 error） |
| `usage` | `prompt`、`completion`、`total` | token 用量（阶段八 8.2，估算值，done 前推送） |
| `strategy_ready` | `strategy_id`、`auto_backtest` | 策略生成校验通过并已保存（阶段八 8.6，前端可自动发起回测） |
| `title` | `title`、`conversation_id` | 会话标题自动生成完成（阶段八 8.7，done 后异步推送） |
| `done` | `message_id`、`conversation_id`、`run_id`、`truncated`?、`reason`?、`partial`? | 正常结束；超时截断时带 `truncated:true,reason:"timeout"`；部分节点异常时带 `partial:true` |
| `error` | `code`、`message`、`retryable`、`retry_after`? | 错误帧（见下错误码） |
| `resync` | `conversation_id` | 断点续传缓存已过期，提示前端重新加载完整消息 |

- **心跳**：空闲每 15s 发送注释行 `:keepalive\n\n`（防 Nginx proxy_read_timeout）。
- **三级超时**：首字 30s / 单 delta 间隔 15s / 总流式 120s，超时返回已生成内容 + `done(truncated=true,reason="timeout")`。
- **错误码**：`NETWORK_ERROR`(可重试)、`RATE_LIMITED`(可重试,带retry_after)、`TOKEN_INVALID`(不可重试)、`TOKEN_QUOTA`(不可重试)、`CONTENT_FILTERED`(不可重试)、`PROVIDER_UNAVAILABLE`(可重试)、`TIMEOUT`(可重试)。
- **错误分级降级**：LLM 熔断/未配置 Key → 返回「AI服务暂时不可用，已切换基础分析模式」+ 规则指标文案；token 无效/余额不足 → 「您的DeepSeek API Key无效或余额不足，请检查配置」；工具失败 → 输出标注「行情数据暂时不可用，以下分析基于历史数据」。

**错误帧示例**

```
data: {"type":"error","code":"RATE_LIMITED","message":"请求过于频繁，请30秒后重试","retryable":true,"retry_after":30}
```

## 2. 断点续传（Resume）

- **接口名称**：流式断点续传（SSE）
- **请求 Method**：GET
- **请求 Path**：/api/v1/chat/resume
- **接口作用**：流式中断后前端带 `last_seq` 重连，后端从 Redis 缓存补发 `seq>last_seq` 的 delta（不重复不丢失），补发完成后若流已结束再发 `done`；缓存已过期（TTL 600s）返回 `{"type":"resync"}` 提示重新加载完整消息。
- **请求 Body**：无（Query：`conversation_id`(必填)、`last_seq`(默认0)；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -N "http://127.0.0.1:8000/api/v1/chat/resume?conversation_id=2&last_seq=42" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例（SSE data 行）**

```
data: {"type":"delta","seq":43,"content":"..."}
data: {"type":"done","message_id":9,"conversation_id":2,"run_id":3}
```

# 交易策略 API（Strategies）

## 1. AI 生成策略

- **接口名称**：AI 生成策略（结构化输出）
- **请求 Method**：POST
- **请求 Path**：/api/v1/strategies/generate
- **接口作用**：LangChain with_structured_output 按用户描述生成策略代码+JSON参数（schema 校验 + ast.parse 语法检查）。
- **请求 Body**：有（Body-JSON：description、symbol?=代码或symbol_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/strategies/generate" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"description":"金叉买入死叉卖出的双均线策略"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"strategy_name":"双均线策略","description":"...","code":"def initialize(context):...","params":{"entry":{"fast":5,"slow":20},"stop_loss":{},"take_profit":{},"position":{}},"risk_warning":"震荡市可能反复止损"}}
```

## 2. 策略列表

- **接口名称**：策略列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategies
- **接口作用**：当前用户交易策略列表（按创建倒序），M 区策略栏数据源。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategies" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"title":"双均线","description":"...","code":"...","params":{...},"status":"active","created_at":"...","updated_at":"..."}]}
```

## 3. 保存策略

- **接口名称**：保存策略
- **请求 Method**：POST
- **请求 Path**：/api/v1/strategies
- **接口作用**：保存交易策略（title/description/code/params/status），与 M 区联动、回测数据源。
- **请求 Body**：有（Body-JSON：title、description?、code?、params?、status?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/strategies" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"title":"双均线","code":"def on_bar(bar,context): pass"}'
```

**成功返回示例**

```json
{"code":0,"msg":"保存成功","data":{"id":1,"title":"双均线","status":"draft",...}}
```

## 4. 策略详情

- **接口名称**：策略详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategies/{strategy_id}
- **接口作用**：单条策略详情（N 区展示代码/参数）。
- **请求 Body**：无（Path：strategy_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategies/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"title":"双均线",...}}
```

## 5. 更新策略

- **接口名称**：更新策略
- **请求 Method**：PUT
- **请求 Path**：/api/v1/strategies/{strategy_id}
- **接口作用**：更新策略字段（title/description/code/params/status）。
- **请求 Body**：有（Body-JSON：title?、description?、code?、params?、status?；Path：strategy_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/strategies/1" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"status":"active"}'
```

**成功返回示例**

```json
{"code":0,"msg":"更新成功","data":{"id":1,"title":"双均线","status":"active",...}}
```

## 6. 删除策略

- **接口名称**：删除策略
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/strategies/{strategy_id}
- **接口作用**：删除策略（仅本人）。
- **请求 Body**：无（Path：strategy_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/strategies/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 策略模板 API（Strategy-Templates）

## 1. 模板列表

- **接口名称**：策略模板列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategy-templates
- **接口作用**：内置策略模板列表（id/name/description/params_schema，不含完整 code，按需获取），「基于模板创建」数据源。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategy-templates" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"name":"双均线交叉","description":"短期均线上穿长期均线买入，下穿卖出...","params_schema":{"entry":{"fast":5,"slow":20}}}]}
```

## 2. 模板详情

- **接口名称**：策略模板详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategy-templates/{template_id}
- **接口作用**：单个模板详情（含完整 code），前端加载到编辑器供用户修改保存。
- **请求 Body**：无（Path：template_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategy-templates/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"name":"双均线交叉","description":"...","params_schema":{...},"code":"def initialize(context):\n    ...\n\ndef on_bar(bar, context):\n    ..."}}
```

# 用户定制 Agent API（Agents）

## 1. 创建定制 Agent

- **接口名称**：创建定制 Agent
- **请求 Method**：POST
- **请求 Path**：/api/v1/agents
- **接口作用**：创建用户定制 Agent（system_prompt/tools/llm_config/memory_config JSONB），支持从预设模板（technical/fundamental/risk_control）创建。
- **请求 Body**：有（Body-JSON：name、agent_type?、system_prompt?、tools?、llm_config?、memory_config?、status?、template?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/agents" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"name":"我的风控","template":"risk_control"}'
```

**成功返回示例**

```json
{"code":0,"msg":"创建成功","data":{"id":1,"name":"我的风控","agent_type":"custom","system_prompt":"你是风控专员...","tools":{...},"llm_config":{"temperature":0.2},"memory_config":{...},"status":"draft","created_at":"...","updated_at":"..."}}
```

## 2. Agent 列表

- **接口名称**：Agent 列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/agents
- **接口作用**：当前用户定制 Agent 列表。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agents" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"name":"我的风控",...}]}
```

## 3. Agent 详情

- **接口名称**：Agent 详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/agents/{agent_id}
- **接口作用**：单条定制 Agent 配置详情。
- **请求 Body**：无（Path：agent_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agents/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"name":"我的风控",...}}
```

## 4. 更新 Agent

- **接口名称**：更新 Agent（启停）
- **请求 Method**：PATCH
- **请求 Path**：/api/v1/agents/{agent_id}
- **接口作用**：更新 Agent 配置或启停（status=active|draft）。
- **请求 Body**：有（Body-JSON：name?、agent_type?、system_prompt?、tools?、llm_config?、memory_config?、status?；Path：agent_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/agents/1" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"status":"active"}'
```

**成功返回示例**

```json
{"code":0,"msg":"更新成功","data":{"id":1,"name":"我的风控","status":"active",...}}
```

## 5. 删除 Agent

- **接口名称**：删除 Agent
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/agents/{agent_id}
- **接口作用**：删除定制 Agent（仅本人）。
- **请求 Body**：无（Path：agent_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/agents/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 回测 API（Backtest）

## 1. 发起回测

- **接口名称**：发起回测（异步）
- **请求 Method**：POST
- **请求 Path**：/api/v1/backtest
- **接口作用**：创建回测任务（queued）→ Celery backtest 队列异步执行，返回任务 ID 供前端轮询；回测结束结果写 backtest_results。
- **请求 Body**：有（Body-JSON：strategy_id、symbol=标的代码或symbol_id、period?=15m|1d|1w|1mon、start?、end?、fill_on?=close|open；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/backtest" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"strategy_id":1,"symbol":"600519","period":"1d"}'
```

**成功返回示例**

```json
{"code":0,"msg":"回测已提交","data":{"id":17,"strategy_id":1,"symbol_id":125,"period":"1d","status":"queued","progress":0,"error":null,"created_at":"...","updated_at":"..."}}
```

## 2. 任务状态轮询

- **接口名称**：回测任务状态
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/tasks/{task_id}
- **接口作用**：查询回测任务状态（queued/running/success/failed）与进度（0-100），前端轮询。
- **请求 Body**：无（Path：task_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/tasks/17" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":17,"strategy_id":1,"symbol_id":125,"period":"1d","status":"success","progress":100,"error":null,"created_at":"...","updated_at":"..."}}
```

## 3. 回测任务列表

- **接口名称**：回测任务列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/tasks
- **接口作用**：当前用户回测任务列表（可按 strategy_id 过滤，N 区历史任务）。
- **请求 Body**：无（Query：strategy_id?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/tasks?strategy_id=1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":17,"strategy_id":1,"symbol_id":125,"status":"success","progress":100},...]}
```

## 4. 结果查询（按策略）

- **接口名称**：回测结果列表（按策略）
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/results
- **接口作用**：按策略查询回测结果列表（N 区与全景K线策略指标数据源：胜率/盈亏比/夏普/年化/最大回撤等）。
- **请求 Body**：无（Query：strategy_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/results?strategy_id=1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":5,"task_id":17,"strategy_id":1,"symbol_id":125,"win_rate":0.25,"profit_loss_ratio":1.8273,"sharpe":-0.8449,"total_buys":8,"total_sells":8,"annual_return":-0.1472,"max_drawdown":0.1124,"metrics_json":{"total_return":-0.0493,"total_trades":8,"commission_total":7750.04,...},"start_ts":"...","end_ts":"..."}]}
```

## 5. 结果详情

- **接口名称**：回测结果详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/results/{result_id}
- **接口作用**：单条回测结果详情（含 metrics_json 扩展指标与交易统计）。
- **请求 Body**：无（Path：result_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/results/5" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":5,"task_id":17,"strategy_id":1,"win_rate":0.25,"metrics_json":{...}}}
```

# Agent 运行记录与记忆文件 API（Agent-Ops）

## 1. Agent 运行历史

- **接口名称**：Agent 运行历史
- **请求 Method**：GET
- **请求 Path**：/api/v1/agent/runs
- **接口作用**：当前用户 Agent 运行记录列表（按时间倒序，支持按会话筛选 + 分页，前端 AgentRunsDialog 数据源）。
- **请求 Body**：无（Query：conversation_id?、page?=1、size?=20；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agent/runs?conversation_id=2&page=1&size=20" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":3,"agent_id":null,"conversation_id":2,"symbol_id":125,"run_type":"diagnostic","status":"success","input":"分析贵州茅台趋势","output":"结论：持有","final_decision":"结论：持有","total_duration":3500,"tokens":null,"error":null,"created_at":"...","updated_at":"..."}],"total":1,"page":1,"size":20}}
```

## 2. Agent 运行节点步骤

- **接口名称**：Agent 运行节点步骤
- **请求 Method**：GET
- **请求 Path**：/api/v1/agent/runs/{run_id}/steps
- **接口作用**：某次运行的完整多智能体节点步骤（node/status/summary/content/duration_ms，按节点执行顺序）。
- **请求 Body**：无（Path：run_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agent/runs/3/steps" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"run_id":3,"step_name":"technical_analyst","node":"technical_analyst","agent_role":"analyst","status":"done","content":"趋势向上...","summary":"趋势向上，支撑1200","duration_ms":2100,"meta":null,"created_at":"..."}]}
```

## 3. Agent 运行详情

- **接口名称**：Agent 运行详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/agent/runs/{run_id}
- **接口作用**：单条运行记录详情（内嵌 agent_steps 多智能体步骤输出，可观测/复盘）。
- **请求 Body**：无（Path：run_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agent/runs/3" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":3,"run_type":"diagnostic","status":"success","output":"结论：持有","final_decision":"结论：持有","total_duration":3500,"steps":[{"id":1,"run_id":3,"step_name":"technical_analyst","node":"technical_analyst","agent_role":"analyst","status":"done","content":"技术面看多","summary":"技术面看多","duration_ms":2100,"meta":null,"created_at":"..."}],"created_at":"..."}}
```

## 4. 本地记忆文件

- **接口名称**：本地记忆文件列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/memory/files
- **接口作用**：当前用户本地记忆文件列表（M 区「记忆文件」数据源；记忆本体存本地路径，接口返回索引元数据）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/memory/files" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"path":"D:/stock-invest-system/stock_backend/data/memory/1/rule.md","content_type":"rule","updated_at":"2026-08-11T05:00:00Z"}]}
```

## 5. 记忆事实列表（V0.2 阶段六 6.4）

- **接口名称**：记忆事实列表（分页）
- **请求 Method**：GET
- **请求 Path**：/api/v1/memory/facts
- **接口作用**：分页返回当前用户记忆列表（内容、重要性、来源类型/对话ID、创建时间），支持按重要性下限筛选。M 区「记忆文件」数据源。
- **请求 Body**：无（Query：`page`(默认1)、`size`(默认20，≤100)、`importance_min`(可选 1-10)；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/memory/facts?page=1&size=20&importance_min=7" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":12,"content":"止损不超过2%","importance":8,"source_type":"rule","source_id":3,"created_at":"2026-08-11T05:00:00Z"}],"total":1,"page":1,"size":20}}
```

## 6. 删除单条记忆（V0.2 阶段六 6.4）

- **接口名称**：删除单条记忆
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/memory/facts/{fact_id}
- **接口作用**：删除单条记忆（同步删 ChromaDB 向量 + PG 记录），删除后 AI 不再召回。
- **请求 Body**：无（Path：fact_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/memory/facts/12" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"已删除","data":null}
```

## 7. 清空全部记忆（V0.2 阶段六 6.4）

- **接口名称**：清空全部记忆
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/memory/facts
- **接口作用**：清空当前用户全部记忆（重建 ChromaDB collection + 删 PG 记录 + 删本地记忆文件）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/memory/facts" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"已清空","data":{"deleted":5}}
```

# 管理员 API（Admin）

## 1. Provider 健康检查

- **接口名称**：行情 Provider 健康状态
- **请求 Method**：GET
- **请求 Path**：/api/v1/admin/providers/health
- **接口作用**：返回各行情 Provider（eastmoney/sina/ths）可用状态/熔断中/失败次数/最近成功时间（is_admin 鉴权）。
- **请求 Body**：无（Header：Authorization: Bearer <token>，需 is_admin）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/admin/providers/health" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"name":"eastmoney","state":"closed","failures":0,"last_success_at":"2026-08-20T10:00:00Z","cooldown_remaining":0},...]}
```

## 2. 全量目录同步（手动触发）

- **接口名称**：触发标的目录同步
- **请求 Method**：POST
- **请求 Path**：/api/v1/admin/catalog/sync
- **接口作用**：手动触发全量A股+ETF目录同步（akshare），异步执行，返回任务 ID（is_admin 鉴权）。
- **请求 Body**：无（Header：Authorization: Bearer <token>，需 is_admin）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/catalog/sync" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"目录同步已提交","data":{"task_id":"e2a1...","status":"queued"}}
```

# 实时行情 WebSocket API（WS）

## 1. 实时行情推送

- **接口名称**：实时行情 WebSocket
- **请求 Method**：WS
- **请求 Path**：/api/v1/ws/market
- **接口作用**：实时快照/K线增量推送。query 传 token 鉴权；订阅消息 `{"action":"subscribe","symbol_ids":[1,2]}`；服务端每 15s 发 `{"type":"ping"}`，30s 无 pong 断开；断线补拉 `{"action":"sync","since":"ISO时间"}`。
- **请求 Body**：无（Query：token=JWT）

**请求示例（JS 伪代码）**

```js
const ws = new WebSocket(`ws://127.0.0.1:8000/api/v1/ws/market?token=${token}`);
ws.onopen = () => ws.send(JSON.stringify({action:"subscribe", symbol_ids:[125,70]}));
ws.onmessage = e => console.log(e.data); // {"type":"ping"} / {"type":"snapshot","data":{...}} / {"type":"kline",...}
```

**成功返回示例（推送消息）**

```json
{"type":"snapshot","data":{"125":{"price":1309.22,"change":4.57,"change_pct":0.35,"updated_at":"2026-08-20T10:00:00Z"}}}
```

# V0.2 现有端点增强说明

- `GET /api/v1/symbols/search`：新增 Query `type`（stock/etf/index 过滤）与 `limit`；返回字段新增 `is_catalog`（TRUE=仅目录未同步K线）、`has_kline`（是否已有K线），前端据此标注"已同步/未同步"。
- `GET /api/v1/snapshot`：返回字段新增 `data_age_seconds`（快照数据龄，当前时间-updated_at），前端据此标注"数据时间"而非"--"；请求带有效登录 token 且 symbol 集合 ⊆ 该用户关注列表时，结果按 `watchlist_snap:{user_id}` 缓存（交易时段 10s / 非交易 300s）。
- `GET /api/v1/watchlist`：返回字段新增 `sync_status`（pending/syncing/done/failed）与 `last_synced_at`，前端展示"同步中/已同步/失败"。
- `GET /api/v1/kline`：默认区间（未传 start/end）走 Redis "最近N根"缓存，连续请求毫秒级返回；显式区间仍直查 PG。
