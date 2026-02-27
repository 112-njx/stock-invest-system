package com.example.stock_invest_backend.lof.controller;

import com.example.stock_invest_backend.lof.dto.LofPremiumResponse;
import com.example.stock_invest_backend.lof.service.LofPremiumSourceService;
import org.springframework.util.StringUtils;
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

    public LofPremiumController(LofPremiumSourceService lofPremiumSourceService) {
        this.lofPremiumSourceService = lofPremiumSourceService;
    }

    @GetMapping("/premium")
    public Mono<LofPremiumResponse> getPremium(@RequestParam(value = "symbols", required = false) String symbols) {
        List<String> symbolList = parseSymbols(symbols);
        return lofPremiumSourceService.fetchPremiums(symbolList);
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
