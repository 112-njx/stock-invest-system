# Agent 记忆文件

> 每次开启 Agent 先阅读最新记忆内容，快速重新上手。

保存时间：2026-08-25（V0.2 第三波前端阶段六+七完成时更新）
记忆内容：

1. 项目定位：量化交易软件——选股买卖决策 + DeepSeek Agent 辅助（主观交易经验转量化因子/回测），Agent 记忆本地存储。
2. 技术栈：Python(FastAPI) + PostgreSQL + Vue3(TS) + Redis + Celery + Nginx + DeepSeek + LangChain/LangGraph + ChromaDB + ONNX Runtime。
3. 硬约束：前端不计算复杂指标（后端算）；回测走 Celery 不阻塞主线程；Agent 记忆本地存储（ChromaDB + ONNX MiniLM 语义向量，hash 回退）；行情数据源走 DataProvider 抽象可插拔；缓存层仅 Redis+PostgreSQL（无内存缓存）。
4. 已注册 skill：quant-prod-arch（生产级架构六要素审查）、quant-trading-frontend（交易终端前端规范）。

5. V0.1 已全部完成（后端五阶段+前端五阶段，121 pytest 全绿），核心功能：
   - 后端：FastAPI 分层架构（api→services→repositories 单向依赖）、24表+K线按月分区（680分区子表）、DataProvider(东方财富)+新浪/同花顺降级、Celery三队列(sync/backtest/ai)、用户鉴权(bcrypt+JWT)、关注列表、支撑压力位、技术指标(MACD/KDJ/成交量/成交额，Redis缓存)、AI对话(LangChain ReAct+SSE流式)、本地记忆(ChromaDB+HashEmbedding)、策略生成(ast.parse校验)+CRUD、定制Agent、多智能体(LangGraph五节点：技术分析→多空辩论→风控→决策)、回测引擎(RestrictedPython沙箱+撮合+胜率/夏普/最大回撤)、Docker Compose全栈编排、Nginx反代+分级限流、Prometheus+Grafana监控(9面板+4告警)、CI/CD。
   - 前端：Vue3+TS+Vite+Pinia+lightweight-charts v5，行情双层页(E/F/G/H/I首页 + A/B/C/D详情)、AI策略页(J/K/L/M/N分区，借鉴QuantDinger)、暗黑/明亮双主题、7s轮询快照、SSE流式对话。
   - V0.1 已知 bug 已修复：固定指数预同步脚本(sync_fixed_indices.py)、指数快照 NOT NULL 兜底写0、AI对话降级条件误判(model is None)、行业指数关联ETF种子补齐。

