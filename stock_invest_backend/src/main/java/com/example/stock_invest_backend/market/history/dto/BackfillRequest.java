package com.example.stock_invest_backend.market.history.dto;

import java.time.LocalDate;

public class BackfillRequest {

    private String symbol;
    private LocalDate startDate;
    private LocalDate endDate;
    private String adjustType = "qfq";

    public String getSymbol() { return symbol; }
    public void setSymbol(String symbol) { this.symbol = symbol; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) { this.startDate = startDate; }

    public LocalDate getEndDate() { return endDate; }
    public void setEndDate(LocalDate endDate) { this.endDate = endDate; }

    public String getAdjustType() { return adjustType; }
    public void setAdjustType(String adjustType) { this.adjustType = adjustType; }
}
