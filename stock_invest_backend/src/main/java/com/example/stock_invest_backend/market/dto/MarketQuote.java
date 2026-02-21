package com.example.stock_invest_backend.market.dto;

import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;

@Setter
@Getter
public class MarketQuote {

    private String symbol;
    private String source;
    private BigDecimal lastPrice;
    private BigDecimal changePercent;
    private BigDecimal openPrice;
    private BigDecimal highPrice;
    private BigDecimal lowPrice;
    private BigDecimal prevClosePrice;
    private Long volume;
    private BigDecimal turnover;
    private Long quoteTimestamp;

}
