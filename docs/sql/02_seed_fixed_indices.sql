-- ==============================================================
-- 种子数据：固定大盘指数 + 行业指数（G/H 区固定列表）
-- 幂等：按 (type, name) 唯一约束 upsert
-- 行业指数 code 留空，由行情同步任务按名称回填
-- ==============================================================

INSERT INTO symbols (code, name, type, market, etf_linked, is_fixed_index, sort_order) VALUES
-- ---- 大盘指数（G区，sort 1~8）----
('000001', '上证指数',   'index', 'SSE',  '',        TRUE,  1),
('000300', '沪深300',    'index', 'CSI',  '510300',  TRUE,  2),
('399006', '创业板指',   'index', 'SZSE', '159915',  TRUE,  3),
('000688', '科创50',     'index', 'SSE',  '588000',  TRUE,  4),
('399001', '深证成指',   'index', 'SZSE', '',        TRUE,  5),
('000016', '上证50',     'index', 'SSE',  '510050',  TRUE,  6),
('000852', '中证1000',   'index', 'CSI',  '512100',  TRUE,  7),
('932000', '中证2000',   'index', 'CSI',  '563300',  TRUE,  8),
-- ---- 行业指数（H区，sort 9~36，code 待同步回填；etf_linked 为对应行业ETF代码）----
-- 说明：光学光电子、商业航天暂无直接对应行业ETF，etf_linked 留空显示 "--"。
('', '通信设备',   'index', 'SSE', '515880', TRUE, 9),
('', '半导体',     'index', 'SSE', '512480', TRUE, 10),
('', '元件',       'index', 'SSE', '515260', TRUE, 11),
('', '游戏',       'index', 'SSE', '159869', TRUE, 12),
('', '教育',       'index', 'SSE', '513360', TRUE, 13),
('', '半导体设备', 'index', 'SSE', '561980', TRUE, 14),
('', '光学光电子', 'index', 'SSE', '',      TRUE, 15),
('', '软件开发',   'index', 'SSE', '159035', TRUE, 16),
('', '消费电子',   'index', 'SSE', '159732', TRUE, 17),
('', '电网设备',   'index', 'SSE', '561380', TRUE, 18),
('', '文化传媒',   'index', 'SSE', '512980', TRUE, 19),
('', '机器人概念', 'index', 'SSE', '159770', TRUE, 20),
('', '电池',       'index', 'SSE', '159071', TRUE, 21),
('', '工业金属',   'index', 'SSE', '512400', TRUE, 22),
('', '光伏设备',   'index', 'SSE', '560230', TRUE, 23),
('', '贵金属',     'index', 'SSE', '518880', TRUE, 24),
('', '油气开采及服务', 'index', 'SSE', '563150', TRUE, 25),
('', '电力',       'index', 'SSE', '560450', TRUE, 26),
('', '证券',       'index', 'SSE', '512880', TRUE, 27),
('', '工程机械',   'index', 'SSE', '159161', TRUE, 28),
('', '房地产',     'index', 'SSE', '512200', TRUE, 29),
('', '煤炭开采加工','index', 'SSE', '515220', TRUE, 30),
('', '白酒',       'index', 'SSE', '512690', TRUE, 31),
('', '港口航运',   'index', 'SSE', '159666', TRUE, 32),
('', '公路铁路运输','index', 'SSE', '159666', TRUE, 33),
('', '汽车整车',   'index', 'SSE', '516110', TRUE, 34),
('', '保险',       'index', 'SSE', '512070', TRUE, 35),
('', '银行',       'index', 'SSE', '512800', TRUE, 36)
ON CONFLICT (type, name) DO UPDATE
SET sort_order = EXCLUDED.sort_order,
    etf_linked = EXCLUDED.etf_linked,
    is_fixed_index = TRUE;

-- 查询验证：G/H 区列表按 sort_order 排序
SELECT sort_order, code, name, etf_linked FROM symbols
WHERE is_fixed_index ORDER BY sort_order;
