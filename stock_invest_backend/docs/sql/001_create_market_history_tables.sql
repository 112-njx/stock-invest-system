-- MA 回测阶段：最小历史数据结构（MySQL 8+）
-- 用途：先落地 3 个月日 K 数据，供 C++ 回测引擎直接读取。

CREATE TABLE IF NOT EXISTS stock_daily_kline (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    symbol VARCHAR(16) NOT NULL COMMENT '如 sh600519 / sz000001',
    trade_date DATE NOT NULL,
    open_price DECIMAL(18,4) NOT NULL,
    high_price DECIMAL(18,4) NOT NULL,
    low_price DECIMAL(18,4) NOT NULL,
    close_price DECIMAL(18,4) NOT NULL,
    volume BIGINT NULL,
    turnover DECIMAL(20,2) NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_symbol_date(symbol, trade_date),
    KEY idx_symbol_trade_date(symbol, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS strategy_backtest_result (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_code VARCHAR(64) NOT NULL COMMENT '如 MA_CROSS_5',
    symbol VARCHAR(16) NOT NULL,
    period INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_signals INT NOT NULL,
    win_signals INT NOT NULL,
    success_rate DECIMAL(8,4) NOT NULL COMMENT '0~1',
    payload_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_strategy_symbol(strategy_code, symbol),
    KEY idx_created_at(created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
