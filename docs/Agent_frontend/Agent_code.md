Agent的前端编码记录,你需要按照：
编码时间：
编码内容（描述）：
的格式对该文档进行编写，要求编码内容简练而说明主要内容，
一次编写的编码内容描述在200字以内，如果超出字数而不能说明主要内容则新开一次编码记录。
每一次阶段下的细分任务都需要新开一次编码记录。

---

编码时间：2026-08-09
编码内容（描述）：1.1 工程脚手架——Vite8+Vue3+TS 工程初始化于 stock_frontend；配 @ 别名与 /api 开发代理（→8000）；路由 /login、/market、/market/detail、/ai 及登录守卫；Pinia 建 userStore/themeStore/marketStore；ESLint(flat)+Prettier。验收：typecheck/lint/build 全绿，四路由可达。

编码时间：2026-08-09
编码内容（描述）：1.2 设计体系——CSS 变量实现暗黑/明亮双主题（默认暗黑，html[data-theme] 切换），themeStore 持久化 localStorage 并在 App 启动时应用；封装 BaseButton/BaseCard/BaseInput/BaseSelect/ListRow；语义色红涨绿跌工具类与 color.ts 格式化。切换主题全局即时换色。

编码时间：2026-08-09
编码内容（描述）：1.3 API 封装层——axios 实例 baseURL=/api/v1，请求拦截注入 Bearer token，响应拦截统一 toast 错误、401 登出跳登录；api/{types,auth,market,ai}.ts 类型化接口（含标的/K线/快照/关注/会话/策略占位）。经 vite 代理实测登录后请求自动带 token。

编码时间：2026-08-09
编码内容（描述）：1.4 登录/注册页——Tab 切换表单与前端校验（用户名3-32/密码≥6/确认密码/昵称）；注册成功自动登录（后端注册即签发 JWT）；登录成功存 token 跳 /market；AppBar 顶部展示头像/昵称、主题切换、退出。注册→登录→/users/me 全流程经后端实测通过。

编码时间：2026-08-10
编码内容（描述）：2.1 KLineChart.vue 核心——封装 lightweight-charts v5（蜡烛图+成交量副图独立 pane、autoSize 自适应、CSS 变量取色随主题切换）；周期 Tab 日/周/月/15min 写 marketStore.period 联动重拉 /kline；暴露 setSRLines/refreshSRLines（内部按标的加载支撑/压力横线，刷新后仍在）；双击 emit；监听快照实时更新末根 K 线收盘。验收：四周期渲染正确、横线持久。

编码时间：2026-08-10
编码内容（描述）：2.2 BasicInfoPanel.vue（C区）渲染快照 14 项通用字段（名称/代码/现价/涨跌额/涨跌幅/昨收/今开/最高/最低/成交量/成交额/换手率/振幅/更新时间），按 type 渲染特殊字段（股票总市值+PE、ETF 溢价+净值、指数PE），红涨绿跌语义色；标的切换自动重拉、随轮询自动刷新。验收：三类标的全字段显示正确。

编码时间：2026-08-10
编码内容（描述）：2.3 IndicatorPanel.vue（B区）拉取 /indicators（macd,kdj,volume,amount）渲染四卡片+SVG 迷你图，随周期切换刷新；左上角设置键弹窗输入支撑/压力位 POST /support-resistance 联动 A 区横线（含已设列表删除）。验收：设置后 K 线出现对应横线、刷新后仍在。

编码时间：2026-08-10
编码内容（描述）：2.4 WatchlistPanel.vue（D区可复用）关注行（代码/名称/最新价/涨跌幅）行点击切 A 区标的；底部搜索栏仅 6 位代码联想（/symbols/search 防抖）选中添加；行内删除；数据入 marketStore.watchlist 供轮询与 E 区共用。验收：联想→添加→展示→删除闭环。

编码时间：2026-08-10
编码内容（描述）：2.5 实时行情刷新——useSnapshotPolling 轮询 composable（4s 拉 /snapshot，silent 失败不 toast）合并 store；MarketDetailView 组装 A/B/C/D 区，Esc/左上角返回 /market，无标的时自动兜底（关注第一项/上证指数），K 线末根实时价随快照更新。验收：页面停留价格自动刷新。typecheck/lint/build 全绿，后端 API 冒烟通过。

---

