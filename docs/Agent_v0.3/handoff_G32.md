# 交接提示词 — 泳道 D / G32（P1-11 回测结果可视化）

> 用途：G06、G20 已由前序 agent 完成并提交，本文件是交给**下一个 agent** 执行 G32 的完整自包含提示词。
> 直接复制下方「提示词正文」全部内容作为新 agent 的输入即可。

---

# 提示词正文（从此行以下复制）

【角色】
你是该项目（`D:\stock-invest-system`）的全栈开发工程师（测试先行、后端改造、前端可视化），用中文回答。
本提示词对应 V0.3 泳道 D「回测引擎」的**第 3 步 G32（P1-11 回测结果可视化）**。
前置步骤 G06、G20 已由前序 agent 完成并推送，你**只需做 G32**，不要重做或修改 G06/G20 的成果（除非发现明确 bug，此时先停下报告）。

────────────────────────────────

## 【最高优先级约束 · 不可违反】

1. 每步开工前用 Glob/Grep/Read 读全「前置阅读」列出的文件，**先输出已读清单 + 理解 + 风险点**，再动手。
2. 以下情况**必须停止报告**，不得自行绕过：
   - 规划与代码冲突
   - 后端实际数据结构与本文档描述不一致
   - 与其它泳道文件冲突无法协调
   - 需要改动本文档未授权的内容
3. **本步已获人工批准：允许新增 Alembic 迁移给 `backtest_results` 表加列**（详见「三、后端改造」）。这是**唯一**被批准的表结构变更，禁止额外加列/改列/删列。
4. 其余表结构一律不得修改；如发现必须变更，只能列为「建议调整项」并说明迁移与回滚方案。
5. 保持向后兼容：现有回测 API 请求/响应格式不破坏（新增字段可加，已有字段语义不变）。
6. 每步完成必须：跑测试 + 手动验证 + 更新文档，才能收尾。
7. **前端不得直接计算复杂指标**（后端算，前端只渲染）——项目硬约束。
8. 完成本步后，把代码提交到 GitHub（`git push`）。

────────────────────────────────

## 【项目上手 · 必读全文】

1. `CLAUDE.md`（项目根）— 技术栈与架构约束。
2. `docs/Agent_v0.3/project_constraints_v0.3.md` — 依赖图、泳道表、**第八节「需人类操作配置事项」**（含 pgvector 阻塞项，见下方「五、开工前必须确认的环境问题」）。
3. `docs/Agent_v0.3/Reference_guide_v0.3.md` — **只读 P1-11 条目 + 第 4 章**（其余不读）。
4. `docs/Agent_main_v0.1/memory.md` — 项目进度、开发环境、启动命令。

## 【项目上手 · 选读（按锚点精读）】

5. `docs/Agent_backend/api-docs.md` — **只读「回测 API（Backtest）」一节**，了解现有 5 个端点格式。
6. `docs/Agent_backend/fixed.md` — **只读文末两条**（`2026-09-17 G06 回测引擎修复前口径基线` 与 `2026-09-17 G20 回测引擎修复`），这是 G20 的口径变更说明与修复前后对比。
7. `docs/Agent_backend/Agent_code.md` — 文末两条 G20 编码记录。
8. `stock_backend/app/backtest/engine.py`、`metrics.py` — 回测引擎与指标实现（G20 修复后版本）。
9. `stock_backend/tests/test_backtest_correctness.py` — G06/G20 回归测试，理解当前口径。

────────────────────────────────

## 一、前置步骤已完成内容（G06 / G20，勿重做）

### G06（commit `6640f6a`）— 回测正确性回归测试
新增 `stock_backend/tests/test_backtest_correctness.py`，23 项确定性断言，覆盖：净盈亏配对 / 完整交易回合 / 期末未平仓浮动结算 / 平手 draw / 涨停禁买 / 跌停禁卖 / 同 bar 止损后禁止再入 / 微利毛赚净亏 / 滑点 / 成交量上限。

### G20（commit `5ae7ada`）— 回测引擎正确性修复

**改动文件**：
- `stock_backend/app/backtest/engine.py`
- `stock_backend/app/backtest/metrics.py`
- `stock_backend/app/services/backtest_service.py`
- `stock_backend/tests/test_backtest_engine.py`、`tests/test_backtest_correctness.py`

**修复后口径（G32 展示必须以此为准）**：

