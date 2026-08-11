# 后端修复记录

> 记录开发过程中发现并修复的问题（含测试数据事故），方便回溯。

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

**待办**：由后端在后续阶段补齐上述两个只读接口。
