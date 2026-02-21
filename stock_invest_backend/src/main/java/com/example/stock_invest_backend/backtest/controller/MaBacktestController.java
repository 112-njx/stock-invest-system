package com.example.stock_invest_backend.backtest.controller;

import com.example.stock_invest_backend.backtest.dto.MaBacktestRequest;
import com.example.stock_invest_backend.backtest.dto.MaBacktestResponse;
import com.example.stock_invest_backend.backtest.service.MaBacktestService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/backtest")
public class MaBacktestController {

    private final MaBacktestService maBacktestService;

    public MaBacktestController(MaBacktestService maBacktestService) {
        this.maBacktestService = maBacktestService;
    }

    @PostMapping("/ma")
    public Mono<MaBacktestResponse> runMaBacktest(@RequestBody MaBacktestRequest request) {
        return maBacktestService.runBacktest(request);
    }
}
