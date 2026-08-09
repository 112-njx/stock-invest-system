-- ==============================================================
-- 股票量化交易系统 数据库 Schema（PostgreSQL 13+）
-- 对应 docs.md 第三部分数据库设计，生产迁移用 Alembic，此文件为初始化脚本
-- ==============================================================

BEGIN;

-- ==============================================================
-- 通用：updated_at 自动更新触发器
-- ==============================================================
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================
-- 行情域
-- ==============================================================

-- 标的统一模型（股票/ETF/指数）
CREATE TABLE symbols (
    id            BIGSERIAL   PRIMARY KEY,
    code          VARCHAR(16) NOT NULL DEFAULT '',          -- 代码(600519)，行业指数由同步任务回填
    name          VARCHAR(64) NOT NULL,                     -- 名称
    type          VARCHAR(16) NOT NULL,                     -- stock / etf / index
    market        VARCHAR(16) NOT NULL DEFAULT 'SSE',       -- 市场: SSE/SZSE/CSI/US/JP/KR/XAU...
    industry      VARCHAR(64),                              -- 行业（指数/行业）
    etf_linked    VARCHAR(16),                              -- 关联ETF代码
    is_fixed_index BOOLEAN    NOT NULL DEFAULT FALSE,       -- 是否固定大盘/行业指数
    sort_order    INT,                                      -- 固定列表排序
    updated_at    TIMESTAMP   NOT NULL DEFAULT now(),
    UNIQUE (type, name)
);
COMMENT ON COLUMN symbols.code IS '行业指数代码由行情同步任务按名称回填';

-- K线分区父表（按月分区，PK 含分区键 ts，天然幂等去重）
CREATE TABLE kline_15m (
    symbol_id BIGINT       NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    ts        TIMESTAMP    NOT NULL,
    open      NUMERIC(12,3) NOT NULL,
    high      NUMERIC(12,3) NOT NULL,
    low       NUMERIC(12,3) NOT NULL,
    close     NUMERIC(12,3) NOT NULL,
    volume    BIGINT       NOT NULL DEFAULT 0,
    amount    NUMERIC(20,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol_id, ts)
) PARTITION BY RANGE (ts);

CREATE TABLE kline_1d (
    symbol_id BIGINT       NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    ts        TIMESTAMP    NOT NULL,
    open      NUMERIC(12,3) NOT NULL,
    high      NUMERIC(12,3) NOT NULL,
    low       NUMERIC(12,3) NOT NULL,
    close     NUMERIC(12,3) NOT NULL,
    volume    BIGINT       NOT NULL DEFAULT 0,
    amount    NUMERIC(20,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol_id, ts)
) PARTITION BY RANGE (ts);

CREATE TABLE kline_1w (
    symbol_id BIGINT       NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    ts        TIMESTAMP    NOT NULL,
    open      NUMERIC(12,3) NOT NULL,
    high      NUMERIC(12,3) NOT NULL,
    low       NUMERIC(12,3) NOT NULL,
    close     NUMERIC(12,3) NOT NULL,
    volume    BIGINT       NOT NULL DEFAULT 0,
    amount    NUMERIC(20,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol_id, ts)
) PARTITION BY RANGE (ts);

CREATE TABLE kline_1mon (
    symbol_id BIGINT       NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    ts        TIMESTAMP    NOT NULL,
    open      NUMERIC(12,3) NOT NULL,
    high      NUMERIC(12,3) NOT NULL,
    low       NUMERIC(12,3) NOT NULL,
    close     NUMERIC(12,3) NOT NULL,
    volume    BIGINT       NOT NULL DEFAULT 0,
    amount    NUMERIC(20,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol_id, ts)
) PARTITION BY RANGE (ts);

-- 按月建分区函数：create_kline_partitions('kline_1d', '2020-01-01', '2027-01-01')
CREATE OR REPLACE FUNCTION create_kline_partitions(p_table TEXT, p_start DATE, p_end DATE)
RETURNS void AS $$
DECLARE
    d DATE := date_trunc('month', p_start)::DATE;
