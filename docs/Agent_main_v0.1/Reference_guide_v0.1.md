# 后端开发规划细化（阶段二 ~ 阶段五）

> 对照开源项目：TradingAgents-CN（多智能体 LangChain 框架）、QuantDinger（生产级量化平台）
> 目的：在原有 roadmap 基础上，明确每个任务点可能借鉴的开源实现，减少造轮子
> 原则：你并非必须借鉴开源项目，而是尽量借鉴他们解决的开发生产级问题的方法，如果其实现的功能特别类似但并不完全相同，可以在需求文档的基础上小幅扩展功能，但是最终还是需要符合需求文档中的需求。
---

## 阶段二：用户域与技术指标服务

### 2.1 用户鉴权

**原规划**：
- `POST /api/v1/auth/register`、`POST /api/v1/auth/login`（密码 bcrypt 哈希 → JWT）
- 当前用户依赖注入（`Depends(get_current_user)`）；`PUT /api/v1/users/me` 更新昵称/头像

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **多租户隔离设计** | QuantDinger | QuantDinger 的 Agent Gateway 用 `tenant_id` 做数据隔离，你的 `user_id` 隔离可以参考同样的模式——所有查询强制带 user_id 过滤，防止越权 |
| **Token 分级权限** | QuantDinger | QuantDinger 把能力按风险分级（R/W/B/T），你可以借鉴这个思路：普通用户 token 只能读行情和回测，实盘交易（如果未来加）需要单独授权 |
| **JWT 刷新机制** | TradingAgents-CN | TradingAgents-CN 的 Web 界面有 token 自动刷新，你可以加 refresh token 机制，避免用户频繁登录 |

**实施建议**：
- 用户表预留 `role` 字段（user/admin），为未来多用户和管理后台铺路
- 所有数据库查询通过 `current_user.id` 过滤，封装成 repository 层的基础方法

---

### 2.2 重点关注股票

**原规划**：
- `GET/POST/DELETE /api/v1/watchlist`：列表/添加/删除，`UNIQUE(user,symbol)` 幂等
- 列表合并 snapshot 实时价返回（代码/名称/最新价/涨跌幅）

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **自选股分组** | QuantDinger | QuantDinger 的 watchlist 支持分组（如"长线持仓"、"短线观察"），你可以预留 `group_id` 字段，未来扩展 |
| **批量实时价查询优化** | TradingAgents-CN | TradingAgents-CN 用 Redis pipeline 批量获取缓存，你的 watchlist 列表也可以批量查 snapshot，减少数据库往返 |

**实施建议**：
- `user_watchlist` 表预留 `sort_order` 和 `group_name` 字段，为未来排序和分组做准备
- 列表接口一次性返回所有标的的实时价，走 Redis 缓存，不回源数据库

---

### 2.3 支撑/压力位

**原规划**：
- `GET/POST/DELETE /api/v1/support-resistance`（user, symbol, type=support|pressure, price, note）

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **自动识别支撑压力位** | TradingAgents-CN | TradingAgents-CN 的技术面分析师能自动识别关键支撑/阻力位（基于前高前低、密集成交区）。你现在是手动添加，未来可以加 AI 自动识别功能，直接调用技术指标服务计算 |
| **支撑压力强度分级** | TradingAgents-CN | 它把支撑压力位按"测试次数"和"成交量"分级（强/中/弱），你的 note 字段可以扩展成结构化数据（强度、测试次数、最近测试时间） |

**实施建议**：
- 表结构预留 `strength`（强度）和 `test_count`（测试次数）字段
- 未来加 AI 自动识别时，只需在 service 层加方法，不用改表结构

---

### 2.4 技术指标服务

**原规划**：
- 服务端实现 MACD/KDJ/成交量/成交额计算（入参 K 线序列，输出指标序列）
- Redis 缓存指标（key 含 symbol+period+K 线最新 ts），失效回源重算

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **指标库直接复用** | TradingAgents-CN | TradingAgents-CN 实现了 50+ 技术指标（RSI、MACD、KDJ、布林带、ATR、OBV 等），代码在 `tradingagents/indicators/` 目录。你的 MACD/KDJ 可以直接参考它的实现，不用从零写公式 |
| **指标统一接口** | TradingAgents-CN | 它的指标都遵循统一接口：输入 K 线 DataFrame + 参数，输出指标 DataFrame。你也可以定义 `Indicator` 基类，所有指标继承，方便未来扩展 |
| **增量计算优化** | TradingAgents-CN | 它对长周期指标做增量计算——新 K 线来了只算最新一个点，不重算全量。你的缓存策略可以配合这个：缓存历史指标值，新数据来了追加计算 |
| **指标参数可配置** | QuantDinger | QuantDinger 的指标参数（如 MACD 的快慢线周期）是用户可配置的，不是写死的。你的指标服务也应该支持参数传入，不写死默认值 |

