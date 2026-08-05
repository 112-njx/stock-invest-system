package com.example.stock_invest_backend.pay;

import lombok.Data;

@Data
public class CreatePayOrderRequest {
    private Long amount; // 1000=10元, 2000=20元
}
