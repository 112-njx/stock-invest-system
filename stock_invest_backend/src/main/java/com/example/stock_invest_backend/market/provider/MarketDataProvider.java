package com.example.stock_invest_backend.market.provider;

import com.example.stock_invest_backend.market.dto.MarketQuote;
import reactor.core.publisher.Mono;

import java.util.List;

public interface MarketDataProvider {

    Mono<List<MarketQuote>> fetchRealtimeQuotes(List<String> symbols);

    String providerName();
}
