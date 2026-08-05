-- 支付订单表（支付宝沙箱，仅支持 10元/20元 两档）
CREATE TABLE IF NOT EXISTS t_pay_order (
    pay_order_id   VARCHAR(30)  PRIMARY KEY COMMENT '系统订单号',
    amount         BIGINT       NOT NULL COMMENT '金额,单位分(1000=10元,2000=20元)',
    subject        VARCHAR(64)  NOT NULL COMMENT '商品标题',
    state          TINYINT      NOT NULL DEFAULT 0 COMMENT '0-生成,1-支付中,2-成功,3-失败,6-关闭',
    channel_order_no VARCHAR(64) DEFAULT NULL COMMENT '支付宝交易号(trade_no)',
    expired_time   DATETIME     NOT NULL COMMENT '订单过期时间',
    success_time   DATETIME     DEFAULT NULL COMMENT '支付成功时间',
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_state_expired (state, expired_time),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付订单表';