**实施建议**：
- 第一版先实现 MACD/KDJ/成交量/成交额，但接口设计成可扩展的
- 定义 `BaseIndicator` 抽象类：`calculate(df, params) -> df`
- 预留 RSI、布林带、ATR 等指标的实现位置，未来加新指标只需加一个类
- Redis 缓存 key 设计：`indicator:{symbol}:{period}:{indicator_name}:{params_hash}:{latest_ts}`，参数变化时自动失效

---

## 阶段三：AI 策略页后端（LangChain Agent + 本地记忆）

### 3.1 会话与消息

**原规划**：
- `conversations` CRUD：创建/列表/重命名/删除
- `chat_messages`：追加消息、按会话拉取（时间升序）；带 symbol_id 绑定标的

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **会话元数据扩展** | QuantDinger | QuantDinger 的会话记录了 agent_id、model、token_usage、cost 等元数据。你的 `conversations` 表可以预留 `agent_id`、`model_name`、`total_tokens` 字段，为未来统计和计费做准备 |
| **消息角色扩展** | TradingAgents-CN | TradingAgents-CN 的消息不只有 user/assistant，还有 tool_call、tool_result、system 等角色。你的 `chat_messages.role` 可以用 VARCHAR 而不是枚举，方便未来加工具调用消息 |
| **消息流式存储** | AgentQuant | AgentQuant 用 SSE 流式返回，同时边生成边存数据库。你的流式输出也应该在生成结束后一次性存，不要每个字都写库 |

**实施建议**：
- `conversations` 表预留 `agent_id`、`model`、`token_count`、`cost` 字段
- `chat_messages.role` 用 VARCHAR，不做数据库枚举约束，在代码层定义常量
- 流式输出结束后再存消息，过程中不写库

---

### 3.2 LangChain LLM 封装

**原规划**：
- 用 langchain 集成 DeepSeek（langchain-openai 兼容，`ChatDeepSeek`），流式输出 → SSE 透传前端
- 外部调用防护：超时、指数退避重试、熔断（连续失败熔断 + 半开探测）、限流

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **多 LLM 适配器架构** | TradingAgents-CN | TradingAgents-CN 的 `llm_adapters/` 目录封装了多家 LLM（阿里百炼、OpenAI、Anthropic、Google），统一接口。你现在只有 DeepSeek，但可以按同样的架构设计——定义 `BaseLLMProvider` 抽象，未来加新模型只需加一个适配器 |
| **智能模型路由** | TradingAgents-CN | 它根据任务类型选择不同模型：简单任务用轻量模型（省钱），复杂任务用强模型（效果好）。你也可以做：对话闲聊用 DeepSeek Lite，策略生成用 DeepSeek V3 |
| **Token 用量统计** | TradingAgents-CN | 它每次 LLM 调用都统计 token 数和估算成本，存在数据库里。你的封装层也应该统计 token 用量，为未来成本控制和用户计费做准备 |
| **故障转移（Failover）** | TradingAgents-CN | 主模型挂了自动切到备用模型。你可以预留配置：主模型 DeepSeek，备用模型可选（如通义千问），熔断后自动切换 |
| **LLM 调用审计日志** | QuantDinger | QuantDinger 的 Agent Gateway 记录所有 AI 调用的审计日志。你也应该记录每次 LLM 调用的 prompt、response、token、耗时、错误，方便排查问题 |

**实施建议**：
- 封装 `LLMService` 类，内部用 LangChain 的 `ChatOpenAI`（兼容 DeepSeek）
- 统一接口：`chat(messages, stream=False, model_config=None)`
- 内置：超时、重试、熔断、限流、token 统计、调用日志
- 预留多模型配置，第一版只用 DeepSeek，但架构支持扩展
- 借鉴 TradingAgents-CN 的 `llm_adapters` 目录结构，放在 `app/services/llm/providers/`

---

### 3.3 LangChain 工具集 + 上下文组装

