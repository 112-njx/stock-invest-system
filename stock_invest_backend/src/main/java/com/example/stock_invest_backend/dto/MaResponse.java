package com.example.stock_invest_backend.dto;

import lombok.Data;

@Data
public class MaResponse {
    private String symbol;
    private int period;
    private double ma;
}