6. V0.2 第一波（行情数据基础，约占总工作量40%）后端已完成（2026-08-20，全库 188 pytest 全绿 + ruff 通过），前端未完成：
   - 第一波范围（参考 docs/Agent/Reference_guide_v0.2.md）：后端阶段四→一→三→二 + 前端阶段一→二→三。
   - 后端阶段四 DataProvider 可插拔：SinaProvider/THSProvider 独立拆分、DataProviderFactory 优先级链[eastmoney,sina,ths]+每源独立熔断(半开探测)、GET /api/v1/admin/providers/health、beat provider_probe 每60s恢复探测。
   - 后端阶段一 缓存体系：sync_status 表+entrypoint 预同步(固定指数 X/49 进度)+startup 预热、K线"最近N根"Redis缓存(kline:{symbol_id}:{period}:{limit}, TTL300s)+击穿锁(SETNX)、快照14字段Redis缓存(snapshot:{symbol_id}, TTL300s)+data_age_seconds、指标缓存键含 latest_ts 自动失效。
   - 后端阶段三 目录/搜索/关注：symbols.is_catalog 字段+catalog_sync(全A股约5000+ETF, 每日3:00, partial失败1h重试)+POST /admin/catalog/sync 手动触发、搜索三层(精确>已同步>仅目录)+外部回退+search:* 缓存(1h)+is_catalog/has_kline 返回、关注添加自动触发 kline_init+sync_status(pending/syncing/done/failed)、watchlist/watchlist_snap Redis 缓存。
   - 后端阶段二 WebSocket：/api/v1/ws/market(query token 鉴权)、ConnectionManager 多标签页共享、心跳15s ping/30s超时断连、订阅模型、realtime_poll 经 Redis pub/sub 桥接推送增量快照、sync 断线补拉(按 since 时间戳)。
   - 第一波前端（2026-08-21 完成）：前端阶段一(加载体验)+阶段二(WS基础设施)+阶段三(搜索关注)全部完成。
     - 阶段一：sync-status 轮询进度条(absolute覆盖层不改布局)、K线切换无闪烁(保留旧数据+顶部细进度条)、统一三态(加载/错误重试/空态)、数据新鲜度标注(utils/tradingTime.ts，交易时段绿/延迟黄/非交易灰)。
     - 阶段二：utils/wsClient.ts(单例WS+指数退避重连+心跳+断线补拉+BroadcastChannel多标签页leader选举)、stores/wsStore.ts(订阅集合管理+snapshot merge到marketStore+kline回调)、useSnapshotPolling 加WS连接检测(连上停轮询/断线降级)。浏览器实测WS连接成功订阅49个固定指数。
     - 阶段三：WatchlistPanel 搜索结果按 has_kline/is_catalog 分组(已同步/未同步灰色标注)、关注行同步状态图标(syncing旋转/failed黄色感叹号点击重试)、关注增删自动调 wsStore.syncSubscriptions()。
     - 全部最小化增量改动，不改布局/路由/样式结构；typecheck 全绿。
   - Alembic 0004 迁移：users.is_admin、sync_status 表、symbols.is_catalog、user_watchlist.sync_status。
   - 需人工配置：ADMIN_USERNAMES（管理端点访问权限）。
   - 2026-08-21 补齐 sync-status 查询端点：新增 GET /api/v1/sync-status?scope=fixed_indices（market.py，公开），返回 {status/progress/total/message}，供行情页轮询"数据同步中（X/49）"；ops_repo.get_latest_sync_status。全库 190 pytest 全绿。
   - 注意：K线 ts/快照 updated_at 列为 timestamp without time zone（DB naive，代码内 as_utc 归一）。

7. 开发环境：
   - Python 3.14（D:\Pycharm\python），venv 在 stock_backend/.venv
   - PostgreSQL 本机 5432（postgres/123456，库 stock_invest）
   - Redis Docker 容器 stock-redis（redis:7-alpine，端口 6379，需先启动 Docker Desktop）
   - 前端：stock_frontend，npm run dev（端口 5173），vite 代理 /api 到后端 8000
   - 启动后端：cd stock_backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   - 启动 Celery worker：.venv/Scripts/celery.exe -A app.worker.celery worker --pool=solo -l info
   - 启动 Celery beat：.venv/Scripts/celery.exe -A app.worker.celery beat -l info
   - 跑测试：.venv/Scripts/python.exe -m pytest tests/ -v

8. 参考开源项目（须借鉴避免造轮子）：
   - TradingAgents-CN：C:\Users\112\Desktop\TradingAgents-CN-main\TradingAgents-CN-main（MongoDB+Redis 双层缓存、数据源优先级链、全量标的预同步、新鲜度容错匹配）
   - QuantDinger：C:\Users\112\Desktop\QuantDinger-main\QuantDinger-main（内存LRU+Redis可选+PG 三层缓存、全量目录搜索+别名表、关注列表验证+名称解析、AI策略页 J/K/L/M/N 分区）

