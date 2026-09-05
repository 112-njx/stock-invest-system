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
## bug问题描述：目前后端最大的问题是行情数据获取不清晰。
## v0.1版本前端无法正常显示的数据：
## （1）大盘指数右侧的成交量成交额，指数PE。
## （2）行情页行业指数最新价涨跌幅
## （3）行情详细页行业指数右方基本数据全部。

**现象**：行情页大盘指数成交量/成交额、指数 PE，行业指数最新价/涨跌幅，详情页行业指数 C 区基本数据均无法显示（"--"/空）；本地库 `stock_fundamentals`/`etf_premiums`/`index_valuations` 三张特殊字段表均为 0 行。

**根因**（复述）：
1. **大盘指数成交量**：`stock_zh_index_spot_em`（国内4分类）有成交量列，但 `index_global_spot_em`（海外指数）无此字段；`_map_spot` 对缺失列返回 None，经 `snapshot_repo._not_null` 写 0，前端显示 0 而非 "--"，无法区分"真实零成交"与"数据缺失"。
2. **指数PE**：`index_valuations` 表已建、`snapshot_repo.upsert_index_valuation` 方法已写，但 `sync_service.run_realtime_poll()` 同步流程中从未调用；同理 `stock_fundamentals`（个股总市值/PE）、`etf_premiums`（ETF净值/溢价）也未在同步中填充。
3. **行业指数最新价涨跌幅**：`_map_industry_spot` 按名称精确匹配，种子行业名与东财板块名不一致即 available=False 被跳过；实测 35 个行业 code 全部未回填、仅 16 个名称精确命中东财板块；且实时快照 `retry_times=1`，被限流无重试。
4. **行业指数基本数据**：`stock_board_industry_name_em` 实时接口仅返回最新价/涨跌额/涨跌幅/换手率 4 字段，无昨收/今开/最高/最低/成交量/振幅，C 区基本数据大部分为空。

**修复**（实际实施）：
1. **大盘指数成交量/成交额**：Alembic 迁移 0003 将 `snapshot_realtime.volume/amount` 改为 nullable（保留 DEFAULT 0）；`snapshot_repo.upsert_snapshot` 对 volume/amount 不再 `_not_null` 兜底，数据源缺失列保持 NULL 写入，前端 `formatAmount(NULL)` 显示 "--"（海外指数无成交量属数据源正常，非 bug）。
2. **特殊字段纳入同步主链路**（`sync_service.run_realtime_poll`）：
   - 个股总市值/PE：`_map_spot` 从 `stock_zh_a_spot_em` 的"总市值""市盈率-动态"列提取到 quote.extra → `upsert_fundamentals`；
   - ETF净值/溢价：从 `fund_etf_spot_em` 的"IOPV实时估值""基金折价率"（溢价率=-折价率）提取 → `upsert_etf_premium`；
   - 指数PE：新增 `EastMoneyProvider.fetch_index_pe`，用乐咕 `stock_index_pe_lg` 取最新"滚动市盈率" → `upsert_index_valuation`。
3. **行业指数匹配改为通用评分模糊匹配**（不硬编码映射，数据源可扩展）：板块代码 BKxxxx 精确优先 → 名称精确 → 评分匹配（剥离罗马数字分类后缀 Ⅲ/Ⅱ、前后缀包含长度差≤3 且仅限≥3字词、否定前缀"非"强惩罚、阈值 75，全部候选取最高分）。真实东财板块列表（491 个）离线验证：35 行业 23 个正确匹配（白酒→白酒Ⅲ、游戏→游戏Ⅲ、证券→证券Ⅲ、煤炭开采加工→煤炭开采等），10 个无对应板块诚实显示 "--"（创新药/文化传媒/军工/消费/细分化工/农业种植/猪肉/港口航运/公路铁路运输/汽车整车）；并避免"白酒→非白酒""消费→消费电子"误配。`resolve_index_code` 复用评分逻辑使行业 code 可回填（BKxxxx），回填后实时/K线同步优先 code。实时接口 `retry_times` 1→2。
4. **行业指数基本数据 K 线推导**：`run_realtime_poll` 对 industry_index 类型补充——昨收=前一根日K close，今开/最高/最低/量/额=最新根，振幅=(high-low)/pre_close×100，推导后写入 quote 再 `upsert_snapshot`。