BEGIN
    WHILE d < p_end LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
            p_table || '_' || to_char(d, 'YYYYMM'), p_table, d, d + INTERVAL '1 month');
        d := d + INTERVAL '1 month';
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- 初始分区（2020-01 ~ 2026-12）+ 兜底默认分区，防止越界写入报错
SELECT create_kline_partitions('kline_15m', '2020-01-01', '2027-01-01');
SELECT create_kline_partitions('kline_1d',  '2020-01-01', '2027-01-01');
SELECT create_kline_partitions('kline_1w',  '2020-01-01', '2027-01-01');
SELECT create_kline_partitions('kline_1mon','2020-01-01', '2027-01-01');
CREATE TABLE kline_15m_default  PARTITION OF kline_15m  DEFAULT;
CREATE TABLE kline_1d_default   PARTITION OF kline_1d   DEFAULT;
CREATE TABLE kline_1w_default   PARTITION OF kline_1w   DEFAULT;
CREATE TABLE kline_1mon_default PARTITION OF kline_1mon DEFAULT;

-- 实时行情快照（每标的一行，轮询更新）
CREATE TABLE snapshot_realtime (
    symbol_id  BIGINT        PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    price      NUMERIC(12,3) NOT NULL,       -- 最新价
    change     NUMERIC(12,3) NOT NULL DEFAULT 0,   -- 涨跌额
    change_pct NUMERIC(12,4) NOT NULL DEFAULT 0,   -- 涨跌幅
    open       NUMERIC(12,3),
    high       NUMERIC(12,3),
    low        NUMERIC(12,3),
    pre_close  NUMERIC(12,3),                -- 昨收
    volume     BIGINT        NOT NULL DEFAULT 0,
    amount     NUMERIC(20,2) NOT NULL DEFAULT 0,
    turnover   NUMERIC(8,4),                 -- 换手率
    amplitude  NUMERIC(8,4),                 -- 振幅
    updated_at TIMESTAMP     NOT NULL DEFAULT now()
);

-- 个股特殊数据：总市值 / PE
CREATE TABLE stock_fundamentals (
    symbol_id  BIGINT        PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    market_cap NUMERIC(20,2),
    pe         NUMERIC(12,3),
    updated_at TIMESTAMP     NOT NULL DEFAULT now()
);

-- ETF 特殊数据：净值 / 溢价
CREATE TABLE etf_premiums (
    symbol_id  BIGINT        PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    nav        NUMERIC(12,3),
    premium    NUMERIC(8,4),                 -- 溢价率
    updated_at TIMESTAMP     NOT NULL DEFAULT now()
);

-- 指数特殊数据：指数总 PE
CREATE TABLE index_valuations (
    symbol_id  BIGINT        PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    pe         NUMERIC(12,3),
    updated_at TIMESTAMP     NOT NULL DEFAULT now()
);


-- ==============================================================
-- 用户域
-- ==============================================================

