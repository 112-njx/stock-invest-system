package com.example.stock_invest_backend.market.history.controller;

import com.example.stock_invest_backend.market.history.config.HistoryIngestionProperties;
import com.example.stock_invest_backend.market.history.service.FakeHistoryIngestionService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/market/history")
public class HistoryIngestionController {

    private final FakeHistoryIngestionService ingestionService;
    private final HistoryIngestionProperties properties;

    public HistoryIngestionController(FakeHistoryIngestionService ingestionService,
                                      HistoryIngestionProperties properties) {
        this.ingestionService = ingestionService;
        this.properties = properties;
    }

    @PostMapping("/ingest")
    public Map<String, Object> ingest(@RequestBody(required = false) Map<String, Object> body) {
        List<String> symbols = properties.getDefaultSymbols();
        int months = properties.getMonths();

        if (body != null && body.get("symbols") instanceof List<?> list && !list.isEmpty()) {
            symbols = list.stream().map(String::valueOf).toList();
        }
        if (body != null && body.get("months") != null) {
            months = Integer.parseInt(String.valueOf(body.get("months")));
        }

        int affected = ingestionService.ingest(symbols, months);
        return Map.of(
                "symbols", symbols,
                "months", months,
                "affectedRows", affected,
                "note", "uses INSERT ... ON DUPLICATE KEY UPDATE");
    }
}
