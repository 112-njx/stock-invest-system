package com.example.stock_invest_backend.backtest.dto;

import java.math.BigDecimal;

public class MaBacktestResponse {

    private String symbol;
    private Integer period;
    private Integer totalSignals;
    private Integer winSignals;
    private BigDecimal successRate;
    private String source;
    private String message;

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
    }

    public Integer getPeriod() {
        return period;
    }

    public void setPeriod(Integer period) {
        this.period = period;
    }

    public Integer getTotalSignals() {
        return totalSignals;
    }

    public void setTotalSignals(Integer totalSignals) {
        this.totalSignals = totalSignals;
    }

    public Integer getWinSignals() {
        return winSignals;
    }

    public void setWinSignals(Integer winSignals) {
        this.winSignals = winSignals;
    }

    public BigDecimal getSuccessRate() {
        return successRate;
    }

    public void setSuccessRate(BigDecimal successRate) {
        this.successRate = successRate;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