**原规划**：
- 将行情快照/技术指标/记忆检索封装为 LangChain Tool（`@tool`），Agent 按需取数
- 拼接 system prompt（角色 + 风险提示 + 「数据不可用须明说、不编造」）

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **工具分层设计** | TradingAgents-CN | TradingAgents-CN 的工具按领域分层：`tools/market/`（行情）、`tools/indicators/`（指标）、`tools/analysis/`（分析）、`tools/risk/`（风控）。你的工具也可以按领域组织，不要都堆在一个文件里 |
| **工具描述规范** | TradingAgents-CN | 它的每个 tool 都有清晰的 name、description、args_schema，而且 description 写得非常详细——告诉 LLM 什么时候用、怎么用、返回什么。这直接影响 Agent 调用工具的准确率，一定要写好 |
| **工具结果格式化** | TradingAgents-CN | 它的工具返回结果是结构化的（dict/DataFrame），不是自然语言。Agent 拿到结构化数据后再自己组织语言回答。你的工具也应该返回结构化数据，不要在工具里生成自然语言 |
| **工具调用安全边界** | QuantDinger | QuantDinger 按风险等级给工具分类（R 读 / W 写 / B 回测 / T 交易），不同权限的 Agent 只能调用对应等级的工具。你的工具也应该打标签，比如"只读行情"是安全的，"保存策略"需要用户确认 |
| **System Prompt 模板化** | TradingAgents-CN | 它的 system prompt 是模板化的，包含：角色定义、能力边界、输出格式要求、风险提示、禁止事项。你的 system prompt 可以参考它的结构，特别是"数据不可用必须明说，禁止编造"这一条一定要强调 |

**实施建议**：
- 工具目录结构：`app/agent/tools/{market,indicator,memory,strategy,backtest}/`
- 每个工具用 `@tool` 装饰器，写清楚 description 和 args_schema
- 工具返回结构化数据（dict），不返回自然语言
- 工具分类打标签：`read_only=True/False`、`risk_level="R/W/B/T"`
- System Prompt 拆成模板文件，不要硬编码在代码里
- 第一版工具集：获取行情快照、获取 K 线、计算指标、检索记忆、保存策略（后续加）

---

### 3.4 本地记忆系统（LangChain 本地向量库）

**原规划**：
- 记忆抽取：LangChain 从对话/策略结果抽取关键事实（交易体系/规则/偏好），写用户本地记忆文件
- 向量化：本地 ChromaDB 持久化（切片 + embedding），`memory_chunks` 登记 chunk/vector_id/file_path，`user_memory_files` 登记文件
- 检索：相似度检索 TopK 注入上下文（默认本地 embedding，后续可换）

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **记忆分层架构** | TradingAgents-CN | TradingAgents-CN 的记忆分三层：短期记忆（当前会话）、中期记忆（最近 N 次对话）、长期记忆（RAG 向量库）。你的记忆系统也可以这样设计——短期记忆走会话历史，长期记忆走向量库，中间可以有一个"重要事实"提取层 |
| **记忆抽取 Prompt** | TradingAgents-CN | 它有专门的记忆抽取 prompt，指导 LLM 从对话中提取结构化的交易规则、偏好、经验教训。你的抽取逻辑可以直接参考它的 prompt 设计 |
| **记忆重要性评分** | TradingAgents-CN | 它给每条记忆打重要性分数（1-10），检索时加权。不重要的记忆（比如闲聊）会被过滤掉。你也可以加这个机制，避免记忆库被噪音淹没 |
| **记忆衰减机制** | TradingAgents-CN | 旧记忆的权重会随时间衰减，新记忆权重更高。你的检索排序可以结合"相似度 + 重要性 + 时效性"三个维度 |
| **本地向量库选型** | QuantDinger | QuantDinger 用的是 SQLite + 向量扩展，不是独立的向量数据库。你用 ChromaDB 也可以，但要注意：ChromaDB 是嵌入式的，不需要额外部署，适合本地优先的设计 |
| **记忆文件可读** | QuantDinger | QuantDinger 的记忆文件是人类可读的 JSON/Markdown，用户可以直接打开查看和编辑。你的本地记忆文件也要保持人类可读，不要只有向量库二进制 |

**实施建议**：
- 记忆分三层：会话记忆（短期）→ 工作记忆（中期，最近 N 条重要事实）→ 长期记忆（向量库）
- 记忆抽取：用 LangChain 的 `LLMChain` + 专门的抽取 prompt，输出结构化 JSON
- 每条记忆包含：content（内容）、type（rule/preference/experience/strategy）、importance（重要性 1-10）、created_at、source（来源会话/策略）
- 检索排序：`score = similarity * 0.6 + importance * 0.2 + recency * 0.2`
- 本地存储：ChromaDB 做向量检索，同时存一份人类可读的 JSON 文件（M 区"记忆文件"按钮可以打开）
- 借鉴 TradingAgents-CN 的 `memory/` 目录结构，放在 `app/agent/memory/`

---

### 3.5 策略生成（LangChain 结构化输出）

