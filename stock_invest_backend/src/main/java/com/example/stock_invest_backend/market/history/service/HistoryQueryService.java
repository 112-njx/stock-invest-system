package com.example.stock_invest_backend.market.history.service;

import com.example.stock_invest_backend.market.history.dto.KLineDataPoint;
import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;
import com.example.stock_invest_backend.market.history.repository.StockDailyKlineRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

@Service
public class HistoryQueryService {

    private static final Logger log = LoggerFactory.getLogger(HistoryQueryService.class);
    private static final int MAX_DAYS = 365;
    private static final int DEFAULT_DAYS = 90;

    private final StockDailyKlineRepository repository;

    public HistoryQueryService(StockDailyKlineRepository repository) {
        this.repository = repository;
    }

    public List<KLineDataPoint> queryKLine(String symbol, LocalDate startDate, LocalDate endDate, Integer days) {
        if (symbol == null || symbol.isBlank()) {
            throw new IllegalArgumentException("symbol is required");
        }

        List<StockDailyKlineRecord> records;

        if (startDate != null && endDate != null) {
            if (endDate.isBefore(startDate)) {
                throw new IllegalArgumentException("endDate must be after startDate");
            }
            if (startDate.until(endDate).getYears() > 10) {
                throw new IllegalArgumentException("date range must not exceed 10 years");
            }
            log.info("Query K-line by date range: symbol={}, start={}, end={}", symbol, startDate, endDate);
            records = repository.findBySymbolAndDateRange(symbol, startDate, endDate);
        } else {
            int actualDays = (days != null && days > 0) ? Math.min(days, MAX_DAYS) : DEFAULT_DAYS;
            log.info("Query K-line by days: symbol={}, days={}", symbol, actualDays);
            records = repository.findBySymbolAndDays(symbol, actualDays);
        }

        List<StockDailyKlineRecord> sorted = new ArrayList<>(records);
        sorted.sort(Comparator.comparing(StockDailyKlineRecord::getTradeDate));

        return sorted.stream().map(KLineDataPoint::from).toList();
    }
}
