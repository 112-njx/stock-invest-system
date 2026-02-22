package com.example.stock_invest_backend.backtest.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "backtest.engine")
public class BacktestEngineProperties {

    private String baseUrl = "http://localhost:8080";
    private String maPath = "/api/backtest/ma";
    private int timeoutMillis = 5000;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getMaPath() {
        return maPath;
    }

    public void setMaPath(String maPath) {
        this.maPath = maPath;
    }

    public int getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(int timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }
}
