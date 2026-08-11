前端实施规划
在实施规划后方提前写出前端软件vibe coding后需要人配置的地方或日志文件说明，要求遵循简洁的原则，一条一句话总结即可
并且每一条都必须是需要手动配置或观看系统运行的。

---

## 前端开发实施方案（项目启动 → 第一版发布）

> 目标：专业交易终端风格 Vue3 前端，实现「行情双层页 + AI 策略页」；复杂指标一律后端算、前端只渲染。
> 约束：默认暗黑设计；双层页共用同一套 K 线组件；AI 策略页 J/K/L/M/N 分区架构完全借鉴 QuantDinger。
> 页面设计详见 docs/Agent_frontend/PageDesign.md（每区功能/数据源/交互）。

### 阶段一：工程与基础框架

**1.1 工程脚手架**
- 用 Vite 初始化 Vue3 + TS 工程，目录：`src/{views,components,api,stores,router,utils,assets}`。
- 路由：`/login`、`/market`（第二层）、`/market/detail`（第一层）、`/ai`。
- Pinia 全局状态：`userStore`/`themeStore`/`marketStore`；配 ESLint + Prettier。
- 验收：`npm run dev` 启动、四路由可达。

**1.2 设计体系（交易终端风格）**
- 用 CSS 变量实现暗黑/明亮主题（默认暗黑），`themeStore` 切换并持久化 localStorage。
- 封装通用组件：BaseButton/BaseCard/BaseInput/BaseSelect/ListRow；定义语义色（红涨绿跌）。
- 验收：切换主题后所有组件即时换色。

**1.3 API 封装层**
- axios 实例（baseURL `/api/v1`），请求拦截注入 token，响应拦截统一错误处理（toast）与 401 跳登录。
- 按业务拆模块：`api/{auth,market,ai}.ts`，类型化接口。
- 验收：登录后请求自动带 token。

**1.4 登录/注册页**
- 登录/注册 Tab 表单；注册成功自动登录；登录成功存 token 跳 `/market`。
- 顶部展示用户头像/昵称（登录后）。
- 验收：注册→登录→进入行情页全流程。

### 阶段二：行情双层页第一层（双击进入 A/B/C/D 区）

**2.1 K 线图组件 `KLineChart.vue`（核心）**
- 用 lightweight-charts 封装：蜡烛图 + 成交量副图 + 指标叠加区（预留）。
- 周期切换 Tab：日K/周K/月K/15min，切换后重拉 `GET /api/v1/kline`。
- 交互：双击进入 `/market/detail`，Esc + 左上角按钮退出返回 `/market`。
- 支撑/压力横线：`setSRLines(prices)` 供 B 区调用。
- 验收：四周期切换渲染正确、双击/Esc 进出正常。

**2.2 C 区基本数据 `BasicInfoPanel.vue`**
- 渲染通用字段：名称/代码/现价/涨跌额/涨跌幅/昨收/今开/最高/最低/成交量/成交额/换手率/振幅/更新时间。
- 按标的 `type` 渲染特殊字段：股票(总市值/PE)、ETF(溢价)、指数(总PE)。
- 数据：`GET /api/v1/snapshot?symbols=`。
- 验收：三类标的全字段显示正确。

**2.3 B 区技术指标 `IndicatorPanel.vue`**
- 渲染后端返回的成交量/成交额/MACD/KDJ，随周期切换刷新（`GET /api/v1/indicators`）。
- 左上角设置键 → 弹窗输入支撑位/压力位 → `POST /api/v1/support-resistance` → 调 `KLineChart.setSRLines`。
- 验收：设置后 K 线出现对应横线、刷新后仍在。

**2.4 D 区重点关注列表 `WatchlistPanel.vue`（可复用）**
- 列表行：代码/名称/最新价/涨跌幅（红涨绿跌）；行点击切换 K 线标的。
- 底部搜索栏：输入 6 位代码实时联想（`GET /api/v1/symbols/search`），选中添加。
- 行内删除按钮 → `DELETE /api/v1/watchlist`。
- 验收：联想→添加→展示→删除闭环。

