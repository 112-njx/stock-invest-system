package com.example.stock_invest_backend.pay;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.util.Date;

@Data
@TableName("t_pay_order")
public class PayOrder {

    public static final byte STATE_INIT = 0;
    public static final byte STATE_ING = 1;
    public static final byte STATE_SUCCESS = 2;
    public static final byte STATE_FAIL = 3;
    public static final byte STATE_CLOSED = 6;

    @TableId
    private String payOrderId;
    private Long amount;
    private String subject;
    private Byte state;
    private String channelOrderNo;
    private Date expiredTime;
    private Date successTime;
    private Date createdAt;
    private Date updatedAt;
}
