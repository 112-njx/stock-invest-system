package com.example.stock_invest_backend.lof.dto;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class LofPremiumRankResponse {

    private List<LofPremiumItem> items = new ArrayList<>();
    private Integer total = 0;
    private List<String> filtersApplied = new ArrayList<>();
    private String tradingWindow = "UNKNOWN";
    private String message;
    private Instant generatedAt = Instant.now();

    public List<LofPremiumItem> getItems() {
        return items;
    }

    public void setItems(List<LofPremiumItem> items) {
        this.items = items;
    }

    public Integer getTotal() {
        return total;
    }

    public void setTotal(Integer total) {
        this.total = total;
    }

    public List<String> getFiltersApplied() {
        return filtersApplied;
    }

    public void setFiltersApplied(List<String> filtersApplied) {
        this.filtersApplied = filtersApplied;
    }

    public String getTradingWindow() {
        return tradingWindow;
    }

    public void setTradingWindow(String tradingWindow) {
        this.tradingWindow = tradingWindow;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public Instant getGeneratedAt() {
        return generatedAt;
    }

    public void setGeneratedAt(Instant generatedAt) {
        this.generatedAt = generatedAt;
    }
}
