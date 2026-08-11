该文档中你将记录对前端系统修复的bug，格式按照：
时间：
修复bug内容（描述）：
的格式对该文档进行编写，要求编码内容简练而说明主要内容，
一次编写的编码内容描述在200字以内

---

时间：2026-08-10
修复bug内容（描述）：阶段四联调发现两个后端接口编排缺失，前端已按 roadmap 约定路径对接并做 404 占位（仅此两项处于占位态，其余 J/K/L/M/N 区、深度模式、步骤时间线均正常；后端补齐后前端自动生效，无需改动）：

1. **GET /api/v1/agent/runs（含 /api/v1/agent/runs/{id}）缺失**：roadmap 4.8.4「M 区 Agent 运行记录」要求按该接口展示多智能体运行历史与完整 agent_steps。后端当前仅有 /api/v1/agents（定制 Agent 配置 CRUD），无运行记录查询路由（agent_runs/agent_steps 表有数据但无接口）。前端 AgentRunsDialog 已按约定实现列表+详情（节点时间线），请求 404 时展示占位说明「运行记录接口后端尚未实现」。该问题为开发路线编排缺失：规划了接口但后端未实现。

2. **GET /api/v1/memory/files 缺失**：roadmap 4.6「记忆文件」按钮需展示/打开用户本地记忆文件夹，PageDesign 注明「由后端提供打开能力/返回本地路径」。后端当前仅配置 MEMORY_DIR，无返回记忆文件列表的接口。前端 MemoryFilesDialog 已按约定实现只读文件列表展示，请求 404 时展示占位说明（含记忆路径提示 data/memory/{user_id}/*.md）。同上为编排缺失：规划了能力但后端未实现。

以上两条已同步记录至 docs/Agent_backend/fixed.md，由后端在后续阶段补齐接口。

---

时间：2026-08-11
修复bug内容（描述）：行情页 G/H 区（IndexListPanel）与 D/E 区（WatchlistPanel）行此前只有单击联动 F 区 K 线，缺少双击打开第一层详情页（A/B/C/D 区）的事件，与需求「双击鼠标左键点开个股/ETF/行业指数具体K线」不符；另因固定指数无 K 线/快照数据，指数最新价、涨跌幅与行业关联 ETF 显示 "--"。已：① 两面板行增加 dblclick 事件，MarketView 接线跳转 /market/detail（单击仍联动）；② 依赖后端补齐固定指数数据（见 Agent_backend/fixed.md）。需重建前端（npm run build 或重启 dev）生效。