**原规划**：
- 定义四类 prompt 模板：诊断符号/交易计划/机会雷达/创建交易策略（入场/止损/止盈/仓位规则文案）
- 用 LangChain `with_structured_output` 生成策略代码 + JSON 参数，schema 校验

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **自然语言 → 策略代码生成** | AgentQuant | AgentQuant 的核心功能就是"自然语言 → 策略代码 → 回测"全链路。它的 code_generator 工具可以直接借鉴——用 LLM 生成 Python 策略代码，然后在沙箱里执行 |
| **策略代码模板化** | QuantDinger | QuantDinger 的策略不是从零生成，而是基于模板填充——用户描述 → 选模板 → 填参数 → 生成代码。这样比从零生成更可靠，不容易出语法错误。你也可以先做几个基础策略模板（双均线、RSI 均值回归、布林带突破等），AI 负责选模板和填参数 |
| **结构化输出 Schema 设计** | TradingAgents-CN | TradingAgents-CN 的分析结果是严格结构化的（action、confidence、reasoning、target_price、stop_loss 等）。你的策略参数也应该定义严格的 Pydantic schema，用 `with_structured_output` 保证输出格式正确 |
| **代码安全检查** | AgentQuant | AgentQuant 在执行生成的代码前会做安全检查——禁止危险操作（文件读写、网络请求、执行系统命令）。你的回测沙箱也应该做同样的检查 |
| **多轮策略优化** | TradingAgents-CN | 它支持多轮对话优化策略——用户说"把止损改成 2%"，AI 就修改对应参数重新生成。你也可以支持这种迭代式的策略生成，而不是一次生成就结束 |
| **策略解释生成** | TradingAgents-CN | 它生成策略的同时会生成一份解释——为什么这样设计、逻辑是什么、风险在哪。你的"创建交易策略"也应该返回解释，让用户理解策略逻辑 |

**实施建议**：
- 第一版先做"模板填充"模式，比从零生成更稳：
  - 定义基础策略模板库（双均线、RSI 均值回归、MACD 金叉死叉、布林带突破等）
  - AI 根据用户描述选择最合适的模板，填充参数
  - 生成完整的策略代码
- 用 LangChain `with_structured_output(Pydantic Model)` 保证输出格式
- 策略输出结构：`{strategy_name, description, code, params: {entry, exit, stop_loss, take_profit, position}, risk_warning}`
- 生成后做语法检查（`ast.parse`），确保代码能运行
- 借鉴 AgentQuant 的 code_generator 工具设计
- 未来再做"从零生成"的高级模式

---

### 3.6 交易策略 CRUD

**原规划**：
- `trading_strategies`：保存（title/description/code/params/status）/列表/详情/更新，按 user 隔离

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **策略版本管理** | QuantDinger | QuantDinger 的策略支持版本化——每次修改保存一个新版本，可以回滚到历史版本。你的策略表可以加 `version` 字段，或者单独建 `strategy_versions` 表 |
| **策略标签分类** | QuantDinger | 它的策略可以打标签（趋势/均值回归/套利/高频等），方便筛选。你的策略也可以加 `tags` 字段（JSONB 数组） |
| **策略评分系统** | TradingAgents-CN | TradingAgents-CN 给策略打分（夏普比率、胜率、盈亏比等综合评分），按评分排序。你的策略列表可以加一个 `score` 字段，回测后自动更新 |
| **策略分享/复制** | QuantDinger | QuantDinger 支持策略导出/导入，用户可以分享策略。你可以预留 `is_public` 字段，未来加策略社区功能 |

**实施建议**：
- `trading_strategies` 表预留字段：`version`、`tags`（JSONB）、`score`、`is_public`、`parent_id`（复制来源）
- 列表接口支持按标签、评分、创建时间筛选排序
- 保存策略时自动保存一个版本（第一版可以简单，每次修改都新建一条记录，软删除旧的）

---

### 3.7 用户定制 Agent（user_agents CRUD）

**原规划**：
- CRUD：创建/列表/启停定制 Agent，配置 system_prompt/tools/llm_config/memory_config（JSONB）
- 会话发送时按所选 agent_id 加载配置，构造 LangChain Agent

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **Agent 配置化设计** | QuantDinger | QuantDinger 的 Agent Gateway 支持按 token 配置不同的权限、速率限制、可用工具。你的用户定制 Agent 也可以参考——每个 Agent 有自己的配置：可用工具列表、LLM 模型、记忆开关、system prompt 等 |
| **Agent 模板市场** | TradingAgents-CN | TradingAgents-CN 预设了多种分析师角色（基本面分析师、技术面分析师等）作为模板。你也可以预设几个 Agent 模板（保守型交易员、激进型交易员、研究员等），用户可以基于模板创建自己的 Agent |
| **Agent 能力开关** | QuantDinger | QuantDinger 按风险等级控制 Agent 能调用的工具。你的定制 Agent 也应该有"能力开关"——用户可以勾选这个 Agent 能做什么（只能分析 / 可以生成策略 / 可以自动回测等） |

