package com.example.stock_invest_backend.backtest.controller;

import com.example.stock_invest_backend.backtest.dto.MaBacktestRequest;
import com.example.stock_invest_backend.backtest.dto.MaBacktestResponse;
import com.example.stock_invest_backend.backtest.dto.BacktestResultView;
import com.example.stock_invest_backend.backtest.service.BacktestResultQueryService;
import com.example.stock_invest_backend.backtest.service.MaBacktestService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

import java.util.List;

@RestController
@RequestMapping("/api/backtest")
public class MaBacktestController {

    private final MaBacktestService maBacktestService;
    private final BacktestResultQueryService backtestResultQueryService;

    public MaBacktestController(MaBacktestService maBacktestService,
                                BacktestResultQueryService backtestResultQueryService) {
        this.maBacktestService = maBacktestService;
        this.backtestResultQueryService = backtestResultQueryService;
    }

    @PostMapping("/ma")
    public Mono<MaBacktestResponse> runMaBacktest(@RequestBody MaBacktestRequest request) {
        return maBacktestService.runBacktest(request);
    }

    @GetMapping("/results")
    public List<BacktestResultView> queryBacktestResults(@RequestParam String symbol,
                                                         @RequestParam(required = false) String strategyCode,
                                                         @RequestParam(required = false) String strategy,
                                                         @RequestParam(defaultValue = "20") Integer limit) {
        String resolvedStrategy = strategyCode;
        if (resolvedStrategy == null || resolvedStrategy.isBlank()) {
            resolvedStrategy = strategy;
        }
        try {
            return backtestResultQueryService.query(symbol, resolvedStrategy, limit);
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, ex.getMessage(), ex);
        }
    }
}
