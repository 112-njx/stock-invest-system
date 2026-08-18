# 后端修复记录

> 记录开发过程中发现并修复的问题（含测试数据事故），方便回溯。
> 不要删除我对bug的描述，你将在每一个“bug问题描述”标题下按照格式对文档进行补充
> 如果需要你补充bug问题描述，你将按照以下格式进行补充：
> 日期：
> bug问题描述：
> 解决方案：
> 例如： 2026-08-11
>  bug问题描述：行情页原本的设计是进入即可以看到默认上证指数的k线，但是行情页下方的行业指数，包括左下方的大盘指数双击或所有标的都无法看到k线，
>  包括原本设置的最新价涨跌幅，行业指数关联的ETF，均无法看到在前端显示两条横杠。同样双击后无法看到页面a b c d。
> 解决方式：补齐固定指数数据，快照 NOT NULL 兜底.行情源降级等等。

## 2026-08-09 测试误删真实 600519（贵州茅台）

**现象**：开发阶段三测试时，早期 `test_chat.py` 用固定代码 `600519` 作为测试种子，清理逻辑按 `code` 删除，误删了真实标的 600519（贵州茅台，symbol_id=125），并把 600519 换成测试符号，导致 `test_market_api.py::test_snapshot_merges_symbols`、`test_watchlist.py::test_add_list_delete` 失败。

**修复**：删除残留测试符号（`name LIKE '聊天%'`），以显式 `id=125` 恢复 `600519/贵州茅台`，并重置 `symbols_id_seq`。测试种子改为随机代码/名称，杜绝与真实数据冲突。

**教训**：测试种子数据必须使用不可能与真实数据冲突的随机代码，清理必须按测试专属标识，禁止按通用 code 删除。

## 2026-08-11 阶段五补齐前端已对接但后端缺失的编排接口

**现象**：前端 AI 策略页阶段四按约定对接了 `GET /api/v1/agent/runs`（运行记录）与 `GET /api/v1/memory/files`（记忆文件），但后端未实现，前端以 404 空态占位。

**修复**：阶段五 5.5 补齐：agent_repo 增 list_runs/get_run/list_memory_files，schemas 增 AgentRunOut/AgentStepOut/MemoryFileOut（path 用 validation_alias 映射 file_path），新增 api/v1/agent_ops.py 三个只读接口（含 /agent/runs/{id} 内嵌 steps），router.py 注册，user 隔离 404/401。前端无需改动自动生效。

## 2026-08-11 监控指标采集容错（/metrics 不因 Redis/DB 不可用而失败）

**现象**：/metrics 端点扩展平台指标（队列深度/缓存命中率/行情新鲜度/回测积压）后，若 Redis 未启动或 DB 连接异常，采集会抛异常导致 /metrics 5xx。

**修复**：app/core/metrics_ext.py 各采集函数独立 try/except 静默跳过（仅记 warning），DB/Redis 不可用时对应 Gauge 保持旧值，不影响 /metrics 正常返回与既有指标。


---

## 2026-08-10 前端阶段四联调发现的两个接口编排缺失

**现象**：前端阶段四（AI 策略页）联调时，发现 roadmap/PageDesign 规划应有、但后端当前未实现/未暴露的两个接口：

1. **GET /api/v1/agent/runs（及 GET /api/v1/agent/runs/{run_id}）**
   - 需求来源：前端 roadmap 4.8.4「M 区 Agent 运行记录」要求按该接口展示多智能体运行历史，点击单条可查看完整 agent_steps 各节点原始输出。
   - 现状：后端仅暴露 `/api/v1/agents`（定制 Agent 配置 CRUD，阶段 3.7）；`agent_runs` / `agent_steps` 表已在 `03_agent_extensions.sql` 建表，LangGraph 深度模式运行时会写入数据，但**没有任何查询接口**，前端无法读取运行历史。
   - 建议补齐：`GET /api/v1/agent/runs`（列表：run_id/agent_id/conversation_id/symbol_id/run_type/status/input/output/tokens/error/created_at，支持按 conversation_id 过滤，仅本人）；`GET /api/v1/agent/runs/{id}`（含 `steps` 数组：step_name/agent_role/content/meta/created_at）。

2. **GET /api/v1/memory/files**
   - 需求来源：前端 roadmap 4.6「记忆文件」按钮需打开/展示用户本地记忆文件夹，PageDesign 亦注明「由后端提供打开能力/返回本地路径」。
   - 现状：后端仅在 config 配置 `MEMORY_DIR = data/memory`，记忆写入时生成人类可读 markdown 文件并登记 `user_memory_files` 索引，但**没有返回记忆文件列表的接口**。
   - 建议补齐：`GET /api/v1/memory/files`（返回当前用户记忆文件列表：path/content_type/content/updated_at；可选提供后端本机 `os.startfile` 打开文件夹能力）。

**影响与前端处理**：前端已按上述路径约定对接，接口 404/失败时展示占位空态提示，不影响其余 6 个任务验收；后端补齐后无需改动前端即可自动生效。



## 2026-08-11
## bug问题描述：行情页原本的设计是进入即可以看到默认上证指数的k线，但是行情页下方的行业指数，包括左下方的大盘指数双击或所有标的都无法看到k线，
## 包括原本设置的最新价涨跌幅，行业指数关联的ETF，均无法看到在前端显示两条横杠。同样双击后无法看到页面a b c d。 