**2.5 实时行情刷新**
- 前台轮询 `GET /api/v1/snapshot?symbols=`（3~5s）或 WebSocket，更新 D 区与 K 线最新价。
- 涨跌颜色规则统一（涨红/跌绿/平灰）。
- 验收：页面停留时价格自动刷新。

### 阶段三：行情第二层页面（默认首页 E/F/G/H/I 区）

**3.1 E 区重点关注列**
- 复用 `WatchlistPanel`（只读行 + 点击联动 F 区）；与第一层 D 区共用同一 store 数据源。
- 验收：两页关注数据一致。

**3.2 F 区单击 K 线图**
- 复用 `KLineChart`，默认展示当前选中标的日K。
- E/G/H 行点击 → `marketStore` 切标的 → F 区重拉 K 线。
- 验收：点击联动切换。

**3.3 G/H 区固定指数列表 `IndexListPanel.vue`**
- G 区大盘指数 14 项、H 区行业指数 35 项，固定顺序（后端 `is_fixed` + `sort_order` 返回，前端分组）。
- 每行：名称/最新价/涨跌幅/关联ETF/机会指标（本版置空）。
- 列表可滚动；行点击联动 F 区。
- 验收：两区顺序与种子数据一致。

**3.4 I 区通用设置**
- 用户头像/名称、主题切换开关、开发者信息「本软件由 Xhope(发誓不做夜猫子)全程开发」。
- 验收：主题即时切换且持久化。

**3.5 全局布局与加载**
- `/market` 首屏并行加载：固定指数列表、关注列表、默认标的 K 线。
- 统一加载态（骨架/loading）、错误态、空态。
- 验收：打开页面即有数据、无白屏。

### 阶段四：AI 策略页（J/K/L/M/N 区）

**4.1 J 区会话侧边栏**
- 顶部「策略/聊天」切换标识，当前页标识底部浅白色圆角背景。
- 聊天页：历史会话列表（`GET /api/v1/conversations`）、新建会话、点击加载消息。
- 策略页：交易策略列表（切换 J 区视图为策略列表）。
- 验收：切换选中态正确、会话增查正常。

**4.2 K 区 + L 区功能卡片**
- K 区：图标 + 主标题《定制你的交易Agent》+ 小字「询问市场情况，解释日志，定制策略，永久记忆」。
- L 区卡片两行三列：第一行正中间「创建交易策略」（小字：描述一个入场想法，AI 会补齐规则和风控）；第二行「诊断符号/交易计划/机会雷达」（小字对应 docs.md）。
- 点击卡片 → 将对应 prompt 模板（docs.md 4.1/4.2/4.3）写入输入框；「创建交易策略」额外插入策略模块。
- 验收：四卡片 prompt 正确注入。

**4.3 输入区（标的选择行 + 文本输入 + 底部操作栏）**
- 标的选择行：「选择要分析的标的」+ 下拉框（名称 + 类型：股票/指数/ETF）。
- 可选「使用哪个 Agent」：默认系统 Agent，已定制则列出 `user_agents` 供选择（发送请求带 agent_id）。
- 大文本输入框，placeholder 示例「例如：帮我分析一小时内上证指数的趋势……」。
- 底部：左侧风险提示「风险提示：AI 输出仅用于研究参考，不构成投资建议。决策前请自行核对数据、风险和仓位。」右侧「发送」。
- 验收：发送请求携带所选 symbol_id。

**4.4 流式对话 + 创建交易策略模块**
- 用 SSE 流式渲染后端（LangChain Agent）输出（markdown），打字机效果。
- 创建交易策略模块（插入标的选择行下方）：三层布局——标题「你希望策略怎么交易？」+ 标签「可直接发送」+ 说明「不需要写代码。可以直接发送，也可以点选你最关心的规则。」+ 按钮「+ 入场规则 / + 止损止盈 / + 仓位管理」+ 一行「我不选择标的，我思考的是通用的交易体系」。
- 按钮点击 → prompt 追加对应规则文案（docs.md 4 小节）；勾选「不选择标的」则提示后端返回后追加「保存该交易策略到回测页面」。
- 验收：流式显示、按钮可追加规则、不选标的逻辑生效。

