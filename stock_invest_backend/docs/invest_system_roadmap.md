# MA 策略回测（功能1）分步实施建议

## 
1. **回测与实时建议共用同一套“策略定义”**（参数、信号规则统一），避免 Java/C++ 两套逻辑漂移。
2. **历史数据写 MySQL 时增加幂等约束**（`symbol + trade_date` 唯一），避免重复采集导致回测偏差。

## 分阶段任务（先实现功能1）

### Task 1
- 设计并落地 MySQL 表结构（`stock_daily_kline`、`strategy_backtest_result`）。
- 新增 Java 回测 API：`POST /api/backtest/ma`。
- 打通 Java -> C++ 回测调用链（先用 mock 结果）。

### Task 2（已完成）
- Java 增加“补齐近 3 个月日K”的采集任务（按 symbol 批量写入 MySQL）。
- 增加去重写入逻辑：`INSERT ... ON DUPLICATE KEY UPDATE`。

### Task 3（下一步）
- C++ 回测引擎接入 MySQL（Connector/C API），按请求参数读取区间数据。
- 实现 MA(5) 策略：上穿买入，下穿卖出；输出总信号数、胜率。

### Task 4（下一步）
- Java 持久化 C++ 回测结果到 `strategy_backtest_result`。
- 增加按 symbol/strategy 的查询接口，供前端展示。


## LOF 实时溢价率模块实施路线（可用版 -> 扩展版）

你的思路是当前阶段的最佳方案：
1. 先做 Java 独立模块，不引入 C++，可以最短路径上线可用能力。
2. 复用已验证的 `market` 东方财富行情源，降低接入风险。
3. Redis 做 3~10 秒短 TTL 缓存，能显著降低第三方请求压力。
4. “实时 iopv 优先，缺失则退化昨收单位净值并标记非实时”符合业务可解释性。

补充优化建议（纳入步骤中）：
1. 模块落在 `src/main/java/.../lof`（Java 包）更符合当前工程结构。
2. 同步输出 `navType` 与 `status`，前端可直接区分“实时/非实时/不可计算”。

### 本期目标（只做可用版）
- 只支持 2 只 LOF（先写死默认列表，可后续配置化）。
- 只实现：数据源接入 + Redis 缓存 + 查询接口。
- 提供接口：`GET /api/market/lof/premium`。

### Step 1：模块骨架与配置
- 新建软件包：`stock_invest_backend/src/main/java/com/example/stock_invest_backend/lof/`
- 子包建议：`config`、`controller`、`service`、`dto`、`provider`、`cache`
- 新增配置：
  - `lof.premium.default-symbols`（先放 2 只，如 `sz161129,sz161130`）
  - `lof.premium.cache-ttl-seconds`（默认 5，范围 3~10）
  - `lof.premium.retry.max-attempts`（默认 3）
  - `lof.premium.retry.base-delay-ms`（默认 200）
  - `lof.premium.rate-limit.permits-per-second`（默认 5）

### Step 2：DTO 与返回协议（先定标准）
- 设计 `LofPremiumItem` 返回字段：
  - `symbol`
  - `name`
  - `lastPrice`
  - `nav`
  - `navType`：`IOPV_REALTIME` / `PREV_DAY_NAV`
  - `premiumRate`（百分比或小数统一约定）
  - `status`：`OK` / `NO_NAV` / `NO_PRICE` / `UPSTREAM_ERROR`
  - `quoteTime`
  - `navDate`
  - `cacheHit`
  - `message`
- 设计 `LofPremiumResponse`：`items` + `requestId` + `generatedAt`

### Step 3：数据源适配（复用 market 东方财富）
- 在 `lof/provider` 中封装读取逻辑：
  - 实时价：复用 `market` 模块已有东方财富行情能力。
  - 净值优先级：
    1) 有 `iopv/估算净值` -> `navType=IOPV_REALTIME`
    2) 无 iopv -> 取“上一交易日单位净值” -> `navType=PREV_DAY_NAV`
- 若 `nav<=0` 或缺失：不计算溢价率，返回 `status=NO_NAV`。

### Step 4：Redis 缓存（短 TTL）
- Key 设计：`lof:premium:{symbol}`
- Value：序列化后的 `LofPremiumItem`
- TTL：默认 5 秒（限制在 3~10 秒）
- 读流程：
  1) 先查 Redis，有则返回并标 `cacheHit=true`
  2) 未命中才请求上游，计算后写缓存并返回

### Step 5：批量、限流、重试（指数退避）
- 批量：按 symbols 一次请求或分批聚合（避免单 symbol 多次调用）。
- 限流：对上游调用统一限速（每秒 permit 可配置）。
- 重试：仅对可重试错误（超时/5xx/网络抖动）重试。
- 重试策略：指数退避（如 200ms、400ms、800ms），设置最大次数与总超时。