| 项 | 修复后口径 |
|---|---|
| 胜率 `win_rate` | 按**净盈亏**（扣买卖费用）判定；分母 = 回合数 − draws；无已实现回合时为 `null` |
| `total_trades` | **完整交易回合数**（一次买→卖为一笔；FIFO 仅用于成本分摊） |
| 平手 | 毛盈亏为 0 记入 `metrics_json.draws`，**不计入**胜率分母、不并入亏损 |
| 期末持仓 | 按最后一根 bar 收盘价浮动结算，`metrics_json.unrealized_pnl` / `unrealized_count` 单列 |
| best/worst_trade | 改用**净盈亏** |
| 成本法 | **FIFO 首批成本**（止损止盈触发价与配对口径统一） |
| 涨跌停 | 一字板（`open==high==low==close`）涨停禁买、跌停禁卖；bar 带 `limit_up`/`limit_down` 显式字段则优先 |
| 成交量 | 新增 `max_volume_pct`（默认 1.0 不限制），单笔 ≤ `bar.volume × pct` |
| 同 bar | 自动止损/止盈平仓后，当根 bar 禁止再开同向仓 |

**引擎 `BacktestEngine.run()` 返回的 output dict 结构**（G32 数据源）：

```python
{
  "params": {...},
  "trades": [
     {"ts": datetime, "side": "buy"|"sell", "price": float, "shares": int,
      "amount": float, "fee": float,
      "reason": "signal"|"stop_loss"|"take_profit"}   # reason 用于区分止损/止盈样式
  ],
  "equity_curve": [
     {"ts": datetime, "equity": float, "cash": float, "pos": int, "price": float}
  ],
  "bars_used": int,
  "fill_on": "close"|"open",
  "initial_cash": float,
  "final_equity": float,
  "start_ts": datetime, "end_ts": datetime,
  "open_position": {"shares": int, "fifo_cost": float, "last_close": float} | None,
}
```

**关键事实**：`equity_curve` 与 `trades` **目前没有落库**——`execute_backtest()` 算出 `out` 后只把 `metrics` 写进 `backtest_results.metrics_json`，`out["trades"]` / `out["equity_curve"]` 用完即弃。这正是 G32 要解决的第一个问题（见「三、后端改造」）。

────────────────────────────────

## 二、G32 任务说明（P1-11 回测结果可视化）

### 原始规划要求

> **说明**：后端回测已返回 equity_curve（资金曲线）与 trades（买卖流水），但前端 `StrategyMetricsPanel.vue` 仅展示 7 个汇总数字，**无资金曲线图、K 线上无买卖点标记**，已有 `Sparkline.vue` 未被回测面板复用，用户无法直观看懂策略执行过程。
>
> **优化方案**：
> - **资金曲线**：回测结果卡片/详情内用 lightweight-charts 面积图渲染 equity_curve（复用 KLineChart 图表能力），可叠加初始资金线/标的涨幅基准对比
> - **K 线买卖点标注**：在标的 K 线上按 trades 叠加买入/卖出标记（遵循本项目红涨绿跌配色），止损/止盈用不同样式区分，hover 显示成交价/数量/费用/触发原因
> - **交易明细列表**：trades 流水表（时间/方向/价格/数量/费用/累计持仓/已实现盈亏），与图表联动高亮
> - **状态联动**：指标数字与图表、明细同区展示；回测中显示进度，失败显示原因与重试（配合 P1-4 队列繁忙提示）
> - **依赖**：展示数值口径以 P0-10 修复后的净盈亏/胜率为准

### 本轮追加要求（人工指定，优先级高于原始规划）

1. **不局限于复用 `KLineChart` 组件本身**——允许按需改造或新建图表组件。
2. **买卖点展示位置改为「跳转到对应股票的行情详细页」**：即用户从回测结果处点击，跳转到 `/market/detail?symbol=<code>&strategy_id=<id>`，在该页的 K 线上叠加买卖点。
3. **本轮先完成最基础的 B/S 点**（买入/卖出标记），止损/止盈区分样式、hover 详情、明细表联动等作为后续增量（可一并做，但**B/S 点必须先跑通**）。

────────────────────────────────

## 三、后端改造（方案 B，已获批准）

### 3.1 数据库迁移（唯一被批准的表结构变更）

新增 `stock_backend/alembic/versions/0013_backtest_curve_trades.py`：

