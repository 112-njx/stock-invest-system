package com.example.stock_invest_backend.market.history.controller;

import com.example.stock_invest_backend.market.history.config.HistoryIngestionProperties;
import com.example.stock_invest_backend.market.history.provider.EastMoneyHistoryDataProvider;
import com.example.stock_invest_backend.market.history.service.FakeHistoryIngestionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/market/history")
public class HistoryIngestionController {

    private static final Logger log = LoggerFactory.getLogger(HistoryIngestionController.class);

    private final FakeHistoryIngestionService fakeIngestionService;
    private final EastMoneyHistoryDataProvider eastMoneyHistoryDataProvider;
    private final HistoryIngestionProperties properties;

    public HistoryIngestionController(FakeHistoryIngestionService fakeIngestionService,
                                      EastMoneyHistoryDataProvider eastMoneyHistoryDataProvider,
                                      HistoryIngestionProperties properties) {
        this.fakeIngestionService = fakeIngestionService;
        this.eastMoneyHistoryDataProvider = eastMoneyHistoryDataProvider;
        this.properties = properties;
    }

    @PostMapping("/ingest")
    public Map<String, Object> ingest(@RequestBody(required = false) Map<String, Object> body) {
        List<String> symbols = properties.getDefaultSymbols();
        int months = properties.getMonths();
        String source = "fake";

        if (body != null) {
            if (body.get("symbols") instanceof List<?> list && !list.isEmpty()) {
                symbols = list.stream().map(String::valueOf).toList();
            }
            if (body.get("months") instanceof Number n) {
                months = n.intValue();
            }
            if (body.get("source") instanceof String s && !s.isBlank()) {
                source = s.toLowerCase();
            }
        }

        int affected;
        String note;
        if ("eastmoney".equals(source)) {
            log.info("Ingesting real K-line from EastMoney: symbols={}, months={}", symbols, months);
            affected = eastMoneyHistoryDataProvider.ingest(symbols, months);
            note = "fetched from EastMoney K-line API, upserted to stock_daily_kline";
        } else {
            log.info("Ingesting fake K-line: symbols={}, months={}", symbols, months);
            affected = fakeIngestionService.ingest(symbols, months);
            note = "uses INSERT ... ON DUPLICATE KEY UPDATE";
        }

        return Map.of(
                "symbols", symbols,
                "months", months,
                "source", source,
                "affectedRows", affected,
                "note", note);
    }
}