**实施建议**：
- `user_agents` 表字段：`id, user_id, name, description, avatar, system_prompt, model_config(JSONB), tool_config(JSONB), memory_config(JSONB), is_active, created_at, updated_at`
- 预设几个官方模板（技术分析型、基本面型、保守风控型），用户可以"从模板创建"
- Agent 配置校验：创建时验证配置是否合法（工具是否存在、模型是否可用等）
- 会话创建时选择 agent_id，对话过程中 Agent 配置不变

---

### 3.8 多智能体编排（LangGraph）

**原规划**：
- 基于 TradingAgents-CN trading_graph 构建：分析（行情/指标/新闻）→ 多空研究员辩论 → 风控 → 交易决策
- LangGraph StateGraph 编排，条件路由/反射/信号处理，执行落 `agent_runs`/`agent_steps`
- 与 L 区功能卡片对接：诊断/交易计划/机会雷达走不同图分支，UI 不变

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **多智能体组织架构** | TradingAgents-CN | 这是最核心的借鉴点！TradingAgents-CN 的架构是：管理层 → 分析师团队（基本面/技术面/新闻/情绪）→ 研究员团队（看涨/看跌辩论）→ 交易员 → 风控。你的多 Agent 可以完全照搬这个组织架构 |
| **看涨/看跌辩论机制** | TradingAgents-CN | 两个持相反立场的研究员各自论证，然后由交易员做最终决策。这个设计比单 Agent 分析更全面，能减少偏见。你的"诊断符号"和"交易计划"可以用这个辩论机制提升分析质量 |
| **LangGraph 图结构设计** | TradingAgents-CN | 它的 `trading_graph.py` 用 LangGraph StateGraph 实现了完整的多 Agent 工作流，包含节点定义、状态管理、条件路由。你的图结构可以直接参考它的代码组织方式 |
| **研究深度分级** | TradingAgents-CN | 它有 5 级研究深度，级别越高，启用的分析师越多、辩论轮次越多。你的功能卡片也可以加深度选项——快速分析走轻量图（单 Agent），深度分析走全量图（多 Agent + 多轮辩论） |
| **Agent 执行轨迹记录** | QuantDinger | QuantDinger 的 agent_steps 记录了每一步的输入输出、耗时、token 用量。你的 `agent_runs` 和 `agent_steps` 表也应该记录完整的执行轨迹，方便调试和用户查看分析过程 |
| **并行分析优化** | TradingAgents-CN | 多个分析师可以并行工作（技术面和基本面同时分析），然后汇总结果。LangGraph 支持并行节点，你的图也可以设计成并行的，提高响应速度 |

**实施建议**：
- 第一版先实现简化版多 Agent，不要一上来就做全量：
  - **轻量模式**（默认）：单 Agent + 工具调用，响应快，适合日常对话
  - **深度模式**：多 Agent 辩论，适合"诊断符号"、"交易计划"等深度分析
- 图结构设计（深度模式）：
  ```
  入口 → 技术分析师 → 看涨研究员 ←→ 看跌研究员（辩论 N 轮）→ 风控 → 交易员决策 → 输出
  ```
- 状态管理：用 LangGraph 的 State，包含 `symbol, market_data, analysis, bull_arg, bear_arg, debate_rounds, risk_assessment, final_decision`
- 执行过程记录到 `agent_runs` 和 `agent_steps` 表，前端可以展示"AI 正在思考..."的步骤
- 直接参考 TradingAgents-CN 的 `graph/trading_graph.py` 和 `agents/` 目录结构
- 辩论轮次可配置（默认 2 轮），轮次越多分析越深入，但耗时越长

---

## 阶段四：回测引擎（异步，不阻塞主线程）

### 4.1 回测引擎