编码时间：2026-08-10
编码内容（描述）：4.1 J区会话侧边栏——SessionSidebar「策略/聊天」tab（选中项底部浅白圆角背景）；聊天页会话列表增/查/删（/conversations），策略页策略列表（点击切 N 区）；新建会话。新增 aiStore 承载会话/消息/策略/Agent/输入/流式全量状态；AIView 组装 J/M/K/L/N 布局（左侧固定侧边栏 + 右侧主区，K+L 与 N 互斥切换）。

编码时间：2026-08-10
编码内容（描述）：4.2 K区标题 + L区功能卡片——WelcomeHeader 图标 +《定制你的交易Agent》+ 小字；QuickCards 两行三列四卡片（创建交易策略第一行居中，诊断符号/交易计划/机会雷达第二行），点击写入 docs.md 4.1/4.2/4.3 prompt 模板并设 run_type（create→strategy，其余对应 diagnose/plan/radar）。

编码时间：2026-08-10
编码内容（描述）：4.3 输入区——ChatInput：标的选择行（SymbolPicker 可搜索下拉：固定指数+关注+代码/名称联想，显示名称+类型）、Agent 选择下拉（系统 Agent/定制，发送带 agent_id）、大文本输入框（Enter 发送/Shift+Enter 换行）、底部风险提示+发送。发送请求携带 symbol_id（未选/不选标的传 null）。

编码时间：2026-08-10
编码内容（描述）：4.4 流式对话 + 创建策略模块——streamChat 用 fetch 流式解析 SSE（start/delta/tool_call/done/error）；后端分片+前端累积渲染实现打字机；手写 renderMarkdown 安全子集（HTML 转义+白名单标签，无 XSS）；创建策略模块三层布局 + 入场/止损/仓位规则按钮 + 「我不选择标的」勾选，发送时拼接规则文案。

编码时间：2026-08-10
编码内容（描述）：4.5 策略联动——策略模式输出结束下方「保存交易策略/回测显示」按钮（未选标的文案「保存该交易策略到回测页面」）；保存自动调 generate 生成代码+参数再 POST /strategies 联动 M 区；回测显示跳转 /market/detail?strategy_id= 且 D 区替换 StrategyMetricsPanel（胜率/盈亏比/夏普/累计买卖/年化/最大回撤）。MarketDetailView 支持 query 参数。

编码时间：2026-08-10
编码内容（描述）：4.6 M区——策略列表（行样式同会话，点击切 N 区）+「记忆文件/我的Agent/运行记录」三个入口；MemoryFilesDialog 只读展示记忆文件（按 GET /memory/files 约定，后端缺失 404 占位）；AgentManageDialog 创建（名称/预设模板/system_prompt）+启停+删除。集成于 AIView 左侧底部。

编码时间：2026-08-10
编码内容（描述）：4.7 N区策略显示——StrategyDetailPanel 四部分居中：策略描述 / 回测结果（GET /backtest/results?strategy_id）/ 代码实现（可编辑保存 PUT /strategies/{id}）/ 回测模块（SymbolPicker 选标的+周期 → POST /backtest → 2s 轮询任务 → 完成后自动刷新结果）。返回按钮切回 K+L。

编码时间：2026-08-10
编码内容（描述）：4.8 多智能体编排显示——输入区「深度分析」开关（开启后普通输入 run_type=diagnose 走 LangGraph）；SSE delta 带 node 字段维护 streamingSteps 数组；AgentStepsPanel「查看分析过程」折叠时间线（技术分析师/多空研究员/风控/决策节点，状态+摘要展开全文）；AgentRunsDialog 运行记录按 GET /agent/runs 约定对接（后端缺失 404 占位）。typecheck/lint/build 全绿，SSE 协议经真实后端冒烟通过。

编码时间：2026-08-10
编码内容（描述）：3.1 E 区重点关注列——WatchlistPanel 增加 readonly prop（只读模式隐藏搜索栏与删除按钮，行点击仍联动 F 区）；E 区与第一层 D 区共用 marketStore.watchlist 同一数据源，两页关注数据一致。

编码时间：2026-08-10
编码内容（描述）：3.2 F 区单击 K 线图——MarketView 复用 KLineChart 绑定 marketStore.current（默认日K，随 period 切换重拉）；E/G/H 行点击切标的后自动重拉 K 线；双击 F 区进入 /market/detail，Esc/返回退出。

