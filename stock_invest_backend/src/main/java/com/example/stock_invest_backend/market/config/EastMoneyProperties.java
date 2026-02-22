package com.example.stock_invest_backend.market.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "market.data.eastmoney")
public class EastMoneyProperties {

    private String baseUrl = "https://push2.eastmoney.com";
    private String quotePath = "/api/qt/ulist.np/get";
    private String fields = "f12,f13,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18,f124";
    private int timeoutMillis = 5000;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getQuotePath() {
        return quotePath;
    }

    public void setQuotePath(String quotePath) {
        this.quotePath = quotePath;
    }

    public String getFields() {
        return fields;
    }

    public void setFields(String fields) {
        this.fields = fields;
    }

    public int getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(int timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }
}
