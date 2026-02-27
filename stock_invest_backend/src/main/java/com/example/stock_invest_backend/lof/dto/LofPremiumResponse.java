package com.example.stock_invest_backend.lof.dto;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class LofPremiumResponse {

    private String requestId = UUID.randomUUID().toString();
    private Instant generatedAt = Instant.now();
    private List<LofPremiumItem> items = new ArrayList<>();

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public Instant getGeneratedAt() {
        return generatedAt;
    }

    public void setGeneratedAt(Instant generatedAt) {
        this.generatedAt = generatedAt;
    }

    public List<LofPremiumItem> getItems() {
        return items;
    }

    public void setItems(List<LofPremiumItem> items) {
        this.items = items;
    }
}