编码时间：2026-08-10
编码内容（描述）：3.3 G/H 区固定指数列表——新建 IndexListPanel.vue；首屏拉取 is_fixed=1 固定指数 49 条入 marketStore.fixedIndices，按 sort_order 前端分组（G 大盘 1~14 / H 行业 15~49）；每行名称/最新价/涨跌幅/关联ETF/机会指标(本版置空)；行点击联动 F 区；列表可滚动、骨架加载态。

编码时间：2026-08-10
编码内容（描述）：3.4 I 区通用设置——新建 SettingsPanel.vue：用户头像/名称（硬刷新后懒加载 /users/me）、暗黑/明亮主题切换（即时切换并 localStorage 持久化）、开发者信息「本软件由 Xhope(发誓不做夜猫子)全程开发」。

编码时间：2026-08-10
编码内容（描述）：3.5 全局布局与加载——MarketView 组装 E/F/G/H/I 网格布局（左 260px 列 + F 宽幅 + 右 280px 列）；首屏并行加载固定指数→默认标的（ensureDefaultSymbol 抽为 composable 供两层复用）→4s 轮询（快照纳入固定指数）；统一骨架/加载/空态，无白屏；typecheck/lint/build 全绿，经 vite 代理后端接口冒烟通过。

编码时间：2026-08-10
编码内容（描述）：5.1 全链路联调——双向标的联动：AI 页「回测显示」跳转第一层携带 ?symbol=code，MarketDetailView 按 query 解析并 setCurrent 保证 K 线与策略回测标的一致；行情页进 AI 页未选标时带出 market.current，SymbolPicker 选项并入当前标的；各面板三态（加载/错误/空态）与降级占位已覆盖。typecheck/lint 全绿。

编码时间：2026-08-10
编码内容（描述）：5.2 主题全面落地——KDJ K/D/J 序列色主题化：新增 CSS 变量 --ind-k/--ind-d/--ind-j，dark 用黄/蓝/紫、light 加深保证浅色可读，IndicatorPanel 迷你图与文字随主题切换；其余硬编码色均为主题无关；全局滚动条/表格/Markdown 已用 CSS 变量。切换无样式错乱。

编码时间：2026-08-10
编码内容（描述）：5.3 构建优化与监控埋点——路由懒加载基础上 manualChunks 分包（vue-vendor/charts/axios，gzip 后总约145k）；新增 utils/monitor.ts 前端监控：window error/unhandledrejection/Vue errorHandler 错误上报 + app_mount/page_load/route_change/kline_load 耗时埋点；上报 POST /api/v1/monitor/events 约定接口（后端缺失 404 降级 localStorage 队列补传），dev console 可查。build 分包生效。

编码时间：2026-08-10
编码内容（描述）：5.4 容器化与部署——多阶段 Dockerfile（node:22 构建 → nginx:1.27 托管）；nginx.conf 模板经 envsubst 注入后端地址：gzip、/assets/ 长缓存、/api 反代（proxy_buffering off 透传 SSE）、SPA try_files 回退；.dockerignore；根目录 docker-compose.yml 编排前端 8080:80，默认反代 host.docker.internal:8000。

编码时间：2026-08-10
编码内容（描述）：5.5 收尾检查——对照 working_docs.md 六要素自查：可维护（组件化/CSS变量/API层/注释）、可扩展（懒加载+组件复用）、可演进（接口版本化+占位降级）、稳定性（轮询静默/错误拦截/降级兜底）、可观测（前端监控埋点+JSON日志）、可部署（Docker+Nginx 反代）；typecheck/lint/build 全绿、docker compose build 通过；roadmap.md 已补阶段五人工配置说明。

## v0.2
编码时间：2026-08-21
编码内容（描述）：V0.2 阶段一基础层——api/market.ts 补 Snapshot.data_age_seconds、SymbolInfo.is_catalog/has_kline、WatchlistItem.sync_status/last_synced_at、SyncStatus 类型与 fetchSyncStatus()；marketStore 加 syncStatus 状态+setSyncStatus；新增 utils/tradingTime.ts（A股交易时段判断+数据新鲜度计算，纯工具无UI依赖）。typecheck 通过。

