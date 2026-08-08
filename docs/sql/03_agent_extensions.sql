-- ==============================================================
-- 03 Agent 智能体扩展（LangChain/LangGraph 多智能体）
-- 对应 docs.md 第三部分 3.5 智能体域 + v0.0.2 扩展方向
-- 依赖 01_schema.sql（users/conversations/symbols/trading_strategies）
-- ==============================================================

BEGIN;

-- 用户定制交易 Agent（LangChain 配置）
CREATE TABLE user_agents (
    id            BIGSERIAL   PRIMARY KEY,
    user_id       BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          VARCHAR(64) NOT NULL,                       -- Agent 名称
    agent_type    VARCHAR(32) NOT NULL DEFAULT 'custom',      -- diagnostic/plan/radar/strategy/custom
    system_prompt TEXT,                                       -- 定制 system prompt（交易体系/规则）
    tools         JSONB,                                      -- 启用的工具列表（行情/指标/回测/新闻/财报）
    llm_config    JSONB,                                      -- LLM 配置（provider/model/temperature）
    memory_config JSONB,                                      -- 记忆配置（开关/向量库 collection）
    status        VARCHAR(16) NOT NULL DEFAULT 'draft',       -- active/draft
    created_at    TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at    TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_user ON user_agents(user_id);
CREATE TRIGGER trg_user_agents_updated BEFORE UPDATE ON user_agents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Agent 运行记录（一次 LangGraph 执行）
CREATE TABLE agent_runs (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id        BIGINT      REFERENCES user_agents(id) ON DELETE SET NULL,
    conversation_id BIGINT      REFERENCES conversations(id) ON DELETE SET NULL,
    symbol_id       BIGINT      REFERENCES symbols(id) ON DELETE SET NULL,
    run_type        VARCHAR(32) NOT NULL,                     -- diagnostic/strategy/radar/plan/custom
    status          VARCHAR(16) NOT NULL DEFAULT 'queued',    -- queued/running/success/failed
    input           TEXT,
    output          TEXT,                                     -- 最终输出
    tokens          INT,
    error           TEXT,
    created_at      TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_arun_user ON agent_runs(user_id, created_at);
CREATE INDEX idx_arun_conv ON agent_runs(conversation_id);
CREATE TRIGGER trg_agent_runs_updated BEFORE UPDATE ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 多智能体步骤消息（各 Agent 中间输出，供可观测/复盘）
CREATE TABLE agent_steps (
    id         BIGSERIAL   PRIMARY KEY,
    run_id     BIGINT      NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_name  VARCHAR(64) NOT NULL,                          -- bull_research/bear_research/risk_mgmt/trader...
    agent_role VARCHAR(32) NOT NULL,                          -- analyst/researcher/manager/trader
    content    TEXT,                                          -- 该步输出
    meta       JSONB,                                         -- 附加（决策/置信度）
    created_at TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_astep_run ON agent_steps(run_id);

-- 向量记忆切片（LangChain 本地向量库索引，文本+来源+本地文件，满足本地存储）
CREATE TABLE memory_chunks (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL,                         -- strategy/rule/preference/backtest
    source_id   BIGINT,                                       -- 关联业务 ID（strategy_id 等）
    content     TEXT        NOT NULL,                         -- 记忆文本切片
    vector_id   VARCHAR(64),                                  -- 本地向量库(ChromaDB)记录 ID
    file_path   VARCHAR(512),                                 -- 对应本地记忆文件
    created_at  TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_mchunk_user ON memory_chunks(user_id, source_type);

COMMIT;
