# 量化回测软件

## 技术栈
- Backend: Python (FastAPI) + Celery + Redis + PostgreSQL + langchain
- Frontend: Vue 3 + 轻量级 K 线图表库
- AI: DeepSeek API + langchain + 本地记忆
- DevOps: Docker + Nginx + Prometheus/Grafana

## 架构约束
- 生产级六要素：可维护、可扩展、可演进、稳定性、可观测、可部署
- 禁止前端直接计算复杂指标
- 禁止回测引擎阻塞主线程
- Agent 记忆必须本地存储

## 关键路径
1. 行情数据接入 → K 线展示 → 技术指标
2. 策略描述 → AI 补齐规则 → 回测验证 → 保存策略
3. 用户记忆 → 本地文件 → Agent 个性化决策