编码时间：2026-08-21
编码内容（描述）：V0.2 阶段一加载体验——MarketView 加 sync-status 查询（同步中显示 absolute 覆盖进度条+骨架屏，done后加载数据，不改网格布局）；KLineChart 切换标的不清空旧数据（无闪烁）+加载顶部细进度条+错误态重试按钮+暴露 updateLastBar；BasicInfoPanel 更新时间改用新鲜度逻辑（交易时段绿/延迟黄/非交易灰）+错误重试；WatchlistPanel/IndexListPanel 加错误态+重试。全部最小化增量改动，不改布局/路由/样式结构。

编码时间：2026-08-21
编码内容（描述）：V0.2 阶段二WS基础设施——新增 utils/wsClient.ts（单例WS客户端，指数退避重连1s→30s，ping/pong心跳30s超时，消息按type分发，断线补拉sync，BroadcastChannel多标签页单连接leader选举）；新增 stores/wsStore.ts（订阅集合管理 current+watchlist+fixedIndices去重，snapshot消息merge到marketStore，kline消息回调KLineChart.updateLastBar）；useSnapshotPolling 加WS连接检测（连上停轮询、断线自动降级轮询）；MarketView 初始化WS+订阅同步；KLineChart 注册kline回调。纯基础设施，无UI改动。浏览器实测WS连接成功、订阅49个固定指数。

编码时间：2026-08-21
编码内容（描述）：V0.2 阶段三搜索关注增强——WatchlistPanel 搜索结果按 has_kline/is_catalog 分组展示（已同步组/未同步组灰色标注"添加后同步"）；关注列表行加同步状态图标（syncing旋转loading/failed黄色感叹号点击重试/done无图标）；关注增删后自动调 wsStore.syncSubscriptions() 同步WS订阅；retrySync 重新添加幂等触发 kline_init。最小化改动，不改布局结构。typecheck 通过。

编码时间：2026-08-23
编码内容（描述）：V0.2 阶段四 4.1 SSE断线重连与断点续传——api/ai.ts 扩展 SSEEvent 类型（seq/truncated/reason/code/message/retryable/retry_after + resync/memory_saved），抽出 consumeSSEStream/guardedFetch 复用解析与 401 处理，新增 resumeChat()（GET /chat/resume?conversation_id=&last_seq=）；stores/ai.ts 新增 streamSend 编排（POST→事件分发→断线自动 resume→指数退避1s/2s/4s→>3次转 manual→resumeManual 手动续传→resync 全量重载），状态 lastSeq/streamStatus/streamConversationId/reconnectAttempt，abortStream 清理；AIView.send 改用 ai.streamSend，卸载中止流；ChatMessages 流式块下渲染「连接中断，正在重连…/点击继续」按钮。typecheck 通过，后端 SSE+resume+resync 协议经 curl 实测通过（补发/去重/404 均正确）。

编码时间：2026-08-23
编码内容（描述）：V0.2 阶段四 4.2 超时与部分结果展示——store 收到 done(truncated=true) 置 truncatedNotice；ChatMessages 流结束后显示灰色提示「分析超时，已返回部分结果」，不显示错误；首字 30s 无 delta 期间保留「AI 思考中…」loading 动画（后端 30s 首字超时/15s 单 delta/120s 总超时兜底，经 config 核对）。正常流结束部分内容照常推入消息列表。

编码时间：2026-08-23
编码内容（描述）：V0.2 阶段四 4.3 错误分级 UI——store error 事件记录 streamError{code/message/retryable/retry_after}；ChatInput RATE_LIMITED 黄条+倒计时（retry_after 默认 30s 兜底）禁用发送按钮；ChatMessages 按 code 分级渲染：TOKEN_INVALID/QUOTA 红条、CONTENT_FILTERED 灰条、NETWORK_ERROR 消息末尾「点击重试」按钮（ai.retrySend 重发 lastPayload）、PROVIDER_UNAVAILABLE 由降级横幅承载不重复提示。typecheck 通过。

编码时间：2026-08-23
编码内容（描述）：V0.2 阶段四 4.4 降级模式展示——两种降级路径前端统一用 isDegradedContent 检测「AI服务暂时不可用」前缀：① LLM 未配 key 时后端降级文案以 delta 推送（无标记），流式块/历史气泡均按前缀显示蓝色横幅；② PROVIDER_UNAVAILABLE error 帧时 store 置 degradedBanner + _reloadLastAssistantMessage 拉取后端已入库的基础分析内容展示（决策：后端 error 帧不带降级内容，前端拉取补足）。横幅文案「AI服务暂不可用，以下为基于技术指标的基础分析」，内容正常渲染 markdown。typecheck 通过。

