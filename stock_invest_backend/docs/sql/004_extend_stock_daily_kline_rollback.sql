-- 阶段二回滚：恢复 stock_daily_kline 至 001 的唯一键与字段
-- 注意：回滚会丢失 adjust_type 列数据，请提前备份

SET @new_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'stock_daily_kline'
      AND INDEX_NAME = 'uk_symbol_date_adjust'
);
SET @stmt := IF(@new_exists > 0,
    'ALTER TABLE stock_daily_kline DROP INDEX uk_symbol_date_adjust',
    'SELECT ''uk_symbol_date_adjust already dropped'' AS note');
PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;

SET @idx_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'stock_daily_kline'
      AND INDEX_NAME = 'uk_symbol_date'
);
SET @stmt := IF(@idx_exists = 0,
    'ALTER TABLE stock_daily_kline ADD UNIQUE KEY uk_symbol_date (symbol, trade_date)',
    'SELECT ''uk_symbol_date already exists'' AS note');
PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'stock_daily_kline'
      AND COLUMN_NAME = 'adjust_type'
);
SET @stmt := IF(@col_exists > 0,
    'ALTER TABLE stock_daily_kline DROP COLUMN adjust_type',
    'SELECT ''adjust_type already dropped'' AS note');
PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;
