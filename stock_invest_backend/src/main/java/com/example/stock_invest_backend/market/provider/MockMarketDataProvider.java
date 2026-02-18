package com.example.stock_invest_backend.market.provider;

import com.example.stock_invest_backend.market.dto.MarketQuote;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

//这里是本地假数据，用于软件调试
@Component
public class MockMarketDataProvider implements MarketDataProvider {

    @Override
    public Mono<List<MarketQuote>> fetchRealtimeQuotes(List<String> symbols) {
        List<MarketQuote> quotes = symbols.stream()
                .filter(StringUtils::hasText)
                .map(String::trim)
                .map(this::buildQuote)
                .toList();

        return Mono.just(quotes);
    }

    @Override
    public String providerName() {
        return "mock";
    }

    private MarketQuote buildQuote(String symbol) {
        int seed = Math.abs(symbol.hashCode() % 5000);
        BigDecimal base = BigDecimal.valueOf(10 + (seed / 100.0));
        BigDecimal fluctuation = BigDecimal.valueOf(ThreadLocalRandom.current().nextDouble(-0.8, 0.8));

        BigDecimal lastPrice = base.add(fluctuation).setScale(2, RoundingMode.HALF_UP);
        BigDecimal prevClosePrice = base.setScale(2, RoundingMode.HALF_UP);
        BigDecimal openPrice = prevClosePrice.add(BigDecimal.valueOf(0.05)).setScale(2, RoundingMode.HALF_UP);
        BigDecimal highPrice = lastPrice.max(openPrice).add(BigDecimal.valueOf(0.2)).setScale(2, RoundingMode.HALF_UP);
        BigDecimal lowPrice = lastPrice.min(openPrice).subtract(BigDecimal.valueOf(0.2)).max(BigDecimal.ZERO)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal changePercent = lastPrice.subtract(prevClosePrice)
                .divide(prevClosePrice, 4, RoundingMode.HALF_UP)
                .multiply(BigDecimal.valueOf(100))
                .setScale(2, RoundingMode.HALF_UP);

        MarketQuote quote = new MarketQuote();
        quote.setSymbol(symbol.toLowerCase());
        quote.setSource(providerName());
        quote.setLastPrice(lastPrice);
        quote.setPrevClosePrice(prevClosePrice);
        quote.setOpenPrice(openPrice);
        quote.setHighPrice(highPrice);
        quote.setLowPrice(lowPrice);
        quote.setChangePercent(changePercent);
        quote.setVolume((long) ThreadLocalRandom.current().nextInt(50_000, 2_000_000));
        quote.setTurnover(lastPrice.multiply(BigDecimal.valueOf(quote.getVolume())).setScale(2, RoundingMode.HALF_UP));
        quote.setQuoteTimestamp(Instant.now().getEpochSecond());
        return quote;
    }
}
