# 项目约束与遗留问题

> 集中维护项目的已知遗留问题、技术决策、环境配置注意事项、后端能力对接清单。
> 每波开发完成后追加新问题，已解决的标记 [已解决] 并注明版本，不删除（保留历史追溯）。
> 所有波次的开发提示词均应引用本文件，开发Agent必须阅读并规避相关约束。

---

## 一、已知遗留问题

> 测试时间：2026-08-25，测试用户 njx（非管理员），前端/后端本地运行，Redis Docker 运行中。

### 第一波：行情数据基础

| 检查点 | 异常情况 | 可能的异常原因 |
|---|---|---|
| WebSocket 实时推送 | WS 完全未建立连接（performance 无 WS 请求，wsClient 已加载但无实际连接），前端全部依赖 HTTP 轮询 | WS 连接失败静默降级；BroadcastChannel leader 选举异常（stock_ws_leader 有值但不连接）；token 传递或 WS 端点鉴权问题 |
| 实时行情数据新鲜度 | 上证指数快照 data_age_seconds=1166954（约13.5天），updated_at=2026-08-11，当前为8月25日交易时段；大量指数/行业显示"--" | Celery beat/worker 未运行或 realtime_poll 任务失败；DataProvider 全熔断（东方财富被限流+新浪/同花顺不可用）；快照写入链路异常 |
| K线多周期数据 | 日K有491条，周K/月K/15min均返回0条；切换后图表空白 | 后端仅同步了日K数据，周K/月K/15min未同步或未从日K聚合；kline_init 任务仅拉取日K |
| K线空态提示 | 切换到周K/月K/15min无数据时，图表区域纯空白，无"暂无数据"引导文案 | 前端 KLineChart 组件未处理空数据场景，缺少统一空态渲染 |
| 添加关注到列表 | 点击搜索结果（贵州茅台）添加关注时弹出错误 "symbol: Input should be a valid string"（HTTP 422），关注添加失败，列表仍为0 | 前端发送 symbol 为 number 类型（symbol_id），后端 Pydantic schema 要求 str；API 文档标注"标的代码或 symbol_id"但 schema 仅接受字符串 |
| HTTP 轮询间隔 | 快照轮询约4s一次，roadmap 文档标注7s降级间隔 | 前端 useSnapshotPolling 配置与文档不一致（非严重问题，需确认配置项） |
| 搜索结果分组 | "已同步"分组标签正常显示；未测试"未同步"分组（搜索的贵州茅台已同步K线） | 需用未同步标的验证 is_catalog 分组渲染 |
| 大盘指数快照缺失（G区） | 科创50(73)/上证50(75)/中证1000(76)/中证2000(77)及海外指数(日经/韩国/道琼斯/纳指/标普/黄金)最新价、涨跌幅显示"--"；仅上证指数/沪深300/创业板指/深证成指4个有快照（8-11历史数据） | 固定指数实时同步不完整：sync_fixed_indices/预同步仅成功4个大盘指数，其余未拉取到快照（数据源限流或同步任务中断）；快照表仅存历史数据 |
| 行业指数快照缺失（H区） | 35个行业指数最新价、涨跌幅全部显示"--" | **行业指数 code 为空字符串**（symbols.code=""，仅名称无代码），resolve_index_code 名称→代码回填未生效，导致无法从数据源拉取行情；属第一波阶段三/四 DataProvider+目录同步链路 |
| 重点关注股票快照缺失（E/D区） | 关注列表贵州茅台(sync_status=done)有K线但 price/change/change_pct 均为 null，最新价、涨跌幅显示"--" | kline_init 已同步K线（maotai_kline_count=5）但 realtime_poll 未为其生成 snapshot_realtime 记录；快照生成链路对该标未执行/失败，属第一波阶段一实时快照同步 |
| C区基本数据全字段缺失（详情页） | 行业指数/个股详情页：现价-- 涨跌额-- 涨跌幅-- 昨收-- 今开-- 最高-- 最低-- 成交量-- 成交额-- 换手率-- 振幅-- 更新时间--（总市值-- PE--）全为"--" | 与上两行同根因：snapshot_realtime 无这些标的记录，前端如实渲染空态；仅4个有快照的大盘指数可正常显示 |
| 除贵州茅台外大部分 A 股股票无法添加重点关注 | 搜索赛力斯/山东玻纤等未入库股票返回空、无法添加关注；仅已入库的贵州茅台(600519)可正常添加；catalog 同步"A股 2 只 / ETF 0 只"未达标，全A股 5550 只未入库 | **akshare `stock_info_a_code_name()` 返回英文列名 `code/name`，但 `EastMoneyProvider.search_ak_stock` / `fetch_catalog` 硬编码判断中文列名 `"代码"/"名称"`，判断恒 False → 外部回退恒返回空、目录同步恒 0 只**（实测 df.columns=['code','name']，手动英文列名过滤可命中赛力斯 601127；贵州茅台因本地已入库走精确匹配不依赖外部回退） |
| 新添加股票关注后右侧快照缺失 | 新搜索添加的股票（赛力斯 601127）名称/代码正常，但现价/涨跌额/涨跌幅/昨收/今开/最高/最低/成交量/成交额/换手率/振幅/更新时间/总市值/市盈率PE 全部显示"--" | **add_watchlist 添加关注仅触发 kline_init（K线同步），不触发实时快照拉取**；快照依赖 realtime_poll 周期轮询，而新入库标的（is_catalog=True，赛力斯 id=11825 有日K484条）尚未被轮询覆盖；且 get_snapshots 只读 snapshot_realtime 表/Redis 缓存、不主动实时拉取 → 无记录即返回全 null → 前端"--"（佐证：快照表仅贵州茅台 1 只 stock 且停留 7-29 旧数据，38 个指数为 8-26 实时更新 → 个股实时拉取链路长期未生效） |

