package com.example.stock_invest_backend.market.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Setter
@Getter
@ConfigurationProperties(prefix = "market.data.eastmoney")
public class EastMoneyProperties {
    private String baseUrl = "https://push2.eastmoney.com";
    private String quotePath = "/api/qt/ulist.np/get";
    private String fields = "f12,f13,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18,f124";
    private int timeoutMillis = 5000;
}