9. 关键文档索引：
   - 需求：docs/project_docs/docs.md
   - 架构：docs/project_docs/working_docs.md（生产级六要素）
   - 后端规划：docs/Agent_backend/roadmap.md（V0.1 五阶段 + V0.2 八阶段）
   - 前端规划：docs/Agent_frontend/roadmap.md（V0.1 五阶段 + V0.2 七阶段）
   - API 文档：docs/Agent_backend/api-docs.md
   - 编码记录：docs/Agent_backend/Agent_code.md、docs/Agent_frontend/Agent_code.md
   - 修复记录：docs/Agent_backend/fixed.md、docs/Agent_frontend/fixed.md
   - 数据库：docs/sql/（01_schema.sql 建表、02_seed_fixed_indices.sql 固定指数种子、03_agent_extensions.sql Agent 扩展表）
   - 增强提示词：docs/Agent/enhanced_prompt.md（V0.2 开发用，强制设计验证→编码→自我审查→测试→报告流程）

10. V0.2 后续规划（共4波，拓扑依赖见 docs/Agent/Reference_guide_v0.2.md）：
    - 第一波（行情数据基础，40%）：后端阶段四/一/三/二已完成；前端阶段一(加载体验)/二(WS)/三(搜索关注)待开发。
    - 第二波（AI基础加固，25%）：后端阶段五(AI流式稳定性：SSE心跳/超时/错误帧/分级降级)→前端阶段四(AI流式体验)；后端阶段六(记忆系统升级：HashEmbedding→ONNX MiniLM int8量化、分层+重要性评分、去重合并、记忆管理API)→前端阶段五(记忆可视化)。
    - 第三波（AI高级功能，25%）：后端阶段七(多智能体：LangGraph+agent_step SSE+运行历史API)→前端阶段六(多智能体可视化)；后端阶段八(长会话+策略生成：滑动窗口摘要、Token预算、三级校验+重试+模板库+一键回测、标题自动生成)→前端阶段七(长会话+策略生成体验)。
    - 第四波（全链路联调，10%）：全链路联调、边界场景、性能优化、部署验证、收尾检查。
    - 后端能力对接清单（前端开发参考）见 docs/Agent/project_constraints.md 第四章。

11. V0.2 第二波后端（AI基础加固）已完成（2026-08-22，全库 223 pytest 全绿 + ruff 通过），前端阶段四/五未开发：
   - 阶段五（AI流式稳定性）：SSE 心跳 keepalive（每15s `:keepalive`，防 Nginx 断连）+ 三级超时（首字30s/单delta 15s/总120s，超时返已生成内容+`done(truncated=true)`）；delta 递增 seq + Redis 缓存最近100条（`chat_delta:{conv}` TTL600s）+ `GET /api/v1/chat/resume` 断点续传（缓存过期返 `resync`）；错误帧标准化（`ErrorCode` 枚举 + `classify_llm_error` 异常分类 + 不可重试不空转）；错误分级降级（熔断→「已切换基础分析模式」+ MACD/KDJ 规则文案、token 无效→明确提示、工具失败→标注基于历史数据）。
   - 阶段六（记忆系统 int8 量化）：Embedding 升级为 ONNX MiniLM 语义向量（`paraphrase-multilingual-MiniLM-L12-v2` int8，384维，urllib 自动下载到 data/models，加载失败回退 hash）；ChromaDB collection 按 embedding 类型隔离 + `scripts/rebuild_embeddings.py` 重建脚本；memory_chunks.importance（Alembic 0005）+ 检索加权（相似度×0.7+重要性×0.3）+ 低重要性<3 且>30天每日清理（Celery beat 4:00）；记忆去重合并（余弦>0.85 合并，importance 取最大）；记忆管理 API（GET/DELETE /memory/facts + 清空）+ `memory_saved` SSE 事件。
   - 需人工配置：`EMBEDDING_MODEL=minilm`（默认）+ 首次联网下载模型（~118MB）+ 切换后跑 rebuild_embeddings.py（见 roadmap.md 阶段六说明）。
   - 关键决策：roadmap 6.1 原 all-MiniLM-L6-v2 为英文模型中文语义失效（实测相似度全 0.85~1.0），经确认改用多语言 MiniLM-L12（384维、中文语义、118MB，放宽≤50MB 验收为≤120MB）。

