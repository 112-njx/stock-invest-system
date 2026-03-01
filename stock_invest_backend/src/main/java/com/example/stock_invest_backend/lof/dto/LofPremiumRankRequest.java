package com.example.stock_invest_backend.lof.dto;

public class LofPremiumRankRequest {

    private String order = "desc";
    private Integer limit = 20;
    private Boolean onlyStatusOk = false;
    private Boolean tradingOnly = false;

    public String getOrder() {
        return order;
    }

    public void setOrder(String order) {
        this.order = order;
    }

    public Integer getLimit() {
        return limit;
    }

    public void setLimit(Integer limit) {
        this.limit = limit;
    }

    public Boolean getOnlyStatusOk() {
        return onlyStatusOk;
    }

    public void setOnlyStatusOk(Boolean onlyStatusOk) {
        this.onlyStatusOk = onlyStatusOk;
    }

    public Boolean getTradingOnly() {
        return tradingOnly;
    }

    public void setTradingOnly(Boolean tradingOnly) {
        this.tradingOnly = tradingOnly;
    }
}
