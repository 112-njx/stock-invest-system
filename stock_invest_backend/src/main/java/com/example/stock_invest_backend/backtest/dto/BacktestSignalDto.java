package com.example.stock_invest_backend.backtest.dto;

import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;

@Setter
@Getter
//这是前端查询视图的DTO
public class BacktestSignalDto {

    private String date;
    private String signalCode;
    private String signal;
    private String legacySignal5;
    private BigDecimal closePrice;
    private BigDecimal ma;

}
