package com.example.stock_invest_backend.ai.gateway;

import com.example.stock_invest_backend.ai.config.DeepSeekProperties;
import com.example.stock_invest_backend.ai.dto.ToolCall;
import com.example.stock_invest_backend.ai.gateway.model.GatewayAnalysisResult;
import com.example.stock_invest_backend.ai.gateway.model.GatewayToolCallResult;
import com.example.stock_invest_backend.ai.gateway.model.GatewayToolDefinition;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class DeepSeekAiGatewayClient implements AiGatewayClient {

    private static final Logger log = LoggerFactory.getLogger(DeepSeekAiGatewayClient.class);
    private static final String CHAT_COMPLETIONS_PATH = "/v1/chat/completions";

    private final WebClient webClient;
    private final DeepSeekProperties properties;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DeepSeekAiGatewayClient(
            @Qualifier("deepSeekWebClient") WebClient webClient,
            DeepSeekProperties properties) {
        this.webClient = webClient;
        this.properties = properties;
    }

    @Override
    public GatewayToolCallResult requestToolCalls(String systemPrompt, String userPrompt,
                                                   List<GatewayToolDefinition> tools) {
        GatewayToolCallResult result = new GatewayToolCallResult();
        long start = System.currentTimeMillis();

        try {
            List<Map<String, Object>> toolDefs = tools.stream()
                    .map(this::buildToolDefForApi)
                    .toList();
            Map<String, Object> requestBody = buildChatRequest(systemPrompt, userPrompt, toolDefs, 0.3);
            Map<String, Object> response = callApi(requestBody);

            result.setLatencyMs(System.currentTimeMillis() - start);
            extractUsage(response, result);
            result.setToolCalls(extractToolCalls(response));
            result.setSuccess(true);
        } catch (Exception ex) {
            result.setLatencyMs(System.currentTimeMillis() - start);
            result.setSuccess(false);
            result.setErrorMessage(normalizeError(ex));
            result.setToolCalls(List.of());
            log.warn("DeepSeek tool call request failed: {}", ex.getMessage());
        }

        return result;
    }

    @Override
    public GatewayAnalysisResult generateAnalysis(String systemPrompt, String userPrompt) {
        GatewayAnalysisResult result = new GatewayAnalysisResult();
        long start = System.currentTimeMillis();

        try {
            Map<String, Object> requestBody = buildChatRequest(systemPrompt, userPrompt, null, 0.7);
            Map<String, Object> response = callApi(requestBody);

            result.setLatencyMs(System.currentTimeMillis() - start);
            extractUsage(response, result);
            result.setContent(extractContent(response));
            result.setSuccess(true);
        } catch (Exception ex) {
            result.setLatencyMs(System.currentTimeMillis() - start);
            result.setSuccess(false);
            result.setErrorMessage(normalizeError(ex));
            result.setContent("");
            log.warn("DeepSeek analysis request failed: {}", ex.getMessage());
        }

        return result;
    }

    @Override
    public String getProviderName() {
        return "deepseek";
    }

    // ---------- request construction ----------

    private Map<String, Object> buildChatRequest(String systemPrompt, String userPrompt,
                                                  List<Map<String, Object>> tools, double temperature) {
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(Map.of("role", "system", "content", systemPrompt));
        messages.add(Map.of("role", "user", "content", userPrompt));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", properties.getModel());
        body.put("messages", messages);
        body.put("temperature", temperature);
        if (tools != null && !tools.isEmpty()) {
            body.put("tools", tools);
        }
        return body;
    }

    private Map<String, Object> buildToolDefForApi(GatewayToolDefinition def) {
        Map<String, Object> function = new LinkedHashMap<>();
        function.put("name", def.getName());
        function.put("description", def.getDescription());
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("type", "object");
        params.put("properties", def.getParameters());
        params.put("required", def.getRequired());
        function.put("parameters", params);

        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("type", "function");
        tool.put("function", function);
        return tool;
    }

    // ---------- HTTP call ----------

    private Map<String, Object> callApi(Map<String, Object> requestBody) {
        @SuppressWarnings("unchecked")
        Map<String, Object> result = webClient.post()
                .uri(CHAT_COMPLETIONS_PATH)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(Map.class)
                .timeout(Duration.ofMillis(properties.getTimeoutMillis()))
                .block(Duration.ofMillis(properties.getTimeoutMillis() + 2000));
        return result;
    }

    // ---------- response parsing ----------

    @SuppressWarnings("unchecked")
    private List<ToolCall> extractToolCalls(Map<String, Object> response) {
        if (response == null) {
            return List.of();
        }
        List<Map<String, Object>> choices = (List<Map<String, Object>>) response.get("choices");
        if (choices == null || choices.isEmpty()) {
            return List.of();
        }
        Map<String, Object> message = (Map<String, Object>) choices.get(0).get("message");
        if (message == null) {
            return List.of();
        }
        List<Map<String, Object>> toolCallsRaw = (List<Map<String, Object>>) message.get("tool_calls");
        if (toolCallsRaw == null || toolCallsRaw.isEmpty()) {
            return List.of();
        }

        List<ToolCall> result = new ArrayList<>();
        for (Map<String, Object> tc : toolCallsRaw) {
            try {
                Map<String, Object> func = (Map<String, Object>) tc.get("function");
                if (func == null) continue;
                String name = (String) func.get("name");
                String argsJson = (String) func.get("arguments");
                Map<String, Object> args = objectMapper.readValue(argsJson,
                        new TypeReference<Map<String, Object>>() {});
                result.add(new ToolCall(name, args));
            } catch (Exception ex) {
                log.warn("Failed to parse individual tool call: {}", ex.getMessage());
            }
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private String extractContent(Map<String, Object> response) {
        if (response == null) {
            return "";
        }
        List<Map<String, Object>> choices = (List<Map<String, Object>>) response.get("choices");
        if (choices == null || choices.isEmpty()) {
            return "";
        }
        Map<String, Object> message = (Map<String, Object>) choices.get(0).get("message");
        if (message == null) {
            return "";
        }
        String content = (String) message.get("content");
        return content != null ? content : "";
    }

    @SuppressWarnings("unchecked")
    private void extractUsage(Map<String, Object> response, Object target) {
        if (response == null) {
            return;
        }
        try {
            Map<String, Object> usage = (Map<String, Object>) response.get("usage");
            if (usage == null) {
                return;
            }
            int promptTokens = toInt(usage.get("prompt_tokens"));
            int completionTokens = toInt(usage.get("completion_tokens"));
            if (target instanceof GatewayToolCallResult r) {
                r.setPromptTokens(promptTokens);
                r.setCompletionTokens(completionTokens);
            } else if (target instanceof GatewayAnalysisResult r) {
                r.setPromptTokens(promptTokens);
                r.setCompletionTokens(completionTokens);
            }
        } catch (Exception ex) {
            log.debug("Failed to extract token usage: {}", ex.getMessage());
        }
    }

    private int toInt(Object val) {
        if (val instanceof Number n) {
            return n.intValue();
        }
        return 0;
    }

    // ---------- error normalization ----------

    private String normalizeError(Exception ex) {
        String msg = ex.getMessage();
        if (msg == null) {
            return "UNKNOWN_ERROR";
        }
        if (msg.contains("timeout") || msg.contains("Timeout")) {
            return "LLM_TIMEOUT";
        }
        if (msg.contains("401") || msg.contains("403")) {
            return "LLM_AUTH_ERROR";
        }
        if (msg.contains("429")) {
            return "LLM_RATE_LIMITED";
        }
        if (msg.contains("5") && (msg.contains("500") || msg.contains("502") || msg.contains("503"))) {
            return "LLM_UPSTREAM_ERROR";
        }
        return "LLM_ERROR: " + msg;
    }
}
