package com.example.stock_invest_backend.lof.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
@ConfigurationProperties(prefix = "lof.premium")
public class LofPremiumProperties {

    private List<String> defaultSymbols = List.of("sz161129", "sz161130");
    private String symbolSource = "db";
    private int symbolRefreshSeconds = 120;
    private int symbolDbQueryLimit = 2000;
    private int fetchBatchSize = 100;
    private int cacheTtlSeconds = 5;
    private int retryMaxAttempts = 3;
    private int retryBaseDelayMs = 200;
    private int rateLimitPermitsPerSecond = 5;
    private String fields = "f12,f13,f14,f2,f18,f124,f257,f258,f339,f340";
    private List<String> iopvFieldCodes = List.of("f340", "f258", "f257");
    private List<String> prevNavFieldCodes = List.of("f339", "f18");

    public List<String> getDefaultSymbols() {
        return defaultSymbols;
    }

    public void setDefaultSymbols(List<String> defaultSymbols) {
        this.defaultSymbols = defaultSymbols;
    }

    public String getSymbolSource() {
        return symbolSource;
    }

    public void setSymbolSource(String symbolSource) {
        this.symbolSource = symbolSource;
    }

    public int getSymbolRefreshSeconds() {
        return symbolRefreshSeconds;
    }

    public void setSymbolRefreshSeconds(int symbolRefreshSeconds) {
        this.symbolRefreshSeconds = symbolRefreshSeconds;
    }

    public int getSymbolDbQueryLimit() {
        return symbolDbQueryLimit;
    }

    public void setSymbolDbQueryLimit(int symbolDbQueryLimit) {
        this.symbolDbQueryLimit = symbolDbQueryLimit;
    }

    public int getFetchBatchSize() {
        return fetchBatchSize;
    }

    public void setFetchBatchSize(int fetchBatchSize) {
        this.fetchBatchSize = fetchBatchSize;
    }

    public int getCacheTtlSeconds() {
        return cacheTtlSeconds;
    }

    public void setCacheTtlSeconds(int cacheTtlSeconds) {
        this.cacheTtlSeconds = cacheTtlSeconds;
    }

    public int getRetryMaxAttempts() {
        return retryMaxAttempts;
    }

    public void setRetryMaxAttempts(int retryMaxAttempts) {
        this.retryMaxAttempts = retryMaxAttempts;
    }

    public int getRetryBaseDelayMs() {
        return retryBaseDelayMs;
    }

    public void setRetryBaseDelayMs(int retryBaseDelayMs) {
        this.retryBaseDelayMs = retryBaseDelayMs;
    }

    public int getRateLimitPermitsPerSecond() {
        return rateLimitPermitsPerSecond;
    }

    public void setRateLimitPermitsPerSecond(int rateLimitPermitsPerSecond) {
        this.rateLimitPermitsPerSecond = rateLimitPermitsPerSecond;
    }

    public String getFields() {
        return fields;
    }

    public void setFields(String fields) {
        this.fields = fields;
    }

    public List<String> getIopvFieldCodes() {
        return iopvFieldCodes;
    }

    public void setIopvFieldCodes(List<String> iopvFieldCodes) {
        this.iopvFieldCodes = iopvFieldCodes;
    }

    public List<String> getPrevNavFieldCodes() {
        return prevNavFieldCodes;
    }

    public void setPrevNavFieldCodes(List<String> prevNavFieldCodes) {
        this.prevNavFieldCodes = prevNavFieldCodes;
    }
}
