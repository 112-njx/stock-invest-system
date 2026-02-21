package com.example.stock_invest_backend.backtest.dto;

import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;

@Setter
@Getter
public class MaBacktestResponse {

    private String symbol;
    private Integer period;
    private Integer totalSignals;
    private Integer winSignals;
    private BigDecimal successRate;
    private String source;
    private String message;

}