编码时间：2026-08-23
编码内容（描述）：V0.2 阶段五 5.1 M区记忆文件面板——升级 MemoryFilesDialog.vue（复用原弹窗骨架，替代 /memory/files 只读占位）：GET /memory/facts 分页列表（page/size/importance_min）；卡片含内容摘要 2 行点击展开全文、重要性星级 1-5（高≥7 红/中≥4 黄/低灰 t-warn 自定义色）、来源标签+时间、删除按钮；顶部记忆总数+重要性筛选（全部/高≥7/中≥4/低≥1，映射 importance_min，记录 低≈全部 语义）、清空二次确认；分页上一页/下一页；删除单条 DELETE /memory/facts/{id}、清空 DELETE /memory/facts，操作后刷新+toast。api/ai.ts 新增 fetchMemoryFacts/deleteMemoryFact/clearMemoryFacts + MemoryFact/MemoryFactPage 类型。经真实后端实测：列表/importance_min 筛选/删除/清空全通过，vite 编译 200。

编码时间：2026-08-23
编码内容（描述）：V0.2 阶段五 5.2 记忆写入反馈——复用阶段四 SSE 事件框架：store _handleSSEEvent 新增 memory_saved 分支 → setMemorySaved（{summary,importance}，setTimeout 2s 自动清除，不打断对话）；ChatMessages 消息底部渲染轻量提示「已记住：{摘要}」（绿色圆点 + muted 文案），非阻塞式。SSE 事件字段 summary/importance 已入 SSEEvent 类型。typecheck 通过。（注：真实对话触发 memory_saved 需后端记忆抽取成功，本次 curl 测试中后端 aextract_facts 返回空、未见 memory_saved 事件，属后端行为观察，已在总结中记录。）

编码时间：2026-08-24
编码内容（描述）：V0.2 阶段六 6.1 深度分析进度时间线——api/ai.ts 扩展 SSEEvent 增 agent_step/usage/strategy_ready/title 事件及字段（status/duration_ms/error/strategy_id/title 等），新增 AGENT_NODE_ORDER 5 节点常量、AGENT_NODE_LABEL 中文标签、TimelineNode 类型；stores/ai.ts 新增 timeline 状态（startStreaming 初始化为 5 waiting 节点，agent_step 事件驱动 running/done/failed，delta 带 node 时累积 content 到对应节点），abortStream/resetPanel/打开会话均重置；新增 AgentTimeline.vue 横向 5 节点时间线（等待灰/运行蓝旋转/完成绿勾+耗时/失败红感叹号，节点间连线已完成变绿）；ChatMessages 气泡上方渲染。typecheck/lint/build 全绿。

编码时间：2026-08-24
编码内容（描述）：V0.2 阶段六 6.2 节点输出展开——AgentTimeline.vue 补完成节点点击展开完整输出（renderMarkdown 渲染 + 复制按钮），失败节点展开显示 error 详情 + 「该节点使用默认观点」标注；结论区在全部节点完成后显示：有失败节点时黄色「部分节点异常，结论仅供参考」，否则绿色「分析完成」；仅 done/failed 节点可点击。展开详情单节点面板（content 优先，fallback summary）。typecheck/lint/build 全绿。

编码时间：2026-08-24
编码内容（描述）：V0.2 阶段六 6.3 运行历史回看——api/ai.ts fetchAgentRuns 改为分页（返回 AgentRunPage{items,total,page,size}，新增 page/size/conversation_id 参数）、新增 fetchAgentRunSteps()、AgentRun 补 final_decision/total_duration 字段、AgentStep 补 node/status/summary/duration_ms；AgentRunsDialog.vue 重构：分页列表（行含 run_type 标签+final_decision 结论徽标+input 问题+耗时+时间+失败标记），上一页/下一页分页；点击复用 AgentTimeline 回看完整 5 节点决策链（AgentStep→TimelineNode 映射，error 取自 meta.error）。保持现有弹窗式交互不改布局。typecheck/lint/build 全绿。