> **判断结论**：以上均属**第一波（行情数据基础）问题**——第一波验收目标即"行情数据从数据源同步→快照→前端展示"，当前快照缺失导致前端"--"是行情数据链路未达标。根因在后端同步环节而非前端渲染：① 行业指数 code 未回填（阶段三/四）；② realtime_poll 快照生成不完整（阶段一）；③ 固定指数预同步仅成功部分（阶段一）。

### 第二波：AI 基础加固

| 检查点 | 异常情况 | 可能的异常原因 |
|---|---|-|
| SSE 流式对话 | 普通对话流式输出正常，markdown 渲染正常，无异常 ||
| 记忆写入反馈 | 对话后未出现"已记住：{摘要}"轻量提示 | 后端 aextract_facts 返回空（已知问题，memory.md §13：抽取LLM调用失败或importance<5过滤），SSE memory_saved 事件未触发 |
| 错误分级UI | HTTP 422 错误显示红色条+"点击重试"按钮；未触发 RATE_LIMITED/TOKEN_INVALID 等场景 | 普通网络错误处理正常；限流/token错误需模拟场景验证 |
|策略生成 LLM 400 |已修复|
||
### 第三波：AI 高级功能

| 检查点 | 异常情况 | 可能的异常原因 |
|---|---|---|
| 深度分析请求 | 开启"深度分析"开关后发送请求返回 HTTP 422（验证错误），多智能体5节点时间线未渲染 | 前端发送的 run_type 参数值不符合后端枚举（后端接受 diagnostic/plan/radar/strategy/custom，前端可能发送 diagnose 或其他值）；请求体缺少深度模式必需字段 |
| 多智能体节点时间线 | 因深度分析请求422失败，无法验证时间线组件是否存在；从失败表现看阶段六可视化可能未完整对接 | 前端阶段六（多智能体可视化）可能未实现或未正确对接 agent_step SSE 事件 |
| 运行记录耗时 | 运行记录列表正常展示，但所有记录"耗时 --"；API 返回 total_duration=null（含今日新记录） | 后端 agent_runs.duration_ms 未正确记录（Alembic 0006 已加字段但运行时未写入）；或 run 结束时未计算耗时 |
| 运行记录详情跳转 | 点击运行记录列表项仅高亮，不跳转N区展示完整节点时间线+输出 | 前端阶段六6.3（运行历史回看）未实现点击跳转和节点详情展示 |
| 策略模板库API | GET /api/v1/strategy-templates 正常返回5个模板（双均线/MACD/KDJ/布林带/成交量异动） | —（后端正常） |
| "从模板创建"按钮 | 点击策略模块中"从模板创建"按钮后页面挂起无响应（浏览器超时），模板选择弹窗未出现 | 前端模板弹窗组件可能有渲染死循环或API调用阻塞；阶段七7.4模板库UI未完整实现 |
| 新会话残留旧错误 | 创建新会话后，上一会话的 HTTP 422 错误消息仍显示在新会话聊天区域 | 前端 aiStore 切换会话时未清空错误状态/消息列表；新会话初始化逻辑遗漏错误态重置 |
| 策略生成校验状态 | 未完整测试（"从模板创建"挂起后无法继续）；普通创建策略模块UI正常显示（入场规则/止损止盈/仓位管理按钮） | 阶段七7.3（策略三级校验+重试UI）需在策略生成成功后验证 |
| 生成→回测内嵌 | 未测试（深度分析422+模板按钮挂起，无法走完策略生成流程） | 阶段七7.5需端到端验证 |
| 策略回测发起（N区） [已解决 2026-08-27] | 策略生成成功后，在策略详情页选择标的点击「回测」报错 `symbol: Input should be a valid string`（HTTP 422），回测任务未提交 | 前端 StrategyDetailPanel.vue 发送 symbol 为数字（btSymbol.id），后端 BacktestCreateIn.symbol 为 str（Pydantic 2 拒绝 int→str 触发 422）；与「添加关注 422」「深度分析 422」同根因，前端未统一 symbol 转字符串 |
| LLM 流式输出 | 发送提示词后前端长时间显示「AI思考中」，无逐字打字机效果；LLM 生成完成后整段结果一次性出现，等待体验差 | 后端 LLM 输出从未走 token 级流式：普通对话走 create_agent().astream(stream_mode="updates")（节点级，整条 AI 消息作单个 delta）、深度模式节点用 ainvoke、策略生成用 ainvoke；llm_svc.astream（逐 token）已存在但 chat_service 未调用 → 生成期间零输出、完成后整段一次性推送 |
|在AI策略页点击回测，系统一直显示任务 #326 · queued · 进度 0%卡死| [已解决 2026-08-27]|
|当前对话消耗的 token 数|
| 策略详情页回测结果展示（回测后） | 回测结果区域指标卡片整组重复显示 n 次（胜率/盈亏比/夏普比率/累计买入/累计卖出/年化收益率/最大回撤 7 个字段循环出现，回测几次就出现几组）；首组有值（胜率0.00%/夏普-1.82/累计买入1/累计卖出1/年化-2.04%/最大回撤0.65%），后续组全空：盈亏比--、夏普比率--、累计买入0、累计卖出0、年化收益率0.00%、最大回撤0.00%、胜率-- | ① 前端 StrategyDetailPanel.vue 用 `v-for="r in results"` 对**每条历史回测记录**整组渲染 7 个指标卡片，未仅取最新一条（对比 StrategyMetricsPanel.vue 用 `latest()` 只取首条）→ 每次回测新增一组 → 重复显示；② 后续回测记录 win_rate/profit_loss_ratio/sharpe 等指标为 null（后端回测空跑/未产出有效交易，如标的无数据或回测失败仅存空记录）→ 前端如实渲染 "--"/0/0.00% |
偶现生成策略显示策略生成遇到问题，请尝试调整描述或基于模板创建的问题。
在ai生成策略后在对话框中立刻点击回测按钮，报错symbol: Input should be a valid string的问题
---