### Step 6：接口实现
- 新增接口：`GET /api/market/lof/premium`
- Query 参数：
  - `symbols`（可选，不传则用默认 2 只）
- 返回：`LofPremiumResponse`
- 行为要求：
  - 单个 symbol 失败不拖垮整体，逐项给 `status/message`
  - 对 NO_NAV 项保留价格等上下文字段，便于前端展示

### Step 7：可观测性与保护
- 日志：记录上游耗时、重试次数、缓存命中率。
- 指标：请求成功率、NO_NAV 比例、平均响应时间。
- 熔断/降级（可选）：上游连续失败时优先返回短期缓存。

### Step 8：验收清单（本期）
- 能返回 2 只 LOF 溢价率。
- iopv 有值时标记 `IOPV_REALTIME`；无值时退化 `PREV_DAY_NAV`。
- `nav<=0` 返回 `NO_NAV`。
- 已接入 Redis 3~10 秒缓存。
- 已实现批量 + 限流 + 指数退避重试。
- `GET /api/market/lof/premium` 可稳定响应。

## 长期目标实施步骤（可直接编码）

### L1：全量 LOF 覆盖（symbol 清单由配置中心/数据库维护）

#### Step L1-1：引入 symbol 元数据存储
- 新建表：`lof_symbol_registry`
- 字段建议：
  - `symbol`（唯一）
  - `name`
  - `market`（`SH`/`SZ`）
  - `enabled`（是否参与实时计算）
  - `priority`（优先级）
  - `tags`（主题标签）
  - `updated_at`
- 新建仓储：`lof/repository/LofSymbolRegistryRepository`

#### Step L1-2：配置中心兜底
- 增加配置项：`lof.premium.symbol-source=db|config`（默认 `db`）
- 当 `db` 不可用时，自动降级读取 `application.properties` 中 `lof.premium.default-symbols`

#### Step L1-3：symbol 刷新与缓存
- 增加本地 symbol 缓存（如 1~5 分钟刷新一次）
- 提供管理接口（可选）：
  - `POST /api/market/lof/symbols/reload`

#### Step L1-4：分批拉取
- 对全量 symbols 做分片（例如每批 50~200）
- 批次间应用限流，防止上游压力过大

---

### L2：溢价率排行接口（升序/降序）

#### Step L2-1：新增查询 DTO
- `LofPremiumRankRequest`：
  - `order`（`asc|desc`）
  - `limit`
  - `onlyStatusOk`
  - `tradingOnly`
- `LofPremiumRankResponse`：
  - `items`
  - `total`
  - `generatedAt`

#### Step L2-2：新增接口
- `GET /api/market/lof/premium/rank`
- Query 参数：
  - `order=desc`（默认）
  - `limit=20`（默认）
  - `onlyStatusOk=true|false`
  - `tradingOnly=true|false`

#### Step L2-3：排序规则
- 主排序：`premiumRate`
- 次排序：`quoteTime`（新优先）
- 空值策略：`premiumRate=null` 统一排最后

---

### L3：筛选能力（仅交易时段、仅 status=OK）

#### Step L3-1：交易时段判定器
- 新建 `LofTradingSessionService`
- 判定维度：
  - 工作日
  - A 股交易时段（09:30-11:30, 13:00-15:00）
- 节假日先做简版（仅周末过滤），后续接交易日历表

#### Step L3-2：筛选器实现
- 在 service 层统一过滤：
  - `onlyStatusOk=true` -> 仅保留 `status=OK`
  - `tradingOnly=true` -> 非交易时段返回空列表或保留并标记（建议返回空列表+message）

#### Step L3-3：响应可解释性
- 在响应增加：
  - `filtersApplied`
  - `tradingWindow`（`OPEN|CLOSED`）
  - `message`

---

### L4：为“按溢价率触发策略”预留标准化事件结构（后续接 C++）

#### Step L4-1：定义标准事件 DTO
- `LofPremiumEvent` 字段建议：
  - `eventId`
  - `eventType`（`LOF_PREMIUM_SNAPSHOT`/`LOF_PREMIUM_ALERT`）
  - `symbol`
  - `premiumRate`
  - `status`
  - `navType`
  - `quoteTime`
  - `producedAt`
  - `source`
  - `version`

#### Step L4-2：事件发布接口与通道抽象
- 新建发布器接口：`LofPremiumEventPublisher`
- 默认实现先写日志（`log publisher`）
- 预留 Redis Stream/Kafka 实现（后续切换）