CREATE TABLE users (
    id            BIGSERIAL   PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email         VARCHAR(128),
    nickname      VARCHAR(64),
    avatar_url    VARCHAR(255),
    created_at    TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at    TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE user_watchlist (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol_id  BIGINT    NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (user_id, symbol_id)
);

CREATE TABLE user_memory_files (
    id           BIGSERIAL   PRIMARY KEY,
    user_id      BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_path    VARCHAR(512) NOT NULL,
    content_type VARCHAR(32) NOT NULL,       -- strategy / rule / preference
    updated_at   TIMESTAMP   NOT NULL DEFAULT now(),
    UNIQUE (user_id, file_path)
);

-- 支撑/压力位（B 区设置，K线图叠加）
CREATE TABLE support_resistance (
    id         BIGSERIAL   PRIMARY KEY,
    user_id    BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol_id  BIGINT      NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    type       VARCHAR(16) NOT NULL,         -- support / pressure
    price      NUMERIC(12,3) NOT NULL,
    note       VARCHAR(255),
    created_at TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_sr_user_symbol ON support_resistance(user_id, symbol_id);

-- ==============================================================
-- 策略 / AI 域
-- ==============================================================

CREATE TABLE conversations (
    id         BIGSERIAL   PRIMARY KEY,
    user_id    BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      VARCHAR(128) NOT NULL DEFAULT '新会话',
    created_at TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_conversations_updated BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE chat_messages (
    id              BIGSERIAL   PRIMARY KEY,
    conversation_id BIGINT      NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,    -- user / assistant / system
    symbol_id       BIGINT      REFERENCES symbols(id) ON DELETE SET NULL,
    content         TEXT        NOT NULL,
    tokens          INT,
    created_at      TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_msg_conv ON chat_messages(conversation_id, created_at);
CREATE INDEX idx_msg_symbol ON chat_messages(symbol_id);

CREATE TABLE trading_strategies (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(128) NOT NULL,
    description TEXT,                        -- 用户描述文字
    code        TEXT,                        -- 策略代码
    params      JSONB,                       -- 入场/止损/仓位参数
    status      VARCHAR(16) NOT NULL DEFAULT 'draft',  -- active / draft
    created_at  TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at  TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_strategy_user ON trading_strategies(user_id);
CREATE TRIGGER trg_strategies_updated BEFORE UPDATE ON trading_strategies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE backtest_tasks (
    id          BIGSERIAL   PRIMARY KEY,
    strategy_id BIGINT      NOT NULL REFERENCES trading_strategies(id) ON DELETE CASCADE,
    symbol_id   BIGINT      NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    period      VARCHAR(8)  NOT NULL DEFAULT '1d',     -- 回测K线周期 15m/1d/1w/1mon
    start_ts    TIMESTAMP,                              -- 回测区间起
    end_ts      TIMESTAMP,                              -- 回测区间止
    fill_on     VARCHAR(8)  NOT NULL DEFAULT 'close',  -- 撮合价 close/open
    status      VARCHAR(16) NOT NULL DEFAULT 'queued',  -- queued/running/success/failed
    progress    INT         NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at  TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_btask_status ON backtest_tasks(status);
CREATE TRIGGER trg_btasks_updated BEFORE UPDATE ON backtest_tasks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE backtest_results (
    id               BIGSERIAL    PRIMARY KEY,
    task_id          BIGINT       NOT NULL REFERENCES backtest_tasks(id) ON DELETE CASCADE,
    strategy_id      BIGINT       NOT NULL REFERENCES trading_strategies(id) ON DELETE CASCADE,
    symbol_id        BIGINT       NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    win_rate         NUMERIC(8,4),           -- 策略胜率
    profit_loss_ratio NUMERIC(8,4),          -- 盈亏比
    sharpe           NUMERIC(8,4),           -- 夏普比率
    total_buys       INT,
    total_sells      INT,
    annual_return    NUMERIC(8,4),           -- 年化收益率
    max_drawdown     NUMERIC(8,4),           -- 最大回撤
    metrics_json     JSONB,                  -- 扩展指标
    start_ts         TIMESTAMP,
    end_ts           TIMESTAMP,
    created_at       TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX idx_bresult_task ON backtest_results(task_id);
CREATE INDEX idx_bresult_strategy ON backtest_results(strategy_id);

-- ==============================================================
-- 运维域
-- ==============================================================

CREATE TABLE sync_tasks (
    id           BIGSERIAL   PRIMARY KEY,
    task_type    VARCHAR(32) NOT NULL,       -- kline_init / kline_incremental / realtime
    symbol_id    BIGINT      REFERENCES symbols(id) ON DELETE CASCADE,
    status       VARCHAR(16) NOT NULL DEFAULT 'running',  -- running/success/failed
    last_run_at  TIMESTAMP,
    next_run_at  TIMESTAMP
);
CREATE INDEX idx_sync_type_status ON sync_tasks(task_type, status);

CREATE TABLE task_logs (
    id         BIGSERIAL   PRIMARY KEY,
    task_type  VARCHAR(32),
    task_id    VARCHAR(64),                  -- Celery 任务ID
    request_id VARCHAR(64),                  -- 全链路 request-id
    status     VARCHAR(16),
    message    TEXT,
    created_at TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX idx_tlog_req ON task_logs(request_id);
CREATE INDEX idx_tlog_created ON task_logs(created_at);

COMMIT;

--阶段四更改表结构的sql语句
ALTER TABLE backtest_tasks
    ADD COLUMN period   VARCHAR(8)  NOT NULL DEFAULT '1d',
    ADD COLUMN start_ts TIMESTAMP,
    ADD COLUMN end_ts   TIMESTAMP,
    ADD COLUMN fill_on  VARCHAR(8)  NOT NULL DEFAULT 'close';

-- 可选：添加列注释（PostgreSQL）
COMMENT ON COLUMN backtest_tasks.period   IS '回测K线周期 15m/1d/1w/1mon';
COMMENT ON COLUMN backtest_tasks.start_ts IS '回测区间起';
COMMENT ON COLUMN backtest_tasks.end_ts   IS '回测区间止';
COMMENT ON COLUMN backtest_tasks.fill_on  IS '撮合价 close/open';