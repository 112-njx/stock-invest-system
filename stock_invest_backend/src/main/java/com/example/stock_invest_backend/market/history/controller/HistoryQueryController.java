package com.example.stock_invest_backend.market.history.controller;

import com.example.stock_invest_backend.market.history.dto.BackfillRequest;
import com.example.stock_invest_backend.market.history.dto.BackfillResponse;
import com.example.stock_invest_backend.market.history.dto.CompletenessResult;
import com.example.stock_invest_backend.market.history.dto.KLineDataPoint;
import com.example.stock_invest_backend.market.history.service.HistoryBackfillService;
import com.example.stock_invest_backend.market.history.service.HistoryDataCompletenessService;
import com.example.stock_invest_backend.market.history.service.HistoryQueryService;
import com.example.stock_invest_backend.market.history.service.PythonHealthCheckService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api/market/history")
public class HistoryQueryController {

    private static final Logger log = LoggerFactory.getLogger(HistoryQueryController.class);
    private static final Pattern SYMBOL_PATTERN = Pattern.compile("^(sh|sz|bj)\\d{6}$");

    private final HistoryQueryService historyQueryService;
    private final HistoryDataCompletenessService completenessService;
    private final HistoryBackfillService backfillService;
    private final PythonHealthCheckService healthCheckService;

    public HistoryQueryController(HistoryQueryService historyQueryService,
                                  HistoryDataCompletenessService completenessService,
                                  HistoryBackfillService backfillService,
                                  PythonHealthCheckService healthCheckService) {
        this.historyQueryService = historyQueryService;
        this.completenessService = completenessService;
        this.backfillService = backfillService;
        this.healthCheckService = healthCheckService;
    }

    @GetMapping("/kline")
    public ResponseEntity<?> queryKLine(
            @RequestParam("symbol") String symbol,
            @RequestParam(value = "startDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate startDate,
            @RequestParam(value = "endDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate endDate,
            @RequestParam(value = "days", required = false) Integer days,
            @RequestParam(value = "adjustType", required = false, defaultValue = "qfq") String adjustType) {

        if (symbol == null || symbol.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "symbol is required",
                    "message", "symbol must not be blank"));
        }

        if (!SYMBOL_PATTERN.matcher(symbol).matches()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "invalid symbol format",
                    "message", "symbol must match pattern: sh|sz|bj + 6 digits, e.g. sh600519"));
        }

        try {
            List<KLineDataPoint> data = historyQueryService.queryKLine(symbol, startDate, endDate, days);
            log.info("K-line query result: symbol={}, count={}", symbol, data.size());
            return ResponseEntity.ok(data);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "invalid parameters",
                    "message", e.getMessage()));
        }
    }

    @GetMapping("/completeness")
    public ResponseEntity<?> checkCompleteness(
            @RequestParam("symbol") String symbol,
            @RequestParam("startDate") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate startDate,
            @RequestParam("endDate") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate endDate,
            @RequestParam(value = "adjustType", required = false, defaultValue = "qfq") String adjustType) {

        if (symbol == null || !SYMBOL_PATTERN.matcher(symbol).matches()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "invalid symbol format",
                    "message", "symbol must match pattern: sh|sz|bj + 6 digits"));
        }
        try {
            CompletenessResult r = completenessService.check(symbol, startDate, endDate, adjustType);
            return ResponseEntity.ok(r);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "invalid parameters", "message", e.getMessage()));
        }
    }

    @PostMapping("/backfill")
    public ResponseEntity<?> backfill(@RequestBody BackfillRequest req) {
        if (req.getSymbol() == null || !SYMBOL_PATTERN.matcher(req.getSymbol()).matches()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "invalid symbol format",
                    "message", "symbol must match pattern: sh|sz|bj + 6 digits"));
        }
        if (req.getStartDate() == null || req.getEndDate() == null) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "invalid parameters",
                    "message", "startDate and endDate are required"));
        }
        try {
            BackfillResponse resp = backfillService.backfill(
                    req.getSymbol(), req.getStartDate(), req.getEndDate(),
                    req.getAdjustType() == null ? "qfq" : req.getAdjustType());
            return ResponseEntity.ok(resp);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "invalid parameters", "message", e.getMessage()));
        }
    }

    @GetMapping("/ingest-health")
    public ResponseEntity<?> ingestHealth() {
        return ResponseEntity.ok(healthCheckService.runHealthCheck());
    }
}
