# Agent 记忆文件

> 每次开启 Agent 先阅读最新记忆内容，快速重新上手。

保存时间：2026-08-08
记忆内容：
1. 项目定位：量化交易软件——选股买卖决策 + DeepSeek Agent 辅助（主观交易经验转量化因子/回测），Agent 记忆本地存储。
2. 技术栈：Python(FastAPI) + PostgreSQL + Vue3 + Redis + Celery + Nginx + DeepSeek + langchain/LangGraph。
3. 硬约束：前端不计算复杂指标；回测不阻塞主线程（走 Celery）；Agent 记忆本地存储（LangChain 本地向量库 ChromaDB）；行情数据源走 DataProvider 抽象（默认 Akshare/东方财富）。
4. 架构文档：docs/project_docs/docs.md（需求 + 第二部分数据流 + 第三部分数据库设计 + v0.0.2 扩展方向）；docs/project_docs/working_docs.md（生产级六要素架构说明，开发后收尾检查按其中模板写）；docs/sql/（01_schema.sql 建表、02_seed_fixed_indices.sql 固定指数种子、03_agent_extensions.sql Agent 扩展表、sql.md 各表系统作用说明）。
5. 已注册 skill：quant-prod-arch（生产级架构审查与开发规范），开发时自动应用。
6. 当前进度：需求文档/架构/SQL 已定稿；AI 定制 Agent 已改为 LangChain/LangGraph 方案（借鉴 TradingAgents-CN），docs.md 数据流/数据库设计与 working_docs.md 架构已同步更新并新增 03_agent_extensions.sql（user_agents/agent_runs/agent_steps/memory_chunks）；docs.md 底部已补 v0.0.2 扩展方向（多智能体/机会雷达增强/财报因子/工具化数据/定制Agent/风控辩论/LLM可插拔/记忆升级/复盘闭环/多市场）；后端实施规划已写入 docs/Agent_backend/roadmap.md（五阶段，阶段三为 LangChain Agent），前端实施规划已写入 docs/Agent_frontend/roadmap.md（五阶段），前端页面设计已写入 docs/Agent_frontend/PageDesign.md；代码目录（stock_backend、stock_frontend、stock_invest_backend）均为空，尚未开始编码，下一步应从后端数据层（DataProvider + 行情同步）起步。
7. 参考开源项目（须借鉴避免造轮子）：TradingAgents-CN-main（C:\Users\112\Desktop\TradingAgents-CN-main\TradingAgents-CN-main）；QuantDinger（C:\Users\112\Desktop\QuantDinger-main\QuantDinger-main，AI策略页 J/K/L/M/N 分区架构可完全借鉴）。
