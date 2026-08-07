-- ==============================================================
-- 种子数据：固定大盘指数 + 行业指数（G/H 区固定列表）
-- 幂等：按 (type, name) 唯一约束 upsert
-- 行业指数 code 留空，由行情同步任务按名称回填
-- ==============================================================

INSERT INTO symbols (code, name, type, market, etf_linked, is_fixed_index, sort_order) VALUES
-- ---- 大盘指数（G区，sort 1~14）----
('000001', '上证指数',   'index', 'SSE',  '',        TRUE,  1),
('000300', '沪深300',    'index', 'CSI',  '510300',  TRUE,  2),
('399006', '创业板指',   'index', 'SZSE', '159915',  TRUE,  3),
('000688', '科创50',     'index', 'SSE',  '588000',  TRUE,  4),
('399001', '深证成指',   'index', 'SZSE', '',        TRUE,  5),
('000016', '上证50',     'index', 'SSE',  '510050',  TRUE,  6),
('000852', '中证1000',   'index', 'CSI',  '512100',  TRUE,  7),
('932000', '中证2000',   'index', 'CSI',  '563300',  TRUE,  8),
('N225',   '日经指数',   'index', 'JP',   '513520',  TRUE,  9),
('KS11',   '韩国综合',   'index', 'KR',   '',        TRUE, 10),
('DJI',    '道琼斯指数', 'index', 'US',   '',        TRUE, 11),
('IXIC',   '纳斯达克指数','index', 'US',   '513100',  TRUE, 12),
('INX',    '标普500',    'index', 'US',   '513500',  TRUE, 13),
('XAU',    '现货黄金',   'index', 'XAU',  '518880',  TRUE, 14),
-- ---- 行业指数（H区，sort 15~49，code 待同步回填）----
('', '通信设备',   'index', 'SSE', '', TRUE, 15),
('', '半导体',     'index', 'SSE', '', TRUE, 16),
('', '元件',       'index', 'SSE', '', TRUE, 17),
('', '游戏',       'index', 'SSE', '', TRUE, 18),
('', '教育',       'index', 'SSE', '', TRUE, 19),
('', '半导体设备', 'index', 'SSE', '', TRUE, 20),
('', '光学光电子', 'index', 'SSE', '', TRUE, 21),
('', '软件开发',   'index', 'SSE', '', TRUE, 22),
('', '消费电子',   'index', 'SSE', '', TRUE, 23),
('', '创新药',     'index', 'SSE', '', TRUE, 24),
('', '商业航天',   'index', 'SSE', '', TRUE, 25),
('', '电网设备',   'index', 'SSE', '', TRUE, 26),
('', '文化传媒',   'index', 'SSE', '', TRUE, 27),
('', '军工',       'index', 'SSE', '', TRUE, 28),
('', '机器人概念', 'index', 'SSE', '', TRUE, 29),
('', '电池',       'index', 'SSE', '', TRUE, 30),
('', '工业金属',   'index', 'SSE', '', TRUE, 31),
('', '光伏设备',   'index', 'SSE', '', TRUE, 32),
('', '贵金属',     'index', 'SSE', '', TRUE, 33),
('', '消费',       'index', 'SSE', '', TRUE, 34),
('', '细分化工',   'index', 'SSE', '', TRUE, 35),
('', '油气开采及服务', 'index', 'SSE', '', TRUE, 36),
('', '电力',       'index', 'SSE', '', TRUE, 37),
('', '证券',       'index', 'SSE', '', TRUE, 38),
('', '工程机械',   'index', 'SSE', '', TRUE, 39),
('', '农业种植',   'index', 'SSE', '', TRUE, 40),
('', '房地产',     'index', 'SSE', '', TRUE, 41),
('', '煤炭开采加工','index', 'SSE', '', TRUE, 42),
('', '猪肉',       'index', 'SSE', '', TRUE, 43),
('', '白酒',       'index', 'SSE', '', TRUE, 44),
('', '港口航运',   'index', 'SSE', '', TRUE, 45),
('', '公路铁路运输','index', 'SSE', '', TRUE, 46),
('', '汽车整车',   'index', 'SSE', '', TRUE, 47),
('', '保险',       'index', 'SSE', '', TRUE, 48),
('', '银行',       'index', 'SSE', '', TRUE, 49)
ON CONFLICT (type, name) DO UPDATE
SET sort_order = EXCLUDED.sort_order,
    is_fixed_index = TRUE;

-- 查询验证：G/H 区列表按 sort_order 排序
SELECT sort_order, code, name, etf_linked FROM symbols
WHERE is_fixed_index ORDER BY sort_order;
