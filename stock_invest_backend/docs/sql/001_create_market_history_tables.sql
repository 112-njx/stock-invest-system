-- MA 回测阶段：最小历史数据结构（MySQL 8+）
-- 用途：先落地 3 个月日 K 数据，供 C++ 回测引擎直接读取。

#数据库名称:invest_stock_system
#这是交易日线数据库
CREATE TABLE IF NOT EXISTS stock_daily_kline (
                                                 id BIGINT PRIMARY KEY AUTO_INCREMENT,
                                                 symbol VARCHAR(16) NOT NULL COMMENT '如 sh600519 / sz000001', #股票代码
                                                 trade_date DATE NOT NULL,
                                                 open_price DECIMAL(18,4) NOT NULL,
                                                 high_price DECIMAL(18,4) NOT NULL,
                                                 low_price DECIMAL(18,4) NOT NULL,
                                                 close_price DECIMAL(18,4) NOT NULL,
                                                 volume BIGINT NULL,
                                                 turnover DECIMAL(20,2) NULL,
                                                 source VARCHAR(32) NOT NULL DEFAULT 'unknown',   #行情数据来源
                                                 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,   #创建时间
                                                 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,  #最新更新时间
                                                 UNIQUE KEY uk_symbol_date(symbol, trade_date),   #同一股票在一天内只能有一次交易记录
                                                 KEY idx_symbol_trade_date(symbol, trade_date)    #提高区间查询效率
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

#这是回测结果持久化层表，用于存储计算结果，可以适用于多种策略
CREATE TABLE IF NOT EXISTS strategy_backtest_result (
                                                        id BIGINT PRIMARY KEY AUTO_INCREMENT,
                                                        strategy_code VARCHAR(64) NOT NULL COMMENT 'MA_CROSS_5', #策略名称，如 MA_CROSS_5
                                                        symbol VARCHAR(16) NOT NULL,    #股票代码
                                                        period INT NOT NULL,     #回测总时间（天数）
                                                        start_date DATE NOT NULL,   #开始时间
                                                        end_date DATE NOT NULL,     #结束时间
                                                        total_signals INT NOT NULL,   #总买入信号
                                                        win_signals INT NOT NULL,     #买入盈利的信号
                                                        success_rate DECIMAL(8,4) NOT NULL COMMENT '0~1',     #成功率
                                                        payload_json JSON NULL,   #（以后的）扩展数据
                                                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,   #创建时间
                                                        KEY idx_strategy_symbol(strategy_code, symbol),
                                                        KEY idx_created_at(created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;