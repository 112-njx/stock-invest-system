package com.example.stock_invest_backend.ai.controller;

import com.example.stock_invest_backend.ai.dto.AiInvestAnalyzeRequest;
import com.example.stock_invest_backend.ai.dto.AiInvestAnalyzeResponse;
import com.example.stock_invest_backend.ai.service.AiInvestService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

import java.time.Duration;

@RestController
@RequestMapping("/api/ai/invest")
public class AiInvestController {

    private static final Logger log = LoggerFactory.getLogger(AiInvestController.class);

    private final AiInvestService aiInvestService;

    public AiInvestController(AiInvestService aiInvestService) {
        this.aiInvestService = aiInvestService;
    }

    @PostMapping("/analyze")
    public Mono<AiInvestAnalyzeResponse> analyze(@RequestBody AiInvestAnalyzeRequest request) {
        if (request.getPrompt() == null || request.getPrompt().isBlank()) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "prompt is required"));
        }
        // Service has internal timeout; controller adds safety-net (+5s)
        return Mono.fromCallable(() -> aiInvestService.analyze(request))
                .timeout(Duration.ofSeconds(aiInvestService.getTimeoutSeconds() + 5))
                .onErrorResume(e -> {
                    log.error("AI analysis safety-net timeout triggered: {}", e.getMessage());
                    return Mono.just(aiInvestService.buildTimeoutFallback(request));
                });
    }
}
