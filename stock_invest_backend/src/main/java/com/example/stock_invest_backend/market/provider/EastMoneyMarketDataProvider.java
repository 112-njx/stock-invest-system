package com.example.stock_invest_backend.market.provider;

import com.example.stock_invest_backend.market.config.EastMoneyProperties;
import com.example.stock_invest_backend.market.dto.MarketQuote;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

@Component
public class EastMoneyMarketDataProvider implements MarketDataProvider {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_RESPONSE_TYPE =
            new ParameterizedTypeReference<>() {
            };

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
                .bodyToMono(MAP_RESPONSE_TYPE)
                .timeout(Duration.ofMillis(properties.getTimeoutMillis()))
                .map(this::mapToQuotes)
                .onErrorReturn(List.of());
    }

    @Override
    public String providerName() {
        return "eastmoney";
    }

    private List<MarketQuote> mapToQuotes(Map<String, Object> root) {
        if (root == null) {
            return List.of();
        }

        Object dataObject = root.get("data");
        if (!(dataObject instanceof Map<?, ?> dataMap)) {
            return List.of();
        }

        Object diffObject = dataMap.get("diff");
        if (!(diffObject instanceof List<?> diffList)) {
            return List.of();
        }

        List<MarketQuote> result = new ArrayList<>();
        for (Object item : diffList) {
            if (!(item instanceof Map<?, ?> rawRow)) {
                continue;
            }

            Map<String, Object> row = castRow(rawRow);
            MarketQuote quote = new MarketQuote();
            quote.setSource(providerName());
            quote.setSymbol(buildSymbol(asString(row.get("f13")), asString(row.get("f12"))));
            quote.setLastPrice(toBigDecimal(row.get("f2")));
            quote.setChangePercent(toBigDecimal(row.get("f3")));
            quote.setVolume(toLong(row.get("f5")));
            quote.setTurnover(toBigDecimal(row.get("f6")));
            quote.setHighPrice(toBigDecimal(row.get("f15")));
            quote.setLowPrice(toBigDecimal(row.get("f16")));
            quote.setOpenPrice(toBigDecimal(row.get("f17")));
            quote.setPrevClosePrice(toBigDecimal(row.get("f18")));
            quote.setQuoteTimestamp(toLong(row.get("f124")));
            result.add(quote);
        }

        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castRow(Map<?, ?> rawRow) {
        try {
            return (Map<String, Object>) rawRow;
        } catch (ClassCastException ex) {
            return Collections.emptyMap();
        }
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

    private String asString(Object value) {
        if (value == null) {
            return null;
        }
        return String.valueOf(value);
    }

    private BigDecimal toBigDecimal(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        if (!StringUtils.hasText(text) || "-".equals(text)) {
            return null;
        }
        return new BigDecimal(text);
    }

    private Long toLong(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        if (!StringUtils.hasText(text) || "-".equals(text)) {
            return null;
        }
        return Long.valueOf(text);
    }
}