**原规划**：
- 策略代码沙箱执行：限制内置依赖/超时/内存，禁网络
- 撮合规则（按开盘/收盘价成交）、持仓与交易流水、参数 JSON 化（入场/止损/止盈/仓位）

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **策略沙箱安全** | AgentQuant | AgentQuant 用 Kubernetes Pod 做沙箱隔离，每个回测跑在独立容器里。你第一版可以用 `RestrictedPython` 或 `exec` + 白名单做轻量沙箱，未来再升级容器级隔离 |
| **策略 API 设计** | QuantDinger | QuantDinger 的策略有统一的 API 接口：`initialize()`、`on_bar()`、`on_order()`、`on_trade()` 等回调函数。你的策略代码也应该遵循统一的接口规范，而不是随便写 |
| **撮合引擎实现** | QuantDinger | QuantDinger 的撮合引擎支持市价单、限价单、止损单，还有滑点、手续费模拟。你的第一版可以简单点（只有市价单，按收盘价成交），但接口设计要支持未来扩展 |
| **参数化策略** | QuantDinger | QuantDinger 的策略参数是从外部注入的，不是写死在代码里。你的策略也应该这样——参数存在 `params` JSONB 字段，回测时注入到策略代码中 |
| **回测进度回调** | AgentQuant | AgentQuant 的回测过程有进度回调，实时更新进度条。你的 Celery 任务也应该实时更新 `progress` 字段，前端轮询展示 |

**实施建议**：
- 策略基类设计：
  ```python
  class BaseStrategy:
      params = {}  # 默认参数
      def initialize(self, context): pass
      def on_bar(self, bar, context): pass
      def on_trade(self, trade, context): pass
  ```
- 沙箱执行：第一版用 `exec` + 内置白名单（只允许 pandas、numpy、talib 等安全库），禁文件 IO 和网络
- 撮合规则：第一版简化——按当日收盘价成交，T+1 卖出（A股规则），手续费万分之三
- 回测过程中实时更新 Celery 任务进度（0-100%）
- 借鉴 QuantDinger 的策略 API 设计和 AgentQuant 的沙箱执行

---

### 4.2 指标计算

**原规划**：
- 胜率/盈亏比/夏普/累计买入/累计卖出/年化收益率/最大回撤 + `metrics_json` 扩展字段

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **绩效指标库** | TradingAgents-CN | TradingAgents-CN 实现了完整的绩效指标计算：夏普比率、索提诺比率、最大回撤、卡玛比率、胜率、盈亏比、年化收益、波动率等。你的指标计算可以直接参考它的实现 |
| **指标分类展示** | QuantDinger | QuantDinger 把回测指标分成几类：收益指标、风险指标、风险调整收益指标、交易统计。你的 `metrics_json` 也可以按分类组织，前端展示更清晰 |
| **基准对比** | QuantDinger | QuantDinger 的回测结果会和基准（如沪深300）对比，计算超额收益。你也可以加基准对比，让用户知道策略是不是跑赢了大盘 |
| **月度收益统计** | TradingAgents-CN | 它会统计每个月的收益率，生成热力图。你也可以加月度收益统计，未来前端做可视化 |

**实施建议**：
- 指标分四类：
  - **收益指标**：累计收益、年化收益、基准收益、超额收益
  - **风险指标**：最大回撤、波动率、下行风险
  - **风险调整收益**：夏普比率、索提诺比率、卡玛比率
  - **交易统计**：胜率、盈亏比、交易次数、平均持仓天数
- 所有指标放在 `metrics_json` 里，结构化存储
- 第一版先实现你 roadmap 里列的那几个，预留扩展空间
- 借鉴 TradingAgents-CN 的 `analysis/performance.py` 实现

---

### 4.3 回测任务流（Celery）

**原规划**：
- `POST /api/v1/backtest` 创建 `backtest_tasks`（queued）→ worker 执行
- 状态机 queued→running→success/failed，`progress` 进度回写
- 结果事务写入 `backtest_results`（与策略原子保存）；结果抽取转本地向量记忆（memory_chunks）
- 失败自动重试 + `task_logs` 记录

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **异步任务状态机** | QuantDinger | QuantDinger 的 Agent Gateway 用异步任务模式——提交任务返回 job_id，然后轮询状态。你的回测任务也是这个模式，可以参考它的状态机设计和 job 表结构 |
| **任务优先级队列** | QuantDinger | QuantDinger 按任务类型分队列（sync/backtest/ai），不同队列有不同的 worker 数量和优先级。你的 Celery 也已经分了三队列，可以继续沿用 |
| **任务幂等性** | QuantDinger | 相同参数的回测任务不会重复执行，直接返回已有结果。你也可以做——用策略 ID + 标的 + 时间范围做幂等键，避免重复计算 |
| **任务取消** | AgentQuant | AgentQuant 支持取消正在运行的回测任务。你也可以加取消功能——用户点取消后，Celery 任务终止，状态标记为 cancelled |
| **回测结果缓存** | TradingAgents-CN | 相同策略+相同标的+相同时间段的回测结果会缓存，下次直接返回。你的 Redis 可以加回测结果缓存，key 用策略+标的+时间段的 hash |