12. 当前状态：V0.2 第一波/第二波/第三波均已全部完成（后端阶段四~八 + 前端阶段一~七）。第四波（全链路联调打磨）待开发。下一波开发前必须阅读 docs/Agent/enhanced_prompt.md（强制流程）+ docs/Agent/Reference_guide_v0.2.md（波次拓扑）+ docs/Agent/project_constraints_v0.2.md（遗留问题+对接清单）。

13. V0.2 第二波前端（AI基础加固）已完成（2026-08-23，typecheck/lint/build 全绿），前端阶段四+五：
   - 前端阶段四（AI流式稳定性）：
     - 4.1 SSE断点续传：api/ai.ts 扩展 SSEEvent 类型（seq/truncated/code/retry_after/resync/memory_saved），抽出 consumeSSEStream/guardedFetch；新增 resumeChat()（GET /chat/resume）；aiStore 新增 streamSend 编排（POST→事件分发→断线自动 resume→指数退避 1s/2s/4s→>3次转 manual→resumeManual 手动续传→resync 全量重载），状态 lastSeq/streamStatus/streamError/reconnectAttempt。
     - 4.2 超时部分结果：done(truncated=true) 灰色提示「分析超时，已返回部分结果」；首字 30s loading「AI 思考中…」。
     - 4.3 错误分级：RATE_LIMITED 黄条+倒计时（retry_after 默认30s）禁用发送；TOKEN_INVALID/QUOTA 红条；CONTENT_FILTERED 灰条；NETWORK_ERROR 消息末尾「点击重试」（ai.retrySend 重发 lastPayload）；PROVIDER_UNAVAILABLE 降级横幅承载。
     - 4.4 降级横幅：isDegradedContent 检测「AI服务暂时不可用」前缀（未配 key 的 delta 文案 + PROVIDER_UNAVAILABLE error 帧后拉取入库内容两种路径统一）。
   - 前端阶段五（记忆可视化）：
     - 5.1 M区记忆面板：升级 MemoryFilesDialog.vue（复用弹窗骨架替代 /memory/files 占位）→ GET /memory/facts 分页+重要性星级（高红/中黄/低灰）+筛选（全部/高≥7/中≥4/低）+删除/清空二次确认；api/ai.ts 新增 fetchMemoryFacts/deleteMemoryFact/clearMemoryFacts。
     - 5.2 记忆写入反馈：SSE memory_saved →「已记住：{摘要}」轻量提示 2s 自动消失。
   - 关键决策记录：后端 PROVIDER_UNAVAILABLE 的 error 帧不含降级内容（只入库），前端 _reloadLastAssistantMessage 拉取补足（非阻塞，前端方案）。
   - 后端行为观察（非前端问题，供后端参考）：真实对话触发记忆抽取时，aextract_facts 返回空、未见 memory_saved 事件（可能抽取 LLM 调用失败/importance<5 过滤），5.2 的 memory_saved 展示逻辑已就绪但端到端待后端抽取正常后复验。

