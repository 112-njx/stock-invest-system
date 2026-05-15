package com.example.stock_invest_backend.ai.service;

import com.example.stock_invest_backend.ai.dto.AiInvestAnalyzeRequest;
import com.example.stock_invest_backend.ai.dto.AiInvestAnalyzeResponse;
import com.example.stock_invest_backend.ai.dto.DataSource;
import com.example.stock_invest_backend.ai.dto.ToolCall;
import com.example.stock_invest_backend.ai.gateway.AiGatewayClient;
import com.example.stock_invest_backend.ai.gateway.model.GatewayAnalysisResult;
import com.example.stock_invest_backend.ai.gateway.model.GatewayToolCallResult;
import com.example.stock_invest_backend.ai.gateway.model.GatewayToolDefinition;
import com.example.stock_invest_backend.backtest.dto.MaBacktestRequest;
import com.example.stock_invest_backend.backtest.dto.MaBacktestResponse;
import com.example.stock_invest_backend.backtest.service.MaBacktestService;
import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;
import com.example.stock_invest_backend.market.history.repository.StockDailyKlineRepository;
import com.example.stock_invest_backend.market.history.service.FakeHistoryIngestionService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class AiInvestService {

    private static final Logger log = LoggerFactory.getLogger(AiInvestService.class);
    private static final Pattern STOCK_CODE_PATTERN = Pattern.compile("\\b(sh|sz|bj)\\d{6}\\b");
    private static final String DISCLAIMER = "本分析仅供参考，不构成任何投资建议。";
    private static final int DEFAULT_DAYS = 30;
    private static final int DEFAULT_MA_PERIOD = 5;
    private static final String MODE_TOOL_CHAIN = "TOOL_CHAIN";
    private static final String MODE_MACRO_ONLY = "MACRO_ONLY";
    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final ZoneId ZONE_SHANGHAI = ZoneId.of("Asia/Shanghai");

    private final AiGatewayClient aiGatewayClient;
    private final FakeHistoryIngestionService historyIngestionService;
    private final StockDailyKlineRepository klineRepository;
    private final MaBacktestService maBacktestService;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final AtomicInteger requestCounter = new AtomicInteger(0);

    public AiInvestService(AiGatewayClient aiGatewayClient,
                           FakeHistoryIngestionService historyIngestionService,
                           StockDailyKlineRepository klineRepository,
                           MaBacktestService maBacktestService) {
        this.aiGatewayClient = aiGatewayClient;
        this.historyIngestionService = historyIngestionService;
        this.klineRepository = klineRepository;
        this.maBacktestService = maBacktestService;
    }

    public AiInvestAnalyzeResponse analyze(AiInvestAnalyzeRequest request) {
        String prompt = request.getPrompt();
        String requestId = generateRequestId();
        String stockCode = extractStockCode(prompt);

        log.info("[{}] AI analyze request, prompt={}, stockCode={}, provider={}",
                requestId, prompt, stockCode, aiGatewayClient.getProviderName());

        if (stockCode == null) {
            return analyzeMacroOnly(requestId, prompt);
        }
        return analyzeWithToolChain(requestId, prompt, stockCode);
    }

    // ---------- stock code extraction ----------

    private String extractStockCode(String prompt) {
        if (prompt == null || prompt.isBlank()) {
            return null;
        }
        Matcher m = STOCK_CODE_PATTERN.matcher(prompt.toLowerCase());
        return m.find() ? m.group() : null;
    }

    // ---------- MACRO_ONLY mode ----------

    private AiInvestAnalyzeResponse analyzeMacroOnly(String requestId, String prompt) {
        AiInvestAnalyzeResponse response = buildBaseResponse(requestId, prompt, MODE_MACRO_ONLY, null, 0);
        response.setToolCalls(List.of());
        response.setDataSources(List.of());

        String systemPrompt = """
                你是一个专业的股票投资宏观分析师。请基于当前市场环境，对用户的问题进行宏观层面的分析。
                分析应涵盖市场整体趋势、政策面、资金面等角度，避免针对具体个股给出买卖建议。
                回复末尾必须附上：「""" + DISCLAIMER + "」";

        GatewayAnalysisResult result = aiGatewayClient.generateAnalysis(systemPrompt, prompt);
        log.info("[{}] Macro analysis: latencyMs={}, promptTokens={}, completionTokens={}",
                requestId, result.getLatencyMs(), result.getPromptTokens(), result.getCompletionTokens());

        if (result.isSuccess()) {
            response.setAnalysisText(result.getContent());
        } else {
            log.warn("[{}] Macro analysis LLM call failed: {}", requestId, result.getErrorMessage());
            response.setAnalysisText("当前宏观层面更需要关注成交量修复、政策预期和板块轮动节奏，结论应以市场实际风险偏好变化为准。" + DISCLAIMER);
            response.setDegraded(true);
            response.setFallbackReason(result.getErrorMessage());
        }

        return response;
    }

    // ---------- TOOL_CHAIN mode ----------

    private AiInvestAnalyzeResponse analyzeWithToolChain(String requestId, String prompt, String stockCode) {
        int usedDays = DEFAULT_DAYS;
        AiInvestAnalyzeResponse response = buildBaseResponse(requestId, prompt, MODE_TOOL_CHAIN, stockCode, usedDays);

        // Step 1: request tool calls from LLM via gateway
        List<ToolCall> toolCalls;
        GatewayToolCallResult toolCallResult = requestToolCallsViaGateway(prompt);
        log.info("[{}] Tool call generation: latencyMs={}, promptTokens={}, completionTokens={}, success={}",
                requestId, toolCallResult.getLatencyMs(), toolCallResult.getPromptTokens(),
                toolCallResult.getCompletionTokens(), toolCallResult.isSuccess());

        if (toolCallResult.isSuccess() && !toolCallResult.getToolCalls().isEmpty()) {
            toolCalls = toolCallResult.getToolCalls();
        } else {
            log.warn("[{}] Tool call generation failed or returned empty, using defaults: {}",
                    requestId, toolCallResult.getErrorMessage());
            toolCalls = buildDefaultToolCalls(stockCode, usedDays);
        }
        response.setToolCalls(toolCalls);

        // Step 2: build data source descriptors
        List<DataSource> dataSources = buildDataSources(toolCalls);
        response.setDataSources(dataSources);

        // Step 3: execute tool calls and aggregate results
        Map<String, Object> aggregatedData = new LinkedHashMap<>();
        for (ToolCall tc : toolCalls) {
            try {
                Map<String, Object> result = executeToolCall(tc);
                aggregatedData.put(tc.getToolName(), result);
                if ("get_market_history".equals(tc.getToolName()) && tc.getArguments() != null) {
                    Object daysObj = tc.getArguments().get("days");
                    if (daysObj instanceof Number n) {
                        usedDays = n.intValue();
                        response.setUsedDays(usedDays);
                    }
                }
            } catch (Exception ex) {
                log.warn("[{}] Tool call execution failed for {}: {}", requestId, tc.getToolName(), ex.getMessage());
                aggregatedData.put(tc.getToolName(), Map.of("error", ex.getMessage()));
            }
        }

        // Step 4: build raw data summary
        response.setRawData(buildRawDataSummary(stockCode, usedDays, aggregatedData));

        // Step 5: request final analysis from LLM via gateway
        String analysisSystemPrompt = """
                你是一个专业的股票投资技术分析师。请基于提供的真实行情数据和MA5信号数据，对股票进行技术分析。
                分析应包括：趋势判断、MA5信号解读、支撑/压力位、短期风险提示。
                回复末尾必须附上：「""" + DISCLAIMER + "」";
        String dataJson = safeSerializeJson(aggregatedData);
        String analysisUserPrompt = String.format(
                "用户问题：%s\n\n股票代码：%s\n\n以下是获取到的真实数据（JSON格式）：\n%s\n\n请基于以上数据进行技术分析。",
                prompt, stockCode, dataJson);

        GatewayAnalysisResult analysisResult = aiGatewayClient.generateAnalysis(analysisSystemPrompt, analysisUserPrompt);
        log.info("[{}] Final analysis: latencyMs={}, promptTokens={}, completionTokens={}, success={}",
                requestId, analysisResult.getLatencyMs(), analysisResult.getPromptTokens(),
                analysisResult.getCompletionTokens(), analysisResult.isSuccess());

        if (analysisResult.isSuccess()) {
            response.setAnalysisText(analysisResult.getContent());
        } else {
            log.warn("[{}] Final analysis LLM call failed: {}", requestId, analysisResult.getErrorMessage());
            response.setAnalysisText("AI 分析阶段超时，已返回原生行情与 MA5 信号数据供前端展示。" + DISCLAIMER);
            response.setDegraded(true);
            response.setFallbackReason(analysisResult.getErrorMessage());
        }

        return response;
    }

    // ---------- gateway interaction ----------

    private GatewayToolCallResult requestToolCallsViaGateway(String prompt) {
        String systemPrompt = """
                你是一个股票投资分析助手。根据用户的自然语言请求，判断需要调用哪些工具来获取数据。
                如果用户询问股票分析相关的问题，请调用相应的工具。如果用户只做宏观分析，可以不调用工具直接回复。
                可用工具：
                - get_market_history: 获取股票历史日K线数据（开盘价、收盘价、最高价、最低价、成交量等）
                - get_ma5_cross_signals: 获取MA5均线上穿/下穿信号，用于判断短期趋势变化
                """;

        List<GatewayToolDefinition> tools = List.of(
                new GatewayToolDefinition("get_market_history",
                        "获取股票历史日K线数据，包含开盘价、收盘价、最高价、最低价、成交量等",
                        Map.of(
                                "symbol", Map.of("type", "string", "description", "股票代码，如sh600519"),
                                "days", Map.of("type", "integer", "description", "查询近N天的K线数据，默认30")
                        ),
                        List.of("symbol")),
                new GatewayToolDefinition("get_ma5_cross_signals",
                        "获取MA5均线上穿/下穿信号，用于判断短期趋势变化",
                        Map.of(
                                "symbol", Map.of("type", "string", "description", "股票代码，如sh600519"),
                                "period", Map.of("type", "integer", "description", "MA周期，默认5")
                        ),
                        List.of("symbol"))
        );

        return aiGatewayClient.requestToolCalls(systemPrompt, prompt, tools);
    }

    // ---------- Tool call execution ----------

    private Map<String, Object> executeToolCall(ToolCall toolCall) {
        String toolName = toolCall.getToolName();
        Map<String, Object> args = toolCall.getArguments() != null ? toolCall.getArguments() : Map.of();
        String symbol = String.valueOf(args.getOrDefault("symbol", ""));

        return switch (toolName) {
            case "get_market_history" -> {
                int days = args.get("days") instanceof Number n ? n.intValue() : DEFAULT_DAYS;
                yield executeMarketHistory(symbol, days);
            }
            case "get_ma5_cross_signals" -> {
                int period = args.get("period") instanceof Number n ? n.intValue() : DEFAULT_MA_PERIOD;
                int days = args.get("days") instanceof Number n ? n.intValue() : DEFAULT_DAYS;
                yield executeMaCrossSignals(symbol, period, days);
            }
            default -> Map.of("error", "Unknown tool: " + toolName);
        };
    }

    private Map<String, Object> executeMarketHistory(String symbol, int days) {
        int ingestMonths = Math.max(2, days / 15 + 1);
        historyIngestionService.ingest(List.of(symbol), ingestMonths);

        List<StockDailyKlineRecord> records = klineRepository.findBySymbolAndDays(symbol, days);
        List<StockDailyKlineRecord> chronological = new ArrayList<>(records);
        Collections.reverse(chronological);

        BigDecimal latestClose = chronological.isEmpty() ? BigDecimal.ZERO
                : chronological.get(chronological.size() - 1).getClosePrice();
        BigDecimal firstClose = chronological.isEmpty() ? BigDecimal.ZERO
                : chronological.get(0).getClosePrice();
        BigDecimal changePercent = firstClose.compareTo(BigDecimal.ZERO) > 0
                ? latestClose.subtract(firstClose).divide(firstClose, 4, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        List<Map<String, Object>> klineList = new ArrayList<>();
        for (StockDailyKlineRecord r : chronological) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("date", r.getTradeDate().format(DATE_FMT));
            item.put("open", r.getOpenPrice());
            item.put("high", r.getHighPrice());
            item.put("low", r.getLowPrice());
            item.put("close", r.getClosePrice());
            item.put("volume", r.getVolume());
            klineList.add(item);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("symbol", symbol);
        result.put("days", days);
        result.put("actualRecords", chronological.size());
        result.put("latestClose", latestClose);
        result.put("changePercent", changePercent);
        result.put("klineData", klineList);
        return result;
    }

    private Map<String, Object> executeMaCrossSignals(String symbol, int period, int days) {
        LocalDate endDate = LocalDate.now();
        LocalDate startDate = endDate.minusDays(days * 2L);

        MaBacktestRequest request = new MaBacktestRequest();
        request.setSymbol(symbol);
        request.setPeriod(period);
        request.setStartDate(startDate.format(DATE_FMT));
        request.setEndDate(endDate.format(DATE_FMT));

        MaBacktestResponse backtestResult;
        try {
            backtestResult = maBacktestService.runBacktest(request)
                    .block(Duration.ofSeconds(8));
        } catch (Exception ex) {
            log.warn("MA backtest call failed: {}", ex.getMessage());
            return Map.of("symbol", symbol, "period", period, "error", ex.getMessage());
        }

        if (backtestResult == null) {
            return Map.of("symbol", symbol, "period", period, "error", "Backtest returned null");
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("symbol", backtestResult.getSymbol());
        result.put("strategyCode", backtestResult.getStrategyCode());
        result.put("period", backtestResult.getPeriod());
        result.put("totalSignals", backtestResult.getTotalSignals());
        result.put("winSignals", backtestResult.getWinSignals());
        result.put("successRate", backtestResult.getSuccessRate());
        result.put("records", backtestResult.getRecords());
        result.put("source", backtestResult.getSource());
        result.put("crossUpDates", backtestResult.getCrossUpDates());
        result.put("crossDownDates", backtestResult.getCrossDownDates());
        result.put("signals", backtestResult.getSignals());
        return result;
    }

    // ---------- helpers ----------

    private List<ToolCall> buildDefaultToolCalls(String symbol, int days) {
        return List.of(
                new ToolCall("get_market_history", Map.of("symbol", symbol, "days", days)),
                new ToolCall("get_ma5_cross_signals", Map.of("symbol", symbol, "period", DEFAULT_MA_PERIOD))
        );
    }

    private List<DataSource> buildDataSources(List<ToolCall> toolCalls) {
        List<DataSource> sources = new ArrayList<>();
        for (ToolCall tc : toolCalls) {
            switch (tc.getToolName()) {
                case "get_market_history" ->
                        sources.add(new DataSource("/api/market/history/ingest", "拉取历史日K所需数据"));
                case "get_ma5_cross_signals" ->
                        sources.add(new DataSource("/api/backtest/ma", "获取MA5上穿/下穿信号"));
            }
        }
        return sources;
    }

    private Map<String, Object> buildRawDataSummary(String symbol, int days, Map<String, Object> aggregatedData) {
        Map<String, Object> rawData = new LinkedHashMap<>();

        @SuppressWarnings("unchecked")
        Map<String, Object> historyData = (Map<String, Object>) aggregatedData.get("get_market_history");
        if (historyData != null) {
            Map<String, Object> summary = new LinkedHashMap<>();
            summary.put("days", historyData.getOrDefault("days", days));
            summary.put("latestClose", historyData.get("latestClose"));
            summary.put("changePercent", historyData.get("changePercent"));
            rawData.put("marketHistorySummary", summary);
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> maData = (Map<String, Object>) aggregatedData.get("get_ma5_cross_signals");
        if (maData != null) {
            Map<String, Object> summary = new LinkedHashMap<>();
            summary.put("strategyCode", maData.getOrDefault("strategyCode", "MA_CROSS_5"));
            List<?> crossUp = (List<?>) maData.get("crossUpDates");
            List<?> crossDown = (List<?>) maData.get("crossDownDates");
            summary.put("crossUpCount", crossUp != null ? crossUp.size() : 0);
            summary.put("crossDownCount", crossDown != null ? crossDown.size() : 0);
            rawData.put("maSignalSummary", summary);
        }

        return rawData;
    }

    private AiInvestAnalyzeResponse buildBaseResponse(String requestId, String prompt, String mode,
                                                       String symbol, int usedDays) {
        AiInvestAnalyzeResponse response = new AiInvestAnalyzeResponse();
        response.setRequestId(requestId);
        response.setPrompt(prompt);
        response.setMode(mode);
        response.setSymbol(symbol);
        response.setUsedDays(usedDays);
        response.setDisclaimer(DISCLAIMER);
        response.setReplyTime(OffsetDateTime.now(ZONE_SHANGHAI));
        response.setDegraded(false);
        return response;
    }

    private String safeSerializeJson(Object obj) {
        try {
            return objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(obj);
        } catch (Exception ex) {
            return String.valueOf(obj);
        }
    }

    private String generateRequestId() {
        String date = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMMdd"));
        int seq = requestCounter.incrementAndGet() % 10000;
        return String.format("ai-invest-%s-%04d", date, seq);
    }
}