**实施建议**：
- 状态机：`queued → running → success / failed / cancelled`
- 幂等键：`md5(strategy_id + symbol_id + start_date + end_date + params_hash)`
- 任务进度：0-100%，每处理 10% 的 K 线更新一次
- 失败重试：最多重试 2 次，指数退避
- 结果写入：策略 + 回测结果 + 记忆抽取 在同一个数据库事务里
- 借鉴 QuantDinger 的异步任务设计和 AgentQuant 的任务取消

---

### 4.4 回测 API

**原规划**：
- 发起回测 / 任务状态轮询 `GET /api/v1/backtest/tasks/{id}` / 结果查询 `GET /api/v1/backtest/results?strategy=`

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **API 版本化** | QuantDinger | QuantDinger 的 Agent Gateway 用 `/api/agent/v1/` 做版本化。你的回测 API 也应该版本化，未来破坏性变更可以升 v2 |
| **SSE 进度推送** | AgentQuant | AgentQuant 用 SSE 实时推送回测进度，不用前端轮询。你的前端如果支持 SSE，可以加这个接口，体验更好 |
| **结果分页** | QuantDinger | 回测结果（交易流水）可能很多，需要分页。你的结果查询接口应该支持分页和筛选 |
| **批量回测** | QuantDinger | QuantDinger 支持批量回测——一个策略跑多个标的，或者多个策略跑一个标的。你可以预留批量回测接口，未来加参数优化功能 |

**实施建议**：
- API 设计：
  - `POST /api/v1/backtest` —— 提交回测任务
  - `GET /api/v1/backtest/tasks/{task_id}` —— 查询任务状态
  - `GET /api/v1/backtest/tasks/{task_id}/stream` —— SSE 进度推送（可选）
  - `GET /api/v1/backtest/results/{result_id}` —— 获取回测结果详情
  - `GET /api/v1/backtest/results?strategy_id=` —— 按策略查询结果列表
- 交易流水支持分页
- 第一版先做轮询，SSE 后续再加
- 借鉴 QuantDinger 的 API 设计规范

---

## 阶段五：部署闭环与生产收尾

### 5.1 容器化

**原规划**：
- 后端/Celery 多阶段 Dockerfile（依赖层缓存）
- Docker Compose：postgres/redis/api/worker/beat/nginx 一键编排

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **多阶段 Dockerfile** | QuantDinger | QuantDinger 的 Dockerfile 用多阶段构建，依赖层和代码层分开，镜像更小，构建更快。你的 Dockerfile 也可以参考 |
| **Docker Compose 多环境** | QuantDinger | QuantDinger 有 dev/test/prod 三套 compose 配置，通过 override 文件叠加。你也可以这样——基础 compose + dev override + prod override |
| **健康检查** | QuantDinger | 每个服务都有健康检查（healthcheck），docker compose 可以根据健康状态决定是否重启。你的 api、worker、postgres、redis 都应该加健康检查 |
| **非 root 用户运行** | TradingAgents-CN | 容器内用非 root 用户运行，更安全。你的 Dockerfile 也应该创建 app 用户，用 app 用户运行 |

**实施建议**：
- 多阶段 Dockerfile：builder 阶段装依赖，runner 阶段只拷运行时需要的文件
- Docker Compose：基础文件 + dev/prod override
- 每个服务加 healthcheck
- 容器内非 root 用户运行
- 借鉴 QuantDinger 的 Docker 配置

---

### 5.2 Nginx

**原规划**：
- 反向代理 `/api` → api、静态资源缓存 + gzip + TLS（证书可配）

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **API 限流** | QuantDinger | QuantDinger 在 Nginx 层做限流（`limit_req_zone`），保护后端不被打爆。你的 Nginx 也应该加限流，特别是 AI 相关接口 |
| **请求体大小限制** | QuantDinger | 限制请求体大小，防止大请求打挂服务 |
| **安全头** | TradingAgents-CN | 加安全响应头（X-Frame-Options、X-Content-Type-Options、CSP 等） |

**实施建议**：
- 加 API 限流，不同接口不同限流策略（行情接口宽松，AI 接口严格）
- 加安全响应头
- 静态资源长期缓存
- 借鉴 QuantDinger 的 Nginx 配置

---

### 5.3 CI/CD

**原规划**：
- GitHub Actions：lint → test → build 镜像 → 部署

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **多阶段 CI** | TradingAgents-CN | lint → test → build → deploy，每阶段失败就停止 |
| **缓存优化** | QuantDinger | pip 依赖、node_modules 都做缓存，加快 CI 速度 |
| **矩阵测试** | TradingAgents-CN | 多个 Python 版本、多个操作系统下跑测试 |

