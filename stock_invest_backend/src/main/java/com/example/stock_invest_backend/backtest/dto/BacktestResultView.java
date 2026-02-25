package com.example.stock_invest_backend.backtest.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class BacktestResultView {

    private Long id;
    private String strategyCode;
    private String symbol;
    private Integer period;
    private LocalDate startDate;
    private LocalDate endDate;
    private Integer totalSignals;
    private Integer winSignals;
    private BigDecimal successRate;
    private LocalDateTime createdAt;
    private List<String> crossUpDates = new ArrayList<>();
    private List<String> crossDownDates = new ArrayList<>();
    private List<BacktestSignalDto> signals = new ArrayList<>();
    private String payloadJson;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getStrategyCode() {
        return strategyCode;
    }

    public void setStrategyCode(String strategyCode) {
        this.strategyCode = strategyCode;
    }

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

    public LocalDate getStartDate() {
        return startDate;
    }

    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }

    public void setEndDate(LocalDate endDate) {
        this.endDate = endDate;
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

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public List<String> getCrossUpDates() {
        return crossUpDates;
    }

    public void setCrossUpDates(List<String> crossUpDates) {
        this.crossUpDates = crossUpDates;
    }

    public List<String> getCrossDownDates() {
        return crossDownDates;
    }

    public void setCrossDownDates(List<String> crossDownDates) {
        this.crossDownDates = crossDownDates;
    }

    public List<BacktestSignalDto> getSignals() {
        return signals;
    }

    public void setSignals(List<BacktestSignalDto> signals) {
        this.signals = signals;
    }

    public String getPayloadJson() {
        return payloadJson;
    }

    public void setPayloadJson(String payloadJson) {
        this.payloadJson = payloadJson;
    }
}
