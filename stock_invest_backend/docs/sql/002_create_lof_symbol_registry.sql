-- LOF symbol registry: metadata source for full-coverage symbol management.

CREATE TABLE IF NOT EXISTS lof_symbol_registry (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    symbol VARCHAR(16) NOT NULL COMMENT 'e.g. sz161129 / sh501018',
    name VARCHAR(128) NULL,
    market VARCHAR(8) NULL COMMENT 'SH / SZ',
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    priority INT NOT NULL DEFAULT 100,
    tags VARCHAR(256) NULL COMMENT 'comma-separated tags',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_symbol(symbol),
    KEY idx_enabled_priority(enabled, priority),
    KEY idx_market_enabled(market, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
