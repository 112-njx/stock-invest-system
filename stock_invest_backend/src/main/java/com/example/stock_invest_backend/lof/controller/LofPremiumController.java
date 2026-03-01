package com.example.stock_invest_backend.lof.controller;

import com.example.stock_invest_backend.lof.dto.LofPremiumResponse;
import com.example.stock_invest_backend.lof.dto.LofPremiumRankRequest;
import com.example.stock_invest_backend.lof.dto.LofPremiumRankResponse;
import com.example.stock_invest_backend.lof.service.LofPremiumRankService;
import com.example.stock_invest_backend.lof.service.LofPremiumSourceService;
import com.example.stock_invest_backend.lof.service.LofSymbolSourceService;
import com.example.stock_invest_backend.lof.service.LofSymbolSourceSnapshot;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Arrays;
import java.util.List;

@RestController
@RequestMapping("/api/market/lof")
public class LofPremiumController {

    private final LofPremiumSourceService lofPremiumSourceService;
    private final LofPremiumRankService lofPremiumRankService;
    private final LofSymbolSourceService lofSymbolSourceService;

    public LofPremiumController(LofPremiumSourceService lofPremiumSourceService,
                                LofPremiumRankService lofPremiumRankService,
                                LofSymbolSourceService lofSymbolSourceService) {
        this.lofPremiumSourceService = lofPremiumSourceService;
        this.lofPremiumRankService = lofPremiumRankService;
        this.lofSymbolSourceService = lofSymbolSourceService;
    }

    @GetMapping("/premium")
    public Mono<LofPremiumResponse> getPremium(@RequestParam(value = "symbols", required = false) String symbols) {
        List<String> symbolList = parseSymbols(symbols);
        return lofPremiumSourceService.fetchPremiums(symbolList);
    }

    @GetMapping("/premium/rank")
    public Mono<LofPremiumRankResponse> getPremiumRank(
            @RequestParam(value = "order", defaultValue = "desc") String order,
            @RequestParam(value = "limit", defaultValue = "20") Integer limit,
            @RequestParam(value = "onlyStatusOk", defaultValue = "false") Boolean onlyStatusOk,
            @RequestParam(value = "tradingOnly", defaultValue = "false") Boolean tradingOnly) {
        LofPremiumRankRequest request = new LofPremiumRankRequest();
        request.setOrder(order);
        request.setLimit(limit);
        request.setOnlyStatusOk(onlyStatusOk);
        request.setTradingOnly(tradingOnly);
        return lofPremiumRankService.rank(request);
    }

    @PostMapping("/symbols/reload")
    public LofSymbolSourceSnapshot reloadSymbols() {
        return lofSymbolSourceService.reloadFromDb();
    }

    private List<String> parseSymbols(String symbols) {
        if (!StringUtils.hasText(symbols)) {
            return List.of();
        }
        return Arrays.stream(symbols.split(","))
                .map(String::trim)
                .filter(StringUtils::hasText)
                .toList();
    }
}