编码时间：2026-08-25
编码内容（描述）：V0.2 阶段七 7.1 Token用量 + 7.2 会话标题——stores/ai.ts 新增 tokenUsage{prompt/completion/total} 会话级累计状态，_handleSSEEvent 新增 usage 事件分支（累计单轮用量）与 title 事件分支（按 conversation_id 更新 J 区列表标题，无需刷新）；createConversation/openConversation/resetPanel 重置 tokenUsage；ChatInput 底部状态栏「本次对话已用 X tokens」悬停 title 展示 prompt/completion 分项（total>0 才显示）。token 用 SSE usage 事件（后端响应头不可行，经确认），非 roadmap 原「响应头 x-token-usage」。typecheck/lint/build 全绿。

编码时间：2026-08-25
编码内容（描述）：V0.2 阶段七 7.3 策略校验状态 + 7.5 生成→回测内嵌——stores/ai.ts 新增 strategyReady（strategy_ready 事件）+ autoBacktest 四字段 + runAutoBacktest 动作（POST /backtest→2s 轮询→成功后取 fetchBacktestResults 首条）；_handleSSEEvent 新增 strategy_ready 分支（刷新 M 区策略列表 + 有标的自动回测）；StrategyOutputInfo 补 symbolId/symbolCode，AIView.send 传入。ChatMessages 策略结果区重构：流式期「正在生成策略…」→ 校验通过绿色「✓ 校验通过」+「保存策略」（updateStrategy 置 active）或失败红色「生成失败，请调整描述或使用模板」；有标的自动回测进度「回测中…」→ 内嵌结果卡片（胜率/盈亏比/最大回撤/年化 4 数字 +「查看详情」跳详情页）。修复前置 bug：startStreaming 清空 strategyOutput 导致旧策略按钮从未生效（改由 AIView.send 先 clearStrategyOutput）。方案A：无逐级重试/错误行号展示、无资金曲线缩略图（后端无该数据）。typecheck/lint/build 全绿。

编码时间：2026-08-25
编码内容（描述）：V0.2 阶段七 7.4 策略模板库——api/ai.ts 新增 StrategyTemplate 类型 + fetchStrategyTemplates()/fetchStrategyTemplate(id)；新增 StrategyTemplatesDialog.vue（5 模板卡片：名称+描述，点击详情拿完整 code → createStrategy 创建草稿 → openStrategy 打开 N 区编辑器）；ChatInput 策略模块顶部新增「从模板创建」入口按钮，弹窗渲染在输入区。参数「高亮可编辑」由 N 区现有 textarea 承载（不引入语法高亮依赖，遵循界面固定约束与避免新依赖）。typecheck/lint/build 全绿。

编码时间：2026-08-26
编码内容（描述）：审计修复 问题1（深度分析 HTTP 422）——根因是前端把 symbol 作为数字（symbol.id）发送，后端 ChatIn.symbol 为 str（Pydantic 2.13 拒绝 int→str 触发 422）；AIView.send 改为 `symbol: symbol ? String(symbol.id) : null`，与关注列表 addWatchlist 的「统一转字符串避免 422」一致。此 422 影响所有带标的的对话（非仅深度分析）。typecheck/lint/build 全绿。

编码时间：2026-08-26
编码内容（描述）：审计修复 问题5（新会话残留旧错误）——根因是 openConversation/createConversation 只重置了 messages/timeline/tokenUsage，未清 streamError 等瞬时态，上一会话的 422（NETWORK_ERROR）错误条残留到新会话。stores/ai.ts 抽 resetTransientState()（清 streamError/truncatedNotice/degradedBanner/memorySavedNotice/strategyOutput/strategyReady/autoBacktest/timeline/tokenUsage），在 openConversation/createConversation 调用，resetPanel 也复用。typecheck/lint/build 全绿。

编码时间：2026-08-26
编码内容（描述）：审计修复 问题3（运行记录点击跳转 N 区）——根因是 6.3 原实现为弹窗内联展开，与 roadmap「跳转 N 区」预期不符（且受 422 连带多数 run 无 steps）。改为：stores/ai.ts 新增 runDetail 状态 + openRunDetail()/closeRunDetail()（AgentStep→TimelineNode 映射抽为模块级 agentStepToNode，失败回退 chat）+ AiPanelMode 增 'run'；新增 AgentRunDetailPanel.vue（N 区位置展示运行元信息 + AgentTimeline 决策链）；AIView 增 run 模式渲染；AgentRunsDialog 点击改为 emit('close') + openRunDetail 跳转。typecheck/lint/build 全绿。