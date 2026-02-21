package com.example.stock_invest_backend.backtest.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Setter
@Getter
@ConfigurationProperties(prefix = "backtest.engine")
public class BacktestEngineProperties {

    private String baseUrl = "http://localhost:8080";
    private String maPath = "/api/backtest/ma";
    private int timeoutMillis = 5000;

}
