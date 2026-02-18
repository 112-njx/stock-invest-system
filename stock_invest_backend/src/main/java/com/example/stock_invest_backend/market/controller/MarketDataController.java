package com.example.stock_invest_backend.market.controller;

import com.example.stock_invest_backend.market.dto.MarketQuote;
import com.example.stock_invest_backend.market.service.MarketDataService;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/market")
public class MarketDataController {

    private final MarketDataService marketDataService;

    public MarketDataController(MarketDataService marketDataService) {
        this.marketDataService = marketDataService;
    }

    @GetMapping("/quotes")
    public Mono<List<MarketQuote>> quotes(@RequestParam("symbols") String symbols) {
        List<String> symbolList = Arrays.stream(symbols.split(","))
                .map(String::trim)
                .filter(StringUtils::hasText)
                .toList();

        return marketDataService.fetchRealtimeQuotes(symbolList);
    }

    @GetMapping("/providers")
    public Map<String, Object> providers() {
        return Map.of(
                "currentProvider", marketDataService.currentProvider(),
                "availableProviders", marketDataService.listAvailableProviders());
    }
}
