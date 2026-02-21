package com.example.stock_invest_backend.market.service;

import com.example.stock_invest_backend.market.config.MarketDataProperties;
import com.example.stock_invest_backend.market.dto.MarketQuote;
import com.example.stock_invest_backend.market.provider.MarketDataProvider;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class MarketDataService {

    private final Map<String, MarketDataProvider> providerMap;
    private final MarketDataProperties marketDataProperties;

    public MarketDataService(List<MarketDataProvider> providers,
                             MarketDataProperties marketDataProperties) {
        this.providerMap = providers.stream()
                .collect(Collectors.toMap(
                        provider -> provider.providerName().toLowerCase(),
                        Function.identity()));
        this.marketDataProperties = marketDataProperties;
    }

    public Mono<List<MarketQuote>> fetchRealtimeQuotes(List<String> symbols) {
        return resolveCurrentProvider().fetchRealtimeQuotes(symbols);
    }

    public List<String> listAvailableProviders() {
        return new TreeSet<>(providerMap.keySet()).stream().toList();
    }

    public String currentProvider() {
        return marketDataProperties.getProvider();
    }

    private MarketDataProvider resolveCurrentProvider() {
        String providerName = marketDataProperties.getProvider();
        MarketDataProvider provider = providerMap.get(providerName.toLowerCase());
        if (provider == null) {
            throw new IllegalStateException("Unsupported market provider: " + providerName
                    + ", available providers: " + listAvailableProviders());
        }
        return provider;
    }
}
