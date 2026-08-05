package com.example.stock_invest_backend.pay;

import lombok.Data;
import java.util.Date;

@Data
public class PayOrderStatusResponse {
    private String payOrderId;
    private Long amount;
    private String subject;
    private Byte state;
    private String stateDesc;
    private String channelOrderNo;
    private Date successTime;
    private Date createdAt;

    public static PayOrderStatusResponse fromEntity(PayOrder order) {
        PayOrderStatusResponse resp = new PayOrderStatusResponse();
        resp.setPayOrderId(order.getPayOrderId());
        resp.setAmount(order.getAmount());
        resp.setSubject(order.getSubject());
        resp.setState(order.getState());
        resp.setStateDesc(describeState(order.getState()));
        resp.setChannelOrderNo(order.getChannelOrderNo());
        resp.setSuccessTime(order.getSuccessTime());
        resp.setCreatedAt(order.getCreatedAt());
        return resp;
    }

    private static String describeState(Byte state) {
        if (state == null) return "未知";
        return switch (state) {
            case PayOrder.STATE_INIT -> "待支付";
            case PayOrder.STATE_ING -> "支付中";
            case PayOrder.STATE_SUCCESS -> "支付成功";
            case PayOrder.STATE_FAIL -> "支付失败";
            case PayOrder.STATE_CLOSED -> "已关闭";
            default -> "未知";
        };
    }
}