**4.5 策略联动（保存/回测）**
- 创建策略场景 AI 输出结束后，输出下方显示「保存交易策略」「回测显示」按钮。
- 保存 → `POST /api/v1/strategies` → M 区列表刷新。
- 回测显示 → 跳转 `/market/detail`，且 D 区替换为 `StrategyMetricsPanel`（胜率/盈亏比/夏普/累计买入/累计卖出/年化收益率/最大回撤，`GET /api/v1/backtest/results?strategy=`）。
- 验收：保存联动 M 区、回测跳转 + D 区换面板。

**4.6 M 区交易策略 + 记忆文件 + 我的 Agent**
- 交易策略列表（行样式同会话）；点击某策略 → K+L 区切换为 N 区。
- 「记忆文件」按钮 → 调用后端打开本地记忆文件夹/向量库目录（LangChain 记忆）。
- 「我的 Agent」入口（M 区底部或 J 区）：列表 `GET /api/v1/agents`，创建/配置弹窗（名称/system_prompt/启用工具/LLM 模型），可启停；UI 保持轻量。
- 验收：列表来自 `GET /api/v1/strategies`；可创建并选用定制 Agent。

**4.7 N 区交易策略显示**
- 四部分居中：策略描述 / 回测结果（已保存）/ 代码实现（展示 + 可编辑保存）/ 回测模块（选标的 → 发起回测 → 保存结果）。
- 验收：可编辑代码并保存、可发起回测并轮询到结果。

**4.8：多智能体编排功能显示**
- 4.8.1 深度模式触发
L 区四个功能卡片旁增加"深度分析"图标按钮（或输入区增加模式切换）。 
点击后请求后端 POST /api/v1/agent/graph/run（或现有 chat 接口增加 mode=deep 参数），走 LangGraph 分支。
- 4.8.2 流式输出适配
SSE 流中除了最终 markdown 结论，还透传 agent_step 事件（节点名 + 节点输出摘要）。
前端维护一个 steps 数组，实时渲染步骤进度条/时间线。
- 4.8.3 步骤展开面板（N 区或对话区嵌入）
在 AI 回复气泡下方增加"查看分析过程"折叠面板。
面板内用时间线/树状图展示各智能体节点输出：
节点名称（技术分析师 / 多头 / 空头 / 风控 / 决策）
节点状态（运行中 / 完成 / 错误）
节点输出摘要（可点击展开全文）
- 4.8.4 Agent 运行历史（M 区新增）
M 区增加"运行记录"标签页。
列表展示 GET /api/v1/agent/runs 数据。
点击单条记录可查看完整的 agent_steps 和各节点原始输出。

### 阶段五：联调、打磨与部署

**5.1 全链路联调**
- 行情页 ↔ AI 策略页数据流打通（标的联动、策略↔回测↔全景K线）。
- 补齐加载/错误/空态三态与边界场景。
- 验收：主流程手工走通。

**5.2 主题全面落地**
- 暗黑/明亮全局一致，检查图表/表格/滚动条等细节。
- 验收：切换无样式错乱。

**5.3 构建优化与监控埋点**
- 路由懒加载（code splitting）、静态资源压缩。
- 前端监控：错误上报 + 页面/K 线加载耗时埋点。
- 验收：构建产物优化、监控有数据。

**5.4 容器化与部署**
- 多阶段 Dockerfile（node 构建 → nginx），Nginx 托管静态 + 反向代理 `/api`。
- 验收：镜像启动经 Nginx 可访问。

**5.5 收尾检查**
- 对照 working_docs.md 六要素逐项自查（可维护/扩展/演进/稳定/可观测/可部署）。
- 验收：每项有结论并补全前端开发收尾记录（docs/Agent_frontend/Agent_code.md）。

---

## 需要人工配置的地方 / 日志文件说明

