package com.example.stock_invest_backend.lof.service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class LofSymbolSourceSnapshot {

    private String source;
    private boolean fallbackToConfig;
    private int symbolCount;
    private Instant refreshedAt = Instant.now();
    private List<String> symbols = new ArrayList<>();

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public boolean isFallbackToConfig() {
        return fallbackToConfig;
    }

    public void setFallbackToConfig(boolean fallbackToConfig) {
        this.fallbackToConfig = fallbackToConfig;
    }

    public int getSymbolCount() {
        return symbolCount;
    }

    public void setSymbolCount(int symbolCount) {
        this.symbolCount = symbolCount;
    }

    public Instant getRefreshedAt() {
        return refreshedAt;
    }

    public void setRefreshedAt(Instant refreshedAt) {
        this.refreshedAt = refreshedAt;
    }

    public List<String> getSymbols() {
        return symbols;
    }

    public void setSymbols(List<String> symbols) {
        this.symbols = symbols;
    }
}
