# SQL 表作用说明

> 对应 `01_schema.sql`（建表）+ `02_seed_fixed_indices.sql`（固定指数种子）+ `03_agent_extensions.sql`（Agent 智能体扩展），按领域说明每张表在系统中的作用。
> 术语：行情页第二层 E/F/G/H/I 区、第一层 A/B/C/D 区、AI 策略页 J/K/L/M/N 区（见 docs.md / PageDesign.md）。

## 一、行情域（Market）

| 表 | 系统中的作用 | 关键说明 |
|---|---|---|
| **symbols** | 标的统一模型：股票/ETF/指数共用一张表，全系统引用标的都走 `symbol_id` | `type` 区分 stock/etf/index；`is_fixed_index + sort_order` 驱动 G/H 区固定指数列表顺序；`etf_linked` 显示关联 ETF；行业指数 `code` 由同步任务按名称回填 |
| **kline_15m / kline_1d / kline_1w / kline_1mon** | 各周期历史 K 线，A/F 区 K 线图数据源；也是指标计算与回测引擎的基础 | 按月分区 + 默认分区兜底；`UNIQUE(symbol_id, ts)` 幂等，重复同步不产生脏数据 |
| **snapshot_realtime** | 实时行情快照（每标的一行），C 区基本数据 + E/D/G/H 区最新价/涨跌幅来源，前台轮询刷新 | 交易时段由同步任务轮询更新；合并特殊字段后返回前端 |
| **stock_fundamentals** | 个股特殊数据：总市值、PE（C 区个股显示） | 与 snapshot 联查返回 |
| **etf_premiums** | ETF 特殊数据：净值、溢价率（C 区 ETF 显示） | 同上 |
| **index_valuations** | 指数特殊数据：指数总 PE（C 区指数显示） | 同上 |
| **support_resistance** | 用户自定义支撑/压力位，B 区设置后叠加到 K 线横线 | 按 user+symbol 隔离，type=support/pressure |

## 二、用户域（User）

| 表 | 系统中的作用 | 关键说明 |
|---|---|---|
| **users** | 用户账号，登录/鉴权与用户信息（头像/昵称）基础 | 密码存哈希，JWT 鉴权 |
| **user_watchlist** | 重点关注股票，D/E 区关注列表数据源 | `UNIQUE(user_id, symbol_id)` 幂等 |
| **user_memory_files** | Agent 本地记忆文件索引，登记每个用户的记忆文件 | `file_path` 指向本地文件，`content_type`=strategy/rule/preference；M 区「记忆文件」按钮打开本地文件夹依据 |

## 三、策略 / AI 域（Strategy / AI）

| 表 | 系统中的作用 | 关键说明 |
|---|---|---|
| **conversations** | 会话（聊天记录），J 区会话列表数据源 | 按 user 隔离 |
| **chat_messages** | 会话内消息，J/K 区对话展示与历史加载数据源 | `role`=user/assistant/system；`symbol_id` 可绑定标的（标的选择行） |
| **trading_strategies** | 用户交易策略（描述/代码/JSON 参数/状态），M 区策略列表 + N 区展示数据源 | 保存策略按钮入库；`code` 供回测执行；`params` 入场/止损/仓位参数 |
| **backtest_tasks** | 回测任务状态机（queued→running→success/failed + 进度），前端轮询任务状态 | Celery worker 异步执行，不阻塞主线程 |
| **backtest_results** | 回测结果指标，N 区回测结果 + 全景K线策略指标（D 区替换面板）数据源 | 胜率/盈亏比/夏普/累计买卖/年化/最大回撤 + `metrics_json` 扩展；与策略保存事务性写入 |

## 四、智能体域（Agent，LangChain/LangGraph）

| 表 | 系统中的作用 | 关键说明 |
|---|---|---|
| **user_agents** | 用户定制交易 Agent 配置，实现「为用户定制自己的交易 Agent」 | `agent_type`=diagnostic/plan/radar/strategy/custom；`system_prompt` 存交易体系/规则；`tools`/`llm_config`/`memory_config` JSONB 配置化 |
| **agent_runs** | 一次 LangGraph 多智能体执行记录（状态机 + 输入输出 + token），可观测与成本追踪 | 关联 user/agent/conversation/symbol；status=queued→running→success/failed |
| **agent_steps** | 多智能体各步骤中间输出（分析/多空辩论/风控/决策），供复盘与链路展示 | 借鉴 TradingAgents-CN 各 agent 角色（analyst/researcher/manager/trader） |
| **memory_chunks** | LangChain 本地向量记忆切片索引（文本+来源+本地文件+向量库ID），RAG 检索回溯 | 记忆本体存本地文件/ChromaDB，`vector_id` 关联向量库记录，`file_path` 关联本地文件 |

## 五、运维域（Ops）

| 表 | 系统中的作用 | 关键说明 |
|---|---|---|
| **sync_tasks** | 行情同步任务运行状态记录，供任务调度与监控 | task_type=kline_init/kline_incremental/realtime |
| **task_logs** | 全链路任务日志，可观测/排查依据 | 记录 Celery 任务 ID 与 request-id，贯穿 API→任务→AI 调用 |

## 六、辅助对象（函数/种子）

- **`set_updated_at()` 触发器**：users / conversations / trading_strategies / backtest_tasks / user_agents / agent_runs 更新时自动维护 `updated_at`。
- **`create_kline_partitions(p_table, p_start, p_end)`**：按月批量创建 K 线分区，并建默认分区兜底越界写入；后续扩分区直接调用。
- **02_seed_fixed_indices.sql**：写入 49 条固定大盘/行业指数（`is_fixed_index=TRUE`），是 G/H 区列表的固定数据来源；行业指数 `code` 留空待同步回填；按 `(type, name)` 幂等 upsert。

## 七、设计要点（跨表）

- 用户专属数据（watchlist/strategies/agents/记忆/支撑压力）均带 `user_id`，保证多用户隔离。
- K 线/快照带 `symbol_id`，关联行情、指标、回测、AI 上下文复用同一标的。
- 策略 + 回测结果 + 记忆文件写入用事务/补偿保证原子性；Agent 运行/步骤与对话消息同事务。
- 记忆本体存本地文件/本地向量库，`user_memory_files`/`memory_chunks` 仅作索引与回溯。
