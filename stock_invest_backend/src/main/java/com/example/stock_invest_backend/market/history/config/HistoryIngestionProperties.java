package com.example.stock_invest_backend.market.history.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

@Component
@ConfigurationProperties(prefix = "market.history.ingestion")
public class HistoryIngestionProperties {

    private boolean enabled = false;
    private int months = 3;
    private List<String> defaultSymbols = new ArrayList<>(List.of("sh600519", "sz000001"));

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getMonths() {
        return months;
    }

    public void setMonths(int months) {
        this.months = months;
    }

    public List<String> getDefaultSymbols() {
        return defaultSymbols;
    }

    public void setDefaultSymbols(List<String> defaultSymbols) {
        this.defaultSymbols = defaultSymbols;
    }
}
