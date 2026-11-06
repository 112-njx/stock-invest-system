-- ==============================================================
-- 种子数据：固定大盘指数 + 行业指数（G/H 区固定列表）
-- 幂等：按 (type, name) 唯一约束 upsert
-- 行业目录使用本地申万一级代码
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
-- ---- 本地申万一级行业（保持原 H 区显示方式）----
('801010.SL', '农林牧渔', 'index', 'SW', '', TRUE, 9),
('801020.SL', '采掘', 'index', 'SW', '', TRUE, 10),
('801030.SL', '化工', 'index', 'SW', '', TRUE, 11),
('801040.SL', '钢铁', 'index', 'SW', '', TRUE, 12),
('801050.SL', '有色金属', 'index', 'SW', '', TRUE, 13),
('801080.SL', '电子', 'index', 'SW', '', TRUE, 14),
('801110.SL', '家用电器', 'index', 'SW', '', TRUE, 15),
('801120.SL', '食品饮料', 'index', 'SW', '', TRUE, 16),
('801130.SL', '纺织服装', 'index', 'SW', '', TRUE, 17),
('801140.SL', '轻工制造', 'index', 'SW', '', TRUE, 18),
('801150.SL', '医药生物', 'index', 'SW', '', TRUE, 19),
('801160.SL', '公用事业', 'index', 'SW', '', TRUE, 20),
('801170.SL', '交通运输', 'index', 'SW', '', TRUE, 21),
('801180.SL', '房地产', 'index', 'SW', '', TRUE, 22),
('801200.SL', '商业贸易', 'index', 'SW', '', TRUE, 23),
('801210.SL', '休闲服务', 'index', 'SW', '', TRUE, 24),
('801230.SL', '综合', 'index', 'SW', '', TRUE, 25),
('801710.SL', '建筑材料', 'index', 'SW', '', TRUE, 26),
('801720.SL', '建筑装饰', 'index', 'SW', '', TRUE, 27),
('801730.SL', '电气设备', 'index', 'SW', '', TRUE, 28),
('801740.SL', '国防军工', 'index', 'SW', '', TRUE, 29),
('801750.SL', '计算机', 'index', 'SW', '', TRUE, 30),
('801760.SL', '传媒', 'index', 'SW', '', TRUE, 31),
('801770.SL', '通信', 'index', 'SW', '', TRUE, 32),
('801780.SL', '银行', 'index', 'SW', '', TRUE, 33),
('801790.SL', '非银金融', 'index', 'SW', '', TRUE, 34),
('801880.SL', '汽车', 'index', 'SW', '', TRUE, 35),
('801890.SL', '机械设备', 'index', 'SW', '', TRUE, 36)
ON CONFLICT (type, name) DO UPDATE
SET code = EXCLUDED.code, market = EXCLUDED.market, sort_order = EXCLUDED.sort_order,
    etf_linked = EXCLUDED.etf_linked,
    is_fixed_index = TRUE;

-- 查询验证：G/H 区列表按 sort_order 排序
SELECT sort_order, code, name, etf_linked FROM symbols
WHERE is_fixed_index ORDER BY sort_order;
