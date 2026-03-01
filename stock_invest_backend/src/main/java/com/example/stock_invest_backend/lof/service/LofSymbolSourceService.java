package com.example.stock_invest_backend.lof.service;

import com.example.stock_invest_backend.lof.config.LofPremiumProperties;
import com.example.stock_invest_backend.lof.repository.LofSymbolRegistryRecord;
import com.example.stock_invest_backend.lof.repository.LofSymbolRegistryRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.Instant;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/*
这里是lof标的来源决策中心
 */
@Service
public class LofSymbolSourceService {

    private static final Logger log = LoggerFactory.getLogger(LofSymbolSourceService.class);

    private final LofPremiumProperties properties;
    private final LofSymbolRegistryRepository symbolRegistryRepository;
    //这里是redis本地缓存机制
    private final AtomicReference<List<String>> cachedSymbols = new AtomicReference<>(List.of());
    private final AtomicLong cacheExpireAtMillis = new AtomicLong(0);

    public LofSymbolSourceService(LofPremiumProperties properties,
                                  LofSymbolRegistryRepository symbolRegistryRepository) {
        this.properties = properties;
        this.symbolRegistryRepository = symbolRegistryRepository;
    }

    public List<String> resolveSymbols(List<String> inputSymbols) {
        //显式传symbols就用请求参数
        if (inputSymbols != null && !inputSymbols.isEmpty()) {
            return normalizeAndLimit(inputSymbols);
        }

        //未传时按symbol-source读取 读取配置文件中的lof代码
        if ("config".equalsIgnoreCase(properties.getSymbolSource())) {
            return normalizeAndLimit(properties.getDefaultSymbols());
        }

        //如果当前时间<过期时间 并且缓存不为空 则直接返回缓存
        long now = System.currentTimeMillis();
        List<String> cached = cachedSymbols.get();
        if (now < cacheExpireAtMillis.get() && !cached.isEmpty()) {
            return cached;
        }
        return reloadFromDb().getSymbols();
    }

    //当缓存没有找到时，这里是查找数据库的逻辑
    public LofSymbolSourceSnapshot reloadFromDb() {
        LofSymbolSourceSnapshot snapshot = new LofSymbolSourceSnapshot();
        snapshot.setSource("db");
        snapshot.setRefreshedAt(Instant.now());

        try {
            List<LofSymbolRegistryRecord> records =
                    symbolRegistryRepository.findEnabledSymbols(properties.getSymbolDbQueryLimit());
            List<String> symbols = normalizeAndLimit(records.stream()
                    .map(LofSymbolRegistryRecord::getSymbol)
                    .toList());
            if (symbols.isEmpty()) {
                List<String> fallback = normalizeAndLimit(properties.getDefaultSymbols());
                snapshot.setFallbackToConfig(true);
                snapshot.setSource("config");
                snapshot.setSymbols(fallback);
                snapshot.setSymbolCount(fallback.size());
                cacheSymbols(fallback);
                return snapshot;
            }
            snapshot.setSymbols(symbols);
            snapshot.setSymbolCount(symbols.size());
            cacheSymbols(symbols);
            return snapshot;
        } catch (Exception ex) {
            log.warn("LOF symbol source db failed, fallback to config: {}", ex.getMessage());
            List<String> fallback = normalizeAndLimit(properties.getDefaultSymbols());
            snapshot.setFallbackToConfig(true);
            snapshot.setSource("config");
            snapshot.setSymbols(fallback);
            snapshot.setSymbolCount(fallback.size());
            cacheSymbols(fallback);
            return snapshot;
        }
    }

    public LofSymbolSourceSnapshot inspectCurrentSnapshot() {
        LofSymbolSourceSnapshot snapshot = new LofSymbolSourceSnapshot();
        snapshot.setSource("db");
        snapshot.setRefreshedAt(Instant.ofEpochMilli(Math.max(0, cacheExpireAtMillis.get())));
        List<String> symbols = cachedSymbols.get();
        snapshot.setSymbols(symbols);
        snapshot.setSymbolCount(symbols.size());
        return snapshot;
    }

    //这里是缓存刷新时间控制逻辑，用于防止误设置缓存时间（最少90s，最多300s）
    private void cacheSymbols(List<String> symbols) {
        cachedSymbols.set(symbols);
        int refreshSeconds = Math.max(60, Math.min(properties.getSymbolRefreshSeconds(), 300));
        cacheExpireAtMillis.set(System.currentTimeMillis() + refreshSeconds * 1000L);
    }

    private List<String> normalizeAndLimit(List<String> symbols) {
        return symbols.stream()
                .map(String::trim)
                .map(String::toLowerCase)
                .filter(StringUtils::hasText)
                .distinct()
                .limit(5000)
                .toList();
    }
}
