-- 阶段二：扩展 stock_daily_kline，支持 AkShare 采集与复权类型区分
-- 目标：
--   1. 新增 adjust_type 列，区分 qfq / hfq / none
--   2. 唯一键升级：(symbol, trade_date, adjust_type)
--   3. source / updated_at 若已存在则跳过（001 已建立）
-- 说明：
--   MySQL 8+，需具备 DDL 权限；执行前建议在测试库跑通再上生产。

-- Step 1: 新增 adjust_type 列（幂等）
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'stock_daily_kline'
      AND COLUMN_NAME = 'adjust_type'
);
SET @stmt := IF(@col_exists = 0,
    'ALTER TABLE stock_daily_kline ADD COLUMN adjust_type VARCHAR(8) NOT NULL DEFAULT ''none'' COMMENT ''复权类型 qfq/hfq/none'' AFTER source',
    'SELECT ''adjust_type already exists'' AS note');
PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;

-- Step 2: 已有历史数据回填默认 qfq（AkShare 补数默认前复权，与阶段一约定一致）
UPDATE stock_daily_kline SET adjust_type = 'qfq' WHERE adjust_type = 'none';

-- Step 3: 唯一键升级：先删旧唯一键 uk_symbol_date，再建带 adjust_type 的新键
SET @idx_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'stock_daily_kline'
      AND INDEX_NAME = 'uk_symbol_date'
);
SET @stmt := IF(@idx_exists > 0,
    'ALTER TABLE stock_daily_kline DROP INDEX uk_symbol_date',
    'SELECT ''uk_symbol_date already dropped'' AS note');
PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;

SET @new_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'stock_daily_kline'
      AND INDEX_NAME = 'uk_symbol_date_adjust'
);
SET @stmt := IF(@new_exists = 0,
    'ALTER TABLE stock_daily_kline ADD UNIQUE KEY uk_symbol_date_adjust (symbol, trade_date, adjust_type)',
    'SELECT ''uk_symbol_date_adjust already exists'' AS note');
PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;
