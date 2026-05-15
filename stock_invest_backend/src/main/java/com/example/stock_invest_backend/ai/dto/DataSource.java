package com.example.stock_invest_backend.ai.dto;

public class DataSource {

    private String api;
    private String purpose;

    public DataSource() {
    }

    public DataSource(String api, String purpose) {
        this.api = api;
        this.purpose = purpose;
    }

    public String getApi() {
        return api;
    }

    public void setApi(String api) {
        this.api = api;
    }

    public String getPurpose() {
        return purpose;
    }

    public void setPurpose(String purpose) {
        this.purpose = purpose;
    }
}