### 阶段一（1.1~1.4）
- 启动后端：`cd stock_backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（需 PostgreSQL 本机 5432 与 Docker Redis stock-redis 已运行）。
- 启动前端：`cd stock_frontend && npm install && npm run dev`，浏览器访问 http://localhost:5173；开发环境 `/api` 由 vite 代理到后端 8000。
- 登录/注册为普通用户流程，无手动配置项；新用户注册后即自动登录。

### 阶段二（2.1~2.5）
- 访问 http://localhost:5173/market/detail 直接查看第一层 A/B/C/D 区；无当前标时自动选中关注第一项或固定指数第一项（上证指数）。
- 实时价刷新依赖后端 Celery 行情同步（realtime_poll/kline_init）已入库，前端 7s 轮询 /api/v1/snapshot；未同步标的现价/涨跌幅显示 --。
- 技术指标、支撑/压力位、关注列表均需登录（JWT）；Redis 未启动时指标缓存自动降级直查库，K 线不受影响。
- 页面调试看浏览器 F12 Console/Network（轮询失败静默不弹 toast）；后端 JSON 日志输出到 uvicorn 控制台 stdout。

### 阶段四（4.1~4.8）
- 访问 http://localhost:5173/ai 进入 AI 策略页（需登录）；SSE 流式对话经 vite 代理到后端 8000，F12 Network 可见 data: JSON 帧（start/delta/done）。
- 4.6 记忆文件（GET /api/v1/memory/files）、4.8.4 运行记录（GET /api/v1/agent/runs）两个后端接口暂未实现，前端已按约定对接并做 404 占位；需后端补齐后自动生效（详见 docs 两个 fixed.md）。
- AI 流式对话、深度分析、策略代码生成依赖后端 DeepSeek API Key（stock_backend/.env 配 DEEPSEEK_API_KEY）；未配置时后端返回降级文案，前端打字机照常渲染。
- 回测显示跳转第一层需策略已有回测结果：先启动 Celery backtest worker 并发起回测（后端阶段四冒烟已跑通）。

### 阶段三（3.1~3.5）
- 访问 http://localhost:5173 默认首页即行情第二层 E/F/G/H/I 区；E/G/H 行点击联动 F 区，双击 F 区 K 线进入第一层详情页（Esc/返回退出）。
- 关注增删仍在第一层 D 区操作，第二层 E 区只读展示、与 D 区共用同一 store 数据源；两页关注数据一致。
- 固定指数列表为后端 is_fixed=1 的 49 条（G 大盘 14 + H 行业 35），前端按 sort_order 分组，顺序与种子数据一致；指数现价依赖 Celery 同步已入库，未同步显示 --。
- 页面调试看浏览器 F12 Console/Network（轮询失败静默不弹 toast）；后端 JSON 日志输出到 uvicorn 控制台 stdout。

### 阶段五（5.1~5.5）
- Docker 部署：需本机 Docker Desktop 已启动；后端 FastAPI 在本机 8000 运行（或把 docker-compose.yml 的 NGINX_PROXY_PASS 改为后端容器服务名）；
- 执行 `cd stock-invest-system && docker compose up -d --build`，访问 http://localhost:8080（Nginx 托管静态 + 反代 /api）。
- Docker 构建需拉取 node:22-alpine / nginx:1.27-alpine（docker.io）；国内网络无法直连 Docker Hub 时，需在 Docker Desktop Settings→Docker Engine 
- 配置镜像加速器（如 https://docker.m.daocloud.io 等）并重启 Docker Desktop，再执行 `docker compose build`（镜像已由 docker compose config 语法校验通过，网络就绪即可构建）。
- 5.3 监控埋点无需人工配置；数据查看：dev 模式浏览器 F12 Console 输出 `[monitor]` 摘要、localStorage key `stock_invest_monitor` 存队列；
- 上报 POST /api/v1/monitor/events 后端尚未实现，404 静默降级本地收集，后端补齐后自动补传。
- 5.1 双向标的联动：AI 页「回测显示」跳转第一层自动携带策略回测标的（?symbol=code）切换 K 线；从行情页进入 AI 页自动带出当前标的到「选择要分析的标的」，无需人工配置。
