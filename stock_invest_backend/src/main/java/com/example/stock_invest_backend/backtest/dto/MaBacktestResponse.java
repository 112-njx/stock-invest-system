package com.example.stock_invest_backend.backtest.dto;

import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Setter
@Getter
public class MaBacktestResponse {

    private String strategyCode;
    private String symbol;
    private Integer period;
    private Integer totalSignals;
    private Integer winSignals;
    private BigDecimal successRate;
    private Integer records;
    private String source;
    private String message;
    private List<String> crossUpDates = new ArrayList<>();
    private List<String> crossDownDates = new ArrayList<>();
    private List<BacktestSignalDto> signals = new ArrayList<>();

}
