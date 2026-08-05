package com.example.stock_invest_backend.pay;

import lombok.Data;

@Data
public class CreatePayOrderResponse {
    private String payOrderId;
    private Long amount;
    private String subject;
    private String payForm; // 支付宝返回的HTML表单，前端直接渲染跳转
}
