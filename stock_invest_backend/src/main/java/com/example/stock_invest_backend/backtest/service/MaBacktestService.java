package com.example.stock_invest_backend.backtest.service;

import com.example.stock_invest_backend.backtest.config.BacktestEngineProperties;
import com.example.stock_invest_backend.backtest.dto.MaBacktestRequest;
import com.example.stock_invest_backend.backtest.dto.MaBacktestResponse;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Duration;

//业务逻辑层，调用 C++ 回测引擎

@Service
public class MaBacktestService {


    private final WebClient webClient;
    private final BacktestEngineProperties properties;

    //配置文件
    public MaBacktestService(@Qualifier("backtestEngineWebClient") WebClient webClient,
                             BacktestEngineProperties properties) {
        this.webClient = webClient;
        this.properties = properties;
    }

    public Mono<MaBacktestResponse> runBacktest(MaBacktestRequest request) {
        return webClient.post()
                .uri(properties.getMaPath())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .bodyToMono(MaBacktestResponse.class)
                .timeout(Duration.ofMillis(properties.getTimeoutMillis()))
                .onErrorResume(ex -> Mono.just(buildFallbackResponse(request, ex.getMessage())));
    }

    private MaBacktestResponse buildFallbackResponse(MaBacktestRequest request, String reason) {
        MaBacktestResponse response = new MaBacktestResponse();
        response.setSymbol(request.getSymbol());
        response.setPeriod(request.getPeriod());
        response.setTotalSignals(0);
        response.setWinSignals(0);
        response.setSuccessRate(BigDecimal.ZERO);
        response.setSource("java-fallback");
        response.setMessage("Backtest engine unavailable: " + reason);
        return response;
    }
}
