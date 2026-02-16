package com.example.stock_invest_backend.market.provider;

import com.example.stock_invest_backend.market.config.EastMoneyProperties;
import com.example.stock_invest_backend.market.dto.MarketQuote;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

@Component
public class EastMoneyMarketDataProvider implements MarketDataProvider {

    private final WebClient webClient;
    private final EastMoneyProperties properties;

    public EastMoneyMarketDataProvider(@Qualifier("eastMoneyWebClient") WebClient webClient,
                                       EastMoneyProperties properties) {
        this.webClient = webClient;
        this.properties = properties;
    }

    @Override
    public Mono<List<MarketQuote>> fetchRealtimeQuotes(List<String> symbols) {
        List<String> secIds = symbols.stream()
                .map(this::toSecId)
                .filter(StringUtils::hasText)
                .toList();

        if (secIds.isEmpty()) {
            return Mono.just(List.of());
        }

        return webClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path(properties.getQuotePath())
                        .queryParam("fltt", "2")
                        .queryParam("invt", "2")
                        .queryParam("fields", properties.getFields())
                        .queryParam("secids", String.join(",", secIds))
                        .build())
                .retrieve()
                .bodyToMono(JsonNode.class)
                .timeout(Duration.ofMillis(properties.getTimeoutMillis()))
                .map(this::mapToQuotes)
                .onErrorReturn(List.of());
    }

    @Override
    public String providerName() {
        return "eastmoney";
    }

    private List<MarketQuote> mapToQuotes(JsonNode rootNode) {
        JsonNode diff = rootNode.path("data").path("diff");
        if (!diff.isArray()) {
            return List.of();
        }

        List<MarketQuote> result = new ArrayList<>();
        for (JsonNode row : diff) {
            MarketQuote quote = new MarketQuote();
            quote.setSource(providerName());
            quote.setSymbol(buildSymbol(row.path("f13").asText(), row.path("f12").asText()));
            quote.setLastPrice(toBigDecimal(row.path("f2")));
            quote.setChangePercent(toBigDecimal(row.path("f3")));
            quote.setVolume(toLong(row.path("f5")));
            quote.setTurnover(toBigDecimal(row.path("f6")));
            quote.setHighPrice(toBigDecimal(row.path("f15")));
            quote.setLowPrice(toBigDecimal(row.path("f16")));
            quote.setOpenPrice(toBigDecimal(row.path("f17")));
            quote.setPrevClosePrice(toBigDecimal(row.path("f18")));
            quote.setQuoteTimestamp(toLong(row.path("f124")));
            result.add(quote);
        }

        return result;
    }

    private String toSecId(String symbol) {
        if (!StringUtils.hasText(symbol)) {
            return null;
        }

        String normalized = symbol.trim().toLowerCase();
        if (normalized.startsWith("sh")) {
            return "1." + normalized.substring(2);
        }

        if (normalized.startsWith("sz")) {
            return "0." + normalized.substring(2);
        }

        if (normalized.startsWith("1.") || normalized.startsWith("0.")) {
            return normalized;
        }

        if (normalized.length() == 6) {
            if (normalized.startsWith("6") || normalized.startsWith("9")) {
                return "1." + normalized;
            }
            return "0." + normalized;
        }

        return null;
    }

    private String buildSymbol(String market, String code) {
        if (!StringUtils.hasText(code)) {
            return code;
        }
        if ("1".equals(market)) {
            return "sh" + code;
        }
        if ("0".equals(market)) {
            return "sz" + code;
        }
        return code;
    }

    private BigDecimal toBigDecimal(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        String value = node.asText();
        if (!StringUtils.hasText(value) || "-".equals(value)) {
            return null;
        }
        return new BigDecimal(value);
    }

    private Long toLong(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        String value = node.asText();
        if (!StringUtils.hasText(value) || "-".equals(value)) {
            return null;
        }
        return Long.valueOf(value);
    }
}
