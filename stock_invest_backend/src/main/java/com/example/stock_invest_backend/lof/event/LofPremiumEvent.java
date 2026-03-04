package com.example.stock_invest_backend.lof.event;

import com.example.stock_invest_backend.lof.dto.LofNavType;
import com.example.stock_invest_backend.lof.dto.LofPremiumStatus;

import java.math.BigDecimal;
import java.time.Instant;

/*
  为“按溢价率触发策略”预留标准化事件结构
  (DTO)
 */
public class LofPremiumEvent {

    private String eventId;
    private LofPremiumEventType eventType;
    private String symbol;
    private BigDecimal premiumRate;
    private LofPremiumStatus status;
    private LofNavType navType;
    private Long quoteTime;
    private Instant producedAt;
    private String source;
    private String version;
    private String message;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public LofPremiumEventType getEventType() {
        return eventType;
    }

    public void setEventType(LofPremiumEventType eventType) {
        this.eventType = eventType;
    }

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
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

    public LofNavType getNavType() {
        return navType;
    }

    public void setNavType(LofNavType navType) {
        this.navType = navType;
    }

    public Long getQuoteTime() {
        return quoteTime;
    }

    public void setQuoteTime(Long quoteTime) {
        this.quoteTime = quoteTime;
    }

    public Instant getProducedAt() {
        return producedAt;
    }

    public void setProducedAt(Instant producedAt) {
        this.producedAt = producedAt;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