**与上方案的差异**：① `index_value_hist_funddb` 在 akshare 1.18.83 不存在，指数PE 改用 `stock_index_pe_lg`（仅覆盖 沪深300/上证50/中证1000，其余指数无 PE 数据源显示 "--"）；② 行业名称不硬编码修正种子，改为通用评分模糊匹配（对齐"不编造、数据源可扩展"原则），部分语义无对应行业诚实 "--"。

**验证**：全库 133 pytest 全绿（新增 12 个：评分匹配规则、否定/过长拒绝、行业K线推导、特殊字段落库、海外指数 NULL 落库、指数PE、code 回填），ruff 通过；迁移 0003 已应用。真实端到端触发 `run_realtime_poll` 代码链路无异常，但东财实时接口当前限流（`RemoteDisconnected`，synced=0），限流冷却后重跑实时同步（beat/`realtime_poll`）即生效。

**教训**：指数/行业板块与个股/ETF 数据源字段完整度本质不同，同步层须按资产类型字段补全（K线推导）或显式置空（NULL），不可用 0 兜底掩盖数据缺失；特殊字段表不能只建表写方法而不在同步主链路调用；中文行业名不可靠简单字面模糊匹配（易"白酒→非白酒"误配），须评分 + 否定惩罚 + 低置信度诚实留空，且不硬编码映射以保数据源可扩展。


## 2026-08-18
## bug问题描述：目前后端最大的问题是行情数据获取不清晰。
## v0.1版本前端无法正常显示的数据：
## （1）大盘指数右侧的成交量成交额，指数PE。
## （2）行情页行业指数最新价涨跌幅
## （3）行情详细页行业指数右方基本数据全部。

**根因**：
1. **大盘指数成交量**：`stock_zh_index_spot_em`（国内4分类）返回成交量列，但 `index_global_spot_em`（海外指数如道琼斯/纳斯达克）无此字段；`_map_spot` 对缺失列返回 None，经 `snapshot_repo._not_null` 写 0，前端显示 0 而非 "--"，无法区分"真实零成交"与"数据缺失"。
2. **指数PE**：`index_valuations` 表已建、`snapshot_repo.upsert_index_valuation` 方法已写，但 `sync_service.run_realtime_poll()` 同步流程中**从未调用**，指数PE数据完全缺失；同理 `stock_fundamentals`（个股总市值/PE）、`etf_premiums`（ETF净值/溢价）也未在同步中填充。
3. **行业指数最新价涨跌幅**：`_map_industry_spot` 按 `s.name` 与"板块名称"**精确匹配**，种子 SQL 中行业名称与东方财富返回的板块名称可能不一致（如"光学光电子"vs"光学光电"、"油气开采及服务"vs"油气开采"），匹配失败即 `available=False` 被跳过；且实时快照调用 `retry_times=1`，行业板块接口被限流后无重试机会。
4. **行业指数基本数据**：`stock_board_industry_name_em` 实时接口仅返回最新价/涨跌额/涨跌幅/换手率4个字段，**无昨收/今开/最高/最低/成交量/振幅**，`_map_industry_spot` 未对缺失字段做任何补全，导致 C 区基本数据大部分为空。

