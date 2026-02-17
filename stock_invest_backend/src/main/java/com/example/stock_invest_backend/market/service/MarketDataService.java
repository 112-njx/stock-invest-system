package com.example.stock_invest_backend.market.service;

import com.example.stock_invest_backend.market.config.MarketDataProperties;
import com.example.stock_invest_backend.market.dto.MarketQuote;
import com.example.stock_invest_backend.market.provider.MarketDataProvider;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class MarketDataService {

    private final Map<String, MarketDataProvider> providerMap;
    private final MarketDataProperties marketDataProperties;

    public MarketDataService(List<MarketDataProvider> providers,
                             MarketDataProperties marketDataProperties) {
        this.providerMap = providers.stream()
                .collect(Collectors.toMap(MarketDataProvider::providerName, Function.identity()));
        this.marketDataProperties = marketDataProperties;
    }

    public Mono<List<MarketQuote>> fetchRealtimeQuotes(List<String> symbols) {
        String providerName = marketDataProperties.getProvider();
        MarketDataProvider provider = providerMap.get(providerName);
        if (provider == null) {
            return Mono.error(new IllegalStateException("Unsupported market provider: " + providerName));
        }

        return provider.fetchRealtimeQuotes(symbols);
    }
}
