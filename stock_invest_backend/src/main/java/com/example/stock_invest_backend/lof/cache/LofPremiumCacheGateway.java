package com.example.stock_invest_backend.lof.cache;

import com.example.stock_invest_backend.lof.dto.LofPremiumItem;

import java.util.Optional;

public interface LofPremiumCacheGateway {

    Optional<LofPremiumItem> get(String symbol);

    void put(String symbol, LofPremiumItem item);
}