## 二、已确认的技术决策

1. **缓存层仅 Redis + PostgreSQL，不引入进程内内存缓存**——所有缓存数据走 Redis，避免多进程状态不一致。
2. **DataProvider 优先级链**：`[eastmoney, sina, ths]`，每源独立熔断（半开探测），可通过 `DATA_PROVIDER_PRIORITY` 环境变量调整。
3. **K线缓存键设计**：`kline:{symbol_id}:{period}:{limit}`（按最近N根，不含完整日期范围），TTL 300s，新K线写入时删除对应键。
4. **快照缓存**：`snapshot:{symbol_id}`，TTL 300s，存完整14字段，非交易时段正常返回并标注 data_age_seconds。
5. **前端不计算复杂指标**：MACD/KDJ等技术指标全部后端计算，前端只渲染。
6. **Agent 记忆本地存储**：ChromaDB + ONNX MiniLM 语义向量（`paraphrase-multilingual-MiniLM-L12-v2` int8，384维，加载失败回退 HashEmbedding），不写入中心数据库。原 roadmap 6.1 指定的 all-MiniLM-L6-v2 为英文模型，中文语义失效（实测相似度全 0.85~1.0），已弃用；多语言 L12 量化后约 118MB（roadmap 原「≤50MB」验收放宽为「≤120MB」，内存约 150~250MB）。

---

## 三、环境配置注意事项

### 必须配置
- **ADMIN_USERNAMES**：逗号分隔的用户名列表（如 `admin,user1`），启动时自动对应用户置 `is_admin=True`。不配则所有 `/admin/*` 端点返回 403。
- **DEEPSEEK_API_KEY**：AI对话功能必需，不配则走降级文案。
- **JWT_SECRET_KEY**：用户鉴权必需。