**修复**：
1. **大盘指数成交量**：`_map_spot` 中对指数类标 volume 缺失时保持 None（不经过 `_not_null` 写 0），`snapshot_realtime` 表对应列允许 NULL，前端 `formatAmount(None)` 显示 "--"；海外指数无成交量属数据源正常现象。
2. **指数PE及特殊字段**：同步流程新增特殊字段填充——指数PE用 akshare `index_value_hist_funddb` / `stock_index_pe_lg` 取最新估值调 `upsert_index_valuation`；个股总市值/PE 从 `stock_zh_a_spot_em` 返回列（"总市值""市盈率-动态"）提取放入 `quote.extra` 后调 `upsert_fundamentals`；ETF净值/溢价从 `fund_etf_spot_em` 返回列提取调 `upsert_etf_premium`。
3. **行业指数最新价涨跌幅**：`_map_industry_spot` 增加子串模糊匹配兜底（精确匹配失败后用名称前2-3字 `str.contains` 匹配，与指数 `_map_spot` 的 match_by_name 逻辑对齐）；行业指数实时接口 `retry_times` 从 1 改为 2~3；首次部署时运行 `stock_board_industry_name_em` 输出真实板块名称，与种子 SQL 中35个行业名称逐一比对修正。
4. **行业指数基本数据**：在 `sync_service.run_realtime_poll` 中对 `industry_index` 类型补充 K 线推导——取该标的最新一根日K填充：昨收=前一根 close，今开/最高/最低=最新根 open/high/low，成交量=最新根 volume，振幅=(high-low)/pre_close×100；推导字段写入 `quote` 后再 `upsert_snapshot`，保证 C 区基本数据完整。

**教训**：指数/行业板块与个股/ETF 的数据源字段完整度本质不同，同步层须按资产类型做字段补全（K线推导）或显式置空（NULL），不可用 0 兜底掩盖数据缺失；特殊字段表（PE/市值/溢价）不能只建表写方法而不在同步流程中调用，须纳入 `run_realtime_poll` 主链路。
---

## 2026-08-18
## bug问题描述：技术指标 Redis 缓存 key 包含动态 start/end 时间，导致缓存命中率几乎为 0，每次进入详情页都要重新查 K 线 + pandas 计算，前端等待明显。

**现象**：前端进入行情详情页后，技术指标区域每次都要等待数百毫秒到 1 秒才显示；即使同一标的同一周期短时间内反复进入，也无法命中 Redis 缓存，始终走全量计算流程。

**根因**：pp/services/indicator_service.py 的 _cache_key 将 start.isoformat() 和 end.isoformat() 纳入缓存 key，而 compute_indicators 中 end 默认取 datetime.now(UTC)、start 默认取 end - 365天，每次请求这两个值都不同 → 缓存 key 每次都不同 → 即使 K 线最新 ts 未变、指标结果完全一致，也无法命中之前的缓存。Redis TTL=300 秒形同虚设。

**修复**：_cache_key 移除 start 和 end 两段，key 仅保留 symbol_id + period + names_sorted + params_hash + limit + latest_ts。指标结果由 K 线数据决定，查询窗口不影响结果（limit 已在 key 中），latest_ts 已能保证新数据到达时自动失效。修改后同一标的同一周期在 K 线未更新时可稳定命中缓存，第二次访问毫秒级返回。

**教训**：缓存 key 只应包含影响结果的变量，动态时间戳（now）不得直接纳入 key，否则缓存永远不命中；时间窗口应通过 latest_ts 等数据版本标记间接体现。

## 2026-08-18
## 优化方案：技术指标加载性能优化（后端侧）

**背景**：v0.1 前端反馈进入详情页后技术指标等待时间长。除上述缓存 key 缺陷外，后端侧还有以下可优化点：

1. **指标预热（Celery 定时任务）**：对用户关注列表（watchlist）中的标的，在 
ealtime_poll 同步 K 线后立即触发指标预计算并写入 Redis，用户首次访问即可命中缓存。实现方式：sync_service 在 K 线增量同步成功后调用 indicator_service.compute_indicators（静默预热，失败不阻塞主链路），或新增独立 beat 任务每 5 分钟对热门标的预热。
2. **计算结果增量更新**：当前每次缓存失效都重算全部历史指标。可改为仅对最新一根 K 线增量计算 MACD/KDJ（指标递推公式），历史结果复用缓存，降低计算量。
3. **批量指标接口**：当前前端每次只查一个标的，可新增 POST /api/v1/indicators/batch 支持一次查多个标的，减少首页 F 区切换标的时的请求次数。