- 给 `backtest_results` 表新增两列：
  - `equity_curve` — `JSONB`，nullable
  - `trades` — `JSONB`，nullable
- `down_revision` 指向当前最新迁移（**先 `ls stock_backend/alembic/versions/` 确认最新编号，当前为 `0012_email_verified.py`**）
- `downgrade()` 逆序 `drop_column` 两列
- 参考同目录既有迁移的写法与命名风格（`revision` / `down_revision` / `op.add_column` / `op.drop_column`）
- **禁止手写 SQL 改表结构**

### 3.2 模型

`stock_backend/app/models/strategy.py` 的 `BacktestResult` 增加两列映射（参考同文件既有 `metrics_json: Mapped[dict | None] = mapped_column(JSON)` 写法；JSONB 用 `from sqlalchemy.dialects.postgresql import JSONB`）。

### 3.3 仓储层

`stock_backend/app/repositories/backtest_repo.py` 的 `create_result()` 增加两个可选入参（`equity_curve` / `trades`）并写入行对象。

### 3.4 服务层

`stock_backend/app/services/backtest_service.py` 的 `execute_backtest()` 中，把 `out["equity_curve"]` 与 `out["trades"]` 传给 `create_result()`。
注意：`trades` 里的 `ts` 是 `datetime`，`equity_curve` 同理——写 JSONB 前需转成可序列化形式（建议 `isoformat()`），**并在 schema 层保持一致**。

### 3.5 响应 schema

`stock_backend/app/schemas/backtest.py` 的 `BacktestResultOut` 增加 `equity_curve` / `trades` 字段。

**重要**：`equity_curve` + `trades` 单条结果约 60KB（2 年日K 约 500 点 + 上百笔交易）。**列表端点 `GET /api/v1/backtest/results` 必须裁剪掉这两个字段**，只在详情端点 `GET /api/v1/backtest/results/{id}` 返回。建议做法：新增一个 `BacktestResultBriefOut`（不含这两字段）用于列表，`BacktestResultOut` 用于详情——**先读 `stock_backend/app/api/v1/backtest.py` 确认两个端点当前共用的 schema，再决定如何拆分**。

### 3.6 API 文档

在 `docs/Agent_backend/api-docs.md` 的「回测 API（Backtest）」一节，按**已有格式**补充这两个新字段的说明（不改动文件最上方的文字说明）。如新增了端点或响应结构，一并补充。

────────────────────────────────

## 四、前端改造（G32 主体）

### 4.1 现状（前序 agent 已核查，供参考，仍需你自行确认）

- 路由 `stock_frontend/src/router/index.ts`：
  - `/market/detail` → `views/MarketDetailView.vue`，**无路径参数，用 query 传参**
- `MarketDetailView.vue` **已经支持**从 query 读取：
  - `route.query.symbol`（标的代码，用于双向标的联动）
  - `route.query.strategy_id`（策略 ID）
  - 并把 `symbol` 传给 `<KLineChart :symbol="market.current" />`
  - → **跳转链路基本已通，你的重点是「在该页 K 线上叠加 B/S 点」**
- 图表组件：`stock_frontend/src/components/trading/KLineChart.vue`（lightweight-charts v5）、`components/trading/Sparkline.vue`
- 现有回测展示：`stock_frontend/src/components/trading/StrategyMetricsPanel.vue`（仅 7 个汇总数字）
- 前端回测 API：`stock_frontend/src/api/ai.ts`（含 `fetchBacktestResults`、`BacktestResult` 类型）

### 4.2 要做的

1. **后端数据打通**：前端新增/扩展 API 方法，调用详情端点拿到 `equity_curve` 与 `trades`。
2. **B/S 点标注（本轮必须完成）**：
   - 在 `MarketDetailView` 的 K 线上，按 `trades` 叠加买入/卖出标记
   - 遵循本项目**红涨绿跌**配色（先 Grep 确认项目既有配色变量，如 `--up` / `--down`，不要硬编码颜色）
   - 使用 lightweight-charts 的 series markers 能力（v5 API，**先读 KLineChart.vue 现有用法确认版本与调用方式**）
