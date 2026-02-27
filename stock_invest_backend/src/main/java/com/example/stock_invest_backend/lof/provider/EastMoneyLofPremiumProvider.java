package com.example.stock_invest_backend.lof.provider;

import com.example.stock_invest_backend.lof.config.LofPremiumProperties;
import com.example.stock_invest_backend.lof.dto.LofNavType;
import com.example.stock_invest_backend.lof.dto.LofPremiumItem;
import com.example.stock_invest_backend.lof.dto.LofPremiumStatus;
import com.example.stock_invest_backend.market.config.EastMoneyProperties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;

//东方财富lof基金实时溢价获取
@Component
public class EastMoneyLofPremiumProvider implements LofPremiumDataProvider {

    private static final Logger log = LoggerFactory.getLogger(EastMoneyLofPremiumProvider.class);

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_RESPONSE_TYPE =
            new ParameterizedTypeReference<>() {
            };

    private final WebClient webClient;
    private final EastMoneyProperties eastMoneyProperties;
    private final LofPremiumProperties lofPremiumProperties;
    private final AtomicLong nextAllowedNanos = new AtomicLong(0);

    public EastMoneyLofPremiumProvider(@Qualifier("eastMoneyWebClient") WebClient webClient,
                                       EastMoneyProperties eastMoneyProperties,
                                       LofPremiumProperties lofPremiumProperties) {
        this.webClient = webClient;
        this.eastMoneyProperties = eastMoneyProperties;
        this.lofPremiumProperties = lofPremiumProperties;
    }

    @Override
    public Mono<List<LofPremiumItem>> fetchPremiumItems(List<String> symbols) {
        List<String> normalizedSymbols = symbols.stream()
                .map(String::trim)
                .map(String::toLowerCase)
                .filter(StringUtils::hasText)
                .toList();
        List<String> secIds = normalizedSymbols.stream()
                .map(this::toSecId)
                .filter(StringUtils::hasText)
                .toList();

        if (secIds.isEmpty()) {
            return Mono.just(List.of());
        }

        return applyRateLimit()
                .then(requestEastMoney(secIds))
                .retryWhen(buildRetrySpec())
                .map(this::mapToPremiumItems)
                .onErrorResume(ex -> Mono.just(buildErrorItems(normalizedSymbols, ex.getMessage())));
    }

    @Override
    public String providerName() {
        return "eastmoney";
    }