### 有默认值（无需强制改）
| 配置项 | 默认值 | 说明 |
|---|---|---|
| DATA_PROVIDER_PRIORITY | eastmoney,sina,ths | DataProvider优先级链 |
| PROVIDER_CIRCUIT_FAILURE_THRESHOLD | 3 | 熔断失败阈值 |
| PROVIDER_CIRCUIT_COOLDOWN | 60 | 熔断冷却时间（秒） |
| PROVIDER_PROBE_INTERVAL | 60 | 熔断恢复探测间隔（秒） |
| SNAPSHOT_CACHE_TTL | 300 | 快照缓存TTL（秒） |
| KLINE_CACHE_TTL | 300 | K线缓存TTL（秒） |
| SEARCH_CACHE_TTL | 3600 | 搜索结果缓存TTL（秒） |
| WATCHLIST_CACHE_TTL | 300 | 关注列表缓存TTL（秒） |
| REALTIME_POLL_INTERVAL | 5 | 实时行情轮询间隔（秒） |

```

---

## 四、后端能力对接清单（前端开发参考）

> V0.2 第一波后端已完成的能力，前端 V0.2 对应阶段开发时必须对接。

### 4.1 WebSocket 实时行情推送（对应前端阶段二）

**后端状态**：已完成（V0.2第一波阶段二）

| 项目 | 说明 |
|---|---|
| 端点 | `ws://{host}/api/v1/ws/market?token={jwt_token}` |
| 鉴权 | query 参数 `token`（JWT），或连接后首条消息 `{"action":"auth","token":"..."}` |
| 心跳 | 服务端每 15s 发 `{"type":"ping"}`，客户端需回 `{"type":"pong"}`，30s 无响应服务端断开 |
| 订阅 | `{"action":"subscribe","symbol_ids":[1,2,3]}` |
| 取消订阅 | `{"action":"unsubscribe","symbol_ids":[1,2]}` |
| 断线补拉 | 重连后发 `{"action":"sync","since":"2026-08-21T10:30:00Z"}`，服务端返回该时间后更新的快照 |
| 推送消息 | `{"type":"snapshot","data":{"1":{"price":...,"change_pct":...,"updated_at":"..."}}}` |
| K线推送 | `{"type":"kline","symbol_id":1,"period":"15m","bar":{"ts":...,"open":...}}` |
| 错误消息 | `{"type":"error","code":"AUTH_FAILED","message":"..."}` |
| 降级策略 | WS不可用时降级为 HTTP 轮询 `GET /api/v1/snapshot?symbols=id1,id2`（7s间隔），重连成功后切回WS |
| 本地开发注意 | 必须同时启动 Celery worker + beat，否则WS无数据推送（realtime_poll 在 worker 中运行） |

### 4.2 搜索接口增强（对应前端阶段三）

**后端状态**：已完成（V0.2第一波阶段三）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/symbols/search?keyword=xxx&type=stock&limit=20` |
| 新增参数 | `type`（stock/etf/index，可选）、`limit`（默认20） |
| 新增返回字段 | `is_catalog`（bool：是否仅在目录中未同步K线）、`has_kline`（bool：是否已有K线数据） |
| 搜索逻辑 | 三层：精确代码匹配 > 已同步K线标的 > 仅目录标的；本地无结果时外部回退（akshare） |
| 前端展示建议 | 分组展示：第一组"已同步"（has_kline=true），第二组"未同步"（is_catalog=true，灰色标注"添加后同步"） |
| 搜索缓存 | 后端已缓存 `search:{type}:{keyword}`，TTL 1h，前端无需额外缓存 |

### 4.3 关注列表同步状态（对应前端阶段三）

**后端状态**：已完成（V0.2第一波阶段三）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/watchlist` |
| 新增返回字段 | `sync_status`（pending/syncing/done/failed）、`last_synced_at`（ISO时间） |
| 自动同步 | 添加关注时后端自动触发 `kline_init` 异步任务，无需前端手动调用 |
| 前端展示建议 | 每行显示同步状态图标：syncing=旋转loading，done=无图标，failed=黄色感叹号（hover提示"点击重试"） |
| 重试 | 失败行点击可重新触发同步（需前端调用对应接口或后端提供重试端点） |
| 关注列表缓存 | 后端已缓存 `watchlist:{user_id}` + `watchlist_snap:{user_id}`，TTL 300s |