**现象**：行情页进入后看不到默认上证指数 K 线；双击/单击任意大盘或行业指数行均无法打开第一层详情页（A/B/C/D 区），G/H 区指数最新价、涨跌幅与行业关联 ETF 全部显示 "--"，接口均返回 200 无报错。

**根因**（本地库数据 + 后端快照写入 + 前端事件三处）：
1. **固定指数数据缺失**：49 个固定指数（大盘 14 + 行业 35）的 K 线与实时快照从未成功入库（库中仅贵州茅台等股票有 81 条日K），`/kline` 返回空数组、`/snapshot` 返回 price=null → 前端空白 K 线与 "--"。
2. **快照 NOT NULL 约束 bug**：`snapshot_repo.upsert_snapshot` 对指数快照（无成交量/成交额字段）向 `volume`/`amount`（NOT NULL）写入 None，抛 `IntegrityError` 使整批快照回滚，`realtime_poll` 对指数全部失败（`synced: 0`）。
3. **行业 ETF 种子为空**：`symbols.etf_linked` 对 35 个行业指数为空，前端 ETF 列恒显示 "--"。
4. **前端缺少双击事件**：G/H 区（IndexListPanel）与 D/E 区（WatchlistPanel）行只有单击联动 F 区 K 线，无双击打开第一层详情页的事件，与需求「双击左键点开个股/ETF/行业指数具体 K 线」不符。

**修复**：
1. **补齐固定指数数据**：新增 `scripts/sync_fixed_indices.py`，一次性同步 49 个固定指数日K（周期 1d）+ 实时快照，幂等 upsert、可重复执行；本机已跑通（大盘指数各 ~483 条日K、9 个指数快照入库）。
2. **快照 NOT NULL 兜底**：`snapshot_repo.upsert_snapshot` 新增 `_not_null`，对 `volume`/`amount`/`change`/`change_pct` 空值写默认 0，指数快照正常入库。
3. **行情源降级**：`EastMoneyProvider` 在东方财富指数/行业板块接口被限流时降级——A 股大盘指数走新浪 `stock_zh_index_daily`、行业板块走同花顺 `stock_board_industry_index_ths`，保证固定指数 K 线可入库。
4. **补齐行业 ETF**：`docs/sql/02_seed_fixed_indices.sql` 为 35 个行业指数补 `etf_linked`（真实行业 ETF 代码，经 `fund_etf_spot_em` 全量校验），已应用到本地库；光学光电子、商业航天暂无直接对应 ETF 保留空。
5. **前端双击打开详情页**：`IndexListPanel`/`WatchlistPanel` 增加 `dblclick` 事件，`MarketView` 接线跳转 `/market/detail`（第一层 A/B/C/D 区）。

**教训**：行情页默认依赖固定指数数据，新增固定指数时必须同步 K 线/快照；快照写入须容忍指数类标缺失成交量/成交额的场景；前端行交互须同时实现单击联动与双击进入详情。


## bug问题描述：接上面的问题尽管无法跳转页面以及看到K线，双击行情页无法在后端终端看到任何报错bug。

**现象**：双击/单击指数行不跳转、看不到 K 线时，后端终端无任何报错日志，表现为"静默失败"。

**根因**：东方财富行情源反爬限流（`RemoteDisconnected`）时，`EastMoneyProvider._call` 指数退避重试后返回 None，同步任务把空结果仍标记为 success 并入库 0 条；`/kline`/`/snapshot` 对空数据返回 200 + 空值，前端只显示空白与 "--"，全程无异常抛给 API 层，故终端无报错。

**修复**：
1. 行情源降级兜底（新浪/同花顺），避免指数取数整体为 0（见上一节修复 3）。
2. 新增 `scripts/sync_fixed_indices.py` 逐标的输出 `ok / EMPTY(被限流/无数据)` 状态，空结果可见；后续可对 0 条同步在任务层追加告警。

**教训**：外部数据源被限流时不可静默成功，须降级兜底或输出可见的失败状态，保证可观测（生产级六要素「可观测」）。

## bug问题描述：app/agent/chat_service.py:183 的降级条件是：if not llm_svc.available or model is None:，可能导致APIKey填入后，ai对话永远走降级。

**现象**：在 `stock_backend/.env` 配置 DeepSeek API Key 并重启后端后，AI 对话仍始终返回降级文案「当前 AI 服务暂不可用…」，无法正常生成分析。

**根因**：`chat_service.stream_chat` 的 `model` 参数是测试注入用的可选参数，真实 API 端点 `/api/v1/chat` 从不传它（恒为 None）；第 183 行降级条件 `if not llm_svc.available or model is None:` 把 `model is None` 当作「服务不可用」信号，导致条件恒真 → 永远走降级分支，即使 `llm_svc.available` 为 True（API Key 已配置）。

**修复**：`chat_service.py` 降级条件去掉 `or model is None`，仅按 `not llm_svc.available` 判定；`model is None` 的兜底已由下方 `agent_model = model if model is not None else llm_svc.provider.raw_model` 正确处理（取 provider 默认模型）。新增回归测试 `test_stream_chat_model_none_with_available_not_fallback`：model=None 且 llm 可用时不得降级。全库 121 pytest 全绿。

**教训**：测试注入参数不得混入业务降级判定；可选参数 None 的语义应与「服务不可用」区分，None 应走默认值兜底而非降级。


## 2026-08-18
## bug问题描述：目前后端最大的问题是行情数据获取不清晰