---

## 2026-08-25 前端 WS 完全未连接 + 添加关注 422（V0.2 全波次审计发现）

**现象**：审计 V0.2 第一波至第三波全部开发后发现两个严重问题：
1. **WS 完全未连接**：`wsClient` 已加载（模块单例已实例化），但 Network 面板无任何 `ws://` 连接，实时行情全靠 HTTP 轮询（7s/4s）兜底。
2. **添加关注 422**：`POST /api/v1/watchlist` 返回 422 `symbol: Input should be a valid string`。

**根因**（前端两处）：
1. **WS leader 选举死锁**：`wsClient.ts` 构造函数里的 `tryBecomeLeader()` 用 localStorage `stock_ws_leader` 键做多标签页 leader 选举，但**无过期检测、无心跳续约**——只要残留旧键（标签页被强杀/浏览器崩溃未触发 `beforeunload` 清理），后续所有新标签页都判定自己是 follower，`connect()` 里 `if (!this.isLeader) return` 直接提前返回，**永远没有标签页真正发起 WS 连接**。5s 轮询也只查"键是否存在"而非"是否过期"，死锁永久持续。浏览器现场证据：`stock_ws_leader` 键存在但 ws store `connected:false`。
2. **MarketDetailView 未初始化 WS**：详情页 `onMounted` 只调 `useSnapshotPolling`（HTTP 轮询），未调 `ws.init()`。SPA 导航（/market→/market/detail）下单例保留 WS 仍有效，但**直接刷新/直达详情页时 WS 永不连接**。
3. **添加关注传参类型不符**：后端 `WatchlistAddIn.symbol: str`（schemas/user.py）期望字符串代码；前端 `WatchlistPanel.onPickSuggestion` 传 `s.id`（数字 symbol_id）→ Pydantic 422。同文件 `retrySync` 用 `item.code`（正确），两处不一致。

**修复**（全部前端文件，无后端改动）：
1. **`src/utils/wsClient.ts` leader 选举重构**：
   - 不在构造函数竞选，改为首次 `connect()` 按需抢占（避免登录页等未真正需要 WS 的页面占用 leader）；
   - `claimLeadership()`：localStorage 键不存在或时间戳超过 `LEADER_TIMEOUT_MS=8s` 视为可抢占，写回后二次确认所有权（防多标签页竞态双 leader）；
   - leader 每 2s 心跳续约时间戳，`beforeunload` 释放；follower 每 2s 检测 leader 超时失效则抢占并建立连接；
   - `disconnect()` 释放 leader（登出场景）。
2. **`src/views/MarketDetailView.vue`**：`onMounted` 补充 `ws.init()` + `ws.syncSubscriptions()`（保证直达/刷新详情页 WS 连接）。
3. **`src/components/trading/WatchlistPanel.vue`**：`onPickSuggestion` 改传 `s.code`（字符串代码）。
4. **`src/api/market.ts`**：`addWatchlist` 请求体统一 `String(symbol)` 强转，杜绝再传数字触发 422（防御性兜底）。

**验证**：`vue-tsc -b --noEmit` 全绿；浏览器实测 /market 与 /market/detail 两页 WS 均 `connected:true`、订阅 49 个固定指数、控制台 0 错误；添加关注「贵州茅台 600519」成功（sync_status:done），无 422。

**教训**：localStorage 标记型多标签页 leader 选举必须有"心跳续约 + 超时抢占"机制，仅"键存在与否"判定会导致陈旧键死锁；凡有实时数据需求的页面都应初始化 WS 基础设施，不能只依赖 SPA 导航下单例的"侥幸存活"；前端调用后端字段类型必须与 Pydantic schema 严格对齐（`str` 就传字符串），API 层对入参做类型强转可有效兜底。


## 2026-08-25 记忆写入反馈缺失（aextract_facts 返回空，对话后无「已记住」提示）