3. **资金曲线**：用 lightweight-charts 面积图渲染 `equity_curve`，可叠加初始资金线 / 标的涨幅基准对比。放置位置由你决定（回测结果卡片/详情内），但需与指标数字同区展示。
4. **交易明细列表**：`trades` 流水表（时间/方向/价格/数量/费用/累计持仓/已实现盈亏），与图表联动高亮（可作为增量，但建议一并做）。
5. **状态联动**：回测中显示进度、失败显示原因与重试（复用现有 `GET /api/v1/backtest/tasks/{id}` 轮询）。
6. **数值口径**：一律以 G20 修复后的净盈亏 / 胜率为准（见「一」的表格），**前端不得自行重算指标**。
7. **跳转入口**：在回测结果处提供「在行情页查看买卖点」入口，跳转 `/market/detail?symbol=<code>&strategy_id=<id>`。

### 4.3 前端约束

- 组件变更须补 `docs/Agent_frontend/Agent_code.md`
- 前端回测结果组件与「AI 页内嵌回测结果」（V0.2 阶段八 8.6）**共用组件**——**先读现状，复用优先，不新建平行组件**
- 个人设置页 / 导航栏 / 路由：**D 泳道不涉及**（`router/index.ts` 被 G35 收口，**禁止改动路由文件**；跳转用现有 `/market/detail` + query 即可）
- 必须通过 `vue-tsc -b --noEmit` 或 `npm run build`

────────────────────────────────

## 五、开工前必须确认的环境问题（重要）

`docs/Agent_v0.3/project_constraints_v0.3.md` 第八节第 1 条已记录：

> **本地 PostgreSQL 缺少 pgvector 扩展，迁移 0009 无法执行。**
> 本地库 `alembic_version` 停在 **0008**，而仓库已有 0009(pgvector) / 0010(user_sessions) / 0011(email_logs) / 0012(email_verified) 四个未应用迁移。
> 导致 `test_memory.py`、`test_agent_ops.py` 部分用例失败（`memory_chunks.embedding` 列不存在）。

**对本步的影响**：你要新增 0013 迁移，`alembic upgrade head` 会**先尝试应用 0009 并在缺 pgvector 时报错**，导致你的迁移无法验证。

**处理建议（按优先级）**：
1. **首选**：先确认本地 PostgreSQL 是否已装 pgvector；若已装，直接 `alembic upgrade head`。
2. 若未装且你有权限安装，安装后 upgrade。
3. 若无法安装：**停止并向人类报告**，说明「0013 迁移无法在本地验证，需要先解决 pgvector 阻塞」；不要用 `alembic stamp` 跳过迁移来伪造通过。

**注意**：此问题**不是**你引入的，也**不要**试图修复 pgvector 或改动 0009~0012。

────────────────────────────────

## 【文档规则】

1. 新增 API / 响应字段：`docs/Agent_backend/api-docs.md` 按已有格式补充，**不改动最上方文字说明**。
2. 前端变更：补 `docs/Agent_frontend/Agent_code.md`（格式：`编码时间：` + `编码内容（描述）：`，单条 ≤200 字，超出则新开一条）。
3. 后端变更：补 `docs/Agent_backend/Agent_code.md`（同上格式）。
4. 发现 bug：按「日期 / 问题描述 / 解决方案」补 `docs/Agent_backend/fixed.md` 或 `docs/Agent_frontend/fixed.md`。
5. 数据库变更：Alembic 迁移放 `stock_backend/alembic/versions/`，**禁止手写 SQL 改表结构**。
6. 发现系统 bug 或需人类操作配置：标清序号 + 当前泳道，写到 `docs/Agent_v0.3/project_constraints_v0.3.md` **第八节**末尾（已有 1~5 条，你从第 6 条开始）。
7. 全部完成：`docs/Agent/memory.md` 总结，同步阶段进度。

────────────────────────────────

## 【开发节奏】

1. 每步执行：前置阅读 → 输出设计方案 → 编码 → 自我审查 → 测试 → 更新文档 → 输出本步报告。
2. 超过 5 个文件的修改**拆成子任务**并在设计方案中说明。
3. 回测修复/改造必须向后兼容：现有回测 API 请求/响应格式不破坏。

## 【设计方案模板】（编码前必须输出）

1. **新增/修改文件**：路径 / 改动类型 / 核心改动
2. **依赖关系**：本步依赖 / 影响现有模块 / 影响其它泳道
3. **数据设计要点**：equity_curve/trades 存储格式与序列化口径 / 列表与详情的字段裁剪策略
4. **可视化设计要点**：B/S 点渲染方式（lightweight-charts markers）/ 配色取值来源 / 跳转链路
5. **风险点**：迁移对存量结果行的影响（老数据两列为 NULL 时前端如何降级）/ 数据体积对列表接口的影响
6. **拆分说明**（超过 5 个文件时）