#### Step L4-3：告警触发规则框架
- 新增规则配置：
  - `threshold.up`
  - `threshold.down`
  - `cooldownSeconds`
- 当溢价率越界时发布 `LOF_PREMIUM_ALERT` 事件

#### Step L4-4：与 C++ 解耦集成方式
- Java 先发布标准化事件，不直接耦合 C++
- 后续新增桥接服务：订阅事件 -> 转标准 JSON -> 推送 C++ 分析服务

---

### 长期里程碑建议（按冲刺）
1. Sprint A（1~2 周）：完成 L1（DB 管理 symbols + 全量拉取稳定）
2. Sprint B（1 周）：完成 L2（排行接口 + 参数校验 + 文档）
3. Sprint C（1 周）：完成 L3（交易时段与筛选）
4. Sprint D（1~2 周）：完成 L4（事件结构 + 发布框架 + 基础告警）

### 验收清单（长期阶段）
- 全量 symbols 可动态维护，不依赖代码改动
- 排行接口支持升序/降序，性能稳定
- 筛选逻辑可配置且可解释
- 事件结构稳定版本化，可无缝接入 C++ 后续策略链路

---

## AI 投资分析能力实施拆分

目标：
- 新增唯一对外接口：`POST /api/ai/invest/analyze`
- 输入为用户自然语言 `prompt`
- 若识别到股票代码，则走 “LLM -> 标准 Tool Call -> Java 聚合真实接口 JSON -> LLM 生成分析” 链路
- 若未识别到股票代码，则终止工具调用链路，仅生成宏观行情分析文本
- 不新增数据库，直接复用现有库与 `stock_invest_backend/docs/sql` 下既有 SQL 体系
- 当前阶段不引入 Redis

### Task AI-1：接口契约与 Tool Call 编排层
- 新增接口：`POST /api/ai/invest/analyze`
- 请求体仅接收自然语言字段：`prompt`
- 在 Controller/Service 层先做股票代码识别：
  - 识别到 `sh600519`、`sz000001` 这类代码时，进入工具调用链路
  - 未识别到代码时，直接进入“宏观分析模式”，不再调用行情接口与 MA 接口
- 定义统一的 Tool Call 标准结构，至少覆盖：
  - `get_market_history(symbol, days=30)`
  - `get_ma5_cross_signals(symbol, period=5)`
- 约束首轮 prompt 默认使用最近 `30` 天 K 线数据
- 定义统一返回模型，至少包含：
  - `requestId`
  - `mode`：`TOOL_CHAIN` / `MACRO_ONLY`
  - `analysisText`
  - `disclaimer`
  - `replyTime`
  - `degraded`
  - `fallbackReason`
  - `rawData`
- 验收点：
  - 无股票代码时不触发工具调用
  - 有股票代码时能产出标准 Tool Call JSON，但不依赖具体厂商 LLM SDK

### Task AI-2：AiGatewayClient 适配器与真实数据聚合层
- 新增 `AiGatewayClient` 适配器，统一封装：
  - LLM 请求构造
  - Tool Call 解析
  - 最终分析文本生成
  - Token/耗时/错误码归一化
- 通过配置切换模型与厂商，不改业务代码
- Java 后端根据 Tool Call 映射调用现有接口，并统一整理真实 JSON：
  - 行情相关：复用 `market-api.md` 第 `73-101` 行定义的自定义天数行情链路能力，默认组织最近 `30` 天 K 线 prompt 数据
  - 策略相关：复用 `market-api.md` 第 `276-322` 行定义的 MA5 上穿/下穿接口能力
- 聚合层负责把原始接口响应收敛成 AI 二次提示所需的结构化摘要，避免将无关字段直接灌给模型
- 复用已有数据库与 SQL 文档，不新建数据库
- 验收点：
  - 业务层只依赖 `AiGatewayClient`，不出现厂商 SDK 直连
  - 两个下游接口响应可被统一整理为标准 JSON 上下文

### Task AI-3：性能降级、风控文案与全链路日志
- 为单次 AI 请求增加统一超时控制，整体耗时上限控制在 `8~12` 秒
- 为模型调用增加 Token 上限；若超限、超时或解析失败，则直接降级返回原生接口数据
- 所有 AI 返回固定附带：
  - 免责声明：`本分析仅供参考，不构成任何投资建议。`
  - `replyTime`
- 建立全链路日志，至少覆盖：
  - `requestId`
  - 原始 `prompt`
  - 股票代码识别结果
  - Tool Call 内容
  - 下游接口调用结果与耗时
  - LLM 请求耗时与 Token 消耗
  - 降级标记与降级原因
  - 最终响应模式
