package com.example.stock_invest_backend.market.history.provider;

import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;
import com.example.stock_invest_backend.market.history.repository.StockDailyKlineRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Component
public class EastMoneyHistoryDataProvider {

    private static final Logger log = LoggerFactory.getLogger(EastMoneyHistoryDataProvider.class);
    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final DateTimeFormatter PARAM_DATE_FMT = DateTimeFormatter.ofPattern("yyyyMMdd");
    private static final String KLINE_PATH = "/api/qt/stock/kline/get";

    private final WebClient webClient;
    private final StockDailyKlineRepository repository;

    public EastMoneyHistoryDataProvider(
            @Qualifier("eastMoneyHistoryWebClient") WebClient webClient,
            StockDailyKlineRepository repository) {
        this.webClient = webClient;
        this.repository = repository;
    }

    public int ingest(List<String> symbols, int months) {
        LocalDate end = LocalDate.now();
        LocalDate start = end.minusMonths(Math.max(months, 1));

        List<StockDailyKlineRecord> allRecords = new ArrayList<>();
        for (String symbol : symbols) {
            log.info("Fetching K-line from EastMoney: symbol={}, months={}", symbol, months);
            List<StockDailyKlineRecord> records = fetchDailyKlines(symbol, start, end);
            allRecords.addAll(records);
            log.info("Fetched {} K-line records for {}", records.size(), symbol);
        }

        return repository.upsertBatch(allRecords);
    }

    private List<StockDailyKlineRecord> fetchDailyKlines(String symbol, LocalDate start, LocalDate end) {
        String secId = toSecId(symbol);

        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = webClient.get()
                    .uri(uriBuilder -> uriBuilder
                            .path(KLINE_PATH)
                            .queryParam("secid", secId)
                            .queryParam("fields1", "f1,f2,f3,f4,f5,f6")
                            .queryParam("fields2", "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61")
                            .queryParam("klt", "101")
                            .queryParam("fqt", "1")
                            .queryParam("beg", start.format(PARAM_DATE_FMT))
                            .queryParam("end", end.format(PARAM_DATE_FMT))
                            .queryParam("lmt", "1000")
                            .build())
                    .retrieve()
                    .bodyToMono(Map.class)
                    .block();

            if (response == null || response.get("data") == null) {
                log.warn("EastMoney K-line returned empty data for {}", symbol);
                return List.of();
            }

            @SuppressWarnings("unchecked")
            Map<String, Object> dataMap = (Map<String, Object>) response.get("data");
            Object klinesObj = dataMap.get("klines");
            if (!(klinesObj instanceof List<?> klines)) {
                log.warn("EastMoney K-line returned no klines for {}", symbol);
                return List.of();
            }

            List<StockDailyKlineRecord> records = new ArrayList<>();
            for (Object item : klines) {
                if (!(item instanceof String line) || line.isBlank()) {
                    continue;
                }
                // 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
                String[] parts = line.split(",");
                if (parts.length < 6) continue;

                StockDailyKlineRecord r = new StockDailyKlineRecord();
                r.setSymbol(symbol.toLowerCase());
                r.setTradeDate(LocalDate.parse(parts[0], DATE_FMT));
                r.setOpenPrice(new BigDecimal(parts[1]));
                r.setClosePrice(new BigDecimal(parts[2]));
                r.setHighPrice(new BigDecimal(parts[3]));
                r.setLowPrice(new BigDecimal(parts[4]));
                r.setVolume(new BigDecimal(parts[5]).longValue());
                r.setTurnover(parts.length >= 7 ? new BigDecimal(parts[6]) : BigDecimal.ZERO);
                r.setSource("eastmoney");
                records.add(r);
            }
            return records;
        } catch (Exception ex) {
            log.error("Failed to fetch K-line for {}: {}", symbol, ex.getMessage());
            throw new RuntimeException("EastMoney K-line fetch failed for " + symbol, ex);
        }
    }

    private String toSecId(String symbol) {
        String s = symbol.trim().toLowerCase();
        if (s.startsWith("sh")) return "1." + s.substring(2);
        if (s.startsWith("sz")) return "0." + s.substring(2);
        return "0." + s;
    }
}