    private Mono<Map<String, Object>> requestEastMoney(List<String> secIds) {
        return webClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path(eastMoneyProperties.getQuotePath())
                        .queryParam("fltt", "2")
                        .queryParam("invt", "2")
                        .queryParam("fields", lofPremiumProperties.getFields())
                        .queryParam("secids", String.join(",", secIds))
                        .build())
                .retrieve()
                .bodyToMono(MAP_RESPONSE_TYPE)
                .timeout(Duration.ofMillis(eastMoneyProperties.getTimeoutMillis()));
    }

    private Retry buildRetrySpec() {
        int maxAttempts = Math.max(1, lofPremiumProperties.getRetryMaxAttempts());
        Duration baseDelay = Duration.ofMillis(Math.max(50, lofPremiumProperties.getRetryBaseDelayMs()));
        long retries = Math.max(0, maxAttempts - 1L);
        return Retry.backoff(retries, baseDelay)
                .doBeforeRetry(signal -> log.warn("LOF upstream retrying: attempt={}, reason={}",
                        signal.totalRetries() + 1, signal.failure().getMessage()))
                .filter(this::isRetriableException);
    }

    private boolean isRetriableException(Throwable ex) {
        if (ex instanceof TimeoutException) {
            return true;
        }
        String message = ex.getMessage();
        if (!StringUtils.hasText(message)) {
            return false;
        }
        String lower = message.toLowerCase();
        return lower.contains("timeout")
                || lower.contains("connection")
                || lower.contains("503")
                || lower.contains("502")
                || lower.contains("500");
    }

    private Mono<Void> applyRateLimit() {
        int permitsPerSecond = Math.max(1, lofPremiumProperties.getRateLimitPermitsPerSecond());
        long intervalNanos = 1_000_000_000L / permitsPerSecond;
        long delayNanos = reserveDelayNanos(intervalNanos);
        if (delayNanos <= 0) {
            return Mono.empty();
        }
        return Mono.delay(Duration.ofNanos(delayNanos)).then();
    }

    private long reserveDelayNanos(long intervalNanos) {
        while (true) {
            long now = System.nanoTime();
            long currentNext = nextAllowedNanos.get();
            long scheduled = Math.max(now, currentNext);
            long updated = scheduled + intervalNanos;
            if (nextAllowedNanos.compareAndSet(currentNext, updated)) {
                return Math.max(0, scheduled - now);
            }
        }
    }

    private List<LofPremiumItem> mapToPremiumItems(Map<String, Object> root) {
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

        List<LofPremiumItem> result = new ArrayList<>();
        for (Object item : diffList) {
            if (!(item instanceof Map<?, ?> rawRow)) {
                continue;
            }
            Map<String, Object> row = castRow(rawRow);
            result.add(mapRow(row));
        }
        return result;
    }

    private LofPremiumItem mapRow(Map<String, Object> row) {
        LofPremiumItem item = new LofPremiumItem();
        item.setSymbol(buildSymbol(asString(row.get("f13")), asString(row.get("f12"))));
        item.setName(asString(row.get("f14")));
        item.setLastPrice(toBigDecimal(row.get("f2")));
        item.setQuoteTime(toLong(row.get("f124")));
        item.setCacheHit(false);

        BigDecimal iopv = firstPositiveValue(row, lofPremiumProperties.getIopvFieldCodes());
        BigDecimal prevDayNav = firstPositiveValue(row, lofPremiumProperties.getPrevNavFieldCodes());
        if (iopv != null) {
            item.setNav(iopv);
            item.setNavType(LofNavType.IOPV_REALTIME);
            item.setNavDate("realtime");
        } else if (prevDayNav != null) {
            item.setNav(prevDayNav);
            item.setNavType(LofNavType.PREV_DAY_NAV);
            item.setNavDate("previous-trading-day");
            item.setMessage("realtime iopv unavailable, fallback to previous day nav");
        }

        if (item.getNav() == null || item.getNav().compareTo(BigDecimal.ZERO) <= 0) {
            item.setStatus(LofPremiumStatus.NO_NAV);
            item.setPremiumRate(null);
            return item;
        }
        if (item.getLastPrice() == null || item.getLastPrice().compareTo(BigDecimal.ZERO) <= 0) {
            item.setStatus(LofPremiumStatus.NO_PRICE);
            item.setPremiumRate(null);
            return item;
        }

        BigDecimal premiumRate = item.getLastPrice()
                .subtract(item.getNav())
                .divide(item.getNav(), 8, RoundingMode.HALF_UP);
        item.setPremiumRate(premiumRate);
        item.setStatus(LofPremiumStatus.OK);
        return item;
    }

    private List<LofPremiumItem> buildErrorItems(List<String> symbols, String reason) {
        List<LofPremiumItem> items = new ArrayList<>();
        for (String symbol : symbols) {
            LofPremiumItem item = new LofPremiumItem();
            item.setSymbol(symbol);
            item.setStatus(LofPremiumStatus.UPSTREAM_ERROR);
            item.setMessage(reason);
            item.setCacheHit(false);
            items.add(item);
        }
        return items;
    }

    private BigDecimal firstPositiveValue(Map<String, Object> row, List<String> fieldCodes) {
        for (String fieldCode : fieldCodes) {
            BigDecimal value = toBigDecimal(row.get(fieldCode));
            if (value != null && value.compareTo(BigDecimal.ZERO) > 0) {
                return value;
            }
        }
        return null;
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
        return value == null ? null : String.valueOf(value);
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

    private BigDecimal toBigDecimal(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        if (!StringUtils.hasText(text) || "-".equals(text)) {
            return null;
        }
        try {
            return new BigDecimal(text);
        } catch (NumberFormatException ex) {
            return null;
        }
    }
}