- 日志与异常信息需可支持后续问题追踪，但避免在日志中泄露敏感配置
- 验收点：
  - AI 异常时接口仍可用，能稳定返回原生数据或宏观分析文本
  - 每条返回都带固定免责声明与回复时间
  - 可通过日志还原一次完整调用链路

---

## 支付模块实施拆分（支付宝沙箱）

目标：
- 仅支持两档固定金额：10 元 / 20 元人民币
- 完整支付链路：下单 → 跳转支付宝 → 异步回调 → 订单状态更新
- 历史订单状态查询接口（支持分页）
- 使用支付宝沙箱环境（`alipay.trade.page.pay` 电脑网站支付）
- 与项目其他模块完全解耦，代码统一放在 `pay/` 包下
- 复用现有 MySQL 数据源，新建 `t_pay_order` 表

### Task PAY-1：建表与订单实体层
- 新建 SQL：`docs/sql/003_create_pay_order.sql`
- 表名 `t_pay_order`，核心字段：pay_order_id、amount、subject、state、channel_order_no、notify_url、success_time、expired_time、created_at
- 订单状态定义：INIT(0)、ING(1)、SUCCESS(2)、FAIL(3)、CLOSED(6)
- 新建 `pay/entity/PayOrder.java`
- 新建 `pay/repository/PayOrderRepository.java`（MybatisPlus，insert + updateState + queryById + queryList）
- 状态更新采用 CAS 模式（`WHERE state=旧状态`）保证幂等
- 验收点：Repository 层编译通过，可独立对 DB 读写

### Task PAY-2：支付宝 SDK 集成与配置
- `pom.xml` 新增依赖 `com.alipay.sdk:alipay-sdk-java`
- 新建 `pay/config/AlipayProperties.java`（appId、privateKey、alipayPublicKey、gateway、notifyUrl）
- 新建 `pay/service/AlipayClientService.java`
  - 初始化 `AlipayClient` Bean（沙箱 gateway）
  - 封装 `createPagePay(payOrderId, amount, subject)` → 返回支付表单 HTML
  - 封装 `verifyNotifySign(params)` → 验证回调签名
- `application.properties` 新增沙箱配置项占位
- 验收点：AlipayClient 可正确构建，createPagePay 可生成表单字符串

### Task PAY-3：下单接口与支付跳转
- 新建 `pay/controller/PayOrderController.java`
- 新增接口：`POST /api/pay/create`
  - 请求体：`{ "amount": 1000 }`（仅允许 1000 或 2000）
  - 生成 payOrderId，入库 state=INIT
  - 调用 AlipayClientService.createPagePay
  - 返回 payOrderId + payForm（HTML 表单，前端直接渲染跳转）
- 新建 `pay/dto/CreatePayOrderRequest.java`、`CreatePayOrderResponse.java`
- 新建 `pay/service/PayOrderService.java`（createOrder + 金额校验）
- 验收点：调用接口返回可用的支付宝跳转表单，沙箱环境可唤起收银台

### Task PAY-4：异步回调与订单状态更新
- 新增接口：`POST /api/pay/notify`（支付宝异步回调入口）
  - 验签（AlipayClientService.verifyNotifySign）
  - 提取 out_trade_no（= payOrderId）+ trade_status
  - trade_status=TRADE_SUCCESS → CAS 更新 state: INIT/ING → SUCCESS
  - 记录 channel_order_no（trade_no）、success_time
  - 返回纯文本 `"success"` 给支付宝
- 回调幂等：state 已为 SUCCESS 时直接返回 success 不重复处理
- 验收点：沙箱付款后回调正确到达，DB 中订单 state 变为 2

### Task PAY-5：订单查询与历史列表
- 新增接口：`GET /api/pay/query?payOrderId=xxx`
  - 返回单条订单详情（payOrderId、amount、state、创建时间、支付时间）
- 新增接口：`GET /api/pay/orders?page=1&size=20`
  - 返回分页历史订单列表，按创建时间降序
  - 响应包含 items、total、page、size
- 新建 `pay/dto/PayOrderStatusResponse.java`、`PayOrderListResponse.java`
- 验收点：可查询到已支付/未支付/已关闭的订单记录

### Task PAY-6：过期关单与健壮性
- 新建 `pay/task/PayOrderExpiredTask.java`
  - 定时扫描 state=INIT 且 expired_time < now 的订单，批量更新为 CLOSED(6)
  - cron：每 5 分钟执行一次
- 全链路日志：下单、回调、状态变更关键节点 INFO 日志
- 异常防护：回调验签失败返回 `"failure"`、金额不匹配返回 `"failure"`
- 验收点：过期订单可自动关闭，异常回调不影响正常订单
