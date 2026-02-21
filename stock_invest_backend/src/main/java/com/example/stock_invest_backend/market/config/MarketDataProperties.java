package com.example.stock_invest_backend.market.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Setter
@Getter
@ConfigurationProperties(prefix = "market.data")
public class MarketDataProperties {
    private String provider = "eastmoney";
}