14. V0.2 第三波后端（AI高级功能）已完成（2026-08-23，全库 250 pytest 全绿 + ruff，前端阶段六/七未开发）：
    - 阶段七（多智能体可观测性）：Alembic 0006 agent_steps 加 summary/duration_ms/status、agent_runs 加 duration_ms；research_graph 逐节点 SSE 推送 agent_step（running/done/failed 含 summary+耗时），节点 try/except 失败降级（默认中性观点 + 结论标注"部分节点异常" + run.error 标记）；运行历史 GET /agent/runs（分页+conversation_id 筛选+final_decision/total_duration 别名）、GET /agent/runs/{id}/steps。
    - 阶段八（长会话+策略生成）：Alembic 0007 conversations.summary；8.1 滑动窗口（最近10轮完整+早期摘要替代，每满10轮异步生成≤200字摘要）；8.2 token 预算（字符启发式估算，超80%自动降轮 20→16→12，SSE push usage 事件）；8.3 策略三级校验（语法/接口/沙箱 dry-run 含异常行号）；8.4 生成失败自动重试（拼错误重生成，最多2次，耗尽抛模板库提示）；8.5 策略模板库（strategy_templates 表+5模板幂等种子，GET 列表/详情）；8.6 生成→回测（run_type=strategy 分支生成+保存+push strategy_ready）；8.7 会话标题自动生成（首条消息异步生成≤15字 title + SSE push title 事件）。
    - 关键决策/修复：① SSE 场景 token 用量用 usage 事件（响应头不可行，经确认）；② run_type=strategy 新增 chat 内深度分支（经确认）；③ roadmap 8.3 的 on_bar 签名"(ctx,bar)"与引擎实际(bar,context)不符，按引擎位置调用只校验参数个数=2；④ RestrictedPython 拒绝 `_` 前缀函数名，模板 helper 改 ema/rsv；⑤ 修复 astream_events 高负载下 on_chain_end 乱序致 agent_steps 逆序落库，改回 astream(stream_mode="updates") 确定性产出。
    - 需人工配置：LLM_MAX_TOKENS/TOKEN_BUDGET_RATIO/STRATEGY_GEN_MAX_RETRIES/TITLE_WAIT_TIMEOUT（均有默认值，见 roadmap.md 第三波说明）。
    - 后续：前端阶段六（多智能体可视化）+ 阶段七（长会话+策略生成体验）待开发，后端能力对接见 api-docs.md（agent_step/usage/strategy_ready/title 事件 + agent/runs + strategy-templates 端点）。

15. V0.2 第三波前端（AI高级功能）已完成（2026-08-25，typecheck/lint/build 全绿），阶段六 + 阶段七：
    - 阶段六（多智能体可视化）：
      - 6.1 深度分析时间线：api/ai.ts 扩展 SSEEvent（agent_step/usage/strategy_ready/title）+ AGENT_NODE_ORDER/LABEL/TimelineNode 类型；stores/ai.ts 新增 timeline 状态（agent_step 事件驱动 running/done/failed，delta 带 node 累积 content）；新增 AgentTimeline.vue 横向 5 节点时间线（等待灰/运行蓝旋转/完成绿勾+耗时/失败红感叹号，连线已完成变绿）；ChatMessages 气泡上方渲染。
      - 6.2 节点输出展开：完成节点点击展开完整输出（markdown+复制）、失败节点显示 error+「该节点使用默认观点」、结论区全部完成后显示（有失败节点黄色「部分节点异常，结论仅供参考」）。
      - 6.3 运行历史回看：fetchAgentRuns 改分页 AgentRunPage + 新增 fetchAgentRunSteps；AgentRunsDialog 重构（分页列表含 final_decision 结论/耗时/时间，点击复用 AgentTimeline 回看决策链）。保持弹窗式不改布局。
    - 阶段七（长会话+策略生成体验）：
      - 7.1 Token 用量：SSE usage 事件累计到 store.tokenUsage，ChatInput 底部「本次对话已用 X tokens」悬停看 prompt/completion 分项（后端响应头不可行，经确认用 usage 事件）。
      - 7.2 会话标题：SSE title 事件按 conversation_id 更新 J 区列表标题，无需刷新。
      - 7.3 策略校验状态 + 7.5 生成→回测内嵌：strategy_ready 事件 → strategyReady 状态 + 刷新 M 区 + 有标的自动回测（runAutoBacktest：POST /backtest→2s 轮询→取结果）；ChatMessages 策略结果区「生成中→校验通过/失败」+ 内嵌回测结果卡片（胜率/盈亏比/最大回撤/年化 4 数字 + 查看详情）。
      - 7.4 策略模板库：fetchStrategyTemplates/Template + StrategyTemplatesDialog（5 模板卡片，点击创建草稿→打开 N 区编辑器）；ChatInput 策略模块新增「从模板创建」入口。
    - 关键决策/修复：① 修复前置 bug——startStreaming 清空 strategyOutput 导致旧策略按钮从未生效（改为 AIView.send 先 clearStrategyOutput）；② 方案A降级——策略校验无逐级重试/错误行号展示（后端单次非流式调用）、无资金曲线缩略图（后端不返回 equity_curve）；③ 运行记录保持弹窗式、标的名称后端仅返回 symbol_id 前端以 input 文本承载；④ 回测区间用后端默认（未传 start/end，非 roadmap「近1年」，与现有 N 区回测一致）。
    - 遗留待确认：MStrategyPanel.vue 为第二波遗留死文件（已由 SessionSidebar 取代），本轮未删；api/ai.ts 的 generateStrategy()（POST /strategies/generate）本轮起无调用方（策略生成已并入 chat SSE），保留未删。
    - 第四波（全链路联调打磨）为下一波。

