package com.example.stock_invest_backend.lof.service;

import com.example.stock_invest_backend.lof.cache.LofPremiumCacheGateway;
import com.example.stock_invest_backend.lof.config.LofPremiumProperties;
import com.example.stock_invest_backend.lof.dto.LofPremiumItem;
import com.example.stock_invest_backend.lof.dto.LofPremiumResponse;
import com.example.stock_invest_backend.lof.dto.LofPremiumStatus;
import com.example.stock_invest_backend.lof.provider.LofPremiumDataProvider;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Service
public class LofPremiumSourceService {

    private static final Logger log = LoggerFactory.getLogger(LofPremiumSourceService.class);

    private final LofPremiumDataProvider dataProvider;
    private final LofSymbolSourceService lofSymbolSourceService;
    private final LofPremiumCacheGateway cacheGateway;
    private final LofPremiumEventService lofPremiumEventService;
    private final LofPremiumProperties properties;
    private final Counter requestCounter;
    private final Counter cacheHitCounter;
    private final Counter cacheMissCounter;
    private final Counter upstreamErrorCounter;
    private final Counter noNavCounter;
    private final Timer requestLatencyTimer;

    public LofPremiumSourceService(LofPremiumDataProvider dataProvider,
                                   LofSymbolSourceService lofSymbolSourceService,
                                   LofPremiumCacheGateway cacheGateway,
                                   LofPremiumEventService lofPremiumEventService,
                                   LofPremiumProperties properties,
                                   MeterRegistry meterRegistry) {
        this.dataProvider = dataProvider;
        this.lofSymbolSourceService = lofSymbolSourceService;
        this.cacheGateway = cacheGateway;
        this.lofPremiumEventService = lofPremiumEventService;
        this.properties = properties;
        this.requestCounter = meterRegistry.counter("lof.premium.requests.total");
        this.cacheHitCounter = meterRegistry.counter("lof.premium.cache.hit.total");
        this.cacheMissCounter = meterRegistry.counter("lof.premium.cache.miss.total");
        this.upstreamErrorCounter = meterRegistry.counter("lof.premium.items.upstream_error.total");
        this.noNavCounter = meterRegistry.counter("lof.premium.items.no_nav.total");
        this.requestLatencyTimer = meterRegistry.timer("lof.premium.request.latency");
    }

    public Mono<LofPremiumResponse> fetchPremiums(List<String> symbols) {
        long startNanos = System.nanoTime();
        requestCounter.increment();

        List<String> targetSymbols = lofSymbolSourceService.resolveSymbols(symbols);
        Map<String, LofPremiumItem> cachedItems = new LinkedHashMap<>();
        List<String> cacheMissSymbols = new ArrayList<>();

        for (String symbol : targetSymbols) {
            cacheGateway.get(symbol).ifPresentOrElse(item -> {
                item.setCacheHit(true);
                cachedItems.put(symbol, item);
                cacheHitCounter.increment();
            }, () -> {
                cacheMissSymbols.add(symbol);
                cacheMissCounter.increment();
            });
        }

        Mono<List<LofPremiumItem>> freshMono = cacheMissSymbols.isEmpty()
                ? Mono.just(List.of())
                : fetchInBatches(cacheMissSymbols)
                .doOnNext(items -> items.forEach(item -> {
                    item.setCacheHit(false);
                    if (StringUtils.hasText(item.getSymbol())) {
                        cacheGateway.put(item.getSymbol(), item);
                    }
                }));

        return freshMono.map(freshItems -> {
            Map<String, LofPremiumItem> merged = new LinkedHashMap<>(cachedItems);
            for (LofPremiumItem item : freshItems) {
                if (StringUtils.hasText(item.getSymbol())) {
                    merged.put(item.getSymbol(), item);
                }
            }

            List<LofPremiumItem> ordered = new ArrayList<>();
            for (String symbol : targetSymbols) {
                LofPremiumItem item = merged.get(symbol);
                if (item == null) {
                    item = buildMissingItem(symbol);
                }
                if (item.getStatus() == LofPremiumStatus.UPSTREAM_ERROR) {
                    upstreamErrorCounter.increment();
                } else if (item.getStatus() == LofPremiumStatus.NO_NAV) {
                    noNavCounter.increment();
                }
                ordered.add(item);
            }

            LofPremiumResponse response = new LofPremiumResponse();
            response.setItems(ordered);
            lofPremiumEventService.publishSnapshotAndAlerts(ordered);
            return response;
        }).doFinally(signalType -> {
            long elapsedNanos = System.nanoTime() - startNanos;
            requestLatencyTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
            log.info("LOF premium request done: symbols={}, cacheHit={}, cacheMiss={}, elapsedMs={}",
                    targetSymbols.size(), cachedItems.size(), cacheMissSymbols.size(),
                    TimeUnit.NANOSECONDS.toMillis(elapsedNanos));
        });
    }

    private Mono<List<LofPremiumItem>> fetchInBatches(List<String> symbols) {
        int batchSize = Math.max(20, Math.min(properties.getFetchBatchSize(), 200));
        List<List<String>> batches = splitBatches(symbols, batchSize);
        return Flux.fromIterable(batches)
                .concatMap(dataProvider::fetchPremiumItems)
                .flatMapIterable(items -> items)
                .collectList();
    }

    private List<List<String>> splitBatches(List<String> symbols, int batchSize) {
        List<List<String>> batches = new ArrayList<>();
        for (int i = 0; i < symbols.size(); i += batchSize) {
            int end = Math.min(i + batchSize, symbols.size());
            batches.add(symbols.subList(i, end));
        }
        return batches;
    }

    private LofPremiumItem buildMissingItem(String symbol) {
        LofPremiumItem item = new LofPremiumItem();
        item.setSymbol(symbol);
        item.setStatus(LofPremiumStatus.UPSTREAM_ERROR);
        item.setCacheHit(false);
        item.setMessage("no upstream data returned for this symbol");
        return item;
    }
}
