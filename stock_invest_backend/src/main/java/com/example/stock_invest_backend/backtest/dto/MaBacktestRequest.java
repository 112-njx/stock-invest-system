package com.example.stock_invest_backend.backtest.dto;

import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
public class MaBacktestRequest {

    private String symbol;
    private Integer period;
    private String startDate;
    private String endDate;

}