## 【冲突报告模板】（发现冲突时停止并输出）

- 冲突点：
- 现有代码实际情况（文件 + 行号）：
- 影响范围：
- 方案 A：做法 / 优点 / 缺点
- 方案 B：做法 / 优点 / 缺点
- 我的推荐：
- 等待确认事项：

────────────────────────────────

## 【测试要求】

**必测**：
- 后端：`create_result` 落库含 equity_curve/trades；详情端点返回两字段、列表端点**不含**两字段；存量 NULL 行不报错；迁移 up/down 可逆
- 前端：B/S 点渲染正确（买卖方向/数量/价格与 trades 一致）；资金曲线渲染；`vue-tsc -b --noEmit` 或 `npm run build` 通过
- 回归：`tests/test_backtest_correctness.py` + `test_backtest_engine.py` + `test_backtest_api.py` 三文件 **44 项必须保持全绿**（G06/G20 成果，不得破坏）

**断言**：每个测试函数必须有明确断言；新增测试放 `tests/` 对应模块，命名遵循现有模式（如 `test_backtest_visualization.py`）。
**禁止**：只用 mock 跳过核心逻辑；跳过失败测试；用 skip/xfail 掩盖失败（除非明确说明并获同意）。

**运行命令**（`stock_backend` 目录下）：
```bash
.venv/Scripts/python.exe -m pytest tests/test_backtest_correctness.py tests/test_backtest_engine.py tests/test_backtest_api.py -q
.venv/Scripts/python.exe -m ruff check app/ tests/
```
前端（`stock_frontend` 目录下）：`npm run build`（或 `npx vue-tsc -b --noEmit`）

────────────────────────────────

## 【自我审查清单 · 每步必查】

1. 是否读全前置文件并输出清单？
2. 是否输出设计方案？
3. 是否只改本步骤范围内文件？
4. 是否前后端同步改动？
5. 是否保持向后兼容（存量 NULL 行、老 API 调用方）？
6. 表结构变更是否用 Alembic 迁移（且**仅**加批准的两列）？
7. 是否新增/修改测试并有明确断言？
8. 是否跑通本模块 + 回测三文件 44 项 + 前端 build？
9. 是否更新 api-docs / Agent_code（前端+后端）/ fixed（如有）/ memory？
10. 是否处理或报告规划冲突？
11. 是否清理弃用代码和临时文件？

────────────────────────────────

## 【G32 验收标准】

- [ ] `backtest_results` 新增 `equity_curve` / `trades` 两列（Alembic 0013，up/down 可逆）
- [ ] 回测执行时两字段落库；**列表端点裁剪、详情端点返回**
- [ ] **B/S 点标注跑通**：跳转 `/market/detail?symbol=<code>&strategy_id=<id>` 后，K 线上按 trades 显示买入/卖出标记，红涨绿跌配色
- [ ] 资金曲线渲染正确（面积图 + 初始资金线/基准对比）
- [ ] 交易明细表与图表联动（可增量）
- [ ] 止损/止盈不同样式区分 + hover 显示成交价/数量/费用/触发原因（可增量）
- [ ] 回测中进度 / 失败原因与重试提示
- [ ] 数值口径以 G20 修复后的净盈亏/胜率为准
- [ ] 前端 build 通过；回测三文件 44 项保持全绿
- [ ] api-docs.md / Agent_code.md（前端+后端）已更新
- [ ] 代码已提交并推送到 GitHub

────────────────────────────────

## 【每步报告模板】

1. 已读文件清单
2. 修改/新增文件（按文件列，简述改动）
3. 自我审查 11 项逐项结果
4. 测试结果（后端 X/Y，前端 build 是否通过）
5. 规划冲突报告（如有按模板；如无写「无」）
6. 待确认事项

## 【总汇报模板】

1. 修改/新增文件清单
2. 完成情况和验收结果（对照上方验收清单逐项勾选）
3. 新增 API / 响应字段列表 + 需人工配置事项
4. 已知遗留问题或需确认的设计决策（含口径说明）
5. 测试运行结果（通过数/失败数）
6. 规划问题及处理结果汇总

（提示词正文结束）
