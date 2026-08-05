package com.example.stock_invest_backend.market.history.repository;

import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;

import java.time.LocalDate;
import java.util.List;

public interface StockDailyKlineRepository {

    int upsertBatch(List<StockDailyKlineRecord> records);

    List<StockDailyKlineRecord> findBySymbolAndDays(String symbol, int days);

    List<StockDailyKlineRecord> findBySymbolAndDateRange(String symbol, LocalDate startDate, LocalDate endDate);
}
