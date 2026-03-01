# MA 策略回测（功能1）分步实施建议

## 你的思路是否最佳？
总体思路是正确的，但建议做两点优化：

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
