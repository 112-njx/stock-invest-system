package com.example.stock_invest_backend.lof.dto;

import java.math.BigDecimal;

public class LofPremiumItem {

    private String symbol;
    private String name;
    private BigDecimal lastPrice;
    private BigDecimal nav;
    private LofNavType navType;
    private BigDecimal premiumRate;
    private LofPremiumStatus status;
    private Long quoteTime;
    private String navDate;
    private boolean cacheHit;
    private String message;

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getLastPrice() {
        return lastPrice;
    }

    public void setLastPrice(BigDecimal lastPrice) {
        this.lastPrice = lastPrice;
    }

    public BigDecimal getNav() {
        return nav;
    }

    public void setNav(BigDecimal nav) {
        this.nav = nav;
    }

    public LofNavType getNavType() {
        return navType;
    }

    public void setNavType(LofNavType navType) {
        this.navType = navType;
    }

    public BigDecimal getPremiumRate() {
        return premiumRate;
    }

    public void setPremiumRate(BigDecimal premiumRate) {
        this.premiumRate = premiumRate;
    }

    public LofPremiumStatus getStatus() {
        return status;
    }

    public void setStatus(LofPremiumStatus status) {
        this.status = status;
    }

    public Long getQuoteTime() {
        return quoteTime;
    }

    public void setQuoteTime(Long quoteTime) {
        this.quoteTime = quoteTime;
    }

    public String getNavDate() {
        return navDate;
    }

    public void setNavDate(String navDate) {
        this.navDate = navDate;
    }

    public boolean isCacheHit() {
        return cacheHit;
    }

    public void setCacheHit(boolean cacheHit) {
        this.cacheHit = cacheHit;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