**现象**：AI 对话完成后前端始终收不到 `memory_saved` 事件，无「已记住」轻提示；后端日志出现 `memory extract/save failed: '"content"'`，记忆抽取从未真正执行。

**根因**：`app/agent/memory/memory_service.py` 的 `_EXTRACT_PROMPT` 模板内嵌 JSON 示例时使用了字面 `{` `}` 花括号（`{"content": "一句话事实", ...}`），而 `aextract_facts` 用 `_EXTRACT_PROMPT.format(user_msg=..., assistant_msg=...)` 填充模板。Python 的 `str.format()` 把 `{` `}` 当占位符，`{"content"` 被解析为字段名 → 抛 `KeyError: '"content"'`。且该 `format()` 调用位于 `aextract_facts` 的 `try/except` 之外，异常向上抛到 `chat_service._extract_and_save_memory` 的 `except`（best-effort 吞掉）→ 返回空，导致无 memory_saved 事件。

**修复**：把 `_EXTRACT_PROMPT` 中 JSON 示例的花括号转义为 `{{` `}}`（`{{"content": ...}}`），使 `str.format()` 仅把 `{user_msg}`/`{assistant_msg}` 当占位符、JSON 示例原样输出。新增回归测试 `test_aextract_facts_parses_valid_json`（假 LLM 返回合法 JSON → 正确解析出 fact），确保 format 不再抛异常、抽取链路可用。

**教训**：用 `str.format()` 填充含 JSON 示例/花括号的 prompt 模板时，字面花括号必须转义为 `{{`/`}}`；best-effort 分支吞异常会掩盖模板 bug——凡格式化/解析类语句应置于 try/except 内，或对 prompt 模板做单测，避免运行时静默失败。

## 2026-08-26 历史 K 线有数据但无技术指标（2025-08-25 之前）

**现象**：大盘指数、行业指数的历史 K 线（2025-08-25 之前）能正常显示，但同区间下方技术指标（MACD/KDJ/成交量/成交额）全部为空（"--"）。

**根因**：技术指标并非落库，而是每次请求时后端从 K 线实时计算（`indicator_service.compute_indicators` → 拉 K 线 → 计算 → Redis 缓存）。其拉取窗口与 K 线接口不一致：
1. 后端 `compute_indicators` 在未显式传 `start` 时用 `_DEFAULT_BACK_DAYS=365`，把 K 线窗口截断到**最近 365 天**（今天 2026-08-26 往前 365 天 ≈ 2025-08-25，正好对上现象日期）；
2. 前端 `KLineChart.vue` 指标请求显式传 `limit:500`、`IndicatorPanel.vue` 传 `limit:200`，而 K 线请求 `fetchKLine` 不传 limit（走后端默认 1000，全历史）。三者叠加导致指标只覆盖最近约 1 年 / 200~500 根，与 K 线全历史脱节。

**修复**：
1. `app/services/indicator_service.py`：`_DEFAULT_BACK_DAYS` 由 365 改为 7300（约 20 年，等价"按 limit 取最近 N 根"，与 `get_kline` 默认区间对齐），未显式传 start 时不再按固定天数截断；
2. 前端 `KLineChart.vue` / `IndicatorPanel.vue` 的指标请求删除显式 `limit` 参数，改用后端默认 1000，与 K 线 `fetchKLine` 深度一致。

**验证**：全库 259 pytest 全绿 + ruff 通过；指标默认区间与 K 线默认区间语义对齐。

**教训**：指标（按需计算类数据）的默认拉取窗口必须与 K 线默认深度一致——未显式指定区间时应"按 limit 取最近 N 根"而非固定天数截断；前后端多处请求同一标的时，limit 要统一到同一默认值，避免"K 线全、指标半"的脱节。


## 2026-09-04 Docker 日志审计：catalog_sync 崩溃（1000 ETF 批量插入撞唯一约束）

**现象**：worker 日志 catalog_sync failed（sync_service.py:218 upsert_catalog_symbols），SQLAlchemy executemany 参数含 1000 个 catalog ETF；容器库 symbols 表 ETF 数量=0，全量目录同步从未成功。

