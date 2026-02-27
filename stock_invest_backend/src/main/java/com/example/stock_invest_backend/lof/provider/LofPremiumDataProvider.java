package com.example.stock_invest_backend.lof.provider;

import com.example.stock_invest_backend.lof.dto.LofPremiumItem;
import reactor.core.publisher.Mono;

import java.util.List;

//provider接口
public interface LofPremiumDataProvider {

    Mono<List<LofPremiumItem>> fetchPremiumItems(List<String> symbols);

    String providerName();
}