### 4.4 快照数据新鲜度（对应前端阶段一/三）

**后端状态**：已完成（V0.2第一波阶段一）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/snapshot?symbols=id1,id2` |
| 新增返回字段 | `data_age_seconds`（int：当前时间与 updated_at 的差值，秒） |
| 前端展示建议 | 交易时段：`data_age < 300` 显示"HH:MM:SS更新"（绿色），`> 300` 显示黄色"数据延迟"；非交易时段：显示"收盘 HH:MM更新"（灰色），不显示"--" |
| 非交易时段 | 后端正常返回缓存快照（TTL 300s），前端不应因非交易时段显示空白 |

### 4.5 固定指数预同步状态（对应前端阶段一）

**后端状态**：已完成（V0.2第一波阶段一）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/sync-status?scope=fixed_indices` |
| 返回 | `{status: running/done/failed, progress: 35, total: 49, message: "..."}` |
| 触发时机 | docker-entrypoint.sh 启动时自动检查，超过1天无数据则触发预同步 |
| 前端展示建议 | 行情页加载时先查此接口，running 时显示顶部进度条"数据同步中（X/49）"，G/H区显示骨架屏，done后自动刷新 |

### 4.6 DataProvider 健康状态（管理端点）

**后端状态**：已完成（V0.2第一波阶段四）

| 项目 | 说明 |
|---|---|
| 端点 | `GET /api/v1/admin/providers/health`（需管理员权限） |
| 返回 | 各Provider状态：available/circuit_open/failed，失败次数，最近成功时间 |
| 用途 | 运维排查行情数据异常时使用，前端普通用户无需对接 |

### 4.7 标的目录手动同步（管理端点）

**后端状态**：已完成（V0.2第一波阶段三）

| 项目 | 说明 |
|---|---|
| 端点 | `POST /api/v1/admin/catalog/sync`（需管理员权限） |
| 功能 | 手动触发全A股+ETF目录同步（akshare），异步任务 |
| 注意 | 无 worker 环境任务停留 queued，需启动 worker |
| 定时 | Celery beat 每日凌晨 3:00 自动执行 |

---

## 五、数据库迁移记录

| 版本 | 文件 | 内容 | 状态 |
|---|---|---|---|
| 0001 | 初始建表 | 24表+K线分区 | 已执行 |
| 0002 | backtest_tasks 扩展 | period/start_ts/end_ts/fill_on | 已执行 |
| 0003 | agent_extensions | user_agents/agent_runs/agent_steps/memory_chunks | 已执行 |
| 0004 | 0004_v02_wave1.py | users.is_admin、sync_status表、symbols.is_catalog+索引、user_watchlist.sync_status/last_synced_at | 已执行（本地），部署环境由 entrypoint 自动迁移 |
| 0005 | 0005_memory_importance.py | memory_chunks.importance（记忆重要性评分，检索加权+低重要性清理） | 已执行（本地），部署环境由 entrypoint 自动迁移 |

迁移执行命令：
```powershell
cd D:\stock-invest-system\stock_backend
.venv\Scripts\alembic.exe current    # 查看当前版本
.venv\Scripts\alembic.exe history    # 查看迁移链
.venv\Scripts\alembic.exe upgrade head  # 升级到最新
```

---

## 六、变更日志

- **2026-08-21**：初始创建，整理 V0.2 第一波遗留问题5项、技术决策6项、环境配置、后端能力对接清单7项、迁移记录。
- **2026-08-21**：V0.2第一波前端完成后更新：问题4状态更新（前端断线降级已实现）；新增问题6（WS推送snapshot仅含价格字段，前端merge规避）、问题7（BroadcastChannel leader接管延迟约5s）、问题8（关注列表失败无专用重试端点，前端重新添加规避）。本轮未删除任何已有遗留问题（问题2/3/5均为后端/设计层面，前端工作未完全解决）。
- **2026-08-22**：V0.2第二波后端（阶段五AI流式稳定性+阶段六记忆系统int8）完成后更新：技术决策6 更新为 ONNX MiniLM 语义向量（多语言 L12 int8）；新增 Embedding 模型选型说明（all-MiniLM-L6-v2 中文失效已弃用，改用多语言 MiniLM-L12，≤50MB 验收放宽≤120MB）；新增阶段六环境配置（EMBEDDING_MODEL/首次下载模型/rebuild_embeddings.py 重建）。迁移记录新增 0005（memory_chunks.importance）。