**根因**：symbol_repo.upsert_catalog_symbols 按 code 查重（existing = select where code==code），存在则跳过、不存在则新增；但 symbols 表唯一约束是 (type, name)（symbols_type_name_key）。全市场 ETF 中存在同名不同 code 的标的（如不同上市地同名牌），按 code 查不到 → 都新增 → 撞 (type,name) 唯一约束批量回滚。

**修复**：upsert_catalog_symbols 查重改为按 (type,name) 对齐唯一约束，并加 seen 集合防同批内同名重复（Session autoflush=False 时同批同名仍会重复插入），每 100 条 flush 一次使 pending 行对后续查询可见。实测同名不同 code 3 条 ETF 合并为 1 条、幂等测试通过（test_tmp_p135 验证后已删）。

**教训**：唯一约束与查重键不一致必然导致幂等 upsert 批量失败；目录同步须按真实唯一键（type+name）判重。

---

## 2026-09-04 Docker 日志审计：新浪 stock_zh_index_daily 仍报 date 列 KeyError

**现象**：日志 [provider:sina] stock_zh_index_daily failed (attempt 1/2/3) 后 give up，多源降级链新浪环节持续打穿。

**根因**：akshare stock_zh_index_daily 返回缺 date 列（列名/格式漂移），sina.py 该调用点的日期列兼容（_pick_col）未覆盖或容器镜像未重建生效，仍按硬编码取列抛 KeyError。

**修复**：已核对——sina.py:75 该调用点已走 `_pick_col(df, "date", "日期")` 兼容逻辑、缺列优雅返回空（属问题三落地修复，随 b218b70 入代码库）；剩确认修复已入容器镜像：`docker compose up --build` 重建后 worker 不再报该 KeyError。

**教训**：外部数据源列名漂移须在 Provider 内统一做列名兼容抽象，且修复后必须重建容器镜像验证，避免修复只落在本地没进容器。

---

## 2026-09-04 重启后仍需重新拉取等待（presync stale 判定 1 天太激进）

**现象**：种子数据已在容器卷中（kline_1d 17368 行、34 个固定指数有日K），但每次 docker 重启后前端仍显示同步中并重新拉取等待。

**根因**：① maybe_presync_fixed_indices 的 stale 判定为最新日K距今超过 1 天或无数据即算 stale，而日K本来就是 T+1 收盘才有，今天盘中看到昨天日K属正常却被判 stale → 每次启动必触发 kline_init_fixed_indices 任务与前端同步提示；② 15 个固定指数（主要为行业指数）无任何日K，数据源不可靠时全量拉取卡等待。

**修复**：stale_fixed_index_count 阈值由 1 天放宽到 7 自然日（覆盖周末+小长假），日K T+1 盘中看昨日不再误判 stale；无日K/超 7 天仍判 stale。无日K的行业指数走既有 skip_existing 逻辑（问题四修复：有数据跳过、仅无数据拉取），过期数据由每日 16:30 增量任务自愈。实测 3 天不 stale、10 天+无数据 stale（test_tmp_p135 验证后已删）。

**教训**：新鲜度判定要贴合数据本身生成周期（日K T+1），不可用固定 1 天硬阈值导致每次重启误触发全量同步。

---

## 2026-09-04 catalog_sync 全量目录同步拉 1000 ETF（体验问题说明）

**现象**：用户疑问行业指数 ETF 就固定几个、为何启动时拉取 1000 个 ETF；日志显示 catalog_sync 对全市场 ETF（1000+只，养殖/光伏/红利等所有品种）做目录批量 upsert，0/16 tqdm 为 akshare 分页进度。

**说明**：非固定指数拉取。catalog_sync（V0.2 3.1）设计为启动时全量同步 A股+ETF 目录元数据到 symbols 表（供搜索/添加关注），行业指数 ETF 只是目录中极小部分。当前因 (type,name) 约束冲突（见上）1000 ETF 全部入库失败，目录同步未生效。
