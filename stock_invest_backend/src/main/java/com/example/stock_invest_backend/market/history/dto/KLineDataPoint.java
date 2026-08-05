package com.example.stock_invest_backend.market.history.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

public class KLineDataPoint {

    private LocalDate tradeDate;
    private BigDecimal open;
    private BigDecimal high;
    private BigDecimal low;
    private BigDecimal close;
    private Long volume;
    private BigDecimal turnover;

    public static KLineDataPoint from(StockDailyKlineRecord r) {
        KLineDataPoint p = new KLineDataPoint();
        p.tradeDate = r.getTradeDate();
        p.open = r.getOpenPrice();
        p.high = r.getHighPrice();
        p.low = r.getLowPrice();
        p.close = r.getClosePrice();
        p.volume = r.getVolume();
        p.turnover = r.getTurnover();
        return p;
    }

    public LocalDate getTradeDate() { return tradeDate; }
    public void setTradeDate(LocalDate tradeDate) { this.tradeDate = tradeDate; }

    public BigDecimal getOpen() { return open; }
    public void setOpen(BigDecimal open) { this.open = open; }

    public BigDecimal getHigh() { return high; }
    public void setHigh(BigDecimal high) { this.high = high; }

    public BigDecimal getLow() { return low; }
    public void setLow(BigDecimal low) { this.low = low; }

    public BigDecimal getClose() { return close; }
    public void setClose(BigDecimal close) { this.close = close; }

    public Long getVolume() { return volume; }
    public void setVolume(Long volume) { this.volume = volume; }

    public BigDecimal getTurnover() { return turnover; }
    public void setTurnover(BigDecimal turnover) { this.turnover = turnover; }
}