16. Docker 一键启动落地 + V0.2 行情系统性 bug 修复（2026-09-04，详见 docs/Agent_main_v0.1/deploy_fixed.md 问题三落地报告）：
    - 启动编排单点化：deploy/docker-compose.dev.yml 抽 x-backend-env 公共锚点，仅 api 置 RUN_MIGRATIONS=1 单点执行 alembic upgrade + seed_fixed_indices + presync；新增 stock_backend/scripts/wait_for_migrations.py，worker/beat 的 docker-entrypoint.sh 轮询等 alembic_version=head(0008) 再启动主进程，消除三容器并发建表撞 pg_type_typname_nsp_index 唯一约束、presync 重复出两个 task_id。
    - 多源 Provider 适配 akshare 1.18.83：eastmoney._fetch_min_kline 行业分支移除 stock_board_industry_hist_min_em 不支持的 start_date/end_date（该接口仅收 symbol/period，取近期全量后按 start<=ts<=end 过滤）；sina 日K日期列改 _pick_col 兼容 date/日期、缺列优雅返回空，不再 KeyError；ths.fetch_kline 调用前新增 _resolve_board_name（复用 _industry_score 模糊匹配，半导体设备→半导体，无匹配返回空），规避 akshare 内部 code_map[symbol] KeyError。
    - 种子引导：新增 deploy/seed_from_local.py——宿主 psycopg2 读本机 PG18、经 docker exec -i psql 写容器 PG16（绕开 pg_dump 18→16 版本差）；自动等迁移、users 非空则跳过（幂等，--force 覆盖）、导入前 docker stop worker/beat 防并发写、导完 DO 块 setval 对齐全部自增序列、finally 恢复；start-dev.bat 增 [4/4] 自动调用（保持原 UTF-8/CRLF，仅插入纯 ASCII 行）。实测导入 362 张表（users=13/symbols=52/快照44/K线齐全），root 登录与行情页打开即有数据，6 容器 RestartCount=0。
    - 关键坑：① COPY 显式 id 后必须 setval 序列到 max(id)，否则 worker 插 task_logs/sync_tasks 撞主键（已在脚本内自动对齐）；② 容器 db 用独立卷 stock-invest-dev_pgdata、不映射宿主 5432，与本机原生库天然隔离；③ 东财 RemoteDisconnected 属外部限流/反爬，非改代码可根治，靠多源降级+降频；④ start-dev.bat 历史中文在转码中损坏成 U+FFFD，只可插入 ASCII 行、勿整体改编码（首行用户注明勿改编码）；⑤ /api/v1/snapshot 的 symbols 参数传 symbol_id（数字）非 code。