**实施建议**：
- CI 流水线：lint (ruff/black) → test (pytest) → build (docker) → deploy (可选)
- 依赖缓存
- 借鉴 TradingAgents-CN 的 GitHub Actions 配置

---

### 5.4 监控告警

**原规划**：
- Prometheus 指标：API 吞吐/延迟/错误率、队列深度、缓存命中率、行情新鲜度
- Grafana 面板 + 告警（接口错误率阈值、队列积压、行情延迟）

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **AI 调用监控** | QuantDinger | QuantDinger 监控 LLM 调用次数、token 用量、失败率、平均耗时。你也应该加这些指标，AI 是核心功能，必须监控 |
| **成本监控** | TradingAgents-CN | TradingAgents-CN 统计 LLM 调用成本，有成本看板。你也可以加成本监控，每天/每月花了多少钱一目了然 |
| **业务指标** | QuantDinger | 除了技术指标，还有业务指标：用户数、策略数、回测次数等。你的监控也应该加业务指标 |

**实施建议**：
- 技术指标：API 吞吐/延迟/错误率、队列深度、缓存命中率、数据库连接数
- AI 指标：LLM 调用次数、token 用量、失败率、平均耗时、估算成本
- 业务指标：注册用户数、策略数、回测任务数
- 告警规则：接口错误率 > 5%、队列积压 > 100、行情延迟 > 5 分钟、LLM 失败率 > 10%
- 借鉴 QuantDinger 的监控指标设计和 TradingAgents-CN 的成本统计

---

### 5.5 测试补齐

**原规划**：
- pytest：指标计算/策略解析/记忆抽取/Agent 编排（LangGraph 单测）/核心 API 冒烟

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **测试分层** | TradingAgents-CN | 单元测试、集成测试、端到端测试分层。你的测试也应该这样——单元测试覆盖核心逻辑，集成测试测 API，冒烟测试测主流程 |
| **Mock 外部依赖** | TradingAgents-CN | LLM 调用、行情 API 这些外部依赖都用 mock，测试不依赖网络。你的测试也应该 mock 掉 DeepSeek 和东方财富 API |
| **LangGraph 测试** | TradingAgents-CN | 它有专门的 LangGraph 测试——测试每个节点的输入输出，测试条件路由是否正确。你的 Agent 编排也应该写单元测试 |

**实施建议**：
- 单元测试：指标计算、策略解析、记忆抽取、工具函数
- 集成测试：API 接口（用 test client）、数据库操作
- Agent 测试：工具调用、多 Agent 流程（mock LLM）
- 所有外部依赖（LLM、行情 API）都 mock
- 借鉴 TradingAgents-CN 的测试结构

---

### 5.6 收尾检查

**原规划**：
- 按 working_docs.md 六要素模板逐项自查（可维护/扩展/演进/稳定/可观测/可部署），每项一句话结论
- 补全 docs/Agent_backend/Agent_code.md 编码记录、api-docs.md API 文档、fixed.md 修复记录

**可借鉴开源项目**：

| 借鉴点 | 来源 | 具体做法 |
|---|---|---|
| **生产就绪检查清单** | QuantDinger | QuantDinger 有完整的生产部署检查清单：安全配置、监控告警、备份策略、灾备方案。你的收尾检查也可以参考这个清单 |
| **文档完整性** | TradingAgents-CN | TradingAgents-CN 的文档非常完整：架构文档、API 文档、部署文档、故障排除指南。你的文档也应该争取达到这个水平 |

**实施建议**：
- 六要素自查逐项过，每项给出具体结论和改进建议
- 补全三类文档：编码记录、API 文档、修复记录
- 加一个部署指南文档
- 借鉴 QuantDinger 的生产检查清单

---

## 总结：各阶段核心借鉴点

| 阶段 | 核心借鉴来源 | 最值得抄的 3 个点 |
|---|---|---|
| **阶段二** | TradingAgents-CN | 1. 指标库直接复用 2. 指标统一接口设计 3. 增量计算优化 |
| **阶段三** | TradingAgents-CN + QuantDinger | 1. LangGraph 多 Agent 辩论架构 2. 记忆分层 + 重要性评分 3. LLM 多适配器 + 故障转移 |
| **阶段四** | QuantDinger + AgentQuant | 1. 策略沙箱安全执行 2. 异步任务状态机 3. 绩效指标计算 |
| **阶段五** | QuantDinger | 1. Docker 多阶段构建 2. AI 调用监控 + 成本统计 3. 生产就绪检查清单 |
